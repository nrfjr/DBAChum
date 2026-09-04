import type { DatabaseEngine } from '@/stores/connections'
import type { DatabaseMonitoringStatus } from '@/stores/databases'

export type OverviewMetricKey = 'active' | 'connections' | 'blocked'

const overviewMetricLabels: Record<DatabaseEngine, Record<OverviewMetricKey, string>> = {
  oracle: {
    active: 'Active sessions',
    connections: 'User sessions',
    blocked: 'Blocked sessions',
  },
  sqlserver: {
    active: 'Active requests',
    connections: 'User connections',
    blocked: 'Blocked requests',
  },
  mysql: {
    active: 'Running threads',
    connections: 'Connected threads',
    blocked: 'Blocked transactions',
  },
}

export function engineLabel(engine: DatabaseEngine): string {
  switch (engine) {
    case 'oracle':
      return 'Oracle'
    case 'sqlserver':
      return 'SQL Server'
    case 'mysql':
      return 'MySQL / MariaDB'
  }
}

export function engineProductLabel(
  engine: DatabaseEngine,
  databaseProduct?: string | null,
): string {
  if (engine === 'mysql' && databaseProduct) return databaseProduct
  return engineLabel(engine)
}

export function statusLabel(status?: DatabaseMonitoringStatus | string): string {
  switch (status) {
    case 'online':
      return 'Online'
    case 'limited':
      return 'Limited'
    case 'unreachable':
      return 'Unreachable'
    case 'disabled':
      return 'Disabled'
    default:
      return 'Not checked'
  }
}

export function overviewMetricLabel(
  engine: DatabaseEngine,
  metric: OverviewMetricKey,
): string {
  return overviewMetricLabels[engine][metric]
}

export function formatMetric(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return '—'
  return new Intl.NumberFormat().format(value)
}

export function formatUptime(seconds: number | null | undefined): string {
  if (seconds == null || !Number.isFinite(seconds) || seconds < 0) return '—'

  const wholeSeconds = Math.floor(seconds)
  const days = Math.floor(wholeSeconds / 86400)
  const hours = Math.floor((wholeSeconds % 86400) / 3600)
  const minutes = Math.floor((wholeSeconds % 3600) / 60)

  if (days > 0) return `${days}d ${hours}h`
  if (hours > 0) return `${hours}h ${minutes}m`
  return `${minutes}m`
}
