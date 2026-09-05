<script setup lang="ts">
import {
  computed,
  onMounted,
  reactive,
  ref,
  watch,
} from 'vue'

import {
  useAuthStore,
  type AccentPreference,
  type DensityPreference,
  type NotificationCategory,
  type NotificationEngine,
  type NotificationScope,
  type NotificationSeverity,
  type ThemePreference,
} from '@/stores/auth'
import { useConnectionsStore } from '@/stores/connections'
import { useServersStore } from '@/stores/servers'
import { useUiStore } from '@/stores/ui'


const authStore = useAuthStore()
const connectionsStore = useConnectionsStore()
const serversStore = useServersStore()
const uiStore = useUiStore()

const identityMessage = ref<string | null>(null)
const identityError = ref<string | null>(null)
const preferencesMessage = ref<string | null>(null)
const preferencesError = ref<string | null>(null)
const notificationsMessage = ref<string | null>(null)
const notificationsError = ref<string | null>(null)

const identity = reactive({
  display_name: '',
  email: '',
})

const preferences = reactive({
  timezone: 'system',
  theme: 'system' as ThemePreference,
  accent: 'purple' as AccentPreference,
  density: 'comfortable' as DensityPreference,
})

const notifications = reactive({
  email_enabled: false,
  severities: [] as NotificationSeverity[],
  categories: [] as NotificationCategory[],
  engines: [] as NotificationEngine[],
  include_servers: true,
  include_system: true,
  scope: 'all' as NotificationScope,
  database_connection_ids: [] as string[],
  server_ids: [] as string[],
})

const browserTimezone =
  Intl.DateTimeFormat().resolvedOptions().timeZone
  || 'system'

const accentOptions: AccentPreference[] = [
  'purple',
  'blue',
  'cyan',
  'green',
  'orange',
  'pink',
]

const severityOptions: Array<{
  value: NotificationSeverity
  label: string
  description: string
}> = [
  {
    value: 'critical',
    label: 'Critical',
    description: 'Outages and conditions requiring immediate attention.',
  },
  {
    value: 'warning',
    label: 'Warning',
    description: 'Degradation, pressure or conditions that should be reviewed.',
  },
]

const categoryOptions: Array<{
  value: NotificationCategory
  label: string
}> = [
  { value: 'availability', label: 'Availability' },
  { value: 'blocking', label: 'Blocking' },
  { value: 'storage', label: 'Storage / capacity' },
  { value: 'performance', label: 'Performance' },
  { value: 'jobs', label: 'Jobs / automation' },
  { value: 'backup', label: 'Backup' },
  { value: 'system', label: 'DBAChum system' },
]

const engineOptions: Array<{
  value: NotificationEngine
  label: string
}> = [
  { value: 'oracle', label: 'Oracle' },
  { value: 'sqlserver', label: 'SQL Server' },
  { value: 'mysql', label: 'MySQL / MariaDB' },
]

const roleLabel = computed(() => {
  const role = authStore.user?.role ?? 'viewer'
  return role.charAt(0).toUpperCase() + role.slice(1)
})

const monitoredConnections = computed(() =>
  connectionsStore.connections.filter(
    (connection) => connection.active && connection.monitor_enabled,
  ),
)

const monitoredServers = computed(() =>
  serversStore.servers.filter((server) => server.enabled),
)

const selectedSourceCount = computed(() =>
  notifications.database_connection_ids.length
  + notifications.server_ids.length,
)

const notificationSourceError = computed(() =>
  connectionsStore.error || serversStore.error,
)

function syncFromUser() {
  const user = authStore.user
  if (!user) return

  identity.display_name = user.display_name
  identity.email = user.email ?? ''

  preferences.timezone = user.preferences.timezone
  preferences.theme = user.preferences.theme
  preferences.accent = user.preferences.accent
  preferences.density = user.preferences.density

  notifications.email_enabled = user.notifications.email_enabled
  notifications.severities = [...user.notifications.severities]
  notifications.categories = [...user.notifications.categories]
  notifications.engines = [...user.notifications.engines]
  notifications.include_servers = user.notifications.include_servers
  notifications.include_system = user.notifications.include_system
  notifications.scope = user.notifications.scope
  notifications.database_connection_ids = [
    ...user.notifications.database_connection_ids,
  ]
  notifications.server_ids = [...user.notifications.server_ids]
}

