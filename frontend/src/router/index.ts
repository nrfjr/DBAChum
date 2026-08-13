import { createRouter, createWebHistory } from 'vue-router'

import DashboardView from '@/views/DashboardView.vue'
import PlaceholderView from '@/views/PlaceholderView.vue'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),

  routes: [
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
      component: PlaceholderView,
      meta: {
        title: 'Databases',
        subtitle: 'Connections, health, sessions, storage and performance.',
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
      name: 'settings',
      component: PlaceholderView,
      meta: {
        title: 'Settings',
        subtitle: 'DBAChum configuration and preferences.',
      },
    },

    {
      path: '/:pathMatch(.*)*',
      redirect: '/',
    },
  ],
})

router.afterEach((to) => {
  const title = String(to.meta.title ?? 'DBAChum')
  document.title = `${title} | DBAChum`
})

export default router