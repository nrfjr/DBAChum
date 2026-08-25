import { defineStore } from 'pinia'

export type DatabaseEngine = 'oracle' | 'sqlserver' | 'mysql'
export type OracleAuthMode = 'normal' | 'sysdba'

export interface DatabaseConnection {
  id: string
  name: string
  engine: DatabaseEngine
  host: string
  port: number
  username: string
  database: string | null
  oracle_identifier_type: 'service_name' | 'sid' | null
  oracle_identifier: string | null
  oracle_auth_mode: OracleAuthMode | null
  active: boolean
  monitor_enabled: boolean
  /** Legacy monitoring alias returned for rollback compatibility. */
  enabled: boolean
  has_password: boolean
  created_at: string
  updated_at: string
  server_ids: string[]
}

export interface DatabaseConnectionInput {
  name: string
  engine: DatabaseEngine
  host: string
  port: number
  username: string
  password?: string
  database: string | null
  oracle_identifier_type: 'service_name' | 'sid' | null
  oracle_identifier: string | null
  oracle_auth_mode: OracleAuthMode | null
  active: boolean
  monitor_enabled: boolean
  server_ids: string[]
}

export interface DatabaseConnectionTestResult {
  success: boolean
  engine: DatabaseEngine
  message: string
  database_name: string | null
  service_name: string | null
  connected_user: string | null
  database_version: string | null
  oracle_auth_mode: OracleAuthMode | null
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

export const useConnectionsStore = defineStore('connections', {
  state: () => ({
    connections: [] as DatabaseConnection[],
    loading: false,
    saving: false,
    error: null as string | null,
  }),

  actions: {
    async load() {
      this.loading = true
      this.error = null

      try {
        this.connections =
          await apiRequest<DatabaseConnection[]>('/connections')
      } catch (error) {
        this.error =
          error instanceof Error
            ? error.message
            : 'Unable to load database connections.'
      } finally {
        this.loading = false
      }
    },

    async create(data: DatabaseConnectionInput) {
      this.saving = true

      try {
        const connection =
          await apiRequest<DatabaseConnection>('/connections', {
            method: 'POST',
            body: JSON.stringify(data),
          })

        this.connections.push(connection)

        this.connections.sort((a, b) =>
          a.name.localeCompare(b.name),
        )

        return connection
      } finally {
        this.saving = false
      }
    },

    async update(
      id: string,
      data: DatabaseConnectionInput,
    ) {
      this.saving = true

      try {
        const connection =
          await apiRequest<DatabaseConnection>(
            `/connections/${id}`,
            {
              method: 'PUT',
              body: JSON.stringify(data),
            },
          )

        const index = this.connections.findIndex(
          (item) => item.id === id,
        )

        if (index !== -1) {
          this.connections[index] = connection
        }

        this.connections.sort((a, b) =>
          a.name.localeCompare(b.name),
        )

        return connection
      } finally {
        this.saving = false
      }
    },

    async remove(id: string) {
      await apiRequest<void>(`/connections/${id}`, {
        method: 'DELETE',
      })

      this.connections = this.connections.filter(
        (connection) => connection.id !== id,
      )
    },

    async test(id: string) {
      return apiRequest<DatabaseConnectionTestResult>(
        `/connections/${id}/test`,
        {
          method: 'POST',
        },
      )
    },
  },
})