watch(
  () => authStore.user,
  syncFromUser,
  {
    immediate: true,
    deep: true,
  },
)

onMounted(async () => {
  await Promise.all([
    connectionsStore.load(),
    serversStore.load(),
  ])
})

async function saveIdentity() {
  identityMessage.value = null
  identityError.value = null

  try {
    await authStore.updateProfile({
      display_name: identity.display_name.trim(),
      email: identity.email.trim() || null,
    })

    identityMessage.value = 'Profile updated.'
  } catch (cause) {
    identityError.value = cause instanceof Error
      ? cause.message
      : 'Unable to update profile.'
  }
}

async function savePreferences() {
  preferencesMessage.value = null
  preferencesError.value = null

  try {
    const user = await authStore.updatePreferences({
      timezone: preferences.timezone.trim() || 'system',
      theme: preferences.theme,
      accent: preferences.accent,
      density: preferences.density,
    })

    uiStore.applyUserPreferences(user.preferences)
    preferencesMessage.value = 'Preferences saved.'
  } catch (cause) {
    preferencesError.value = cause instanceof Error
      ? cause.message
      : 'Unable to save preferences.'
  }
}

async function saveNotifications() {
  notificationsMessage.value = null
  notificationsError.value = null

  try {
    await authStore.updateNotifications({
      email_enabled: notifications.email_enabled,
      severities: [...notifications.severities],
      categories: [...notifications.categories],
      engines: [...notifications.engines],
      include_servers: notifications.include_servers,
      include_system: notifications.include_system,
      scope: notifications.scope,
      database_connection_ids: [
        ...notifications.database_connection_ids,
      ],
      server_ids: [...notifications.server_ids],
    })

    notificationsMessage.value = 'Alert subscription saved.'
  } catch (cause) {
    notificationsError.value = cause instanceof Error
      ? cause.message
      : 'Unable to save alert subscription.'
  }
}

function useBrowserTimezone() {
  preferences.timezone = browserTimezone
}

function engineLabel(engine: NotificationEngine) {
  return engineOptions.find((item) => item.value === engine)?.label ?? engine
}
</script>

