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

export interface DatabaseBackupItem {
  backup_id: string
  database_name: string | null
  kind: BackupKind
  native_type: string | null
  status: BackupStatus
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
  summaries: DatabaseBackupTargetSummary[]
  items: DatabaseBackupItem[]
  warnings: string[]
  notes: string[]
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

export const useDatabaseBackupsStore = defineStore(
  'databaseBackups',
  {
    state: () => ({
      results: {} as Record<string, DatabaseBackupResponse>,
      loadingIds: {} as Record<string, boolean>,
      errors: {} as Record<string, string | null>,
    }),

    actions: {
      async load(connectionId: string) {
        this.loadingIds[connectionId] = true
        this.errors[connectionId] = null

        try {
          const result = await apiRequest<DatabaseBackupResponse>(
            `/databases/${connectionId}/backups`,
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
