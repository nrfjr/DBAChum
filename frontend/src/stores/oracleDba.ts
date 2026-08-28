import { defineStore } from 'pinia'

export interface OracleSession {
  sid: number
  serial_number: number

  username: string | null
  status: string

  os_user: string | null
  machine: string | null
  program: string | null
  module: string | null

  sql_id: string | null
  sql_exec_start: string | null

  event: string | null
  wait_class: string | null

  blocking_instance: number | null
  blocking_session: number | null

  state_seconds: number
  logon_time: string | null
}

export interface OracleSessionsResponse {
  available: boolean

  total: number
  active: number
  blocked: number
  long_running: number

  long_running_threshold_seconds: number

  items: OracleSession[]

  warning: string | null
  checked_at: string
}

export interface OracleTablespace {
  name: string
  contents: string
  status: string

  used_bytes: number
  capacity_bytes: number

  used_percent: number
}

export interface OracleFra {
  destination: string | null

  limit_bytes: number
  used_bytes: number
  reclaimable_bytes: number

  number_of_files: number

  used_percent: number | null
}

export interface OracleStorageResponse {
  tablespaces_available: boolean
  fra_available: boolean

  tablespaces: OracleTablespace[]
  fra: OracleFra | null

  warnings: string[]
  checked_at: string
}

export interface OracleActiveSql {
  sid: number
  serial_number: number

  username: string | null

  sql_id: string
  sql_exec_start: string | null

  active_seconds: number

  module: string | null
  machine: string | null

  event: string | null
  wait_class: string | null

  sql_text: string | null
}

export interface OracleActivityResponse {
  available: boolean
  items: OracleActiveSql[]

  warning: string | null
  checked_at: string
}

export interface OracleDatabaseUser {
  username: string
  status: string

  default_tablespace: string | null
  temporary_tablespace: string | null
  profile: string | null

  created_at: string | null
  lock_date: string | null
  expiry_date: string | null
}

export interface OracleUsernameAvailability {
  username: string
  available: boolean
  message: string | null
}

export interface OracleDatabaseUsersResponse {
  available: boolean

  total: number
  open: number
  locked: number
  expired: number

  items: OracleDatabaseUser[]

  warning: string | null
  checked_at: string
}

export interface OracleReferenceRole {
  name: string
  admin_option: boolean
  default_role: boolean
  sensitive: boolean
}

export interface OracleReferenceSystemPrivilege {
  name: string
  admin_option: boolean
}

export interface OracleReferenceUser {
  username: string
  status: string
  default_tablespace: string | null
  temporary_tablespace: string | null
  profile: string | null
  roles: OracleReferenceRole[]
  system_privileges: OracleReferenceSystemPrivilege[]
  warnings: string[]
}


export interface OracleManageableRole {
  name: string
  sensitive: boolean
}

export interface OracleUserLifecycleState {
  username: string
  status: string
  locked: boolean
  expired: boolean
  default_tablespace: string | null
  temporary_tablespace: string | null
  profile: string | null
  created_at: string | null
  lock_date: string | null
  expiry_date: string | null
  roles: OracleReferenceRole[]
  system_privileges: OracleReferenceSystemPrivilege[]
  available_roles: OracleManageableRole[]
  warnings: string[]
}

export interface OracleAccessGrantSource {
  kind: 'direct' | 'role' | 'public' | string
  via: string[]
  admin_option: boolean
  default_role: boolean | null
  grantable: boolean | null
}

export interface OracleAccessRole {
  name: string
  sources: OracleAccessGrantSource[]
  sensitive: boolean
  powerful: boolean
}

export interface OracleAccessSystemPrivilege {
  name: string
  sources: OracleAccessGrantSource[]
  powerful: boolean
}

export interface OracleAccessObjectPrivilege {
  owner: string
  object_name: string
  privilege: string
  column_name: string | null
  sources: OracleAccessGrantSource[]
}

