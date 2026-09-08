import { defineStore } from 'pinia'

export interface DatabaseAnalyticsItem {
  connection_id: string
  name: string
  engine: 'oracle' | 'sqlserver' | 'mysql'
  host: string
  port: number
  database: string | null
  status: string
  checked_at: string | null
  database_size_bytes?: number | null
  data_size_bytes?: number | null
  used_size_bytes?: number | null
  free_size_bytes?: number | null
  temp_size_bytes?: number | null
  log_size_bytes?: number | null
  index_size_bytes?: number | null
  recovery_size_bytes?: number | null
  recovery_capacity_bytes?: number | null
  sga_bytes?: number | null
  pga_allocated_bytes?: number | null
  pga_target_bytes?: number | null
  storage_used_percent?: number | null
  last_backup_at?: string | null
  last_backup_age_days?: number | null
  last_backup_status?: string | null
  last_backup_kind?: string | null
  last_backup_size_bytes?: number | null
}

export interface DatabaseGrowthPoint {
  connection_id: string
  name: string
  month: string
  size_bytes: number
  source: string
}

export interface DatabaseAnalyticsResponse {
  generated_at: string
  filter_engine: string | null
  summary: {
    database_count: number
    online_count: number
    unreachable_count: number
    total_size_bytes: number
    used_size_bytes: number | null
  }
  engine_distribution: { engine: string; count: number }[]
  items: DatabaseAnalyticsItem[]
  growth: DatabaseGrowthPoint[]
}

export interface ServerAnalyticsItem {
  server_id: string
  name: string
  hostname: string
  os_family: string
  os_version: string | null
  status: string
  checked_at: string | null
  cpu_used_percent: number | null
  memory_total_bytes: number | null
  memory_used_bytes: number | null
  memory_used_percent: number | null
  disk_total_bytes: number | null
  disk_used_bytes: number | null
  disk_used_percent: number | null
  uptime_seconds: number | null
}

export interface ServerAnalyticsResponse {
  generated_at: string
  filter_os_family: string | null
  summary: {
    server_count: number
    online_count: number
    unreachable_count: number
    total_memory_bytes: number
    total_disk_bytes: number
    used_disk_bytes: number
  }
  os_distribution: { os_family: string; count: number }[]
  items: ServerAnalyticsItem[]
}

export interface GrowthImportPreview {
  filename: string
  headers: string[]
  row_count: number
  preview_rows: Record<string, unknown>[]
  column_values: Record<string, string[]>
}

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    credentials: 'include',
    headers: {
      ...options.headers,
    },
  })
  if (!response.ok) {
    const body = await response.json().catch(() => null)
    throw new Error(body?.error?.message ?? `Request failed with status ${response.status}`)
  }
  return response.json()
}

export const useAnalyticsStore = defineStore('analytics', {
  state: () => ({
    databases: null as DatabaseAnalyticsResponse | null,
    servers: null as ServerAnalyticsResponse | null,
    loading: false,
    error: null as string | null,
  }),

  actions: {
    async loadDatabases(engine = '', months = 12) {
      this.loading = true
      this.error = null
      try {
        const params = new URLSearchParams({ months: String(months) })
        if (engine) params.set('engine', engine)
        this.databases = await request<DatabaseAnalyticsResponse>(`/analytics/databases?${params}`)
        return this.databases
      } catch (error) {
        this.error = error instanceof Error ? error.message : 'Unable to load database analytics.'
        throw error
      } finally {
        this.loading = false
      }
    },

    async loadServers(osFamily = '', months = 12) {
      this.loading = true
      this.error = null
      try {
        const params = new URLSearchParams({ months: String(months) })
        if (osFamily) params.set('os_family', osFamily)
        this.servers = await request<ServerAnalyticsResponse>(`/analytics/servers?${params}`)
        return this.servers
      } catch (error) {
        this.error = error instanceof Error ? error.message : 'Unable to load server analytics.'
        throw error
      } finally {
        this.loading = false
      }
    },

    async previewGrowth(file: File) {
      const data = new FormData()
      data.append('file', file)
      return request<GrowthImportPreview>('/analytics/database-growth/preview', {
        method: 'POST',
        body: data,
      })
    },

    async importGrowth(file: File, config: Record<string, unknown>) {
      const data = new FormData()
      data.append('file', file)
      data.append('config_json', JSON.stringify(config))
      return request<{ imported: number; skipped: number; errors: string[] }>('/analytics/database-growth/import', {
        method: 'POST',
        body: data,
      })
    },
  },
})
