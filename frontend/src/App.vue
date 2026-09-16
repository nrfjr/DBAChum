<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import AppShell from '@/layouts/AppShell.vue'
import PwaPrompt from '@/components/pwa/PwaPrompt.vue'
import { SESSION_EXPIRED_EVENT, setSessionActivityTracking } from '@/core/session'
import { useAuthStore } from '@/stores/auth'
import { showToast } from '@/ui/feedback'


const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()
let handlingSessionExpiry = false

async function handleSessionExpired() {
  if (handlingSessionExpiry || route.name === 'login') return
  handlingSessionExpiry = true
  const redirect = route.fullPath
  authStore.expireLocalSession()
  setSessionActivityTracking(false)
  showToast({
    title: 'Session expired',
    message: 'Please log in again.',
    tone: 'warning',
    durationMs: 6500,
  })
  try {
    await router.replace({ name: 'login', query: { redirect } })
  } finally {
    handlingSessionExpiry = false
  }
}

watch(
  () => authStore.isAuthenticated,
  (authenticated) => setSessionActivityTracking(authenticated),
  { immediate: true },
)

onMounted(() => {
  window.addEventListener(SESSION_EXPIRED_EVENT, handleSessionExpired)
})

onBeforeUnmount(() => {
  window.removeEventListener(SESSION_EXPIRED_EVENT, handleSessionExpired)
  setSessionActivityTracking(false)
})

const publicRoute = computed(
  () => route.meta.public === true,
)
</script>


<template>
  <RouterView v-if="publicRoute" />

  <AppShell v-else />

  <PwaPrompt />
</template>