export interface OracleAccessFinding {
  kind: string
  name: string
  source: string
  reason: string
}

export interface OracleUserAccessInspector {
  username: string
  status: string
  default_tablespace: string | null
  temporary_tablespace: string | null
  profile: string | null
  created_at: string | null
  lock_date: string | null
  expiry_date: string | null
  roles: OracleAccessRole[]
  system_privileges: OracleAccessSystemPrivilege[]
  object_privileges: OracleAccessObjectPrivilege[]
  administrative_privileges: string[]
  powerful_findings: OracleAccessFinding[]
  warnings: string[]
  checked_at: string
}

export interface OracleAccessLookupMatch {
  username: string
  status: string
  basis: string
  privilege: string | null
  column_name: string | null
  source: OracleAccessGrantSource
  powerful: boolean
}

export interface OracleAccessLookupResult {
  lookup_type: 'role' | 'system_privilege' | 'object' | string
  target: string
  target_exists: boolean
  object_type: string | null
  matches: OracleAccessLookupMatch[]
  unique_user_count: number
  public_access: boolean
  public_details: string[]
  powerful: boolean
  warnings: string[]
  checked_at: string
}

export interface OracleAccessLookupInput {
  kind: 'role' | 'system_privilege' | 'object'
  value?: string
  owner?: string
  object_name?: string
  privilege?: string
}

export interface OracleAccessCompareUser {
  username: string
  status: string
  profile: string | null
  default_tablespace: string | null
  temporary_tablespace: string | null
}

export interface OracleAccessCompareItem {
  key: string
  label: string
  powerful: boolean
  left_sources: OracleAccessGrantSource[]
  right_sources: OracleAccessGrantSource[]
}

export interface OracleAccessCompareCategory {
  common: OracleAccessCompareItem[]
  left_only: OracleAccessCompareItem[]
  right_only: OracleAccessCompareItem[]
}

export interface OracleAccessCompareResult {
  left: OracleAccessCompareUser
  right: OracleAccessCompareUser
  roles: OracleAccessCompareCategory
  system_privileges: OracleAccessCompareCategory
  object_privileges: OracleAccessCompareCategory
  administrative_privileges: OracleAccessCompareCategory
  common_count: number
  left_only_count: number
  right_only_count: number
  warnings: string[]
  checked_at: string
}

export interface OracleRoleSummary {
  name: string
  password_required: boolean
  oracle_maintained: boolean
  protected: boolean
  powerful: boolean
  manageable: boolean
  member_count: number
  child_role_count: number
  system_privilege_count: number
  object_privilege_count: number
}

export interface OracleRoleListResult {
  roles: OracleRoleSummary[]
  system_privileges_catalog: string[]
  object_privileges_catalog: string[]
  warnings: string[]
  checked_at: string
}

export interface OracleRoleMember {
  username: string
  status: string
  admin_option: boolean
  default_role: boolean
  protected: boolean
}

export interface OracleRoleChild {
  name: string
  admin_option: boolean
  protected: boolean
  powerful: boolean
  manageable: boolean
}

export interface OracleRoleSystemPrivilege {
  name: string
  admin_option: boolean
  powerful: boolean
}

export interface OracleRoleObjectPrivilege {
  owner: string
  object_name: string
  privilege: string
  column_name: string | null
  grantable: boolean
}

export interface OracleRoleDetail extends Omit<OracleRoleSummary, 'member_count' | 'child_role_count' | 'system_privilege_count' | 'object_privilege_count'> {
  members: OracleRoleMember[]
  parent_roles: { name: string; admin_option: boolean }[]
  child_roles: OracleRoleChild[]
  system_privileges: OracleRoleSystemPrivilege[]
  object_privileges: OracleRoleObjectPrivilege[]
  warnings: string[]
  checked_at: string
}

