<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import TerminalDock from '@/components/terminal/TerminalDock.vue'
import { hasPermission, type Permission } from '@/core/permissions'
import { useAlertsStore } from '@/stores/alerts'
import { useAuthStore } from '@/stores/auth'
import { useTerminalSessionsStore } from '@/stores/terminalSessions'
import { useUiStore } from '@/stores/ui'

const route = useRoute()
const router = useRouter()
const uiStore = useUiStore()
const authStore = useAuthStore()
const terminalStore = useTerminalSessionsStore()
const alertsStore = useAlertsStore()

const databaseNavOpen = ref(route.path.startsWith('/databases'))
let alertSummaryTimer: ReturnType<typeof setInterval> | undefined

const pageTitle = computed(() => String(route.meta.title ?? 'DBAChum'))
const pageSubtitle = computed(() =>
  String(route.meta.subtitle ?? 'Database administration workspace.'),
)

watch(
  () => authStore.user?.preferences,
  (preferences) => {
    uiStore.applyUserPreferences(preferences)
  },
  {
    immediate: true,
    deep: true,
  },
)

watch(
  () => route.path,
  (path) => {
    if (path.startsWith('/databases')) databaseNavOpen.value = true
  },
)

const settingsPermissions: Permission[] = [
  'connections:test',
  'users:manage',
  'servers:manage',
  'provisioning:manage',
  'ldap:manage',
  'notifications:manage',
]

const canAccessSettings = computed(() =>
  settingsPermissions.some((permission) => hasPermission(authStore.user, permission)),
)

const navigation = computed(() => [
  {
    label: 'Dashboard',
    path: '/',
    icon: 'gauge-high',
  },
  {
    label: 'Servers',
    path: '/servers',
    icon: 'server',
  },
  {
    label: 'Alerts',
    path: '/alerts',
    icon: 'bell',
    badge: alertsStore.summary.active,
  },
  {
    label: 'Records',
    path: '/records',
    icon: 'book-open',
  },
])

function isSectionActive(path: string) {
  if (path === '/') return route.path === '/'
  return route.path === path || route.path.startsWith(`${path}/`)
}

function databaseRoute(engine?: 'oracle' | 'sqlserver' | 'mysql') {
  return {
    path: '/databases',
    query: engine ? { engine } : {},
  }
}

function databaseSubActive(engine?: 'oracle' | 'sqlserver' | 'mysql') {
  if (!route.path.startsWith('/databases')) return false
  const current = String(route.query.engine ?? '')
  return engine ? current === engine : current === ''
}

