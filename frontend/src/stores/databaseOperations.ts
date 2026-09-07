import { defineStore } from 'pinia'

export type SessionOperation = 'terminate' | 'disconnect' | 'cancel_query'
export type StorageOperation = 'resize_file' | 'add_file' | 'create_tablespace'
export type AccountOperation = 'enable' | 'disable' | 'reset_password'
export type AccessOperation = 'grant_role' | 'revoke_role' | 'grant_privilege' | 'revoke_privilege'

export interface DatabaseActionAudit {
  id: string
  connection_id: string
  engine: string
  action: string
  target: string | null
  risk: 'safe' | 'sensitive' | 'dangerous'
  status: 'running' | 'succeeded' | 'failed' | 'partial'
  operator_user_id: string
  operator_username: string
  request_reference: string | null
  before: Record<string, unknown> | null
  after: Record<string, unknown> | null
  details: Record<string, unknown>
  started_at: string
  completed_at: string | null
  error: string | null
}

export interface SessionOperationInput {
  action: SessionOperation
  session_id: number
  serial_number?: number | null
  request_reference?: string | null
}

export interface StorageOperationInput {
  action: StorageOperation
  size_mb: number
  file_id?: number | null
  file_name?: string | null
  logical_name?: string | null
  tablespace_name?: string | null
  physical_name?: string | null
  file_type?: 'data' | 'log'
  autoextend?: boolean
  growth_mb?: number | null
  max_size_mb?: number | null
  request_reference?: string | null
}


export interface ParameterOperationInput {
  action: 'set'
  name: string
  value: string
  apply_mode?: 'runtime' | 'persistent' | 'both'
  request_reference?: string | null
}

export interface MaintenanceOperationInput {
  action:
    | 'delete_archivelogs'
    | 'delete_obsolete'
    | 'gather_schema_stats'
    | 'gather_table_stats'
    | 'recompile_invalid'
    | 'rebuild_unusable_indexes'
    | 'purge_recyclebin'
    | 'check_integrity'
    | 'update_statistics'
    | 'shrink_database'
    | 'analyze_table'
    | 'optimize_table'
    | 'check_table'
  server_id?: string | null
  oracle_sid?: string | null
  older_than_days?: number | null
  backed_up_times?: number
  schema_name?: string | null
  table_name?: string | null
  target_percent?: number | null
  request_reference?: string | null
}

export interface BackupOperationInput {
  action: 'full' | 'differential' | 'log' | 'archivelog' | 'database_plus_archivelog'
  server_id?: string | null
  destination?: string | null
  oracle_sid?: string | null
  copy_only?: boolean
  cleanup_archivelogs_after?: boolean
  archivelog_retention_days?: number
  request_reference?: string | null
}

export interface AccountOperationInput {
  action: AccountOperation
  account_name: string
  host?: string | null
  password?: string | null
  request_reference?: string | null
}

export interface AccessOperationInput {
  action: AccessOperation
  principal: string
  host?: string | null
  role_name?: string | null
  privilege?: string | null
  object_name?: string | null
  scope?: 'database' | 'server'
  request_reference?: string | null
}

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL

async function postOperation<T>(path: string, body: unknown): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })

  if (!response.ok) {
    const payload = await response.json().catch(() => null)
    throw new Error(
      payload?.error?.message ?? `Request failed with status ${response.status}`,
    )
  }

  return response.json()
}

export const useDatabaseOperationsStore = defineStore('databaseOperations', {
  state: () => ({
    busy: false,
    error: null as string | null,
    lastAction: null as DatabaseActionAudit | null,
  }),

  actions: {
    clearError() {
      this.error = null
    },

    async run<T extends DatabaseActionAudit>(path: string, body: unknown): Promise<T> {
      this.busy = true
      this.error = null
      try {
        const result = await postOperation<T>(path, body)
        this.lastAction = result
        return result
      } catch (error) {
        this.error = error instanceof Error ? error.message : 'Database operation failed.'
        throw error
      } finally {
        this.busy = false
      }
    },

    runSession(id: string, body: SessionOperationInput) {
      return this.run<DatabaseActionAudit>(`/databases/${id}/operations/session`, body)
    },

    runStorage(id: string, body: StorageOperationInput) {
      return this.run<DatabaseActionAudit>(`/databases/${id}/operations/storage`, body)
    },

    runAccount(id: string, body: AccountOperationInput) {
      return this.run<DatabaseActionAudit>(`/databases/${id}/operations/account`, body)
    },

    runAccess(id: string, body: AccessOperationInput) {
      return this.run<DatabaseActionAudit>(`/databases/${id}/operations/access`, body)
    },

    runParameter(id: string, body: ParameterOperationInput) {
      return this.run<DatabaseActionAudit>(`/databases/${id}/operations/parameter`, body)
    },

    runMaintenance(id: string, body: MaintenanceOperationInput) {
      return this.run<DatabaseActionAudit>(`/databases/${id}/operations/maintenance`, body)
    },

    runBackup(id: string, body: BackupOperationInput) {
      return this.run<DatabaseActionAudit>(`/databases/${id}/operations/backup`, body)
    },

    async loadAction(id: string, auditId: string) {
      const response = await fetch(`${API_BASE_URL}/databases/${id}/actions/${auditId}`, {
        credentials: 'include',
      })
      if (!response.ok) {
        const payload = await response.json().catch(() => null)
        throw new Error(payload?.error?.message ?? `Request failed with status ${response.status}`)
      }
      return response.json() as Promise<DatabaseActionAudit>
    },

    async waitForAction(id: string, auditId: string, timeoutMs = 4 * 60 * 60 * 1000) {
      const started = Date.now()
      while (Date.now() - started < timeoutMs) {
        const action = await this.loadAction(id, auditId)
        this.lastAction = action
        if (action.status !== 'running') return action
        await new Promise((resolve) => window.setTimeout(resolve, 2000))
      }
      throw new Error('Database operation is still running. Check the database action history for its final status.')
    },
  },
})
