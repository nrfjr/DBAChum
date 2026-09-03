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


export interface SqlServerLogin {
  name: string
  principal_type: string
  disabled: boolean
  default_database: string | null
  created_at: string | null
  modified_at: string | null
  roles: string[]
}

export interface SqlServerDatabaseUser {
  name: string
  principal_type: string
  login_name: string | null
  default_schema: string | null
  authentication_type: string | null
  orphaned: boolean
  created_at: string | null
  modified_at: string | null
  roles: string[]
}

export interface SqlServerRoleMembership {
  principal: string
  role: string
  source: string
}

export interface SqlServerPermission {
  principal: string
  state: string
  permission: string
  scope: string
  class_name: string | null
  securable: string | null
  grantor: string | null
}

export interface SqlServerElevatedFinding {
  principal: string
  severity: string
  source: string
  detail: string
}

export interface SqlServerSecurityResponse {
  available: boolean
  database_name: string | null
  generation: string | null
  login_count: number
  database_user_count: number
  disabled_login_count: number
  orphaned_user_count: number
  logins: SqlServerLogin[]
  database_users: SqlServerDatabaseUser[]
  server_roles: SqlServerRoleMembership[]
  database_roles: SqlServerRoleMembership[]
  server_permissions: SqlServerPermission[]
  database_permissions: SqlServerPermission[]
  elevated_findings: SqlServerElevatedFinding[]
  warnings: string[]
  checked_at: string
}


export interface SqlServerDatabaseHealth {
  name: string | null
  state: string | null
  recovery_model: string | null
  user_access: string | null
  read_only: boolean | null
  auto_close: boolean | null
  auto_shrink: boolean | null
  log_reuse_wait: string | null
  page_verify: string | null
  compatibility_level: number | null
}

export interface SqlServerLogHealth {
  size_bytes: number | null
  used_bytes: number | null
  free_bytes: number | null
  used_percent: number | null
  status_code: number | null
}

export interface SqlServerWorkloadHealth {
  blocked: number | null
  long_running: number | null
  longest_request_ms: number | null
  long_running_threshold_seconds: number
}

export interface SqlServerTempDbFile {
  name: string
  physical_name: string | null
  file_type: string
  allocated_bytes: number
  used_bytes: number | null
  free_bytes: number | null
  used_percent: number | null
}

export interface SqlServerTempDbHealth {
  allocated_bytes: number | null
  used_bytes: number | null
  free_bytes: number | null
  used_percent: number | null
  files: SqlServerTempDbFile[]
}

export interface SqlServerAgentJob {
  job_id: string
  name: string
  enabled: boolean
  owner: string | null
  description: string | null
  last_status: string
  last_run_at: string | null
  last_duration_seconds: number | null
  last_message: string | null
  running: boolean
}

export interface SqlServerAgentHealth {
  available: boolean
  enabled_jobs: number | null
  failed_jobs: number | null
  running_jobs: number | null
  jobs: SqlServerAgentJob[]
}

export interface SqlServerHealthResponse {
  available: boolean
  database_name: string | null
  generation: string | null
  database: SqlServerDatabaseHealth
  transaction_log: SqlServerLogHealth
  workload: SqlServerWorkloadHealth
  tempdb: SqlServerTempDbHealth
  agent: SqlServerAgentHealth
  warnings: string[]
  checked_at: string
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
    security: {} as Record<string, SqlServerSecurityResponse>,
    health: {} as Record<string, SqlServerHealthResponse>,

    loadingSessions: {} as Record<string, boolean>,
    loadingStorage: {} as Record<string, boolean>,
    loadingActivity: {} as Record<string, boolean>,
    loadingSecurity: {} as Record<string, boolean>,
    loadingHealth: {} as Record<string, boolean>,

    sessionsError: {} as Record<string, string | null>,
    storageError: {} as Record<string, string | null>,
    activityError: {} as Record<string, string | null>,
    securityError: {} as Record<string, string | null>,
    healthError: {} as Record<string, string | null>,
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

    async loadHealth(id: string, force = false) {
      if (!force && this.health[id]) return

      this.loadingHealth[id] = true
      this.healthError[id] = null

      try {
        this.health[id] = await apiRequest<SqlServerHealthResponse>(
          `/databases/${id}/sqlserver/health`,
        )
      } catch (error) {
        this.healthError[id] =
          error instanceof Error
            ? error.message
            : 'Unable to load SQL Server operational health.'
      } finally {
        this.loadingHealth[id] = false
      }
    },

    async loadSecurity(id: string, force = false) {
      if (!force && this.security[id]) return

      this.loadingSecurity[id] = true
      this.securityError[id] = null

      try {
        this.security[id] = await apiRequest<SqlServerSecurityResponse>(
          `/databases/${id}/sqlserver/security`,
        )
      } catch (error) {
        this.securityError[id] =
          error instanceof Error
            ? error.message
            : 'Unable to load SQL Server security metadata.'
      } finally {
        this.loadingSecurity[id] = false
      }
    },
  },
})

