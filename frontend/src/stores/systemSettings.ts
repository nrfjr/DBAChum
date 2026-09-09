import { defineStore } from 'pinia'

export interface BrandingSettings {
  installation_name: string
  has_logo: boolean
  logo_version: string | null
}

export interface GeneralSettings {
  installation_name: string
  default_page_size: 10 | 25 | 50 | 100
  default_analytics_months: number
  environment: string
  app_version: string
  api_docs_enabled: boolean
}

export interface MonitoringSettings {
  enabled: boolean
  database_interval_seconds: number
  server_interval_seconds: number
  storage_interval_seconds: number
  analytics_snapshot_interval_seconds: number
  target_timeout_seconds: number
  concurrency: number
  stale_threshold_seconds: number
  telemetry_retention_hours: number
  collector: Record<string, unknown>
}

export interface DataCollectionStats {
  name: string
  count: number
  size_bytes: number | null
  storage_bytes: number | null
  index_bytes: number | null
}

export interface DataSettings {
  analytics_retention_days: number
  action_audit_retention_days: number
  terminal_audit_retention_days: number
  provisioning_history_retention_days: number
  telemetry_retention_hours: number
  collections: DataCollectionStats[]
}

export interface MaintenanceDiagnostics {
  generated_at: string
  mongodb_ok: boolean
  collection_count: number
  collector: Record<string, unknown>
  orphaned_analytics: number
  stale_terminal_sessions: number
  retention: Record<string, number>
}

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers)
  if (options.body && !(options.body instanceof FormData)) {
    headers.set('Content-Type', 'application/json')
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    credentials: 'include',
    headers,
  })

  if (!response.ok) {
    const body = await response.json().catch(() => null)
    throw new Error(body?.error?.message ?? `Request failed with status ${response.status}`)
  }

  return response.json()
}

export const useSystemSettingsStore = defineStore('systemSettings', {
  state: () => ({
    branding: null as BrandingSettings | null,
    general: null as GeneralSettings | null,
    monitoring: null as MonitoringSettings | null,
    data: null as DataSettings | null,
    maintenance: null as MaintenanceDiagnostics | null,
    loading: false,
    error: null as string | null,
  }),

  getters: {
    brandingLogoUrl: (state) => {
      if (!state.branding?.has_logo) return null
      const version = encodeURIComponent(state.branding.logo_version ?? 'current')
      return `${API_BASE_URL}/branding/logo?v=${version}`
    },
  },

  actions: {
    async loadBranding() {
      this.branding = await request<BrandingSettings>('/branding')
      return this.branding
    },
    async loadGeneral() {
      this.general = await request<GeneralSettings>('/settings/general')
      return this.general
    },
    async saveGeneral(payload: Pick<GeneralSettings, 'installation_name' | 'default_page_size' | 'default_analytics_months'>) {
      this.general = await request<GeneralSettings>('/settings/general', {
        method: 'PATCH',
        body: JSON.stringify(payload),
      })
      if (this.branding) this.branding.installation_name = this.general.installation_name
      return this.general
    },
    async uploadLogo(file: File) {
      const body = new FormData()
      body.append('file', file)
      this.branding = await request<BrandingSettings>('/settings/general/logo', {
        method: 'PUT',
        body,
      })
      return this.branding
    },
    async removeLogo() {
      this.branding = await request<BrandingSettings>('/settings/general/logo', {
        method: 'DELETE',
      })
      return this.branding
    },
    async loadMonitoring() {
      this.monitoring = await request<MonitoringSettings>('/settings/monitoring')
      return this.monitoring
    },
    async saveMonitoring(payload: Omit<MonitoringSettings, 'telemetry_retention_hours' | 'collector'>) {
      this.monitoring = await request<MonitoringSettings>('/settings/monitoring', {
        method: 'PATCH',
        body: JSON.stringify(payload),
      })
      return this.monitoring
    },
    async loadData() {
      this.data = await request<DataSettings>('/settings/data')
      return this.data
    },
    async saveData(payload: Pick<DataSettings, 'analytics_retention_days' | 'action_audit_retention_days' | 'terminal_audit_retention_days' | 'provisioning_history_retention_days'>) {
      this.data = await request<DataSettings>('/settings/data', {
        method: 'PATCH',
        body: JSON.stringify(payload),
      })
      return this.data
    },
    async loadMaintenance() {
      this.maintenance = await request<MaintenanceDiagnostics>('/settings/maintenance')
      return this.maintenance
    },
    async cleanup(payload = { apply_retention: true, remove_orphaned_analytics: true, reconcile_stale_terminal_sessions: true }) {
      return request<{
        retention_deleted: Record<string, number>
        orphaned_analytics_deleted: number
        stale_terminal_sessions_reconciled: number
      }>('/settings/maintenance/cleanup', {
        method: 'POST',
        body: JSON.stringify(payload),
      })
    },
    async verifyIndexes() {
      return request<{ verified_at: string; message: string }>('/settings/maintenance/indexes/verify', {
        method: 'POST',
      })
    },
    async exportMetadata() {
      return request<Record<string, unknown>>('/settings/data/export')
    },
  },
})
