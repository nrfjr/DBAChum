<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import AppDialogHost from '@/components/common/AppDialogHost.vue'
import AppToastHost from '@/components/common/AppToastHost.vue'
import TerminalDock from '@/components/terminal/TerminalDock.vue'
import { hasPermission, type Permission } from '@/core/permissions'
import { useAlertsStore } from '@/stores/alerts'
import { useAuthStore } from '@/stores/auth'
import { useTerminalSessionsStore } from '@/stores/terminalSessions'
import { useSystemSettingsStore } from '@/stores/systemSettings'
import { useUiStore } from '@/stores/ui'

const route = useRoute()
const router = useRouter()
const uiStore = useUiStore()
const authStore = useAuthStore()
const terminalStore = useTerminalSessionsStore()
const alertsStore = useAlertsStore()
const systemSettingsStore = useSystemSettingsStore()

const databaseNavOpen = ref(route.path.startsWith('/databases'))
const analyticsNavOpen = ref(route.path.startsWith('/analytics'))
const serverNavOpen = ref(route.path.startsWith('/servers'))
const profileMenuOpen = ref(false)
let alertSummaryTimer: ReturnType<typeof setInterval> | undefined
let clockTimer: ReturnType<typeof setInterval> | undefined
const currentTime = ref('')

const pageTitle = computed(() => String(route.meta.title ?? 'DBAChum'))
const pageSubtitle = computed(() =>
  String(route.meta.subtitle ?? 'Database administration workspace.'),
)

const isContextDetail = computed(() =>
  route.name === 'database-detail' || route.name === 'server-detail' || route.name === 'record-detail',
)

const displayName = computed(() => authStore.user?.display_name || authStore.user?.username || 'DBA')
const installationName = computed(() => systemSettingsStore.general?.installation_name || 'DBAChum')

function updateClock() {
  currentTime.value = new Intl.DateTimeFormat(undefined, {
    hour: 'numeric',
    minute: '2-digit',
    second: '2-digit',
    timeZoneName: 'short',
  }).format(new Date())
}

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
    if (path.startsWith('/analytics')) analyticsNavOpen.value = true
    if (path.startsWith('/servers')) serverNavOpen.value = true
  },
)