async function toggleTheme() {
  const previous = uiStore.themePreference
  uiStore.toggleTheme()

  try {
    await authStore.updatePreferences({
      theme: uiStore.themePreference,
    })
  } catch {
    uiStore.setThemePreference(previous)
  }
}

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
        <div class="brand__logo">D</div>

        <div class="brand__text">
          <strong>DBAChum</strong>
          <span>Database workspace</span>
        </div>
      </div>

      <nav class="navigation">
        <RouterLink
          to="/"
          class="navigation__item"
          :class="{ 'navigation__item--active': isSectionActive('/') }"
          @click="uiStore.closeSidebar"
        >
          <span class="navigation__icon"><FontAwesomeIcon icon="gauge-high" /></span>
          <span class="navigation__label">Dashboard</span>
        </RouterLink>

        <div class="navigation__group" :class="{ 'navigation__group--active': route.path.startsWith('/databases') }">
          <div class="navigation__group-row">
            <RouterLink
              :to="databaseRoute()"
              class="navigation__item navigation__item--group-parent"
              :class="{ 'navigation__item--active': route.path.startsWith('/databases') }"
              @click="uiStore.closeSidebar"
            >
              <span class="navigation__icon"><FontAwesomeIcon icon="database" /></span>
              <span class="navigation__label">Databases</span>
            </RouterLink>

            <button
              type="button"
              class="navigation__expand"
              :aria-expanded="databaseNavOpen"
              aria-label="Toggle database navigation"
              @click="databaseNavOpen = !databaseNavOpen"
            >
              <FontAwesomeIcon icon="chevron-down" :class="{ 'navigation__chevron--open': databaseNavOpen }" />
            </button>
          </div>

          <div v-if="databaseNavOpen" class="navigation__subnav">
            <RouterLink
              :to="databaseRoute()"
              class="navigation__subitem"
              :class="{ active: databaseSubActive() }"
              @click="uiStore.closeSidebar"
            >
              All databases
            </RouterLink>
            <RouterLink
              :to="databaseRoute('oracle')"
              class="navigation__subitem"
              :class="{ active: databaseSubActive('oracle') }"
              @click="uiStore.closeSidebar"
            >
              Oracle
            </RouterLink>
            <RouterLink
              :to="databaseRoute('sqlserver')"
              class="navigation__subitem"
              :class="{ active: databaseSubActive('sqlserver') }"
              @click="uiStore.closeSidebar"
            >
              SQL Server
            </RouterLink>
            <RouterLink
              :to="databaseRoute('mysql')"
              class="navigation__subitem"
              :class="{ active: databaseSubActive('mysql') }"
              @click="uiStore.closeSidebar"
            >
              MySQL / MariaDB
            </RouterLink>
          </div>
        </div>

        <RouterLink
          v-for="item in navigation.slice(1)"
          :key="item.path"
          :to="item.path"
          class="navigation__item"
          :class="{ 'navigation__item--active': isSectionActive(item.path) }"
          @click="uiStore.closeSidebar"
        >
          <span class="navigation__icon"><FontAwesomeIcon :icon="item.icon" /></span>
          <span class="navigation__label">
            {{ item.label }}
            <span v-if="item.badge" class="navigation__badge">{{ item.badge > 99 ? '99+' : item.badge }}</span>
          </span>
        </RouterLink>

        <div class="navigation__spacer" />

        <RouterLink
          v-if="canAccessSettings"
          to="/settings"
          class="navigation__item navigation__item--settings"
          :class="{ 'navigation__item--active': isSectionActive('/settings') }"
          @click="uiStore.closeSidebar"
        >
          <span class="navigation__icon"><FontAwesomeIcon icon="gear" /></span>
          <span class="navigation__label">Settings</span>
        </RouterLink>
      </nav>

      <div class="sidebar__footer">
        <span class="status-dot status-dot--online" />

        <div>
          <strong>DBAChum v1</strong>
          <span>Development build</span>
        </div>
      </div>
    </aside>

    <section class="workspace">
      <header class="topbar">
        <div class="topbar__left">
          <button class="icon-button mobile-menu" type="button" aria-label="Open navigation" @click="uiStore.toggleSidebar">
            <FontAwesomeIcon icon="bars" />
          </button>

          <div class="page-heading">
            <h1>{{ pageTitle }}</h1>
            <p>{{ pageSubtitle }}</p>
          </div>
        </div>

        <div class="topbar__actions">
          <div v-if="!uiStore.isOnline" class="offline-badge">Offline</div>
          <button class="theme-button" type="button" @click="toggleTheme">
            <FontAwesomeIcon :icon="uiStore.isDark ? 'sun' : 'moon'" />
            <span>{{ uiStore.isDark ? 'Light' : 'Dark' }}</span>
          </button>

          <RouterLink to="/profile" class="profile-link">
            <div class="avatar">{{ authStore.user?.avatar_initials || 'DB' }}</div>
            <span class="current-user">{{ authStore.user?.display_name }}</span>
          </RouterLink>

          <button type="button" class="secondary-button" @click="logout">Logout</button>
        </div>
      </header>

      <main class="content">
        <RouterView />
      </main>
    </section>

    <TerminalDock />
  </div>
</template>
