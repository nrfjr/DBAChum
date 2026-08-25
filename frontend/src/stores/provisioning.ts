import { defineStore } from 'pinia'

export type ProvisioningValueKind =
  | 'form'
  | 'generated'
  | 'sequence'
  | 'custom'
  | 'null'
  | 'omit'

export interface ProvisioningColumnMapping {
  column_name: string
  value_kind: ProvisioningValueKind
  value_key: string | null
  custom_value: string | null
}

export interface ProvisioningTableStep {
  name: string
  connection_id: string
  owner: string
  table_name: string
  mappings: ProvisioningColumnMapping[]
}

export interface ProvisioningProfileInput {
  name: string
  description: string | null
  schema_connection_id: string
  ldap_enabled: boolean
  enabled: boolean
  table_steps: ProvisioningTableStep[]
}

export interface ProvisioningProfile extends ProvisioningProfileInput {
  id: string
  ready: boolean
  issues: string[]
  created_at: string
  updated_at: string
}

export interface ProvisioningSourceOption {
  key: string
  label: string
  kind: 'form' | 'generated'
}

export interface OracleMetadataSchema {
  name: string
}

export interface OracleMetadataTable {
  owner: string
  name: string
}

export interface OracleMetadataSequence {
  owner: string
  name: string
}

export interface OracleMetadataColumn {
  name: string
  data_type: string
  data_length: number | null
  nullable: boolean
  data_default: string | null
  column_id: number
}

export interface LdapSettings {
  configured: boolean
  enabled: boolean
  host: string
  port: number
  use_ssl: boolean
  base_dn: string
  bind_dn: string
  has_bind_password: boolean
  ldif_template: string
  updated_at: string | null
}

export interface LdapSettingsInput {
  enabled: boolean
  host: string
  port: number
  use_ssl: boolean
  base_dn: string
  bind_dn: string
  bind_password?: string
  ldif_template: string
}

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL

async function apiRequest<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
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
      body?.error?.message ??
        `Request failed with status ${response.status}`,
    )
  }

  if (response.status === 204) {
    return undefined as T
  }

  return response.json()
}

export const useProvisioningStore = defineStore('provisioning', {
  state: () => ({
    profiles: [] as ProvisioningProfile[],
    sources: [] as ProvisioningSourceOption[],
    ldap: null as LdapSettings | null,
    loading: false,
    saving: false,
    error: null as string | null,
  }),

  actions: {
    async loadProfiles() {
      this.loading = true
      this.error = null
      try {
        this.profiles = await apiRequest<ProvisioningProfile[]>(
          '/provisioning/profiles',
        )
      } catch (error) {
        this.error = error instanceof Error
          ? error.message
          : 'Unable to load provisioning profiles.'
      } finally {
        this.loading = false
      }
    },

    async loadSources() {
      this.sources = await apiRequest<ProvisioningSourceOption[]>(
        '/provisioning/sources',
      )
    },

    async createProfile(data: ProvisioningProfileInput) {
      this.saving = true
      try {
        const profile = await apiRequest<ProvisioningProfile>(
          '/provisioning/profiles',
          { method: 'POST', body: JSON.stringify(data) },
        )
        this.profiles.push(profile)
        this.profiles.sort((a, b) => a.name.localeCompare(b.name))
        return profile
      } finally {
        this.saving = false
      }
    },

    async updateProfile(id: string, data: ProvisioningProfileInput) {
      this.saving = true
      try {
        const profile = await apiRequest<ProvisioningProfile>(
          `/provisioning/profiles/${id}`,
          { method: 'PUT', body: JSON.stringify(data) },
        )
        const index = this.profiles.findIndex((item) => item.id === id)
        if (index !== -1) this.profiles[index] = profile
        this.profiles.sort((a, b) => a.name.localeCompare(b.name))
        return profile
      } finally {
        this.saving = false
      }
    },

    async removeProfile(id: string) {
      await apiRequest<void>(`/provisioning/profiles/${id}`, {
        method: 'DELETE',
      })
      this.profiles = this.profiles.filter((profile) => profile.id !== id)
    },

    async loadLdap() {
      this.ldap = await apiRequest<LdapSettings>('/provisioning/ldap')
      return this.ldap
    },

    async saveLdap(data: LdapSettingsInput) {
      this.saving = true
      try {
        this.ldap = await apiRequest<LdapSettings>(
          '/provisioning/ldap',
          { method: 'PUT', body: JSON.stringify(data) },
        )
        return this.ldap
      } finally {
        this.saving = false
      }
    },

    async schemas(connectionId: string) {
      return apiRequest<OracleMetadataSchema[]>(
        `/provisioning/oracle/${connectionId}/schemas`,
      )
    },

    async tables(connectionId: string, owner: string) {
      return apiRequest<OracleMetadataTable[]>(
        `/provisioning/oracle/${connectionId}/schemas/${encodeURIComponent(owner)}/tables`,
      )
    },

    async sequences(connectionId: string, owner: string) {
      return apiRequest<OracleMetadataSequence[]>(
        `/provisioning/oracle/${connectionId}/schemas/${encodeURIComponent(owner)}/sequences`,
      )
    },

    async columns(connectionId: string, owner: string, tableName: string) {
      return apiRequest<OracleMetadataColumn[]>(
        `/provisioning/oracle/${connectionId}/schemas/${encodeURIComponent(owner)}`
          + `/tables/${encodeURIComponent(tableName)}/columns`,
      )
    },
  },
})
