import { defineStore } from 'pinia'

import type {
  DatabaseEngine,
} from '@/stores/connections'

import type {
  DatabaseMonitoringStatus,
} from '@/stores/databases'


export interface OracleMetricSystemDeltas {
  cpu_centiseconds?: number | null
  cpu_time_seconds?: number | null
  execute_count?: number | null
  logical_reads?: number | null
  physical_reads?: number | null
  user_commits?: number | null
  user_rollbacks?: number | null
  redo_bytes?: number | null
  hard_parses?: number | null
}

export interface OracleMetricTopSql {
  sql_id: string
  child_number: number
  plan_hash_value?: number
  parsing_schema_name?: string | null
  module?: string | null
  last_active_time?: string | null
  baseline?: boolean
  delta_cpu_time_us?: number | null
  delta_elapsed_time_us?: number | null
  delta_executions?: number | null
  delta_buffer_gets?: number | null
  delta_disk_reads?: number | null
  delta_rows_processed?: number | null
}

export interface OracleMetricTopSession {
  sid: number
  serial_number: number
  username?: string | null
  sql_id?: string | null
  status?: string | null
  module?: string | null
  machine?: string | null
  event?: string | null
  wait_class?: string | null
  active_seconds?: number | null
  blocking_session?: number | null
  cpu_time_seconds?: number | null
  baseline?: boolean
}

export interface OracleMetricTopWait {
  event: string
  waits?: number | null
  wait_time_seconds?: number | null
  baseline?: boolean
}

export interface OracleMetricTablespace {
  name: string
  contents?: string | null
  status?: string | null
  used_bytes?: number | null
  capacity_bytes?: number | null
  used_percent?: number | null
}

export interface OracleMetricStorage {
  tablespaces?: OracleMetricTablespace[]
  fra?: {
    destination?: string | null
    limit_bytes?: number | null
    used_bytes?: number | null
    reclaimable_bytes?: number | null
    number_of_files?: number | null
    used_percent?: number | null
  } | null
}

export interface OracleMetricSample {
  database_name?: string | null
  service_name?: string | null
  instance_name?: string | null
  version?: string | null
  system_deltas?: OracleMetricSystemDeltas
  top_sql?: OracleMetricTopSql[]
  top_sessions?: OracleMetricTopSession[]
  top_waits?: OracleMetricTopWait[]
  storage?: OracleMetricStorage
}

export interface SqlServerMetricFailedJob {
  name?: string | null
  status?: string | null
  last_run_at?: string | null
}

export interface SqlServerMetricSample {
  health_checked_at?: string | null
  database_name?: string | null
  generation?: string | null
  database_state?: string | null
  recovery_model?: string | null
  log_reuse_wait?: string | null
  log_size_bytes?: number | null
  log_used_bytes?: number | null
  log_used_percent?: number | null
  active?: number | null
  blocked?: number | null
  long_running?: number | null
  longest_request_ms?: number | null
  long_running_threshold_seconds?: number | null
  tempdb_allocated_bytes?: number | null
  tempdb_used_bytes?: number | null
  tempdb_used_percent?: number | null
  agent_available?: boolean | null
  agent_enabled_jobs?: number | null
  agent_failed_jobs?: number | null
  agent_running_jobs?: number | null
  failed_jobs?: SqlServerMetricFailedJob[]
  warnings?: string[]
}

export interface DatabaseMetricSample {
  collected_at: string
  checked_at: string | null

  status: DatabaseMonitoringStatus

  response_time_ms: number | null

  active: number | null
  connections: number | null
  blocked: number | null

  uptime_seconds: number | null

  warnings: string[]
  error: string | null
  oracle?: OracleMetricSample | null
  sqlserver?: SqlServerMetricSample | null
}

export interface OracleMetricSqlText {
  sql_id: string
  child_number: number
  sql_text: string
  parsing_schema_name?: string | null
  module?: string | null
  last_seen_at?: string | null
}


export interface DatabaseMetricHistory {
  connection_id: string
  engine: DatabaseEngine

  from_at: string
  to_at: string

  sample_interval_seconds: number

  count: number

  items: DatabaseMetricSample[]
  oracle_sql_texts: OracleMetricSqlText[]
}


const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL


async function apiRequest<T>(
  path: string,
): Promise<T> {
  const response = await fetch(
    `${API_BASE_URL}${path}`,
    {
      credentials: 'include',
    },
  )

  if (!response.ok) {
    const body =
      await response.json().catch(
        () => null,
      )

    throw new Error(
      body?.error?.message ??
        `Request failed with status ${response.status}`,
    )
  }

  return response.json()
}


export const useDatabaseMetricsStore =
  defineStore(
    'databaseMetrics',
    {
      state: () => ({
        histories: {} as Record<
          string,
          DatabaseMetricHistory
        >,

        loading: false,

        error:
          null as string | null,
      }),

      actions: {
        async loadHistory(
          connectionId: string,
          hours = 24,
        ) {
          this.loading = true
          this.error = null

          try {
            const history =
              await apiRequest<DatabaseMetricHistory>(
                `/databases/${connectionId}/metrics/history?hours=${hours}`,
              )

            this.histories[
              connectionId
            ] = history

            return history

          } catch (error) {
            this.error =
              error instanceof Error
                ? error.message
                : 'Unable to load metric history.'

            throw error

          } finally {
            this.loading = false
          }
        },
      },
    },
  )