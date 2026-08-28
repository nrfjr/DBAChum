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
  action: 'generated' | 'created' | 'already_present' | 'not_run' | 'failed' | null
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

export interface ProvisioningRunSummary {
  run_id: string
  status: 'succeeded' | 'partial' | 'failed' | 'running'
  username: string
  employee_id: string | null
  profile_id: string
  profile_name: string
  operator_username: string
  request_reference: string | null
  started_at: string
  completed_at: string | null
  retry_count: number
  retryable: boolean
  password_required: boolean
}

export interface ProvisioningRetryRequirement {
  retryable: boolean
  password_required: boolean
  pending: string[]
  reason: string | null
}

export interface ProvisioningDeprovisionPreviewItem {
  component: 'account' | 'role' | 'table' | 'ldap'
  label: string
  planned_action: string
  safe_to_reverse: boolean
  state: 'candidate' | 'blocked' | 'no_action' | 'already_absent'
  reason: string
}

export interface ProvisioningDeprovisionPreview {
  run_id: string
  username: string
  generated_at: string
  destructive_execution_enabled: boolean
  items: ProvisioningDeprovisionPreviewItem[]
  safe_candidate_count: number
  blocked_count: number
  warnings: string[]
}

export interface OracleUserDeprovisionPreviewItem {
  component: 'account' | 'table' | 'ldap' | 'ldap' | 'history'
  label: string
  planned_action: string
  state: 'candidate' | 'blocked' | 'no_action' | 'already_absent'
  reason: string
  profile_id: string | null
  profile_name: string | null
  step_index: number | null
  connection_id: string | null
  owner: string | null
  table_name: string | null
  match_values: Record<string, string | null>
  existing_rows: number
  ldap_profile_id: string | null
  ldap_dn: string | null
}

export interface OracleUserDeprovisionPreview {
  username: string
  generated_at: string
  account_exists: boolean
  account_status: string | null
  protected_account: boolean
  owned_object_count: number
  drop_cascade: boolean
  lifecycle_run_count: number
  linked_row_count: number
  linked_ldap_count: number
  blocked_count: number
  execution_ready: boolean
  confirmation_text: string
  items: OracleUserDeprovisionPreviewItem[]
  warnings: string[]
  blocked_reasons: string[]
}

export interface OracleUserDeprovisionExecutionItem {
  component: 'account' | 'table' | 'ldap'
  label: string
  status: 'succeeded' | 'failed'
  affected_rows: number
  error: string | null
}

export interface OracleUserDeprovisionResult {
  audit_id: string
  status: 'succeeded' | 'partial' | 'failed'
  username: string
  account_dropped: boolean
  deleted_provisioning_rows: number
  deleted_ldap_entries: number
  items: OracleUserDeprovisionExecutionItem[]
  error: string | null
}


export interface BulkProvisionImportRow {
  row_number: number
  employee_id: string
  first_name: string
  middle_name: string | null
  last_name: string
  reference_user: string | null
  password: string
  password_mode: 'generated' | 'provided'
  username: string | null
  valid: boolean
  errors: Record<string, string>
}

export interface BulkProvisionImportResult {
  filename: string
  required_headers: string[]
  optional_headers: string[]
  row_count: number
  valid_count: number
  invalid_count: number
  rows: BulkProvisionImportRow[]
}

export interface BulkProvisionRowInput {
  row_number: number
  password_mode: 'generated' | 'provided'
  employee_id: string
  first_name: string
  middle_name: string | null
  last_name: string
  reference_user: string | null
  password: string
}

export interface BulkProvisionRequest {
  profile_id: string | null
  use_common_reference: boolean
  common_reference_user: string | null
  requestor: string | null
  request_reference: string | null
  remarks: string | null
  rows: BulkProvisionRowInput[]
}

export interface BulkProvisionPreviewRow {
  row_number: number
  employee_id: string
  first_name: string
  middle_name: string | null
  last_name: string
  username: string | null
  reference_user: string | null
  password_mode: 'generated' | 'provided'
  valid: boolean
  errors: Record<string, string>
  roles: string[]
  provisioning: ProvisioningPreviewResult | null
}

export interface BulkProvisionPreviewResult {
  ready_to_execute: boolean
  row_count: number
  valid_count: number
  invalid_count: number
  profile_id: string | null
  profile_name: string | null
  rows: BulkProvisionPreviewRow[]
}

export interface BulkProvisionExecutionRow {
  row_number: number
  username: string | null
  status: 'succeeded' | 'partial' | 'failed'
  run_id: string | null
  audit_id: string | null
  error: string | null
}

