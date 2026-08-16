import { createRouter, createWebHistory } from 'vue-router'

import DashboardView from '@/views/DashboardView.vue'
import PlaceholderView from '@/views/PlaceholderView.vue'

import LoginView from '@/views/LoginView.vue'

import { useAuthStore } from '@/stores/auth'

import DatabaseWorkspaceView from '@/views/DatabaseWorkspaceView.vue'
import DatabaseDetailView from '@/views/DatabaseDetailView.vue'
import SettingsView from '@/views/SettingsView.vue'
import SettingsConnectionsView from '@/views/SettingsConnectionsView.vue'


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
      component: PlaceholderView,
      meta: {
        title: 'Servers',
        subtitle: 'Server inventory and infrastructure health.',
      },
    },

    {
      path: '/assets',
      name: 'assets',
      component: PlaceholderView,
      meta: {
        title: 'Assets',
        subtitle: 'Infrastructure and application inventory.',
      },
    },

    {
      path: '/alerts',
      name: 'alerts',
      component: PlaceholderView,
      meta: {
        title: 'Alerts',
        subtitle: 'Warnings, incidents and recovery history.',
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
            title: 'Connections',
          },
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

  if (
    to.meta.public
    && authStore.isAuthenticated
    && to.name === 'login'
  ) {
    return {
      name: 'dashboard',
    }
  }

  if (
    !to.meta.public
    && !authStore.isAuthenticated
  ) {
    return {
      name: 'login',

      query: {
        redirect: to.fullPath,
      },
    }
  }
})

router.afterEach((to) => {
  const title = String(to.meta.title ?? 'DBAChum')
  document.title = `${title} | DBAChum`
})

export default router