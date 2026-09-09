<script setup lang="ts">
import { computed, ref } from 'vue'
import { RouterLink, RouterView, useRoute } from 'vue-router'

import '@/assets/settingsCompletion.css'

import { hasPermission, type Permission } from '@/core/permissions'
import { useAuthStore } from '@/stores/auth'

const route = useRoute()
const authStore = useAuthStore()
const search = ref('')

const connectionPermissions: Permission[] = [
  'connections:test',
  'servers:manage',
  'ldap:manage',
  'provisioning:manage',
]

const canAccessConnections = computed(() =>
  connectionPermissions.some((permission) => hasPermission(authStore.user, permission)),
)
const canManageUsers = computed(() => hasPermission(authStore.user, 'users:manage'))
const canManageNotifications = computed(() => hasPermission(authStore.user, 'notifications:manage'))
const canManageSystem = computed(() => hasPermission(authStore.user, 'system:manage'))

const sectionTitle = computed(() => {
  switch (route.name) {
    case 'settings-general':
      return 'General'
    case 'settings-monitoring':
      return 'Monitoring'
    case 'settings-data':
      return 'Data'
    case 'settings-system-maintenance':
      return 'System Maintenance'
    case 'settings-connections':
      return 'Connections'
    case 'settings-users':
      return 'Users & Access'
    case 'settings-alerts-email':
      return 'Alerts & Email'
    default:
      return 'Settings'
  }
})

interface SettingsNavItem {
  label: string
  to?: string
  visible: boolean
  disabled?: boolean
}

interface SettingsNavGroup {
  label: string
  items: SettingsNavItem[]
}

const groups = computed<SettingsNavGroup[]>(() => [
  {
    label: 'System',
    items: [
      {
        label: 'General',
        to: '/settings/general',
        visible: canManageSystem.value,
      },
    ],
  },
  {
    label: 'Connections',
    items: [
      {
        label: 'Connections',
        to: '/settings/connections',
        visible: canAccessConnections.value,
      },
    ],
  },
  {
    label: 'Operations',
    items: [
      {
        label: 'Monitoring',
        to: '/settings/monitoring',
        visible: canManageSystem.value,
      },
      {
        label: 'Alerts & Email',
        to: '/settings/alerts-email',
        visible: canManageNotifications.value,
      },
    ],
  },
  {
    label: 'Administration',
    items: [
      {
        label: 'Users & Access',
        to: '/settings/users',
        visible: canManageUsers.value,
      },
      {
        label: 'Data',
        to: '/settings/data',
        visible: canManageSystem.value,
      },
      {
        label: 'System Maintenance',
        to: '/settings/system-maintenance',
        visible: canManageSystem.value,
      },
    ],
  },
])

const filteredGroups = computed(() => {
  const q = search.value.trim().toLowerCase()

  return groups.value
    .map((group) => ({
      ...group,
      items: group.items.filter((item) => {
        if (!item.visible) return false
        if (!q) return true
        return `${group.label} ${item.label}`.toLowerCase().includes(q)
      }),
    }))
    .filter((group) => group.items.length > 0)
})
</script>

<template>
  <section class="page-header settings-page-header">
    <div title="Technical and installation-wide configuration. Personal choices remain under Profile / Preferences.">
      <h1>Settings</h1>
    </div>
  </section>

  <div class="settings-layout settings-layout--phase8">
    <aside class="settings-nav settings-nav--grouped">
      <label class="settings-search">
        <input v-model="search" type="search" placeholder="Looking for something?" />
      </label>

      <div v-for="group in filteredGroups" :key="group.label" class="settings-nav-group">
        <div class="settings-nav-group__label">{{ group.label }}</div>

        <template v-for="item in group.items" :key="item.label">
          <RouterLink v-if="item.to" class="settings-nav-item settings-nav-item--rich" :to="item.to">
            <span>
              <strong>{{ item.label }}</strong>
            </span>
          </RouterLink>

          <div v-else class="settings-nav-item settings-nav-item--rich disabled">
            <span>
              <strong>{{ item.label }}</strong>
            </span>
            <em>Later</em>
          </div>
        </template>
      </div>

      <p v-if="filteredGroups.length === 0" class="settings-search-empty">No settings match “{{ search }}”.</p>
    </aside>

    <section class="settings-content">
      <header class="settings-section-header">
        <h2>{{ sectionTitle }}</h2>
      </header>

      <RouterView />
    </section>
  </div>
</template>
