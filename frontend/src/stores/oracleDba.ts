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