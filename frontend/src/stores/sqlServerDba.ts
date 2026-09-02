import { defineStore } from 'pinia'

export interface SqlServerSession {
  session_id: number
  login_name: string | null
  status: string | null
  host_name: string | null
  program_name: string | null
  request_status: string | null
  command: string | null
  request_start_time: string | null
  elapsed_ms: number | null
  cpu_ms: number | null
  wait_type: string | null
  blocking_session_id: number | null
  sql_text: string | null
}

export interface SqlServerSessionsResponse {
  available: boolean
  total: number | null
  active: number | null
  blocked: number | null
  long_running: number | null
  long_running_threshold_seconds: number
  items: SqlServerSession[]
  warnings: string[]
  checked_at: string
}

export interface SqlServerFile {
  name: string
  physical_name: string | null
  file_type: string
  allocated_bytes: number
  used_bytes: number | null
  free_bytes: number | null
  used_percent: number | null
}

export interface SqlServerStorageResponse {
  available: boolean
  database_name: string | null
  allocated_bytes: number | null
  used_bytes: number | null
  files: SqlServerFile[]
  warnings: string[]
  checked_at: string
}

export interface SqlServerActivityItem {
  session_id: number
  login_name: string | null
  status: string | null
  command: string | null
  elapsed_ms: number
  cpu_ms: number | null
  wait_type: string | null
  wait_ms: number | null
  blocking_session_id: number | null
  database_name: string | null
  sql_text: string | null
}

export interface SqlServerActivityResponse {
  available: boolean
  items: SqlServerActivityItem[]
  warning: string | null
  checked_at: string
}

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL

async function apiRequest<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    credentials: 'include',
  })

  if (!response.ok) {
    const body = await response.json().catch(() => null)

    throw new Error(
      body?.error?.message ??
        `Request failed with status ${response.status}`,
    )
  }

  return response.json()
}

export const useSqlServerDbaStore = defineStore('sqlServerDba', {
  state: () => ({
    sessions: {} as Record<string, SqlServerSessionsResponse>,
    storage: {} as Record<string, SqlServerStorageResponse>,
    activity: {} as Record<string, SqlServerActivityResponse>,

    loadingSessions: {} as Record<string, boolean>,
    loadingStorage: {} as Record<string, boolean>,
    loadingActivity: {} as Record<string, boolean>,

    sessionsError: {} as Record<string, string | null>,
    storageError: {} as Record<string, string | null>,
    activityError: {} as Record<string, string | null>,
  }),

  actions: {
    async loadSessions(id: string) {
      this.loadingSessions[id] = true
      this.sessionsError[id] = null

      try {
        this.sessions[id] = await apiRequest<SqlServerSessionsResponse>(
          `/databases/${id}/sqlserver/sessions`,
        )
      } catch (error) {
        this.sessionsError[id] =
          error instanceof Error
            ? error.message
            : 'Unable to load SQL Server sessions.'
      } finally {
        this.loadingSessions[id] = false
      }
    },

    async loadStorage(id: string) {
      this.loadingStorage[id] = true
      this.storageError[id] = null

      try {
        this.storage[id] = await apiRequest<SqlServerStorageResponse>(
          `/databases/${id}/sqlserver/storage`,
        )
      } catch (error) {
        this.storageError[id] =
          error instanceof Error
            ? error.message
            : 'Unable to load SQL Server storage.'
      } finally {
        this.loadingStorage[id] = false
      }
    },

    async loadActivity(id: string) {
      this.loadingActivity[id] = true
      this.activityError[id] = null

      try {
        this.activity[id] = await apiRequest<SqlServerActivityResponse>(
          `/databases/${id}/sqlserver/activity`,
        )
      } catch (error) {
        this.activityError[id] =
          error instanceof Error
            ? error.message
            : 'Unable to load SQL Server activity.'
      } finally {
        this.loadingActivity[id] = false
      }
    },
  },
})
