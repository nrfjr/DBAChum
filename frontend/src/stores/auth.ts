import { defineStore } from 'pinia'

import type {
  Permission,
  UserRole,
} from '@/core/permissions'


export type ThemePreference =
  | 'system'
  | 'light'
  | 'dark'

export type AccentPreference =
  | 'purple'
  | 'blue'
  | 'cyan'
  | 'green'
  | 'orange'
  | 'pink'

export type DensityPreference =
  | 'comfortable'
  | 'compact'

export type NotificationSeverity =
  | 'critical'
  | 'warning'

export type NotificationCategory =
  | 'availability'
  | 'blocking'
  | 'storage'
  | 'performance'
  | 'jobs'
  | 'backup'
  | 'system'

export type NotificationEngine =
  | 'oracle'
  | 'sqlserver'
  | 'mysql'

export type NotificationScope =
  | 'all'
  | 'selected'

export interface UserPreferences {
  timezone: string
  theme: ThemePreference
  accent: AccentPreference
  density: DensityPreference
}

export interface UserNotificationPreferences {
  email_enabled: boolean
  severities: NotificationSeverity[]
  categories: NotificationCategory[]
  engines: NotificationEngine[]
  include_servers: boolean
  include_system: boolean
  scope: NotificationScope
  database_connection_ids: string[]
  server_ids: string[]
}

export interface User {
  id: string
  username: string
  display_name: string
  email: string | null
  role: UserRole
  is_active: boolean
  permissions?: Permission[]
  avatar_initials: string
  preferences: UserPreferences
  notifications: UserNotificationPreferences
  created_at?: string | null
  updated_at?: string | null
}

export interface ProfileUpdateInput {
  display_name: string
  email: string | null
}

export interface PreferencesUpdateInput {
  timezone?: string
  theme?: ThemePreference
  accent?: AccentPreference
  density?: DensityPreference
}

export interface NotificationPreferencesUpdateInput {
  email_enabled?: boolean
  severities?: NotificationSeverity[]
  categories?: NotificationCategory[]
  engines?: NotificationEngine[]
  include_servers?: boolean
  include_system?: boolean
  scope?: NotificationScope
  database_connection_ids?: string[]
  server_ids?: string[]
}

interface LoginPayload {
  username: string
  password: string
}


const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL


async function apiRequest<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const response = await fetch(
    `${API_BASE_URL}${path}`,
    {
      ...options,
      credentials: 'include',
      headers: {
        'Content-Type': 'application/json',
        ...options.headers,
      },
    },
  )

  if (!response.ok) {
    const body = await response.json().catch(
      () => null,
    )

    throw new Error(
      body?.error?.message
        ?? `Request failed with status ${response.status}`,
    )
  }

  return response.json()
}


export const useAuthStore = defineStore(
  'auth',
  {
    state: () => ({
      user: null as User | null,
      initialized: false,
      loading: false,
      profileSaving: false,
      preferencesSaving: false,
      notificationsSaving: false,
    }),

    getters: {
      isAuthenticated: (state) =>
        state.user !== null,
    },

    actions: {
      async initialize() {
        if (this.initialized) {
          return
        }

        try {
          const response = await fetch(
            `${API_BASE_URL}/auth/me`,
            {
              credentials: 'include',
            },
          )

          if (response.ok) {
            this.user = await response.json()
          } else {
            this.user = null
          }
        } catch {
          this.user = null
        } finally {
          this.initialized = true
        }
      },

      async login(
        payload: LoginPayload,
      ) {
        this.loading = true

        try {
          const response = await fetch(
            `${API_BASE_URL}/auth/login`,
            {
              method: 'POST',

              headers: {
                'Content-Type':
                  'application/json',
              },

              credentials: 'include',

              body: JSON.stringify(
                payload,
              ),
            },
          )

          if (!response.ok) {
            throw new Error(
              'Invalid username or password.',
            )
          }

          const result = await response.json()

          this.user = result.user

          return true
        } finally {
          this.loading = false
        }
      },

      async updateProfile(
        data: ProfileUpdateInput,
      ) {
        this.profileSaving = true

        try {
          const user = await apiRequest<User>(
            '/profile',
            {
              method: 'PUT',
              body: JSON.stringify(data),
            },
          )

          this.user = user
          return user
        } finally {
          this.profileSaving = false
        }
      },

      async updatePreferences(
        data: PreferencesUpdateInput,
      ) {
        this.preferencesSaving = true

        try {
          const user = await apiRequest<User>(
            '/profile/preferences',
            {
              method: 'PUT',
              body: JSON.stringify(data),
            },
          )

          this.user = user
          return user
        } finally {
          this.preferencesSaving = false
        }
      },

      async updateNotifications(
        data: NotificationPreferencesUpdateInput,
      ) {
        this.notificationsSaving = true

        try {
          const user = await apiRequest<User>(
            '/profile/notifications',
            {
              method: 'PUT',
              body: JSON.stringify(data),
            },
          )

          this.user = user
          return user
        } finally {
          this.notificationsSaving = false
        }
      },

      async logout() {
        try {
          await fetch(
            `${API_BASE_URL}/auth/logout`,
            {
              method: 'POST',
              credentials: 'include',
            },
          )
        } finally {
          this.user = null
        }
      },
    },
  },
)
