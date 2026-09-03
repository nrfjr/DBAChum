import { defineStore } from 'pinia'

import type {
  DatabaseEngine,
} from '@/stores/connections'

export type DatabaseMonitoringStatus =
  | 'online'
  | 'limited'
  | 'unreachable'
  | 'disabled'

export interface DatabaseOverview {
  connection_id: string
  engine: DatabaseEngine

  status: DatabaseMonitoringStatus

  response_time_ms: number | null

  active: number | null
  connections: number | null
  blocked: number | null
  uptime_seconds: number | null

  database_name: string | null
  container_name: string | null
  service_name: string | null
  instance_name: string | null
  version: string | null
  edition: string | null
  product_level: string | null
  generation: string | null
  connection_provider: string | null
  connection_driver: string | null
  connection_encrypt: string | null

  database_product: string | null
  version_comment: string | null
  server_hostname: string | null
  server_port: number | null
  database_count: number | null
  max_connections: number | null
  questions: number | null
  slow_queries: number | null
  data_directory: string | null
  performance_schema_enabled: boolean | null

  capabilities: Record<string, boolean> | null

  checked_at: string

  warnings: string[]
  error: string | null
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
      await response.json().catch(() => null)

    throw new Error(
      body?.error?.message ??
        `Request failed with status ${response.status}`,
    )
  }

  return response.json()
}

export const useDatabasesStore = defineStore(
  'databases',
  {
    state: () => ({
      overviews: {} as Record<
        string,
        DatabaseOverview
      >,

      loading: false,
      error: null as string | null,
    }),

    actions: {
      async loadAll() {
        this.loading = true
        this.error = null

        try {
          const results =
            await apiRequest<DatabaseOverview[]>(
              '/databases/overview',
            )

          this.overviews = Object.fromEntries(
            results.map((overview) => [
              overview.connection_id,
              overview,
            ]),
          )
        } catch (error) {
          this.error =
            error instanceof Error
              ? error.message
              : 'Unable to load database status.'
        } finally {
          this.loading = false
        }
      },

      async loadOne(id: string) {
        const overview =
          await apiRequest<DatabaseOverview>(
            `/databases/${id}/overview`,
          )

        this.overviews[id] = overview

        return overview
      },
    },
  },
)