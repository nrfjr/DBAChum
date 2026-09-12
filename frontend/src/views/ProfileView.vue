<script setup lang="ts">
import {
  computed,
  onBeforeUnmount,
  onMounted,
  reactive,
  ref,
  watch,
} from 'vue'

import {
  useAuthStore,
  type AccentPreference,
  type DateTimeFormatPreference,
  type DensityPreference,
  type HistoryRangePreference,
  type LandingPagePreference,
  type NotificationCategory,
  type NotificationEngine,
  type NotificationScope,
  type NotificationSeverity,
  type ThemePreference,
} from '@/stores/auth'
import { useConnectionsStore } from '@/stores/connections'
import { useServersStore } from '@/stores/servers'
import { useUiStore } from '@/stores/ui'
import { confirmDialog, showToast } from '@/ui/feedback'


const authStore = useAuthStore()
const connectionsStore = useConnectionsStore()
const serversStore = useServersStore()
const uiStore = useUiStore()

const identityError = ref<string | null>(null)
const preferencesError = ref<string | null>(null)
const notificationsError = ref<string | null>(null)
const preferenceDataError = ref<string | null>(null)
const preferenceImportInput = ref<HTMLInputElement | null>(null)
const avatarInput = ref<HTMLInputElement | null>(null)
const avatarSaving = ref(false)
const avatarError = ref<string | null>(null)
const pendingAvatarFile = ref<File | null>(null)
const pendingAvatarPreview = ref<string | null>(null)
const pendingAvatarRemoval = ref(false)

type ProfileSection =
  | 'profile'
  | 'customization'
  | 'alerts'

const activeSection = ref<ProfileSection>('profile')

const profileSectionMeta: Record<
  ProfileSection,
  { title: string; }
> = {
  profile: {
    title: 'Profile',
  },
  customization: {
    title: 'Customization',
  },
  alerts: {
    title: 'Alert subscriptions',
  },
}

const activeSectionMeta = computed(() =>
  profileSectionMeta[activeSection.value],
)

function selectProfileSection(section: ProfileSection) {
  activeSection.value = section

  identityError.value = null
  preferencesError.value = null
  notificationsError.value = null
  preferenceDataError.value = null
}

const identity = reactive({
  display_name: '',
  email: '',
})

