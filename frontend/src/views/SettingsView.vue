<script setup lang="ts">
import { computed } from 'vue'
import { RouterLink, RouterView, useRoute } from 'vue-router'

import {
  useAuthStore,
} from '@/stores/auth'

import {
  hasPermission,
} from '@/core/permissions'

const route = useRoute()
const authStore = useAuthStore()

const sectionTitle = computed(() => {
  switch (route.name) {
    case 'settings-connections':
      return 'Connections'
    default:
      return 'Settings'
  }
})

const canManageUsers = computed(
  () =>
    hasPermission(
      authStore.user?.role,
      'users:manage',
    ),
)


const canAccessConnections = computed(() =>
  hasPermission(
    authStore.user?.role,
    'connections:test',
  ),
)

</script>

<template>
  <section class="page-header">
    <div>
      <h1>Settings</h1>
      <p>Configure DBAChum without cluttering the DBA workspace.</p>
    </div>
  </section>

  <div class="settings-layout">
    <aside class="settings-nav">
      <RouterLink v-if="canAccessConnections" to="/settings/connections">
        Connections
      </RouterLink>
      <RouterLink v-if="canManageUsers" to="/settings/users">
        Users
      </RouterLink>

      <div class="settings-nav-item disabled">
        General
        <span>Later</span>
      </div>

      <div class="settings-nav-item disabled">
        Import / Export
        <span>Later</span>
      </div>
    </aside>

    <section class="settings-content">
      <header class="settings-section-header">
        <h2>{{ sectionTitle }}</h2>
      </header>

      <RouterView />
    </section>
  </div>
</template>