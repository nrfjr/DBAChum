import 'vue-router'

import type { Permission } from '@/core/permissions'

export {}

declare module 'vue-router' {
  interface RouteMeta {
    requiresAuth?: boolean
    public?: boolean
    title?: string
    subtitle?: string
    permission?: Permission
    permissionsAny?: Permission[]
  }
}
