import { createRouter, createWebHistory } from 'vue-router'

import AlertsView from '@/views/AlertsView.vue'
import DashboardView from '@/views/DashboardView.vue'
import DatabaseDetailView from '@/views/DatabaseDetailView.vue'
import DatabaseWorkspaceView from '@/views/DatabaseWorkspaceView.vue'
import LoginView from '@/views/LoginView.vue'
import ProfileView from '@/views/ProfileView.vue'
import RecordsView from '@/views/RecordsView.vue'
import ServerDetailView from '@/views/ServerDetailView.vue'
import ServersView from '@/views/ServersView.vue'
import SettingsAlertsEmailView from '@/views/SettingsAlertsEmailView.vue'
import SettingsConnectionsView from '@/views/SettingsConnectionsView.vue'
import SettingsUsersView from '@/views/SettingsUsersView.vue'
import SettingsView from '@/views/SettingsView.vue'

import { hasPermission } from '@/core/permissions'
import { useAuthStore } from '@/stores/auth'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),

  routes: [
    {
      path: '/login',
      name: 'login',
      component: LoginView,
      meta: {
        public: true,
        title: 'Sign in',
      },
    },
    {
      path: '/',
      name: 'dashboard',
      component: DashboardView,
      meta: {
        title: 'Dashboard',
        subtitle: 'Infrastructure overview and database health.',
      },
    },
    {
      path: '/databases',
      name: 'databases',
      component: DatabaseWorkspaceView,
      meta: {
        title: 'Databases',
        subtitle: 'Monitored Oracle, SQL Server and MySQL / MariaDB databases.',
      },
    },
    {
      path: '/databases/:id',
      name: 'database-detail',
      component: DatabaseDetailView,
      meta: {
        title: 'Database',
      },
    },
    {
      path: '/servers',
      name: 'servers',
      component: ServersView,
      meta: {
        title: 'Servers',
      },
    },
    {
      path: '/servers/:id',
      name: 'server-detail',
      component: ServerDetailView,
      meta: {
        title: 'Server',
      },
    },
    {
      path: '/records',
      name: 'records',
      component: RecordsView,
      meta: {
        title: 'Records',
        subtitle: 'Fast DBA operational lookup and reference catalog.',
      },
    },
    {
      path: '/assets',
      redirect: '/records',
    },
    {
      path: '/alerts',
      name: 'alerts',
      component: AlertsView,
      meta: {
        title: 'Alerts',
        subtitle: 'Warnings, incidents and recovery history.',
      },
    },
    {
      path: '/profile',
      name: 'profile',
      component: ProfileView,
      meta: {
        title: 'My profile',
        subtitle: 'Identity and personal DBAChum preferences.',
      },
    },
    {
      path: '/settings',
      component: SettingsView,
      meta: {
        title: 'Settings',
      },
      children: [
        {
          path: '',
          redirect: '/settings/connections',
        },
        {
          path: 'connections',
          name: 'settings-connections',
          component: SettingsConnectionsView,
          meta: {
            permissionsAny: [
              'connections:test',
              'servers:manage',
              'ldap:manage',
              'provisioning:manage',
            ],
          },
        },
        {
          path: 'users',
          name: 'settings-users',
          component: SettingsUsersView,
          meta: {
            permission: 'users:manage',
          },
        },
        {
          path: 'alerts-email',
          name: 'settings-alerts-email',
          component: SettingsAlertsEmailView,
          meta: {
            permission: 'notifications:manage',
          },
        },
        {
          path: 'provisioning',
          redirect: { path: '/settings/connections', query: { type: 'provisioning' } },
        },
        {
          path: 'ldap',
          redirect: { path: '/settings/connections', query: { type: 'ldap' } },
        },
        {
          path: 'infrastructure',
          redirect: { path: '/settings/connections', query: { type: 'servers' } },
        },
      ],
    },
    {
      path: '/:pathMatch(.*)*',
      redirect: '/',
    },
  ],
})

router.beforeEach(async (to) => {
  const authStore = useAuthStore()

  await authStore.initialize()

  if (to.meta.public && authStore.isAuthenticated && to.name === 'login') {
    return { name: 'dashboard' }
  }

  if (!to.meta.public && !authStore.isAuthenticated) {
    return {
      name: 'login',
      query: {
        redirect: to.fullPath,
      },
    }
  }

  const requiredPermission = to.meta.permission
  if (requiredPermission && !hasPermission(authStore.user, requiredPermission)) {
    return { name: 'dashboard' }
  }

  const anyPermissions = to.meta.permissionsAny
  if (
    anyPermissions?.length
    && !anyPermissions.some((permission) => hasPermission(authStore.user, permission))
  ) {
    return { name: 'dashboard' }
  }
})

router.afterEach((to) => {
  const title = String(to.meta.title ?? 'DBAChum')
  document.title = `${title} | DBAChum`
})

export default router
