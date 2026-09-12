<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import AppLegalFooter from '@/components/common/AppLegalFooter.vue'
import { landingPath } from '@/core/dateTime'
import { useAuthStore } from '@/stores/auth'
import { useSystemSettingsStore } from '@/stores/systemSettings'

const router = useRouter()
const route = useRoute()
const authStore = useAuthStore()
const systemSettingsStore = useSystemSettingsStore()

const username = ref('')
const password = ref('')
const error = ref('')
const currentHour = ref(new Date().getHours())

const installationName = computed(() =>
  systemSettingsStore.branding?.installation_name || 'DBAChum',
)
const logoUrl = computed(() => systemSettingsStore.brandingLogoUrl)
const installationInitial = computed(() => installationName.value.trim().charAt(0).toUpperCase() || 'D')
const greeting = computed(() => {
  const hour = currentHour.value
  if (hour < 5) return 'Good night'
  if (hour < 12) return 'Good morning'
  if (hour < 18) return 'Good afternoon'
  if (hour < 22) return 'Good evening'
  return 'Good night'
})

onMounted(() => {
  currentHour.value = new Date().getHours()
  void systemSettingsStore.loadBranding().catch(() => undefined)
})

async function submit() {
  error.value = ''

  try {
    await authStore.login({
      username: username.value,
      password: password.value,
    })

    const redirect = typeof route.query.redirect === 'string'
      ? route.query.redirect
      : landingPath(authStore.user?.preferences.default_landing_page)

    await router.push(redirect)
  } catch {
    error.value = 'Invalid username or password.'
  }
}
</script>

<template>
  <main class="login-page">
    <div class="login-shell">
      <section class="login-card">
        <div class="login-brand">
          <div class="brand__logo login-brand__logo">
            <img v-if="logoUrl" :src="logoUrl" :alt="`${installationName} logo`" />
            <span v-else>{{ installationInitial }}</span>
          </div>

          <div>
            <strong>{{ installationName }}</strong>
          </div>
        </div>

        <div class="login-heading">
          <h1>{{ greeting }}</h1>
          <p>Sign in to continue to {{ installationName }}.</p>
        </div>

        <form class="login-form" @submit.prevent="submit">
          <label>
            <span class="field-label">Username <span class="required-mark" aria-hidden="true">*</span></span>
            <input v-model="username" type="text" autocomplete="username" required />
          </label>

          <label>
            <span class="field-label">Password <span class="required-mark" aria-hidden="true">*</span></span>
            <input v-model="password" type="password" autocomplete="current-password" required />
          </label>

          <p v-if="error" class="login-error">{{ error }}</p>

          <button class="primary-button login-submit" type="submit" :disabled="authStore.loading">
              <p>{{ authStore.loading ? 'Signing in' : 'Sign in' }}</p>
              <p v-if="authStore.loading" class="loading"></p>
          </button>
        </form>
      </section>

      <AppLegalFooter />
    </div>
<footer class="login-wave-footer">
  <svg viewBox="0 0 120 28" class="login-wave-svg">
    <defs>
      <path
        id="login-wave-path"
        d="M 0,10 C 30,10 30,15 60,15 90,15 90,10 120,10 150,10 150,15 180,15 210,15 210,10 240,10 v 28 h -240 z"
      />
    </defs>

    <use
      id="wave3"
      class="login-wave"
      href="#login-wave-path"
      x="0"
      y="-2"
    />

    <use
      id="wave2"
      class="login-wave"
      href="#login-wave-path"
      x="0"
      y="0"
    />

    <use
      id="wave1"
      class="login-wave"
      href="#login-wave-path"
      x="0"
      y="1"
    />
  </svg>
</footer>
  </main>
</template>
