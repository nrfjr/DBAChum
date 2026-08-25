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
  match_columns: string[]
}

export interface ProvisioningProfileInput {
  name: string
  description: string | null
  schema_connection_id: string
  ldap_enabled: boolean
  ldap_profile_id: string | null
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


export interface ProvisioningPreviewInput {
  username: string | null
  password: string
  first_name: string | null
  middle_name: string | null
  last_name: string | null
  employee_id: string | null
  reference_user: string | null
  requestor: string | null
  request_reference: string | null
  remarks: string | null
}

export interface ProvisioningPreviewRole {
  name: string
  sensitive: boolean
  will_copy: boolean
}

export interface ProvisioningPreviewColumn {
  column_name: string
  source: string
  display_value: string | null
  sensitive: boolean
  expression: boolean
}

export interface ProvisioningPreviewTableStep {
  index: number
  name: string
  connection_id: string
  connection_name: string
  owner: string
  table_name: string
  match_columns: string[]
  match_values: Record<string, string | null>
  existing_rows: number
  planned_action: 'insert' | 'update' | 'conflict'
  columns: ProvisioningPreviewColumn[]
}

export interface ProvisioningPreviewLdap {
  enabled: boolean
  profile_id: string | null
  profile_name: string | null
  filename: string | null
  template_valid: boolean
}

export interface ProvisioningPreviewResult {
  dry_run: boolean
  ready_to_execute: boolean
  profile_id: string
  profile_name: string
  schema_connection_id: string
  schema_connection_name: string
  username: string
  account_exists: boolean
  account_action: 'create' | 'alter'
  requester_ip: string | null
  operator_username: string
  generated_at: string
  reference_user: string | null
  default_tablespace: string | null
  temporary_tablespace: string | null
  oracle_profile: string | null
  roles: ProvisioningPreviewRole[]
  table_steps: ProvisioningPreviewTableStep[]
  ldap: ProvisioningPreviewLdap
  warnings: string[]
}


export interface ProvisioningExecuteInput extends ProvisioningPreviewInput {
  roles: string[]
  default_tablespace: string | null
  temporary_tablespace: string | null
  oracle_profile: string | null
}

export interface ProvisioningExecutionAccount {
  action: 'created' | 'altered' | 'unchanged' | 'failed'
  password_applied: boolean
  default_tablespace: string | null
  temporary_tablespace: string | null
  oracle_profile: string | null
  error: string | null
}

export interface ProvisioningExecutionRole {
  name: string
  action: 'granted' | 'already_present'
}

export interface ProvisioningExecutionTableStep {
  index: number
  name: string
  connection_id: string
  connection_name: string
  owner: string
  table_name: string
  action: 'inserted' | 'updated' | 'unchanged' | 'conflict' | 'failed' | 'not_run'
  match_values: Record<string, string | null>
  generated_values: Record<string, string | number | null>
  error: string | null
}

export interface ProvisioningExecutionLdap {
  enabled: boolean
  action: 'generated' | 'not_run' | 'failed' | null
  profile_id: string | null
  profile_name: string | null
  filename: string | null
  content: string | null
  dn: string | null
  error: string | null
}

export interface ProvisioningExecutionResult {
  run_id: string
  audit_id: string
  status: 'succeeded' | 'partial' | 'failed'
  username: string
  profile_id: string
  profile_name: string
  schema_connection_id: string
  schema_connection_name: string
  requester_ip: string | null
  account: ProvisioningExecutionAccount
  roles: ProvisioningExecutionRole[]
  table_steps: ProvisioningExecutionTableStep[]
  ldap: ProvisioningExecutionLdap
  error: string | null
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

export interface LdapProfileInput {
  name: string
  description: string | null
  enabled: boolean
  host: string
  port: number
  use_ssl: boolean
  base_dn: string
  bind_dn: string
  bind_password?: string
  ldif_template: string
}

export interface LdapProfile extends Omit<LdapProfileInput, 'bind_password'> {
  id: string
  configured: boolean
  has_bind_password: boolean
  migrated_from_legacy: boolean
  created_at: string | null
  updated_at: string | null
}

export interface LdapProfileTestResult {
  success: boolean
  connect_ok: boolean
  bind_ok: boolean
  base_dn_ok: boolean
  message: string
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
    profilesByConnection: {} as Record<string, ProvisioningProfile[]>,
    sources: [] as ProvisioningSourceOption[],
    ldapProfiles: [] as LdapProfile[],
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

    async loadProfilesForConnection(connectionId: string) {
      const profiles = await apiRequest<ProvisioningProfile[]>(
        `/databases/${connectionId}/oracle/provisioning-profiles`,
      )
      this.profilesByConnection[connectionId] = profiles
      return profiles
    },

    async previewForConnection(
      connectionId: string,
      profileId: string,
      data: ProvisioningPreviewInput,
    ) {
      return apiRequest<ProvisioningPreviewResult>(
        `/databases/${connectionId}/oracle/provisioning-profiles/${profileId}/preview`,
        { method: 'POST', body: JSON.stringify(data) },
      )
    },


    async executeForConnection(
      connectionId: string,
      profileId: string,
      data: ProvisioningExecuteInput,
    ) {
      return apiRequest<ProvisioningExecutionResult>(
        `/databases/${connectionId}/oracle/provisioning-profiles/${profileId}/execute`,
        { method: 'POST', body: JSON.stringify(data) },
      )
    },

    async loadLdapProfiles() {
      this.ldapProfiles = await apiRequest<LdapProfile[]>('/provisioning/ldap-profiles')
      return this.ldapProfiles
    },

    async createLdapProfile(data: LdapProfileInput) {
      this.saving = true
      try {
        const profile = await apiRequest<LdapProfile>('/provisioning/ldap-profiles', {
          method: 'POST',
          body: JSON.stringify(data),
        })
        this.ldapProfiles.push(profile)
        this.ldapProfiles.sort((a, b) => a.name.localeCompare(b.name))
        return profile
      } finally {
        this.saving = false
      }
    },

    async updateLdapProfile(id: string, data: LdapProfileInput) {
      this.saving = true
      try {
        const profile = await apiRequest<LdapProfile>(`/provisioning/ldap-profiles/${id}`, {
          method: 'PUT',
          body: JSON.stringify(data),
        })
        const index = this.ldapProfiles.findIndex((item) => item.id === id)
        if (index !== -1) this.ldapProfiles[index] = profile
        this.ldapProfiles.sort((a, b) => a.name.localeCompare(b.name))
        return profile
      } finally {
        this.saving = false
      }
    },

    async removeLdapProfile(id: string) {
      await apiRequest<void>(`/provisioning/ldap-profiles/${id}`, { method: 'DELETE' })
      this.ldapProfiles = this.ldapProfiles.filter((profile) => profile.id !== id)
    },

    async testLdapProfile(id: string) {
      return apiRequest<LdapProfileTestResult>(`/provisioning/ldap-profiles/${id}/test`, {
        method: 'POST',
      })
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
