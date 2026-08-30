import { defineStore } from 'pinia'

export type AlertSeverity = 'warning' | 'critical'
export type AlertStatus = 'active' | 'resolved'
export type AlertSourceType = 'database' | 'server' | 'collector'

export interface AlertItem {
  id: string
  alert_key: string
  source_type: AlertSourceType
  source_id: string
  source_name: string
  rule_key: string
  severity: AlertSeverity
  status: AlertStatus
  title: string
  message: string
  first_seen_at: string
  last_seen_at: string
  resolved_at: string | null
  current_value: number | string | null
  threshold: number | string | null
  context: Record<string, unknown>
}

export interface AlertSummary {
  active: number
  warning: number
  critical: number
  resolved: number
}

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL

async function apiRequest<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
  })

  if (!response.ok) {
    const body = await response.json().catch(() => null)
    throw new Error(
      body?.error?.message ?? `Request failed with status ${response.status}`,
    )
  }

  if (response.status === 204) return undefined as T
  return response.json()
}

export const useAlertsStore = defineStore('alerts', {
  state: () => ({
    items: [] as AlertItem[],
    summary: {
      active: 0,
      warning: 0,
      critical: 0,
      resolved: 0,
    } as AlertSummary,
    loading: false,
    error: null as string | null,
  }),

  actions: {
    async load(status: 'active' | 'resolved' | 'all' = 'active', severity: '' | AlertSeverity = '') {
      this.loading = true
      this.error = null
      try {
        const query = new URLSearchParams({ status })
        if (severity) query.set('severity', severity)
        this.items = await apiRequest<AlertItem[]>(`/alerts?${query.toString()}`)
        return this.items
      } catch (error) {
        this.error = error instanceof Error ? error.message : 'Unable to load alerts.'
        throw error
      } finally {
        this.loading = false
      }
    },

    async loadSummary() {
      try {
        this.summary = await apiRequest<AlertSummary>('/alerts/summary')
        return this.summary
      } catch {
        // Summary is supplemental UI. Do not replace the page with an error if
        // the API is temporarily unavailable.
        return this.summary
      }
    },

    async clear(id: string) {
      await apiRequest<{ cleared: boolean; suppressed_until_recovery: boolean }>(
        `/alerts/${id}`,
        { method: 'DELETE' },
      )
      this.items = this.items.filter((item) => item.id !== id)
      await this.loadSummary()
    },

    async clearResolved() {
      await apiRequest<{ cleared: number }>('/alerts/resolved', { method: 'DELETE' })
      this.items = this.items.filter((item) => item.status !== 'resolved')
      await this.loadSummary()
    },
  },
})