<template>
  <section class="page-header">
    <div>
      <h2>My profile</h2>
      <p>
        Your DBAChum identity, personal workspace defaults and alert subscriptions.
      </p>
    </div>
  </section>

  <div class="profile-layout">
    <section class="panel profile-card">
      <div class="profile-identity-heading">
        <div class="profile-avatar-large">
          {{ authStore.user?.avatar_initials || 'DB' }}
        </div>

        <div>
          <h3>{{ authStore.user?.display_name }}</h3>
          <p>@{{ authStore.user?.username }}</p>
        </div>
      </div>

      <form class="connection-form" @submit.prevent="saveIdentity">
        <label>
          Display name
          <input
            v-model="identity.display_name"
            required
            maxlength="120"
            autocomplete="name"
          />
        </label>

        <label>
          Username
          <input
            :value="authStore.user?.username"
            disabled
            autocomplete="username"
          />
          <small>
            Username remains the sign-in identity and is managed separately.
          </small>
        </label>

        <label>
          Email
          <input
            v-model="identity.email"
            type="email"
            maxlength="254"
            autocomplete="email"
            placeholder="dba@company.com"
          />
          <small>
            This address is used when you opt into email alert delivery.
          </small>
        </label>

        <label>
          Role
          <input :value="roleLabel" disabled />
        </label>

        <p v-if="identityError" class="login-error">
          {{ identityError }}
        </p>
        <p v-if="identityMessage" class="profile-success">
          {{ identityMessage }}
        </p>

        <div class="connection-form-actions">
          <button
            type="submit"
            class="primary-button"
            :disabled="authStore.profileSaving"
          >
            {{ authStore.profileSaving ? 'Saving...' : 'Save profile' }}
          </button>
        </div>
      </form>
    </section>

    <section class="panel profile-card">
      <div class="panel-header">
        <div>
          <h3>Personal preferences</h3>
          <p>
            These belong to your account, not the DBAChum installation.
          </p>
        </div>
      </div>

      <form class="connection-form" @submit.prevent="savePreferences">
        <label>
          Timezone
          <div class="profile-inline-control">
            <input
              v-model="preferences.timezone"
              maxlength="80"
              placeholder="system"
            />
            <button
              type="button"
              class="secondary-button"
              @click="useBrowserTimezone"
            >
              Use browser
            </button>
          </div>
          <small>
            Browser timezone: {{ browserTimezone }}
          </small>
        </label>

        <label>
          Theme
          <select v-model="preferences.theme">
            <option value="system">System</option>
            <option value="light">Light</option>
            <option value="dark">Dark</option>
          </select>
        </label>

        <fieldset class="profile-fieldset">
          <legend>Accent</legend>
          <div class="accent-options">
            <label
              v-for="accent in accentOptions"
              :key="accent"
              class="accent-option"
            >
              <input
                v-model="preferences.accent"
                type="radio"
                name="accent"
                :value="accent"
              />
              <span class="accent-dot" :data-accent-preview="accent" />
              <span>{{ accent }}</span>
            </label>
          </div>
        </fieldset>

        <label>
          Interface density
          <select v-model="preferences.density">
            <option value="comfortable">Comfortable</option>
            <option value="compact">Compact</option>
          </select>
          <small>
            Density is stored now so the Phase 8 UI polish can honor the same preference everywhere.
          </small>
        </label>

        <p v-if="preferencesError" class="login-error">
          {{ preferencesError }}
        </p>
        <p v-if="preferencesMessage" class="profile-success">
          {{ preferencesMessage }}
        </p>

        <div class="connection-form-actions">
          <button
            type="submit"
            class="primary-button"
            :disabled="authStore.preferencesSaving"
          >
            {{ authStore.preferencesSaving ? 'Saving...' : 'Save preferences' }}
          </button>
        </div>
      </form>
    </section>

    <section class="panel profile-card profile-card-wide">
      <div class="panel-header">
        <div>
          <h3>Alert subscriptions</h3>
          <p>
            Choose which centrally-defined DBAChum alerts you want delivered to you.
            The Alert Center itself remains complete for every user.
          </p>
        </div>
      </div>

      <form class="notification-form" @submit.prevent="saveNotifications">
        <div class="notification-delivery-card">
          <label class="notification-toggle-row">
            <span>
              <strong>Email alerts</strong>
              <small>
                Use the email address saved in your profile.
              </small>
            </span>
            <input
              v-model="notifications.email_enabled"
              type="checkbox"
            />
          </label>

          <p
            v-if="notifications.email_enabled && !authStore.user?.email"
            class="notification-warning"
          >
            Add an email address to your profile before email delivery can work.
          </p>

          <p class="notification-foundation-note">
            Phase 7B.3 saves and matches subscriptions now. Actual Brevo/SMTP delivery is added in 7B.4.
          </p>
        </div>

        <div class="notification-grid">
          <fieldset class="profile-fieldset notification-section">
            <legend>Severity</legend>
            <label
              v-for="option in severityOptions"
              :key="option.value"
              class="notification-check-row"
            >
              <input
                v-model="notifications.severities"
                type="checkbox"
                :value="option.value"
              />
              <span>
                <strong>{{ option.label }}</strong>
                <small>{{ option.description }}</small>
              </span>
            </label>
          </fieldset>

          <fieldset class="profile-fieldset notification-section">
            <legend>Database engines</legend>
            <label
              v-for="option in engineOptions"
              :key="option.value"
              class="notification-check-row"
            >
              <input
                v-model="notifications.engines"
                type="checkbox"
                :value="option.value"
              />
              <span>{{ option.label }}</span>
            </label>

            <label class="notification-check-row">
              <input
                v-model="notifications.include_servers"
                type="checkbox"
              />
              <span>Server / infrastructure alerts</span>
            </label>

            <label class="notification-check-row">
              <input
                v-model="notifications.include_system"
                type="checkbox"
              />
              <span>DBAChum collector / system alerts</span>
            </label>
          </fieldset>
        </div>

        <fieldset class="profile-fieldset notification-section">
          <legend>Alert categories</legend>
          <div class="notification-chip-grid">
            <label
              v-for="option in categoryOptions"
              :key="option.value"
              class="notification-chip"
            >
              <input
                v-model="notifications.categories"
                type="checkbox"
                :value="option.value"
              />
              <span>{{ option.label }}</span>
            </label>
          </div>
        </fieldset>

        <fieldset class="profile-fieldset notification-section">
          <legend>Source scope</legend>
          <div class="notification-scope-options">
            <label class="notification-check-row">
              <input
                v-model="notifications.scope"
                type="radio"
                value="all"
              />
              <span>
                <strong>All monitored sources</strong>
                <small>
                  New monitored databases and servers are automatically included if they match your filters above.
                </small>
              </span>
            </label>

            <label class="notification-check-row">
              <input
                v-model="notifications.scope"
                type="radio"
                value="selected"
              />
              <span>
                <strong>Selected databases and servers</strong>
                <small>
                  Useful when you only support a specific application or environment.
                </small>
              </span>
            </label>
          </div>
        </fieldset>

        <div
          v-if="notifications.scope === 'selected'"
          class="notification-source-picker"
        >
          <div class="notification-source-column">
            <div class="notification-source-heading">
              <strong>Databases</strong>
              <small>{{ notifications.database_connection_ids.length }} selected</small>
            </div>

            <p v-if="connectionsStore.loading" class="empty-state">
              Loading database connections...
            </p>

            <div v-else class="notification-source-list">
              <label
                v-for="connection in monitoredConnections"
                :key="connection.id"
                class="notification-source-row"
              >
                <input
                  v-model="notifications.database_connection_ids"
                  type="checkbox"
                  :value="connection.id"
                />
                <span>
                  <strong>{{ connection.name }}</strong>
                  <small>
                    {{ engineLabel(connection.engine) }} · {{ connection.host }}:{{ connection.port }}
                  </small>
                </span>
              </label>

              <p v-if="!monitoredConnections.length" class="empty-state">
                No monitored database connections are available.
              </p>
            </div>
          </div>

          <div class="notification-source-column">
            <div class="notification-source-heading">
              <strong>Servers</strong>
              <small>{{ notifications.server_ids.length }} selected</small>
            </div>

            <p v-if="serversStore.loading" class="empty-state">
              Loading servers...
            </p>

            <div v-else class="notification-source-list">
              <label
                v-for="server in monitoredServers"
                :key="server.id"
                class="notification-source-row"
              >
                <input
                  v-model="notifications.server_ids"
                  type="checkbox"
                  :value="server.id"
                />
                <span>
                  <strong>{{ server.name }}</strong>
                  <small>
                    {{ server.hostname }}{{ server.environment ? ` · ${server.environment}` : '' }}
                  </small>
                </span>
              </label>

              <p v-if="!monitoredServers.length" class="empty-state">
                No enabled servers are available.
              </p>
            </div>
          </div>
        </div>

        <p v-if="notificationSourceError" class="notification-warning">
          Some source choices could not be loaded: {{ notificationSourceError }}
        </p>

        <p
          v-if="notifications.scope === 'selected' && selectedSourceCount === 0 && !notifications.include_system"
          class="notification-warning"
        >
          Selected-source mode currently has no selected database/server and system alerts are disabled, so nothing will match.
        </p>

        <p v-if="notificationsError" class="login-error">
          {{ notificationsError }}
        </p>
        <p v-if="notificationsMessage" class="profile-success">
          {{ notificationsMessage }}
        </p>

        <div class="connection-form-actions">
          <button
            type="submit"
            class="primary-button"
            :disabled="authStore.notificationsSaving"
          >
            {{ authStore.notificationsSaving ? 'Saving...' : 'Save alert subscription' }}
          </button>
        </div>
      </form>
    </section>
  </div>
</template>
