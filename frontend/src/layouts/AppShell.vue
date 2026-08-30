<script setup lang="ts">
import { computed, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { useUiStore } from '@/stores/ui'
import TerminalDock from '@/components/terminal/TerminalDock.vue'
import { useTerminalSessionsStore } from '@/stores/terminalSessions'

import { useAuthStore } from '@/stores/auth'
import { hasPermission } from '@/core/permissions'
import { useAlertsStore } from '@/stores/alerts'

const route = useRoute()
const uiStore = useUiStore()

const pageTitle = computed(() => String(route.meta.title ?? 'DBAChum'))

const router = useRouter()
const authStore = useAuthStore()
const terminalStore = useTerminalSessionsStore()
const alertsStore = useAlertsStore()
let alertSummaryTimer: ReturnType<typeof setInterval> | undefined

const pageSubtitle = computed(() =>
  String(route.meta.subtitle ?? 'Database administration workspace.'),
)


const canAccessSettings = computed(() =>
  hasPermission(
    authStore.user?.role,
    'connections:test',
  ) ||
  hasPermission(
    authStore.user?.role,
    'users:manage',
  ) ||
  hasPermission(
    authStore.user?.role,
    'servers:manage',
  ),
)

const navigation = computed(() => {
  const items = [
    {
      label: 'Dashboard',
      path: '/',
      icon: 'gauge-high',
    },
    {
      label: 'Databases',
      path: '/databases',
      icon: 'database',
    },
    {
      label: 'Servers',
      path: '/servers',
      icon: 'server',
    },
    {
      label: 'Assets',
      path: '/assets',
      icon: 'boxes-stacked',
    },
    {
      label: 'Alerts',
      path: '/alerts',
      icon: 'bell',
      badge: alertsStore.summary.active,
    },
    {
      label: 'Settings',
      path: '/settings',
      icon: 'gear',
    },
  ]

  return items.filter((item) => {
    if (item.path === '/settings') return canAccessSettings.value
    return true
  })
})

async function logout() {
  terminalStore.clear()
  await authStore.logout()

  await router.push({
    name: 'login',
  })
}

onMounted(() => {
  void alertsStore.loadSummary()
  alertSummaryTimer = setInterval(() => {
    void alertsStore.loadSummary()
  }, 30_000)
})

onUnmounted(() => {
  if (alertSummaryTimer) clearInterval(alertSummaryTimer)
})

</script>

<template>
  <div class="app-shell">
    <div v-if="uiStore.sidebarOpen" class="sidebar-overlay" @click="uiStore.closeSidebar" />

    <aside class="sidebar" :class="{ 'sidebar--open': uiStore.sidebarOpen }">
      <div class="brand">
        <div class="brand__logo">
          D
        </div>

        <div class="brand__text">
          <strong>DBAChum</strong>
          <span>Database workspace</span>
        </div>
      </div>

      <nav class="navigation">
        <RouterLink v-for="item in navigation" :key="item.path" :to="item.path" class="navigation__item"
          @click="uiStore.closeSidebar">
          <span class="navigation__icon">
            <FontAwesomeIcon :icon="item.icon" />
          </span>

          <span class="navigation__label">
            {{ item.label }}
            <span v-if="item.badge" class="navigation__badge">{{ item.badge > 99 ? '99+' : item.badge }}</span>
          </span>
        </RouterLink>
      </nav>

      <div class="sidebar__footer">
        <span class="status-dot status-dot--online" />

        <div>
          <strong>DBAChum v2</strong>
          <span>Development build</span>
        </div>
      </div>
    </aside>

    <section class="workspace">
      <header class="topbar">
        <div class="topbar__left">
          <button class="icon-button mobile-menu" type="button" aria-label="Open navigation"
            @click="uiStore.toggleSidebar">
            <FontAwesomeIcon icon="bars" />
          </button>

          <div class="page-heading">
            <h1>{{ pageTitle }}</h1>
            <p>{{ pageSubtitle }}</p>
          </div>
        </div>

        <div class="topbar__actions">
          <div v-if="!uiStore.isOnline" class="offline-badge">
            Offline
          </div>
          <button class="theme-button" type="button" @click="uiStore.toggleTheme">
            <FontAwesomeIcon :icon="uiStore.isDark ? 'sun' : 'moon'" />

            <span>
              {{ uiStore.isDark ? 'Light' : 'Dark' }}
            </span>
          </button>

          <div class="avatar">
            DB
          </div>
          <span class="current-user">
            {{ authStore.user?.display_name }}
          </span>

          <button type="button" class="secondary-button" @click="logout">
            Logout
          </button>
        </div>
      </header>

      <main class="content">
        <RouterView />
      </main>
    </section>

    <TerminalDock />
  </div>
</template>