const preferences = reactive({
  timezone: 'system',
  date_time_format: 'system' as DateTimeFormatPreference,
  default_landing_page: 'dashboard' as LandingPagePreference,
  default_history_range: '1h' as HistoryRangePreference,
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

const avatarUrl = computed(() => pendingAvatarPreview.value ?? (pendingAvatarRemoval.value ? null : authStore.avatarUrl))
const avatarChanged = computed(() => pendingAvatarFile.value !== null || pendingAvatarRemoval.value)

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
  preferences.date_time_format = user.preferences.date_time_format
  preferences.default_landing_page = user.preferences.default_landing_page
  preferences.default_history_range = user.preferences.default_history_range
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

onBeforeUnmount(clearAvatarPreview)

function clearAvatarPreview() {
  if (pendingAvatarPreview.value) URL.revokeObjectURL(pendingAvatarPreview.value)
  pendingAvatarPreview.value = null
}

function resetPendingAvatar() {
  clearAvatarPreview()
  pendingAvatarFile.value = null
  pendingAvatarRemoval.value = false
}

async function saveIdentity() {
  identityError.value = null
  avatarError.value = null

  try {
    await authStore.updateProfile({
      display_name: identity.display_name.trim(),
      email: identity.email.trim() || null,
    })

    if (pendingAvatarFile.value) {
      avatarSaving.value = true
      await authStore.uploadAvatar(pendingAvatarFile.value)
    } else if (pendingAvatarRemoval.value && authStore.user?.has_avatar) {
      avatarSaving.value = true
      await authStore.removeAvatar()
    }

    const photoChanged = avatarChanged.value
    resetPendingAvatar()
    showToast({
      title: photoChanged ? 'Profile and photo updated' : 'Profile updated',
      tone: 'success',
    })
  } catch (cause) {
    const message = cause instanceof Error ? cause.message : 'Unable to update profile.'
    if (avatarSaving.value) avatarError.value = message
    else identityError.value = message
    showToast({ title: 'Unable to update profile', message, tone: 'danger' })
  } finally {
    avatarSaving.value = false
  }
}

function chooseAvatar() {
  avatarInput.value?.click()
}

function uploadAvatar(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return

  avatarError.value = null
  clearAvatarPreview()
  pendingAvatarFile.value = file
  pendingAvatarRemoval.value = false
  pendingAvatarPreview.value = URL.createObjectURL(file)
}

async function removeAvatar() {
  const confirmed = await confirmDialog({
    title: 'Remove profile photo?',
    message: 'Your initials will be shown after you save your profile.',
    confirmLabel: 'Remove photo',
    tone: 'warning',
  })
  if (!confirmed) return

  avatarError.value = null
  clearAvatarPreview()
  pendingAvatarFile.value = null
  pendingAvatarRemoval.value = true
}

async function savePreferences() {
  preferencesError.value = null

  try {
    const user = await authStore.updatePreferences({
      timezone: preferences.timezone.trim() || 'system',
      date_time_format: preferences.date_time_format,
      default_landing_page: preferences.default_landing_page,
      default_history_range: preferences.default_history_range,
      theme: preferences.theme,
      accent: preferences.accent,
      density: preferences.density,
    })

    uiStore.applyUserPreferences(user.preferences)
    showToast({ title: 'Preferences saved', tone: 'success' })
  } catch (cause) {
    const message = cause instanceof Error ? cause.message : 'Unable to save preferences.'
    preferencesError.value = message
    showToast({ title: 'Unable to save preferences', message, tone: 'danger' })
  }
}

async function saveNotifications() {
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

    showToast({ title: 'Alert subscription saved', tone: 'success' })
  } catch (cause) {
    const message = cause instanceof Error ? cause.message : 'Unable to save alert subscription.'
    notificationsError.value = message
    showToast({ title: 'Unable to save alert subscription', message, tone: 'danger' })
  }
}

function downloadJson(filename: string, payload: unknown) {
  const blob = new Blob(
    [JSON.stringify(payload, null, 2)],
    { type: 'application/json' },
  )
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  URL.revokeObjectURL(url)
}

function exportPreferences() {
  const user = authStore.user
  if (!user) return

  preferenceDataError.value = null

  downloadJson(
    `dbachum-preferences-${user.username}.json`,
    {
      format: 'DBAChum user preferences',
      version: 1,
      exported_at: new Date().toISOString(),
      preferences: user.preferences,
      notifications: user.notifications,
    },
  )
  showToast({ title: 'Preferences exported', tone: 'success' })
}

function choosePreferenceImport() {
  preferenceImportInput.value?.click()
}

async function importPreferences(event: Event) {
  preferenceDataError.value = null

  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return

  try {
    const payload = JSON.parse(await file.text()) as Record<string, unknown>
    if (payload.format !== 'DBAChum user preferences' || payload.version !== 1) {
      throw new Error('This is not a supported DBAChum preferences export.')
    }

    if (!payload.preferences || typeof payload.preferences !== 'object') {
      throw new Error('The preferences section is missing.')
    }
    if (!payload.notifications || typeof payload.notifications !== 'object') {
      throw new Error('The notification preferences section is missing.')
    }

    const importedPreferences = payload.preferences as Record<string, unknown>
    const importedNotifications = payload.notifications as Record<string, unknown>

    const user = await authStore.updatePreferences({
      timezone: String(importedPreferences.timezone ?? 'system'),
      date_time_format: importedPreferences.date_time_format as DateTimeFormatPreference,
      default_landing_page: importedPreferences.default_landing_page as LandingPagePreference,
      default_history_range: importedPreferences.default_history_range as HistoryRangePreference,
      theme: importedPreferences.theme as ThemePreference,
      accent: importedPreferences.accent as AccentPreference,
      density: importedPreferences.density as DensityPreference,
    })

    await authStore.updateNotifications({
      email_enabled: Boolean(importedNotifications.email_enabled),
      severities: Array.isArray(importedNotifications.severities)
        ? importedNotifications.severities as NotificationSeverity[]
        : [],
      categories: Array.isArray(importedNotifications.categories)
        ? importedNotifications.categories as NotificationCategory[]
        : [],
      engines: Array.isArray(importedNotifications.engines)
        ? importedNotifications.engines as NotificationEngine[]
        : [],
      include_servers: importedNotifications.include_servers !== false,
      include_system: importedNotifications.include_system !== false,
      scope: importedNotifications.scope === 'selected' ? 'selected' : 'all',
      database_connection_ids: Array.isArray(importedNotifications.database_connection_ids)
        ? importedNotifications.database_connection_ids.map(String)
        : [],
      server_ids: Array.isArray(importedNotifications.server_ids)
        ? importedNotifications.server_ids.map(String)
        : [],
    })

    uiStore.applyUserPreferences(user.preferences)
    syncFromUser()
    showToast({ title: 'Preferences imported', tone: 'success' })
  } catch (cause) {
    const message = cause instanceof Error ? cause.message : 'Unable to import preferences.'
    preferenceDataError.value = message
    showToast({ title: 'Unable to import preferences', message, tone: 'danger' })
  }
}

async function resetPreferences() {
  const confirmed = await confirmDialog({
    title: 'Reset preferences',
    message: 'Reset personal preferences and alert subscriptions to DBAChum defaults? Your profile name and email are not changed.',
    confirmLabel: 'Reset preferences',
    tone: 'warning',
  })
  if (!confirmed) return

  preferenceDataError.value = null

  try {
    const user = await authStore.updatePreferences({
      timezone: 'system',
      date_time_format: 'system',
      default_landing_page: 'dashboard',
      default_history_range: '1h',
      theme: 'system',
      accent: 'purple',
      density: 'comfortable',
    })

    await authStore.updateNotifications({
      email_enabled: false,
      severities: ['critical', 'warning'],
      categories: [
        'availability',
        'blocking',
        'storage',
        'performance',
        'jobs',
        'backup',
        'system',
      ],
      engines: ['oracle', 'sqlserver', 'mysql'],
      include_servers: true,
      include_system: true,
      scope: 'all',
      database_connection_ids: [],
      server_ids: [],
    })

    uiStore.applyUserPreferences(user.preferences)
    syncFromUser()
    showToast({ title: 'Preferences reset to defaults', tone: 'success' })
  } catch (cause) {
    const message = cause instanceof Error ? cause.message : 'Unable to reset preferences.'
    preferenceDataError.value = message
    showToast({ title: 'Unable to reset preferences', message, tone: 'danger' })
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
    <div title="Manage your DBAChum identity, customization, alert subscriptions and preference data.">
      <h2>Profile & Preferences</h2>
    </div>
  </section>

  <div class="settings-layout profile-settings-layout">
    <aside class="settings-nav profile-settings-nav" aria-label="Profile sections">
      <button type="button" class="settings-nav-item profile-section-button"
        :class="{ active: activeSection === 'profile' }" @click="selectProfileSection('profile')">
        Profile
      </button>
      <button type="button" class="settings-nav-item profile-section-button"
        :class="{ active: activeSection === 'customization' }" @click="selectProfileSection('customization')">
        Customization
      </button>
      <button type="button" class="settings-nav-item profile-section-button"
        :class="{ active: activeSection === 'alerts' }" @click="selectProfileSection('alerts')">
        Alert subscriptions
      </button>
    </aside>

    <section class="settings-content profile-settings-content">
      <header class="settings-section-header">
        <h2>{{ activeSectionMeta.title }}</h2>
      </header>

      <div class="profile-section-stack">
        <section v-if="activeSection === 'profile'" class="panel profile-card profile-custom-panel">
          <div class="profile-identity-heading profile-identity-heading--editable">
            <div class="profile-avatar-editor">
              <div class="profile-avatar-large" :class="{ 'profile-avatar-large--image': avatarUrl }">
                <img v-if="avatarUrl" :src="avatarUrl" alt="Profile photo" />
                <span v-else>{{ authStore.user?.avatar_initials || 'DB' }}</span>
              </div>
              <button
                type="button"
                class="profile-avatar-change"
                :disabled="authStore.profileSaving || avatarSaving"
                :aria-label="avatarUrl ? 'Change profile photo' : 'Add profile photo'"
                @click="chooseAvatar"
              >
                {{ avatarUrl ? 'Change' : 'Add' }}
              </button>
            </div>

            <div>
              <h3>{{ authStore.user?.display_name }}</h3>
              <p>@{{ authStore.user?.username }}</p>
              <input
                ref="avatarInput"
                class="hidden-file-input"
                type="file"
                accept="image/png,image/jpeg,image/webp"
                @change="uploadAvatar"
              />
              <div v-if="avatarUrl" class="profile-avatar-actions">
                <button type="button" class="secondary-button" :disabled="authStore.profileSaving || avatarSaving" @click="removeAvatar">
                  Remove
                </button>
              </div>
              <p v-if="avatarError" class="login-error">{{ avatarError }}</p>
            </div>
          </div>

          <form class="connection-form" @submit.prevent="saveIdentity">
            <label>
              <span class="field-label">Display name <span class="required-mark" aria-hidden="true">*</span></span>
              <input v-model="identity.display_name" required maxlength="120" autocomplete="name" />
            </label>

            <label>
              Username
              <input :value="authStore.user?.username" disabled autocomplete="username"
                title="Username remains the sign-in identity and is managed separately." />
            </label>

            <label>
              Email
              <input v-model="identity.email" type="email" maxlength="255" autocomplete="email"
                placeholder="dba@company.com" title="This address is used when you opt into email alert delivery." />
            </label>

            <label>
              Role
              <input :value="roleLabel" disabled />
            </label>

            <p v-if="identityError" class="login-error">
              {{ identityError }}
            </p>

            <div class="connection-form-actions">
              <button type="submit" class="primary-button" :disabled="authStore.profileSaving || avatarSaving">
                {{ authStore.profileSaving || avatarSaving ? 'Saving...' : 'Save profile' }}
              </button>
            </div>
          </form>

          <div class="profile-preference-data">
            <div>
              <h3>Preference data</h3>
            </div>
            <input
              ref="preferenceImportInput"
              type="file"
              accept="application/json,.json"
              class="preference-file-input"
              @change="importPreferences"
            />
            <div class="preference-data-actions">
              <button
                type="button"
                class="secondary-button"
                title="Export includes personal appearance, timezone, landing/history defaults and alert subscriptions. It does not include username, email, passwords, connection credentials or installation settings."
                @click="exportPreferences"
              >
                Export preferences
              </button>
              <button type="button" class="secondary-button" @click="choosePreferenceImport">
                Import preferences
              </button>
              <button type="button" class="danger-button" @click="resetPreferences">
                Reset to defaults
              </button>
            </div>
            <p v-if="preferenceDataError" class="login-error">{{ preferenceDataError }}</p>
          </div>
        </section>

        <section v-if="activeSection === 'customization'" class="panel profile-card">

          <form class="connection-form" @submit.prevent="savePreferences">
            <label>
              Timezone
              <div class="profile-inline-control">
                <input v-model="preferences.timezone" maxlength="80" placeholder="system" />
                <button type="button" class="secondary-button" @click="useBrowserTimezone">
                  Use browser
                </button>
              </div>
              <small>
                Browser timezone: {{ browserTimezone }}
              </small>
            </label>

            <label>
              Date / time format
              <select v-model="preferences.date_time_format">
                <option value="system">System / browser</option>
                <option value="12h">12-hour</option>
                <option value="24h">24-hour</option>
              </select>
            </label>

            <label>
              Default landing page
              <select v-model="preferences.default_landing_page">
                <option value="dashboard">Dashboard</option>
                <option value="databases">Databases</option>
                <option value="servers">Servers</option>
                <option value="alerts">Alerts</option>
              </select>
            </label>

            <label>
              Default History range
              <select v-model="preferences.default_history_range">
                <option value="1h">Last 1 hour</option>
                <option value="6h">Last 6 hours</option>
                <option value="12h">Last 12 hours</option>
                <option value="24h">Last 24 hours</option>
              </select>
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
                <label v-for="accent in accentOptions" :key="accent" class="accent-option">
                  <input v-model="preferences.accent" type="radio" name="accent" :value="accent"
                    class="profile-radio-accent" />
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
            </label>

            <p v-if="preferencesError" class="login-error">
              {{ preferencesError }}
            </p>

            <div class="connection-form-actions">
              <button type="submit" class="primary-button" :disabled="authStore.preferencesSaving">
                {{ authStore.preferencesSaving ? 'Saving...' : 'Save preferences' }}
              </button>
            </div>
          </form>
        </section>

        <section v-if="activeSection === 'alerts'" class="panel profile-card">

          <form class="notification-form" @submit.prevent="saveNotifications">
            <div class="notification-delivery-card">
              <label class="notification-toggle-row">
                <span>
                  <strong>Email alerts</strong>
                </span>
                <input v-model="notifications.email_enabled" type="checkbox" class="toggle-switch"
                  title="Use the email address saved in your profile. " />
              </label>

              <p v-if="notifications.email_enabled && !authStore.user?.email" class="notification-warning">
                Add an email address to your profile before email delivery can work.
              </p>
            </div>

            <div class="notification-grid">
              <fieldset class="profile-fieldset notification-section">
                <legend>Severity</legend>
                <label v-for="option in severityOptions" :key="option.value" class="notification-check-row">
                  <input v-model="notifications.severities" type="checkbox" :value="option.value"
                    title="{{ option.description }}" />
                  <span>
                    <strong>{{ option.label }}</strong>
                  </span>
                </label>
              </fieldset>

              <fieldset class="profile-fieldset notification-section">
                <legend>Database engines</legend>
                <label v-for="option in engineOptions" :key="option.value" class="notification-check-row">
                  <input v-model="notifications.engines" type="checkbox" :value="option.value" />
                  <span>{{ option.label }}</span>
                </label>

                <label class="notification-check-row">
                  <input v-model="notifications.include_servers" type="checkbox" class="toggle-switch"/>
                  <span>Server / infrastructure alerts</span>
                </label>

                <label class="notification-check-row">
                  <input v-model="notifications.include_system" type="checkbox" class="toggle-switch"/>
                  <span>DBAChum collector / system alerts</span>
                </label>
              </fieldset>
            </div>

            <fieldset class="profile-fieldset notification-section">
              <legend>Alert categories</legend>
              <div class="notification-chip-grid">
                <label v-for="option in categoryOptions" :key="option.value" class="notification-chip">
                  <input v-model="notifications.categories" type="checkbox" :value="option.value" />
                  <span>{{ option.label }}</span>
                </label>
              </div>
            </fieldset>

            <fieldset class="profile-fieldset notification-section">
              <legend>Source scope</legend>
              <div class="notification-scope-options">
                <label class="notification-check-row">
                  <input v-model="notifications.scope" type="radio" value="all"
                    title="New monitored databases and servers are automatically included if they match your filters above." />
                  <span>
                    <strong>All monitored sources</strong>
                  </span>
                </label>

                <label class="notification-check-row">
                  <input v-model="notifications.scope" type="radio" value="selected"
                    title="Useful when you only support a specific application or environment." />
                  <span>
                    <strong>Selected databases and servers</strong>
                  </span>
                </label>
              </div>
            </fieldset>

            <div v-if="notifications.scope === 'selected'" class="notification-source-picker">
              <div class="notification-source-column">
                <div class="notification-source-heading">
                  <strong>Databases</strong>
                  <small>{{ notifications.database_connection_ids.length }} selected</small>
                </div>

                <p v-if="connectionsStore.loading" class="empty-state">
                  Loading database connections...
                </p>

                <div v-else class="notification-source-list">
                  <label v-for="connection in monitoredConnections" :key="connection.id"
                    class="notification-source-row">
                    <input v-model="notifications.database_connection_ids" type="checkbox" :value="connection.id" />
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
                  <label v-for="server in monitoredServers" :key="server.id" class="notification-source-row">
                    <input v-model="notifications.server_ids" type="checkbox" :value="server.id" />
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

            <p v-if="notifications.scope === 'selected' && selectedSourceCount === 0 && !notifications.include_system"
              class="notification-warning">
              Selected-source mode currently has no selected database/server and system alerts are disabled, so nothing
              will match.
            </p>

            <p v-if="notificationsError" class="login-error">
              {{ notificationsError }}
            </p>

            <div class="connection-form-actions">
              <button type="submit" class="primary-button" :disabled="authStore.notificationsSaving">
                {{ authStore.notificationsSaving ? 'Saving...' : 'Save alert subscription' }}
              </button>
            </div>
          </form>
        </section>
      </div>
    </section>
  </div>
</template>

<style scoped>
.profile-avatar-editor {
  position: relative;
  flex: 0 0 100px;
  width: 100px;
  height: 100px;
  border-radius: 50%;
  overflow: hidden;
}

.profile-avatar-editor .profile-avatar-large {
  width: 100%;
  height: 100%;
  flex-basis: auto;
}

.profile-avatar-change {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: .75rem;
  border: 0;
  border-radius: 50%;
  background: rgb(17 17 21 / 58%);
  color: #fff;
  font: inherit;
  font-size: .75rem;
  font-weight: 650;
  text-align: center;
  cursor: pointer;
  opacity: 0;
  transition: opacity .18s ease;
  backdrop-filter: blur(5px);
}

.profile-avatar-editor:hover .profile-avatar-change,
.profile-avatar-change:focus-visible {
  opacity: 1;
}

.profile-avatar-change:disabled {
  cursor: wait;
}

.profile-preference-data {
  display: grid;
  gap: .75rem;
  margin-top: 1.25rem;
  padding-top: 1.25rem;
  border-top: 1px solid var(--border);
}

.profile-preference-data h3,
.profile-preference-data p {
  margin: 0;
}

.profile-preference-data p {
  margin-top: .25rem;
  color: var(--text-muted);
  font-size: .82rem;
}

@media (hover: none) {
  .profile-avatar-change {
    opacity: 1;
    background: rgb(17 17 21 / 42%);
  }
}
</style>
