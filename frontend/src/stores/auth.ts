import { defineStore } from 'pinia'

import type {
  UserRole,
} from '@/core/permissions'


export interface AuthUser {
  id: string
  username: string
  role: UserRole
  enabled: boolean
}


interface User {
  id: string
  username: string
  display_name: string
  role: UserRole
  is_active: boolean
  created_at: string
}


interface LoginPayload {
  username: string
  password: string
}


const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL


export const useAuthStore = defineStore(
  'auth',
  {
    state: () => ({
      user: null as User | null,
      initialized: false,
      loading: false,
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

          const result =
            await response.json()

          this.user = result.user

          return true
        } finally {
          this.loading = false
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