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

export type DateTimeFormatPreference =
  | 'system'
  | '12h'
  | '24h'

export type LandingPagePreference =
  | 'dashboard'
  | 'databases'
  | 'servers'
  | 'alerts'

export type HistoryRangePreference =
  | '1h'
  | '6h'
  | '12h'
  | '24h'

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
  date_time_format: DateTimeFormatPreference
  default_landing_page: LandingPagePreference
  default_history_range: HistoryRangePreference
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
  has_avatar: boolean
  avatar_version: string | null
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
  date_time_format?: DateTimeFormatPreference
  default_landing_page?: LandingPagePreference
  default_history_range?: HistoryRangePreference
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
  const headers = new Headers(options.headers)
  if (options.body && !(options.body instanceof FormData)) {
    headers.set('Content-Type', 'application/json')
  }

  const response = await fetch(
    `${API_BASE_URL}${path}`,
    {
      ...options,
      credentials: 'include',
      headers,
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
      avatarUrl: (state) => {
        if (!state.user?.has_avatar) return null
        const version = encodeURIComponent(state.user.avatar_version ?? 'current')
        return `${API_BASE_URL}/profile/avatar?v=${version}`
      },
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

      async uploadAvatar(file: File) {
        const body = new FormData()
        body.append('file', file)
        const user = await apiRequest<User>('/profile/avatar', {
          method: 'PUT',
          body,
        })
        this.user = user
        return user
      },

      async removeAvatar() {
        const user = await apiRequest<User>('/profile/avatar', {
          method: 'DELETE',
        })
        this.user = user
        return user
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
