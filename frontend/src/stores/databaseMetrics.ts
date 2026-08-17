import { defineStore } from 'pinia'

import type {
  DatabaseEngine,
} from '@/stores/connections'

import type {
  DatabaseMonitoringStatus,
} from '@/stores/databases'


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
}


export interface DatabaseMetricHistory {
  connection_id: string
  engine: DatabaseEngine

  from_at: string
  to_at: string

  sample_interval_seconds: number

  count: number

  items: DatabaseMetricSample[]
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