export type OracleRoleOperation =
  | 'grant_to_user'
  | 'revoke_from_user'
  | 'grant_child_role'
  | 'revoke_child_role'
  | 'grant_system_privilege'
  | 'revoke_system_privilege'
  | 'grant_object_privilege'
  | 'revoke_object_privilege'

export interface OracleRoleChangeInput {
  operation: OracleRoleOperation
  value?: string | null
  username?: string | null
  owner?: string | null
  object_name?: string | null
  privilege?: string | null
  request_reference?: string | null
}

export interface OracleRoleChangePreview {
  operation: string
  role_name: string
  target: string
  statement: string
  ready_to_execute: boolean
  powerful: boolean
  warnings: string[]
  generated_at: string | null
}

export interface OracleRoleActionResult {
  audit_id: string
  status: string
  role: OracleRoleDetail
}

export interface OracleRoleDropPreview {
  role: OracleRoleDetail
  statement: string
  ready_to_execute: boolean
  warnings: string[]
}

export interface OracleRoleDropResult {
  audit_id: string
  status: string
  role_name: string
}

export interface OracleUserEditInput {
  roles: string[]
  default_tablespace: string | null
  temporary_tablespace: string | null
  profile: string | null
  locked: boolean
}

export interface OracleUserEditPreviewItem {
  component: string
  action: string
  label: string
  before: string | null
  after: string | null
  sensitive: boolean
}

export interface OracleUserEditPreview {
  username: string
  generated_at: string
  ready_to_execute: boolean
  changes: OracleUserEditPreviewItem[]
  warnings: string[]
}

export interface OracleUserEditResult {
  audit_id: string
  status: string
  username: string
  changes_applied: number
  after: OracleUserLifecycleState
  error: string | null
}

export interface OracleUserLifecycleActionResult {
  audit_id: string
  status: string
  username: string
  action: string
  after: OracleUserLifecycleState
  error: string | null
}

export interface OracleCreateUserInput {
  username: string
  password: string
  reference_username: string | null
  roles: string[]
  default_tablespace: string | null
  temporary_tablespace: string | null
  profile: string | null
  request_reference: string | null
  requestor_name: string | null
  remarks: string | null
  first_name: string | null
  middle_name: string | null
  last_name: string | null
  employee_id: string | null
  generate_ldif: boolean
  ldap_profile_id: string | null
}

export interface OracleCreateUserResult {
  username: string
  roles_applied: string[]
  audit_id: string
  status: string
  requester_ip: string | null
  ldif_filename: string | null
  ldif_content: string | null
}


const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL


