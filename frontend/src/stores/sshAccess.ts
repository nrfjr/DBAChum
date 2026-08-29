import { defineStore } from 'pinia'

export type SshAuthType = 'password' | 'private_key'

export interface SshAccessProfile {
  id: string
  name: string
  username: string
  port: number
  auth_type: SshAuthType
  notes: string | null
  enabled: boolean
  has_password: boolean
  has_private_key: boolean
  has_passphrase: boolean
  server_count: number
  created_at: string
  updated_at: string
}

export interface SshAccessProfileInput {
  name: string
  username: string
  port: number
  auth_type: SshAuthType
  password?: string
  private_key?: string
  passphrase?: string
  notes: string | null
  enabled: boolean
}

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL

async function apiRequest<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
  })

  if (!response.ok) {
    const body = await response.json().catch(() => null)
    throw new Error(
      body?.error?.message ??
        `Request failed with status ${response.status}`,
    )
  }

  if (response.status === 204) return undefined as T
  return response.json()
}

export const useSshAccessStore = defineStore('ssh-access', {
  state: () => ({
    profiles: [] as SshAccessProfile[],
    loading: false,
    saving: false,
    error: null as string | null,
  }),

  actions: {
    async load() {
      this.loading = true
      this.error = null
      try {
        this.profiles = await apiRequest<SshAccessProfile[]>('/ssh-access-profiles')
      } catch (error) {
        this.error = error instanceof Error ? error.message : 'Unable to load SSH access profiles.'
      } finally {
        this.loading = false
      }
    },

    async create(data: SshAccessProfileInput) {
      this.saving = true
      try {
        const profile = await apiRequest<SshAccessProfile>('/ssh-access-profiles', {
          method: 'POST',
          body: JSON.stringify(data),
        })
        this.profiles.push(profile)
        this.profiles.sort((a, b) => a.name.localeCompare(b.name))
        return profile
      } finally {
        this.saving = false
      }
    },

    async update(id: string, data: SshAccessProfileInput) {
      this.saving = true
      try {
        const profile = await apiRequest<SshAccessProfile>(`/ssh-access-profiles/${id}`, {
          method: 'PUT',
          body: JSON.stringify(data),
        })
        const index = this.profiles.findIndex((item) => item.id === id)
        if (index !== -1) this.profiles[index] = profile
        this.profiles.sort((a, b) => a.name.localeCompare(b.name))
        return profile
      } finally {
        this.saving = false
      }
    },

    async remove(id: string) {
      await apiRequest<void>(`/ssh-access-profiles/${id}`, { method: 'DELETE' })
      this.profiles = this.profiles.filter((profile) => profile.id !== id)
    },
  },
})
