import { defineStore } from 'pinia'
import type { DatabaseEngine } from '@/stores/connections'

export type BackupStatus =
  | 'successful'
  | 'warning'
  | 'failed'
  | 'running'
  | 'unknown'

export type BackupKind =
  | 'full'
  | 'differential'
  | 'incremental'
  | 'log'
  | 'archive_log'
  | 'file'
  | 'partial'
  | 'controlfile'
  | 'spfile'
  | 'other'

export type BackupWindow = 'today' | '3d' | '7d' | 'custom'
export type BackupDetailValue = string | number | boolean | null

export interface DatabaseBackupItem {
  backup_id: string
  database_name: string | null
  kind: BackupKind
  native_type: string | null
  status: BackupStatus
  native_status: string | null
  started_at: string | null
  finished_at: string | null
  duration_seconds: number | null
  input_bytes: number | null
  output_bytes: number | null
  backup_size_bytes: number | null
  destinations: string[]
  device_type: string | null
  label: string | null
  owner: string | null
  details: Record<string, BackupDetailValue>
}

export interface DatabaseBackupTargetSummary {
  database_name: string
  recovery_model: string | null
  last_full: DatabaseBackupItem | null
  last_differential: DatabaseBackupItem | null
  last_incremental: DatabaseBackupItem | null
  last_log: DatabaseBackupItem | null
}

export interface DatabaseBackupResponse {
  connection_id: string
  engine: DatabaseEngine
  available: boolean
  source: string
  scope: 'database' | 'instance' | 'external'
  database_name: string | null
  generation: string | null
  selected_window: BackupWindow
  custom_start_date: string | null
  custom_end_date: string | null
  latest_backup: DatabaseBackupItem | null
  summaries: DatabaseBackupTargetSummary[]
  items: DatabaseBackupItem[]
  truncated: boolean
  warnings: string[]
  notes: string[]
  checked_at: string
}

export interface BackupLoadOptions {
  window?: BackupWindow
  startDate?: string
  endDate?: string
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

export const useDatabaseBackupsStore = defineStore(
  'databaseBackups',
  {
    state: () => ({
      results: {} as Record<string, DatabaseBackupResponse>,
      loadingIds: {} as Record<string, boolean>,
      errors: {} as Record<string, string | null>,
    }),

    actions: {
      async load(connectionId: string, options: BackupLoadOptions = {}) {
        this.loadingIds[connectionId] = true
        this.errors[connectionId] = null

        const window = options.window ?? 'today'
        const params = new URLSearchParams({ window })
        if (window === 'custom') {
          if (options.startDate) params.set('start_date', options.startDate)
          if (options.endDate) params.set('end_date', options.endDate)
        }

        try {
          const result = await apiRequest<DatabaseBackupResponse>(
            `/databases/${connectionId}/backups?${params.toString()}`,
          )
          this.results[connectionId] = result
          return result
        } catch (error) {
          this.errors[connectionId] =
            error instanceof Error
              ? error.message
              : 'Unable to load backup history.'
          throw error
        } finally {
          this.loadingIds[connectionId] = false
        }
      },
    },
  },
)
