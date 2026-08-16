import 'vue-router'

import type {
  Permission,
} from '@/core/permissions'


export {}


declare module 'vue-router' {
  interface RouteMeta {
    requiresAuth?: boolean
    permission?: Permission
  }
}