async function apiRequest<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const response = await fetch(
    `${API_BASE_URL}${path}`,
    {
      ...options,
      credentials: 'include',
      headers: {
        'Content-Type': 'application/json',
        ...options.headers,
      },
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


export const useOracleDbaStore =
  defineStore('oracleDba', {
    state: () => ({
      sessions: {} as Record<
        string,
        OracleSessionsResponse
      >,

      storage: {} as Record<
        string,
        OracleStorageResponse
      >,

      activity: {} as Record<
        string,
        OracleActivityResponse
      >,

      users: {} as Record<
        string,
        OracleDatabaseUsersResponse
      >,

      references: {} as Record<
        string,
        OracleReferenceUser
      >,

      loadingSessions: false,
      loadingStorage: false,
      loadingActivity: false,
      loadingUsers: false,
      loadingReference: false,
      creatingUser: false,

      sessionsError: null as string | null,
      storageError: null as string | null,
      activityError: null as string | null,
      usersError: null as string | null,
      referenceError: null as string | null,
      createUserError: null as string | null,
    }),

    actions: {
      async loadSessions(id: string) {
        this.loadingSessions = true
        this.sessionsError = null

        try {
          this.sessions[id] =
            await apiRequest<OracleSessionsResponse>(
              `/databases/${id}/oracle/sessions`,
            )
        } catch (error) {
          this.sessionsError =
            error instanceof Error
              ? error.message
              : 'Unable to load Oracle sessions.'
        } finally {
          this.loadingSessions = false
        }
      },

      async loadStorage(id: string) {
        this.loadingStorage = true
        this.storageError = null

        try {
          this.storage[id] =
            await apiRequest<OracleStorageResponse>(
              `/databases/${id}/oracle/storage`,
            )
        } catch (error) {
          this.storageError =
            error instanceof Error
              ? error.message
              : 'Unable to load Oracle storage.'
        } finally {
          this.loadingStorage = false
        }
      },

      async loadActivity(id: string) {
        this.loadingActivity = true
        this.activityError = null

        try {
          this.activity[id] =
            await apiRequest<OracleActivityResponse>(
              `/databases/${id}/oracle/activity`,
            )
        } catch (error) {
          this.activityError =
            error instanceof Error
              ? error.message
              : 'Unable to load Oracle activity.'
        } finally {
          this.loadingActivity = false
        }
      },

      async loadUsers(id: string) {
        this.loadingUsers = true
        this.usersError = null

        try {
          this.users[id] =
            await apiRequest<OracleDatabaseUsersResponse>(
              `/databases/${id}/oracle/users`,
            )
        } catch (error) {
          this.usersError =
            error instanceof Error
              ? error.message
              : 'Unable to load Oracle users and schemas.'
        } finally {
          this.loadingUsers = false
        }
      },

      async checkUsernameAvailability(id: string, username: string) {
        return apiRequest<OracleUsernameAvailability>(
          `/databases/${id}/oracle/users/${encodeURIComponent(username)}/availability`,
        )
      },

      async loadReferenceUser(
        id: string,
        username: string,
      ) {
        this.loadingReference = true
        this.referenceError = null

        try {
          const reference =
            await apiRequest<OracleReferenceUser>(
              `/databases/${id}/oracle/users/reference/${encodeURIComponent(username)}`,
            )

          this.references[id] = reference
          return reference
        } catch (error) {
          this.referenceError =
            error instanceof Error
              ? error.message
              : 'Unable to inspect the reference user.'
          throw error
        } finally {
          this.loadingReference = false
        }
      },

      async loadUserAccessInspector(id: string, username: string) {
        return apiRequest<OracleUserAccessInspector>(
          `/databases/${id}/oracle/users/${encodeURIComponent(username)}/access-inspector`,
        )
      },

      async loadAccessLookup(id: string, input: OracleAccessLookupInput) {
        const params = new URLSearchParams({ kind: input.kind })
        if (input.value?.trim()) params.set('value', input.value.trim())
        if (input.owner?.trim()) params.set('owner', input.owner.trim())
        if (input.object_name?.trim()) params.set('object_name', input.object_name.trim())
        if (input.privilege?.trim()) params.set('privilege', input.privilege.trim())
        return apiRequest<OracleAccessLookupResult>(
          `/databases/${id}/oracle/access-lookup?${params.toString()}`,
        )
      },

      async compareUserAccess(id: string, leftUsername: string, rightUsername: string) {
        const params = new URLSearchParams({
          left_username: leftUsername.trim(),
          right_username: rightUsername.trim(),
        })
        return apiRequest<OracleAccessCompareResult>(
          `/databases/${id}/oracle/access-compare?${params.toString()}`,
        )
      },

      async loadRoles(id: string) {
        return apiRequest<OracleRoleListResult>(
          `/databases/${id}/oracle/roles`,
        )
      },

      async loadRoleDetail(id: string, roleName: string) {
        return apiRequest<OracleRoleDetail>(
          `/databases/${id}/oracle/roles/${encodeURIComponent(roleName)}`,
        )
      },

      async previewRoleCreate(id: string, roleName: string, requestReference: string | null = null) {
        return apiRequest<OracleRoleChangePreview>(
          `/databases/${id}/oracle/roles/create-preview`,
          {
            method: 'POST',
            body: JSON.stringify({ role_name: roleName, request_reference: requestReference }),
          },
        )
      },

      async createRole(id: string, roleName: string, requestReference: string | null = null) {
        return apiRequest<OracleRoleActionResult>(
          `/databases/${id}/oracle/roles`,
          {
            method: 'POST',
            body: JSON.stringify({ role_name: roleName, request_reference: requestReference }),
          },
        )
      },

      async previewRoleChange(id: string, roleName: string, input: OracleRoleChangeInput) {
        return apiRequest<OracleRoleChangePreview>(
          `/databases/${id}/oracle/roles/${encodeURIComponent(roleName)}/change-preview`,
          { method: 'POST', body: JSON.stringify(input) },
        )
      },

      async changeRole(id: string, roleName: string, input: OracleRoleChangeInput) {
        return apiRequest<OracleRoleActionResult>(
          `/databases/${id}/oracle/roles/${encodeURIComponent(roleName)}/change`,
          { method: 'POST', body: JSON.stringify(input) },
        )
      },

      async previewRoleDrop(id: string, roleName: string) {
        return apiRequest<OracleRoleDropPreview>(
          `/databases/${id}/oracle/roles/${encodeURIComponent(roleName)}/drop-preview`,
        )
      },

      async dropRole(id: string, roleName: string, confirmRoleName: string, requestReference: string | null = null) {
        return apiRequest<OracleRoleDropResult>(
          `/databases/${id}/oracle/roles/${encodeURIComponent(roleName)}/drop`,
          {
            method: 'POST',
            body: JSON.stringify({
              confirm_role_name: confirmRoleName,
              request_reference: requestReference,
            }),
          },
        )
      },

      async loadUserLifecycleState(id: string, username: string) {
        return apiRequest<OracleUserLifecycleState>(
          `/databases/${id}/oracle/users/${encodeURIComponent(username)}/lifecycle`,
        )
      },

      async previewUserEdit(id: string, username: string, data: OracleUserEditInput) {
        return apiRequest<OracleUserEditPreview>(
          `/databases/${id}/oracle/users/${encodeURIComponent(username)}/edit-preview`,
          { method: 'POST', body: JSON.stringify(data) },
        )
      },

      async editUser(
        id: string,
        username: string,
        data: OracleUserEditInput & { request_reference: string | null },
      ) {
        return apiRequest<OracleUserEditResult>(
          `/databases/${id}/oracle/users/${encodeURIComponent(username)}/edit`,
          { method: 'POST', body: JSON.stringify(data) },
        )
      },

      async resetUserPassword(
        id: string,
        username: string,
        password: string,
        expireAfterReset: boolean,
        requestReference: string | null,
      ) {
        return apiRequest<OracleUserLifecycleActionResult>(
          `/databases/${id}/oracle/users/${encodeURIComponent(username)}/reset-password`,
          {
            method: 'POST',
            body: JSON.stringify({
              password,
              expire_after_reset: expireAfterReset,
              request_reference: requestReference,
            }),
          },
        )
      },

      async runUserAccountAction(
        id: string,
        username: string,
        action: 'lock' | 'unlock' | 'expire_password',
        requestReference: string | null,
      ) {
        return apiRequest<OracleUserLifecycleActionResult>(
          `/databases/${id}/oracle/users/${encodeURIComponent(username)}/account-action`,
          {
            method: 'POST',
            body: JSON.stringify({ action, request_reference: requestReference }),
          },
        )
      },

      async createUser(
        id: string,
        data: OracleCreateUserInput,
      ) {
        this.creatingUser = true
        this.createUserError = null

        try {
          return await apiRequest<OracleCreateUserResult>(
            `/databases/${id}/oracle/users`,
            {
              method: 'POST',
              body: JSON.stringify(data),
            },
          )
        } catch (error) {
          this.createUserError =
            error instanceof Error
              ? error.message
              : 'Unable to create Oracle user.'
          throw error
        } finally {
          this.creatingUser = false
        }
      },
    },
  })