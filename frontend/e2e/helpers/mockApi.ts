import type { Page, Route } from '@playwright/test'

export type UserRole = 'viewer' | 'operator' | 'admin'

interface MockApiOptions {
  authenticated?: boolean
  role?: UserRole
  historyFailure?: boolean
}

export interface MockApiState {
  historyHours: number[]
  createdConnections: Record<string, unknown>[]
  updatedUsers: Record<string, unknown>[]
}

const now = '2026-08-19T12:00:00Z'

const adminUser = {
  id: 'user-admin',
  username: 'admin',
  display_name: 'DBA Admin',
  role: 'admin' as UserRole,
  is_active: true,
  created_at: now,
  updated_at: now,
}

const operatorUser = {
  id: 'user-operator',
  username: 'operator',
  display_name: 'DB Operator',
  role: 'operator' as UserRole,
  is_active: true,
  created_at: now,
  updated_at: now,
}

export const oracleConnection = {
  id: 'conn-oracle',
  name: 'ERP Production',
  engine: 'oracle',
  host: 'ora01.example.local',
  port: 1521,
  username: 'dbachum',
  database: null,
  oracle_identifier_type: 'service_name',
  oracle_identifier: 'ERPPRD',
  enabled: true,
  has_password: true,
  created_at: now,
  updated_at: now,
  server_ids: ['server-1'],
}

export const sqlServerConnection = {
  id: 'conn-sqlserver',
  name: 'Reporting SQL',
  engine: 'sqlserver',
  host: 'sql01.example.local',
  port: 1433,
  username: 'monitor',
  database: 'Reporting',
  oracle_identifier_type: null,
  oracle_identifier: null,
  enabled: true,
  has_password: true,
  created_at: now,
  updated_at: now,
  server_ids: [],
}

const server = {
  id: 'server-1',
  name: 'Oracle Server 01',
  hostname: 'ora01',
  ip_address: '10.0.0.11',
  os_family: 'linux',
  os_version: 'RHEL 9',
  environment: 'Production',
  owner: 'DBA',
  tags: ['oracle'],
  notes: null,
  enabled: true,
  database_count: 1,
  created_at: now,
  updated_at: now,
}

const oracleOverview = {
  connection_id: oracleConnection.id,
  engine: 'oracle',
  status: 'online',
  response_time_ms: 18,
  active: 7,
  connections: 42,
  blocked: 0,
  uptime_seconds: 98765,
  database_name: 'ERPPRD',
  container_name: 'ERPPRD',
  service_name: 'ERPPRD',
  instance_name: 'ERP1',
  version: 'Oracle Database 19c',
  checked_at: now,
  warnings: [],
  error: null,
}

const sqlServerOverview = {
  connection_id: sqlServerConnection.id,
  engine: 'sqlserver',
  status: 'unreachable',
  response_time_ms: null,
  active: null,
  connections: null,
  blocked: null,
  uptime_seconds: null,
  database_name: null,
  container_name: null,
  service_name: null,
  instance_name: null,
  version: null,
  checked_at: now,
  warnings: [],
  error: 'Connection failed.',
}

function json(route: Route, body: unknown, status = 200) {
  return route.fulfill({
    status,
    contentType: 'application/json',
    body: JSON.stringify(body),
  })
}

function history(hours: number) {
  const allItems = [
    {
      collected_at: '2026-08-19T10:00:00Z',
      checked_at: '2026-08-19T10:00:00Z',
      status: 'online',
      response_time_ms: 16,
      active: 4,
      connections: 38,
      blocked: 0,
      uptime_seconds: 91565,
      warnings: [],
      error: null,
    },
    {
      collected_at: '2026-08-19T11:00:00Z',
      checked_at: '2026-08-19T11:00:00Z',
      status: 'unreachable',
      response_time_ms: null,
      active: null,
      connections: null,
      blocked: null,
      uptime_seconds: null,
      warnings: [],
      error: 'Connection failed.',
    },
    {
      collected_at: '2026-08-19T12:00:00Z',
      checked_at: '2026-08-19T12:00:00Z',
      status: 'online',
      response_time_ms: 18,
      active: 7,
      connections: 42,
      blocked: 0,
      uptime_seconds: 98765,
      warnings: [],
      error: null,
    },
  ]

  const items = hours === 1 ? allItems.slice(-1) : allItems

  return {
    connection_id: oracleConnection.id,
    engine: 'oracle',
    from_at: '2026-08-18T12:00:00Z',
    to_at: '2026-08-19T12:00:00Z',
    sample_interval_seconds: 60,
    count: items.length,
    items,
  }
}

