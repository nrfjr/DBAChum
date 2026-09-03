import { defineStore } from 'pinia'

export interface MySqlSession {
  connection_id: number
  user: string | null
  host: string | null
  database: string | null
  command: string | null
  state: string | null
  elapsed_seconds: number
  blocking_connection_id: number | null
  sql_text: string | null
}

export interface MySqlSessionsResponse {
  available: boolean
  database_name: string | null
  scope: 'database' | 'instance'
  processlist_source: string | null
  performance_schema_enabled: boolean | null
  total: number | null
  active: number | null
  blocked: number | null
  long_running: number | null
  long_running_threshold_seconds: number
  items: MySqlSession[]
  warnings: string[]
  checked_at: string
}

export interface MySqlSchemaStorage {
  schema_name: string
  data_bytes: number
  index_bytes: number
  total_bytes: number
  table_count: number
}

export interface MySqlTableStorage {
  schema_name: string | null
  table_name: string
  engine: string | null
  data_bytes: number
  index_bytes: number
  total_bytes: number
  rows_estimate: number | null
  collation: string | null
}

export interface MySqlStorageResponse {
  available: boolean
  database_name: string | null
  scope: 'database' | 'instance'
  data_bytes: number
  index_bytes: number
  total_bytes: number
  table_count: number
  schema_count: number
  schemas: MySqlSchemaStorage[]
  tables: MySqlTableStorage[]
  warnings: string[]
  checked_at: string
}

export interface MySqlActivityItem {
  connection_id: number
  user: string | null
  host: string | null
  database: string | null
  command: string | null
  elapsed_seconds: number
  state: string | null
  transaction_id: string | null
  transaction_state: string | null
  transaction_started: string | null
  transaction_wait_started: string | null
  wait_event: string | null
  wait_object: string | null
  blocking_connection_id: number | null
  sql_text: string | null
}

export interface MySqlActivityResponse {
  available: boolean
  database_name: string | null
  scope: 'database' | 'instance'
  processlist_source: string | null
  performance_schema_enabled: boolean | null
  items: MySqlActivityItem[]
  warning: string | null
  warnings: string[]
  checked_at: string
}

export interface MySqlConnectionHealth {
  current: number | null
  maximum: number | null
  utilization_percent: number | null
  max_used: number | null
  max_used_percent: number | null
  total_since_startup: number | null
  aborted_connects: number | null
  aborted_clients: number | null
}

export interface MySqlWorkloadHealth {
  threads_running: number | null
  slow_queries: number | null
  questions: number | null
  longest_active_seconds: number | null
  threads_created: number | null
}

export interface MySqlInnoDbHealth {
  active_transactions: number | null
  blocked_transactions: number | null
  oldest_transaction_seconds: number | null
  buffer_pool_size_bytes: number | null
  buffer_pool_data_bytes: number | null
  buffer_pool_used_percent: number | null
}

export interface MySqlTemporaryTableHealth {
  created: number | null
  created_on_disk: number | null
  disk_percent: number | null
}

export interface MySqlServerHealth {
  uptime_seconds: number | null
  read_only: boolean | null
  slow_query_log: boolean | null
  long_query_time_seconds: number | null
}

export interface MySqlHealthResponse {
  available: boolean
  database_name: string | null
  scope: 'database' | 'instance'
  product: string | null
  generation: string | null
  performance_schema_enabled: boolean
  processlist_source: string | null
  connections: MySqlConnectionHealth
  workload: MySqlWorkloadHealth
  innodb: MySqlInnoDbHealth
  temporary_tables: MySqlTemporaryTableHealth
  server: MySqlServerHealth
  warnings: string[]
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

export const useMySqlDbaStore = defineStore('mysqlDba', {
  state: () => ({
    sessions: {} as Record<string, MySqlSessionsResponse>,
    storage: {} as Record<string, MySqlStorageResponse>,
    activity: {} as Record<string, MySqlActivityResponse>,
    health: {} as Record<string, MySqlHealthResponse>,

    loadingSessions: {} as Record<string, boolean>,
    loadingStorage: {} as Record<string, boolean>,
    loadingActivity: {} as Record<string, boolean>,
    loadingHealth: {} as Record<string, boolean>,

    sessionsError: {} as Record<string, string | null>,
    storageError: {} as Record<string, string | null>,
    activityError: {} as Record<string, string | null>,
    healthError: {} as Record<string, string | null>,
  }),

  actions: {
    async loadSessions(id: string) {
      this.loadingSessions[id] = true
      this.sessionsError[id] = null
      try {
        this.sessions[id] = await apiRequest<MySqlSessionsResponse>(
          `/databases/${id}/mysql/sessions`,
        )
      } catch (error) {
        this.sessionsError[id] =
          error instanceof Error
            ? error.message
            : 'Unable to load MySQL/MariaDB sessions.'
      } finally {
        this.loadingSessions[id] = false
      }
    },

    async loadStorage(id: string) {
      this.loadingStorage[id] = true
      this.storageError[id] = null
      try {
        this.storage[id] = await apiRequest<MySqlStorageResponse>(
          `/databases/${id}/mysql/storage`,
        )
      } catch (error) {
        this.storageError[id] =
          error instanceof Error
            ? error.message
            : 'Unable to load MySQL/MariaDB storage.'
      } finally {
        this.loadingStorage[id] = false
      }
    },

    async loadActivity(id: string) {
      this.loadingActivity[id] = true
      this.activityError[id] = null
      try {
        this.activity[id] = await apiRequest<MySqlActivityResponse>(
          `/databases/${id}/mysql/activity`,
        )
      } catch (error) {
        this.activityError[id] =
          error instanceof Error
            ? error.message
            : 'Unable to load MySQL/MariaDB activity.'
      } finally {
        this.loadingActivity[id] = false
      }
    },

    async loadHealth(id: string, force = false) {
      if (!force && this.health[id]) return
      this.loadingHealth[id] = true
      this.healthError[id] = null
      try {
        this.health[id] = await apiRequest<MySqlHealthResponse>(
          `/databases/${id}/mysql/health`,
        )
      } catch (error) {
        this.healthError[id] =
          error instanceof Error
            ? error.message
            : 'Unable to load MySQL/MariaDB health.'
      } finally {
        this.loadingHealth[id] = false
      }
    },
  },
})
