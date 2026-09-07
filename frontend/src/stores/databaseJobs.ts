import { defineStore } from 'pinia'
import type { DatabaseEngine } from '@/stores/connections'
import type { DatabaseActionAudit } from '@/stores/databaseOperations'

export interface DatabaseJobItem {
  id: string
  name: string
  owner: string | null
  enabled: boolean | null
  status: string | null
  schedule: string | null
  last_run: string | null
  next_run: string | null
  job_type: string | null
  detail: string | null
  can_run: boolean
  can_enable_disable: boolean
}

export interface DatabaseJobsResponse {
  connection_id: string
  engine: DatabaseEngine
  available: boolean
  items: DatabaseJobItem[]
  warnings: string[]
  checked_at: string
}

export type JobOperation = 'run' | 'enable' | 'disable'

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
    const payload = await response.json().catch(() => null)
    throw new Error(payload?.error?.message ?? `Request failed with status ${response.status}`)
  }
  return response.json()
}

export const useDatabaseJobsStore = defineStore('databaseJobs', {
  state: () => ({
    results: {} as Record<string, DatabaseJobsResponse>,
    loading: {} as Record<string, boolean>,
    errors: {} as Record<string, string | null>,
    busy: false,
  }),
  actions: {
    async load(connectionId: string) {
      this.loading[connectionId] = true
      this.errors[connectionId] = null
      try {
        const result = await apiRequest<DatabaseJobsResponse>(`/databases/${connectionId}/jobs`)
        this.results[connectionId] = result
        return result
      } catch (error) {
        this.errors[connectionId] = error instanceof Error ? error.message : 'Unable to load jobs.'
        throw error
      } finally {
        this.loading[connectionId] = false
      }
    },
    async operate(connectionId: string, jobId: string, action: JobOperation) {
      this.busy = true
      this.errors[connectionId] = null
      try {
        const result = await apiRequest<DatabaseActionAudit>(`/databases/${connectionId}/jobs/operation`, {
          method: 'POST',
          body: JSON.stringify({ action, job_id: jobId }),
        })
        await this.load(connectionId)
        return result
      } catch (error) {
        this.errors[connectionId] = error instanceof Error ? error.message : 'Job operation failed.'
        throw error
      } finally {
        this.busy = false
      }
    },
  },
})