export interface BulkProvisionExecutionResult {
  status: 'succeeded' | 'partial' | 'failed'
  row_count: number
  succeeded_count: number
  partial_count: number
  failed_count: number
  rows: BulkProvisionExecutionRow[]
}

export interface BulkProvisionExportRow {
  row: number
  employee_id: string
  first_name: string
  middle_name: string
  last_name: string
  username: string
  initial_password: string
  status: string
  run_or_audit: string
  error: string
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

async function apiFormRequest<T>(path: string, form: FormData): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: 'POST',
    credentials: 'include',
    body: form,
  })

  if (!response.ok) {
    const body = await response.json().catch(() => null)
    throw new Error(
      body?.error?.message ??
        `Request failed with status ${response.status}`,
    )
  }

  return response.json() as Promise<T>
}

async function apiBlobRequest(path: string, options: RequestInit = {}): Promise<Blob> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    credentials: 'include',
    headers: {
      ...(options.body ? { 'Content-Type': 'application/json' } : {}),
      ...options.headers,
    },
  })
  if (!response.ok) {
    const body = await response.json().catch(() => null)
    throw new Error(body?.error?.message ?? `Request failed with status ${response.status}`)
  }
  return response.blob()
}


export const useProvisioningStore = defineStore('provisioning', {
  state: () => ({
    profiles: [] as ProvisioningProfile[],
    profilesByConnection: {} as Record<string, ProvisioningProfile[]>,
    sources: [] as ProvisioningSourceOption[],
    runsByConnection: {} as Record<string, ProvisioningRunSummary[]>,
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

    async downloadBulkTemplateXlsx(connectionId: string) {
      return apiBlobRequest(`/databases/${connectionId}/oracle/bulk-provision/template.xlsx`)
    },

    async exportBulkResultsXlsx(connectionId: string, rows: BulkProvisionExportRow[]) {
      return apiBlobRequest(`/databases/${connectionId}/oracle/bulk-provision/results.xlsx`, {
        method: 'POST',
        body: JSON.stringify({ rows }),
      })
    },

    async importBulkFile(connectionId: string, file: File) {
      const form = new FormData()
      form.append('file', file)
      return apiFormRequest<BulkProvisionImportResult>(
        `/databases/${connectionId}/oracle/bulk-provision/import`,
        form,
      )
    },

    async previewBulk(connectionId: string, data: BulkProvisionRequest) {
      return apiRequest<BulkProvisionPreviewResult>(
        `/databases/${connectionId}/oracle/bulk-provision/preview`,
        { method: 'POST', body: JSON.stringify(data) },
      )
    },

    async executeBulk(connectionId: string, data: BulkProvisionRequest) {
      return apiRequest<BulkProvisionExecutionResult>(
        `/databases/${connectionId}/oracle/bulk-provision/execute`,
        { method: 'POST', body: JSON.stringify(data) },
      )
    },

    async loadRunsForConnection(connectionId: string) {
      const runs = await apiRequest<ProvisioningRunSummary[]>(
        `/databases/${connectionId}/oracle/provisioning-runs`,
      )
      this.runsByConnection[connectionId] = runs
      return runs
    },

    async retryRun(
      connectionId: string,
      runId: string,
      password: string | null = null,
    ) {
      const result = await apiRequest<ProvisioningExecutionResult>(
        `/databases/${connectionId}/oracle/provisioning-runs/${runId}/retry`,
        {
          method: 'POST',
          body: JSON.stringify({ password }),
        },
      )
      await this.loadRunsForConnection(connectionId)
      return result
    },

    async loadDeprovisionPreview(connectionId: string, runId: string) {
      return apiRequest<ProvisioningDeprovisionPreview>(
        `/databases/${connectionId}/oracle/provisioning-runs/${runId}/deprovision-preview`,
      )
    },

    async previewOracleUserDeprovision(connectionId: string, username: string) {
      return apiRequest<OracleUserDeprovisionPreview>(
        `/databases/${connectionId}/oracle/users/${encodeURIComponent(username)}/deprovision-preview`,
      )
    },

    async executeOracleUserDeprovision(
      connectionId: string,
      username: string,
      confirmation: string,
      requestReference: string | null = null,
    ) {
      return apiRequest<OracleUserDeprovisionResult>(
        `/databases/${connectionId}/oracle/users/${encodeURIComponent(username)}/deprovision`,
        {
          method: 'POST',
          body: JSON.stringify({
            confirmation,
            request_reference: requestReference,
          }),
        },
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