export async function installMockApi(
  page: Page,
  options: MockApiOptions = {},
): Promise<MockApiState> {
  const state: MockApiState = {
    historyHours: [],
    createdConnections: [],
    updatedUsers: [],
  }

  let authenticated = options.authenticated ?? true
  const role = options.role ?? 'admin'
  let connections = [oracleConnection, sqlServerConnection]
  let users = [adminUser, operatorUser]

  await page.route('**/api/v1/**', async (route) => {
    const request = route.request()
    const url = new URL(request.url())
    const path = url.pathname.replace(/^\/api\/v1/, '')
    const method = request.method()

    if (path === '/auth/me' && method === 'GET') {
      if (!authenticated) {
        return json(route, { error: { message: 'Not authenticated.' } }, 401)
      }

      return json(route, {
        ...adminUser,
        role,
      })
    }

    if (path === '/auth/login' && method === 'POST') {
      authenticated = true

      return json(route, {
        user: {
          ...adminUser,
          role,
        },
      })
    }

    if (path === '/auth/logout' && method === 'POST') {
      authenticated = false
      return json(route, {})
    }

    if (path === '/users' && method === 'GET') {
      return json(route, users)
    }

    if (path === '/users/user-operator' && method === 'PUT') {
      const payload = request.postDataJSON() as Record<string, unknown>
      state.updatedUsers.push(payload)

      const updated = {
        ...operatorUser,
        ...payload,
        updated_at: now,
      }

      users = users.map((user) =>
        user.id === operatorUser.id ? updated : user,
      )

      return json(route, updated)
    }

    if (path === '/connections' && method === 'GET') {
      return json(route, connections)
    }

    if (path === '/connections' && method === 'POST') {
      const payload = request.postDataJSON() as Record<string, unknown>
      state.createdConnections.push(payload)

      const created = {
        id: 'conn-created',
        ...payload,
        has_password: true,
        created_at: now,
        updated_at: now,
      }

      connections = [...connections, created as typeof oracleConnection]
      return json(route, created, 201)
    }

    if (
      path === `/connections/${oracleConnection.id}/test`
      && method === 'POST'
    ) {
      return json(route, {
        success: true,
        engine: 'oracle',
        message: 'Connection successful.',
        database_name: 'ERPPRD',
        service_name: 'ERPPRD',
        connected_user: 'DBACHUM',
        database_version: 'Oracle Database 19c',
      })
    }

    if (path === '/servers' && method === 'GET') {
      return json(route, [server])
    }

    if (path === '/health' && method === 'GET') {
      return json(route, {
        api: 'healthy',
        mongodb: 'healthy',
      })
    }

    if (path === '/databases/overview' && method === 'GET') {
      return json(route, [oracleOverview, sqlServerOverview])
    }

    if (
      path === `/databases/${oracleConnection.id}/overview`
      && method === 'GET'
    ) {
      return json(route, oracleOverview)
    }

    if (
      path === `/databases/${sqlServerConnection.id}/overview`
      && method === 'GET'
    ) {
      return json(route, sqlServerOverview)
    }

    if (
      path === `/databases/${oracleConnection.id}/metrics/history`
      && method === 'GET'
    ) {
      const hours = Number(url.searchParams.get('hours') ?? '24')
      state.historyHours.push(hours)

      if (options.historyFailure) {
        return json(
          route,
          { error: { message: 'Historical metrics unavailable.' } },
          500,
        )
      }

      return json(route, history(hours))
    }

    return json(
      route,
      { error: { message: `Unhandled mock route: ${method} ${path}` } },
      501,
    )
  })

  return state
}
