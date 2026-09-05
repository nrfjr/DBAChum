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
    case 'settings-provisioning':
      return 'Provisioning'
    case 'settings-ldap':
      return 'LDAP'
    case 'settings-users':
      return 'Users'
    case 'settings-infrastructure':
      return 'Infrastructure'
    case 'settings-alerts-email':
      return 'Alerts & Email'
    default:
      return 'Settings'
  }
})

const canManageUsers = computed(
  () =>
    hasPermission(
      authStore.user,
      'users:manage',
    ),
)



const canManageProvisioning = computed(
  () => hasPermission(authStore.user, 'provisioning:manage'),
)

const canManageLdap = computed(
  () => hasPermission(authStore.user, 'ldap:manage'),
)

const canManageInfrastructure = computed(
  () => hasPermission(authStore.user, 'servers:manage'),
)

const canAccessConnections = computed(() =>
  hasPermission(
    authStore.user,
    'connections:test',
  ),
)

const canManageNotifications = computed(() =>
  hasPermission(
    authStore.user,
    'notifications:manage',
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
      <RouterLink v-if="canAccessConnections" class="settings-nav-item" to="/settings/connections">
        Connections
      </RouterLink>
      <RouterLink v-if="canManageProvisioning" class="settings-nav-item" to="/settings/provisioning">
        Provisioning
      </RouterLink>
      <RouterLink v-if="canManageLdap" class="settings-nav-item" to="/settings/ldap">
        LDAP
      </RouterLink>
      <RouterLink v-if="canManageInfrastructure" class="settings-nav-item" to="/settings/infrastructure">
        Infrastructure
      </RouterLink>
      <RouterLink v-if="canManageUsers" class="settings-nav-item" to="/settings/users">
        Users
      </RouterLink>
      <RouterLink v-if="canManageNotifications" class="settings-nav-item" to="/settings/alerts-email">
        Alerts &amp; Email
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