const settingsPermissions: Permission[] = [
  'connections:test',
  'users:manage',
  'servers:manage',
  'provisioning:manage',
  'ldap:manage',
  'notifications:manage',
  'system:manage',
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

function analyticsRoute(type: 'databases' | 'servers' = 'databases') {
  return {
    path: '/analytics',
    query: type === 'databases' ? {} : { type },
  }
}

function analyticsSubActive(type: 'databases' | 'servers') {
  if (!route.path.startsWith('/analytics')) return false
  const current = String(route.query.type ?? 'databases')
  return current === type
}

function serverRoute(os?: 'windows' | 'linux' | 'aix' | 'unix' | 'other') {
  return {
    path: '/servers',
    query: os ? { os } : {},
  }
}

function serverSubActive(os?: 'windows' | 'linux' | 'aix' | 'unix' | 'other') {
  if (!route.path.startsWith('/servers')) return false
  const current = String(route.query.os ?? '')
  return os ? current === os : current === ''
}

async function setTheme(value: 'system' | 'light' | 'dark') {
  const previous = uiStore.themePreference
  uiStore.setThemePreference(value)
  profileMenuOpen.value = false

  try {
    await authStore.updatePreferences({ theme: value })
  } catch {
    uiStore.setThemePreference(previous)
  }
}

function toggleProfileMenu(event?: Event) {
  event?.stopPropagation()
  profileMenuOpen.value = !profileMenuOpen.value
}

function closeProfileMenu() {
  profileMenuOpen.value = false
}

async function logout() {
  terminalStore.clear()
  await authStore.logout()

  await router.push({
    name: 'login',
  })
}

onMounted(() => {
  document.addEventListener('click', closeProfileMenu)
  updateClock()
  clockTimer = setInterval(updateClock, 1000)
  void alertsStore.loadSummary()
  void systemSettingsStore.loadGeneral().catch(() => undefined)
  alertSummaryTimer = setInterval(() => {
    void alertsStore.loadSummary()
  }, 30_000)
})

onUnmounted(() => {
  document.removeEventListener('click', closeProfileMenu)
  if (alertSummaryTimer) clearInterval(alertSummaryTimer)
  if (clockTimer) clearInterval(clockTimer)
})
</script>

<template>
  <div class="app-shell">
    <div v-if="uiStore.sidebarOpen" class="sidebar-overlay" @click="uiStore.closeSidebar" />

    <aside class="sidebar" :class="{ 'sidebar--open': uiStore.sidebarOpen }">
      <div class="brand">
        <div class="brand__logo">D</div>

        <div class="brand__text">
          <strong>{{ installationName }}</strong>
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

        <div class="navigation__group" :class="{ 'navigation__group--active': route.path.startsWith('/analytics') }">
          <div class="navigation__group-row">
            <RouterLink
              :to="analyticsRoute()"
              class="navigation__item navigation__item--group-parent"
              :class="{ 'navigation__item--active': route.path.startsWith('/analytics') }"
              @click="uiStore.closeSidebar"
            >
              <span class="navigation__icon"><FontAwesomeIcon icon="chart-line" /></span>
              <span class="navigation__label">Analytics</span>
            </RouterLink>

            <button
              type="button"
              class="navigation__expand"
              :aria-expanded="analyticsNavOpen"
              aria-label="Toggle analytics navigation"
              @click="analyticsNavOpen = !analyticsNavOpen"
            >
              <FontAwesomeIcon icon="chevron-down" :class="{ 'navigation__chevron--open': analyticsNavOpen }" />
            </button>
          </div>

          <div v-if="analyticsNavOpen" class="navigation__subnav">
            <RouterLink :to="analyticsRoute('databases')" class="navigation__subitem" :class="{ active: analyticsSubActive('databases') }" @click="uiStore.closeSidebar">
              Database analytics
            </RouterLink>
            <RouterLink :to="analyticsRoute('servers')" class="navigation__subitem" :class="{ active: analyticsSubActive('servers') }" @click="uiStore.closeSidebar">
              Server analytics
            </RouterLink>
          </div>
        </div>

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

        <div class="navigation__group" :class="{ 'navigation__group--active': route.path.startsWith('/servers') }">
          <div class="navigation__group-row">
            <RouterLink
              :to="serverRoute()"
              class="navigation__item navigation__item--group-parent"
              :class="{ 'navigation__item--active': route.path.startsWith('/servers') }"
              @click="uiStore.closeSidebar"
            >
              <span class="navigation__icon"><FontAwesomeIcon icon="server" /></span>
              <span class="navigation__label">Servers</span>
            </RouterLink>

            <button type="button" class="navigation__expand" :aria-expanded="serverNavOpen" aria-label="Toggle server navigation" @click="serverNavOpen = !serverNavOpen">
              <FontAwesomeIcon icon="chevron-down" :class="{ 'navigation__chevron--open': serverNavOpen }" />
            </button>
          </div>

          <div v-if="serverNavOpen" class="navigation__subnav">
            <RouterLink :to="serverRoute()" class="navigation__subitem" :class="{ active: serverSubActive() }" @click="uiStore.closeSidebar">All servers</RouterLink>
            <RouterLink :to="serverRoute('linux')" class="navigation__subitem" :class="{ active: serverSubActive('linux') }" @click="uiStore.closeSidebar">Linux</RouterLink>
            <RouterLink :to="serverRoute('windows')" class="navigation__subitem" :class="{ active: serverSubActive('windows') }" @click="uiStore.closeSidebar">Windows</RouterLink>
            <RouterLink :to="serverRoute('aix')" class="navigation__subitem" :class="{ active: serverSubActive('aix') }" @click="uiStore.closeSidebar">AIX</RouterLink>
            <RouterLink :to="serverRoute('unix')" class="navigation__subitem" :class="{ active: serverSubActive('unix') }" @click="uiStore.closeSidebar">Unix</RouterLink>
            <RouterLink :to="serverRoute('other')" class="navigation__subitem" :class="{ active: serverSubActive('other') }" @click="uiStore.closeSidebar">Other</RouterLink>
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
          <strong>{{ installationName }} v1</strong>
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

          <div v-if="!isContextDetail" class="page-heading">
            <h1>{{ pageTitle }}</h1>
            <p>{{ pageSubtitle }}</p>
          </div>
          <div v-else class="page-heading page-heading--context">
            <strong>{{ installationName }}</strong>
            <span>{{ pageTitle }} workspace</span>
          </div>
        </div>

        <div class="topbar__actions">
          <div v-if="!uiStore.isOnline" class="offline-badge">Offline</div>

          <div class="profile-menu" @click.stop>
            <button
              type="button"
              class="profile-menu__trigger"
              :aria-expanded="profileMenuOpen"
              aria-label="Open profile menu"
              @click="toggleProfileMenu"
            >
              <span class="profile-menu__meta">
                <strong>{{ displayName }}</strong>
                <time>{{ currentTime }}</time>
              </span>
              <div class="avatar">{{ authStore.user?.avatar_initials || 'DB' }}</div>
            </button>

            <div v-if="profileMenuOpen" class="profile-menu__popover">
              <div class="profile-menu__identity">
                <div class="avatar avatar--large">{{ authStore.user?.avatar_initials || 'DB' }}</div>
                <div>
                  <strong>{{ displayName }}</strong>
                  <span>{{ authStore.user?.email || authStore.user?.username }}</span>
                </div>
              </div>

              <RouterLink to="/profile" class="profile-menu__item" @click="profileMenuOpen = false">
                Profile & preferences
              </RouterLink>

              <div class="profile-menu__section">
                <span>Appearance</span>
                <div class="profile-menu__theme-grid">
                  <button type="button" :class="{ active: uiStore.themePreference === 'system' }" @click="setTheme('system')">System</button>
                  <button type="button" :class="{ active: uiStore.themePreference === 'light' }" @click="setTheme('light')">Light</button>
                  <button type="button" :class="{ active: uiStore.themePreference === 'dark' }" @click="setTheme('dark')">Dark</button>
                </div>
              </div>

              <button type="button" class="profile-menu__item profile-menu__item--danger" @click="logout">Logout</button>
            </div>
          </div>
        </div>
      </header>

      <main class="content">
        <RouterView />
      </main>
    </section>

    <TerminalDock />
    <AppDialogHost />
    <AppToastHost />
  </div>
</template>
<style scoped>
.profile-menu__meta {
  display: grid;
  gap: 0.12rem;
  text-align: right;
  line-height: 1.15;
}

.profile-menu__meta strong {
  font-size: 0.78rem;
  font-weight: 600;
}

.profile-menu__meta time {
  color: var(--text-muted);
  font-size: 0.67rem;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}

@media (max-width: 640px) {
  .profile-menu__meta {
    display: none;
  }
}
</style>
