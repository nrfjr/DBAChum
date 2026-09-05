<script setup lang="ts">
import {
  computed,
  reactive,
  ref,
  watch,
} from 'vue'

import {
  useAuthStore,
  type AccentPreference,
  type DensityPreference,
  type ThemePreference,
} from '@/stores/auth'
import { useUiStore } from '@/stores/ui'


const authStore = useAuthStore()
const uiStore = useUiStore()

const identityMessage = ref<string | null>(null)
const identityError = ref<string | null>(null)
const preferencesMessage = ref<string | null>(null)
const preferencesError = ref<string | null>(null)

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

const roleLabel = computed(() => {
  const role = authStore.user?.role ?? 'viewer'
  return role.charAt(0).toUpperCase() + role.slice(1)
})

function syncFromUser() {
  const user = authStore.user
  if (!user) return

  identity.display_name = user.display_name
  identity.email = user.email ?? ''

  preferences.timezone = user.preferences.timezone
  preferences.theme = user.preferences.theme
  preferences.accent = user.preferences.accent
  preferences.density = user.preferences.density
}

watch(
  () => authStore.user,
  syncFromUser,
  {
    immediate: true,
    deep: true,
  },
)

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

function useBrowserTimezone() {
  preferences.timezone = browserTimezone
}
</script>

<template>
  <section class="page-header">
    <div>
      <h2>My profile</h2>
      <p>
        Your DBAChum identity and personal workspace defaults.
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
            Email is optional now and will be used by the upcoming alert-subscription phase.
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
  </div>
</template>
