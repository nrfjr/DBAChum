import { defineStore } from 'pinia'


import type {
  UserRole,
} from '@/core/permissions'

export type {
  UserRole,
}


export interface ManagedUser {
  id: string
  username: string
  display_name: string
  email: string | null
  avatar_initials: string
  role: UserRole
  is_active: boolean

  created_at?: string
  updated_at?: string
}


export interface CreateUserInput {
  username: string
  display_name?: string | null
  email?: string | null
  password: string
  role: UserRole
  is_active: boolean
}


export interface UpdateUserInput {
  role: UserRole
  is_active: boolean
  display_name?: string | null
  email?: string | null
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
        'Content-Type':
          'application/json',

        ...options.headers,
      },
    },
  )

  if (!response.ok) {
    const body =
      await response.json().catch(
        () => null,
      )

    throw new Error(
      body?.error?.message ??
        `Request failed with status ${response.status}`,
    )
  }

  if (response.status === 204) {
    return undefined as T
  }

  return response.json()
}


export const useUsersStore =
  defineStore('users', {
    state: () => ({
      users: [] as ManagedUser[],

      loading: false,
      saving: false,

      error: null as string | null,
    }),

    actions: {
      async load() {
        this.loading = true
        this.error = null

        try {
          this.users =
            await apiRequest<ManagedUser[]>(
              '/users',
            )

        } catch (error) {
          this.error =
            error instanceof Error
              ? error.message
              : 'Unable to load users.'

        } finally {
          this.loading = false
        }
      },

      async create(
        data: CreateUserInput,
      ) {
        this.saving = true

        try {
          const user =
            await apiRequest<ManagedUser>(
              '/users',
              {
                method: 'POST',
                body: JSON.stringify(data),
              },
            )

          this.users.push(user)

          this.users.sort(
            (a, b) =>
              a.username.localeCompare(
                b.username,
              ),
          )

          return user

        } finally {
          this.saving = false
        }
      },

      async update(
        id: string,
        data: UpdateUserInput,
      ) {
        const user =
          await apiRequest<ManagedUser>(
            `/users/${id}`,
            {
              method: 'PUT',
              body: JSON.stringify(data),
            },
          )

        const index =
          this.users.findIndex(
            (item) => item.id === id,
          )

        if (index !== -1) {
          this.users[index] = user
        }

        return user
      },

      async resetPassword(
        id: string,
        password: string,
      ) {
        await apiRequest<void>(
          `/users/${id}/password`,
          {
            method: 'PUT',

            body: JSON.stringify({
              password,
            }),
          },
        )
      },

      async remove(id: string) {
        await apiRequest<void>(
          `/users/${id}`,
          {
            method: 'DELETE',
          },
        )

        this.users =
          this.users.filter(
            (user) =>
              user.id !== id,
          )
      },
    },
  })
