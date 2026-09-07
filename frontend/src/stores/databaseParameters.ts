import { defineStore } from 'pinia'
import type { DatabaseEngine } from '@/stores/connections'

export interface DatabaseParameterItem {
  name: string
  value: string | null
  display_value: string | null
  default_value: string | null
  runtime_value: string | null
  configured_value: string | null
  dynamic: boolean | null
  session_modifiable: boolean | null
  system_modifiable: string | null
  advanced: boolean | null
  description: string | null
  source: string | null
}

export interface DatabaseParametersResponse {
  connection_id: string
  engine: DatabaseEngine
  scope: 'database' | 'instance' | 'server'
  generation: string | null
  available: boolean
  items: DatabaseParameterItem[]
  warnings: string[]
  checked_at: string
}

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL

async function apiRequest<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, { credentials: 'include' })
  if (!response.ok) {
    const payload = await response.json().catch(() => null)
    throw new Error(payload?.error?.message ?? `Request failed with status ${response.status}`)
  }
  return response.json()
}

export const useDatabaseParametersStore = defineStore('databaseParameters', {
  state: () => ({
    results: {} as Record<string, DatabaseParametersResponse>,
    loading: {} as Record<string, boolean>,
    errors: {} as Record<string, string | null>,
  }),
  actions: {
    async load(connectionId: string) {
      this.loading[connectionId] = true
      this.errors[connectionId] = null
      try {
        const result = await apiRequest<DatabaseParametersResponse>(`/databases/${connectionId}/parameters`)
        this.results[connectionId] = result
        return result
      } catch (error) {
        this.errors[connectionId] = error instanceof Error ? error.message : 'Unable to load database parameters.'
        throw error
      } finally {
        this.loading[connectionId] = false
      }
    },
  },
})
