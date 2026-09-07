import { defineStore } from 'pinia'
import type { DatabaseEngine } from '@/stores/connections'

export interface TopSqlItem {
  key: string
  sql_text: string | null
  normalized_sql: boolean
  schema_name: string | null
  executions: number | null
  elapsed_seconds: number | null
  cpu_seconds: number | null
  logical_reads: number | null
  physical_reads: number | null
  rows_processed: number | null
  last_active_at: string | null
  sql_id: string | null
  child_number: number | null
  plan_hash_value: number | null
  plan_handle: string | null
  sql_handle: string | null
  statement_start_offset: number | null
  statement_end_offset: number | null
  digest: string | null
  rows_examined: number | null
  rows_sent: number | null
  no_index_used: number | null
  no_good_index_used: number | null
  temp_disk_tables: number | null
  diagnostics: string[]
}

export interface TopSqlResponse {
  connection_id: string
  engine: DatabaseEngine
  source: string
  available: boolean
  items: TopSqlItem[]
  warnings: string[]
  checked_at: string
}

export interface SqlPlanStep {
  id: number | null
  parent_id: number | null
  operation: string | null
  options: string | null
  object_owner: string | null
  object_name: string | null
  cost: number | null
  cardinality: number | null
  bytes: number | null
  access_predicates: string | null
  filter_predicates: string | null
  extra: Record<string, unknown>
}

export interface SqlPlanResponse {
  connection_id: string
  engine: DatabaseEngine
  source: string
  available: boolean
  plan_text: string | null
  steps: SqlPlanStep[]
  diagnostics: string[]
  warnings: string[]
  checked_at: string
}

export interface SqlPlanRequest {
  sql_id?: string | null
  child_number?: number | null
  plan_handle?: string | null
  sql_text?: string | null
}

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL

async function apiRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    credentials: 'include',
    ...init,
    headers: init?.body ? { 'Content-Type': 'application/json', ...(init.headers ?? {}) } : init?.headers,
  })
  if (!response.ok) {
    const payload = await response.json().catch(() => null)
    throw new Error(payload?.error?.message ?? `Request failed with status ${response.status}`)
  }
  return response.json()
}

export const useDatabasePerformanceStore = defineStore('databasePerformance', {
  state: () => ({
    topSql: {} as Record<string, TopSqlResponse>,
    plans: {} as Record<string, SqlPlanResponse>,
    loadingTopSql: {} as Record<string, boolean>,
    loadingPlan: {} as Record<string, boolean>,
    errors: {} as Record<string, string | null>,
  }),
  actions: {
    async loadTopSql(connectionId: string, limit = 20) {
      this.loadingTopSql[connectionId] = true
      this.errors[connectionId] = null
      try {
        const result = await apiRequest<TopSqlResponse>(`/databases/${connectionId}/performance/top-sql?limit=${limit}`)
        this.topSql[connectionId] = result
        return result
      } catch (error) {
        this.errors[connectionId] = error instanceof Error ? error.message : 'Unable to load Top SQL.'
        throw error
      } finally {
        this.loadingTopSql[connectionId] = false
      }
    },

    async loadPlan(connectionId: string, request: SqlPlanRequest, cacheKey = 'selected') {
      this.loadingPlan[connectionId] = true
      this.errors[connectionId] = null
      try {
        const result = await apiRequest<SqlPlanResponse>(`/databases/${connectionId}/performance/plan`, {
          method: 'POST',
          body: JSON.stringify(request),
        })
        this.plans[`${connectionId}:${cacheKey}`] = result
        return result
      } catch (error) {
        this.errors[connectionId] = error instanceof Error ? error.message : 'Unable to load SQL plan.'
        throw error
      } finally {
        this.loadingPlan[connectionId] = false
      }
    },
  },
})
