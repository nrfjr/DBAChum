import { defineStore } from 'pinia'

import type { DatabaseConnection } from '@/stores/connections'

export type ServerOsFamily =
  | 'windows'
  | 'linux'
  | 'aix'
  | 'unix'
  | 'other'

export type ServerType =
  | 'database'
  | 'application'
  | 'utility'
  | 'other'

export interface Server {
  id: string
  name: string
  hostname: string
  ip_address: string | null
  server_type: ServerType
  os_family: ServerOsFamily
  os_version: string | null
  environment: string | null
  owner: string | null
  tags: string[]
  notes: string | null
  ssh_profile_id: string | null
  ssh_profile_name: string | null
  ssh_host_key_fingerprint: string | null
  ssh_host_key_trusted_at: string | null
  database_connection_ids: string[]
  enabled: boolean
  database_count: number
  created_at: string
  updated_at: string
}

export interface ServerInput {
  name: string
  hostname: string
  ip_address: string | null
  server_type: ServerType
  os_family: ServerOsFamily
  os_version: string | null
  environment: string | null
  owner: string | null
  tags: string[]
  notes: string | null
  ssh_profile_id: string | null
  database_connection_ids: string[]
  enabled: boolean
}

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL

async function apiRequest<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
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

  if (response.status === 204) {
    return undefined as T
  }

  return response.json()
}

export const useServersStore = defineStore('servers', {
  state: () => ({
    servers: [] as Server[],
    loading: false,
    saving: false,
    error: null as string | null,
  }),

  actions: {
    async load() {
      this.loading = true
      this.error = null

      try {
        this.servers = await apiRequest<Server[]>('/servers')
      } catch (error) {
        this.error =
          error instanceof Error
            ? error.message
            : 'Unable to load servers.'
      } finally {
        this.loading = false
      }
    },

    async loadOne(id: string) {
      const server = await apiRequest<Server>(`/servers/${id}`)
      const index = this.servers.findIndex((item) => item.id === id)
      if (index === -1) {
        this.servers.push(server)
      } else {
        this.servers[index] = server
      }
      return server
    },

    async create(data: ServerInput) {
      this.saving = true
      try {
        const server = await apiRequest<Server>('/servers', {
          method: 'POST',
          body: JSON.stringify(data),
        })
        this.servers.push(server)
        this.servers.sort((a, b) => a.name.localeCompare(b.name))
        return server
      } finally {
        this.saving = false
      }
    },

    async update(id: string, data: ServerInput) {
      this.saving = true
      try {
        const server = await apiRequest<Server>(`/servers/${id}`, {
          method: 'PUT',
          body: JSON.stringify(data),
        })
        const index = this.servers.findIndex((item) => item.id === id)
        if (index !== -1) this.servers[index] = server
        this.servers.sort((a, b) => a.name.localeCompare(b.name))
        return server
      } finally {
        this.saving = false
      }
    },

    async remove(id: string) {
      await apiRequest<void>(`/servers/${id}`, { method: 'DELETE' })
      this.servers = this.servers.filter((server) => server.id !== id)
    },

    async loadDatabases(id: string) {
      return apiRequest<DatabaseConnection[]>(`/servers/${id}/databases`)
    },
  },
})
