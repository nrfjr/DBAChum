<script setup lang="ts">
import {
  computed,
  onMounted,
  onUnmounted,
  ref,
  watch,
} from 'vue'

import VChart from 'vue-echarts'

import '@/charts/echarts'

import ScrollableDataTable from '@/components/common/ScrollableDataTable.vue'
import {
  useDatabaseMetricsStore,
  type DatabaseMetricSample,
} from '@/stores/databaseMetrics'
import { useUiStore } from '@/stores/ui'
import { useAuthStore } from '@/stores/auth'
import { overviewMetricLabel } from '@/core/databasePresentation'


const props = defineProps<{
  connectionId: string
}>()

const metricsStore = useDatabaseMetricsStore()
const uiStore = useUiStore()
const authStore = useAuthStore()


type HistoryRange = 1 | 6 | 12 | 24

type HistoryMetric =
  | 'active'
  | 'connections'
  | 'blocked'
  | 'cpu'
  | 'executions'
  | 'logical_reads'
  | 'physical_reads'
  | 'latency'
  | 'log_used'
  | 'long_running'
  | 'tempdb_used'
  | 'failed_jobs'
  | 'connection_utilization'
  | 'mysql_long_running'
  | 'slow_queries_delta'
  | 'aborted_connects_delta'
  | 'aborted_clients_delta'
  | 'buffer_pool_used'
  | 'tmp_disk_interval'
  | 'storage_bytes'

type MetricGroupKey = 'workload' | 'connections' | 'performance' | 'storage' | 'jobs'

interface MetricDefinition {
  key: HistoryMetric
  label: string
  axis: string
  group: MetricGroupKey
  oracleOnly?: boolean
  sqlserverOnly?: boolean
  mysqlOnly?: boolean
}

interface MetricGroupDefinition {
  key: MetricGroupKey
  label: string
}

interface AggregatedSqlRow {
  key: string
  sql_id: string
  child_number: number
  parsing_schema_name: string | null
  module: string | null
  sql_text: string | null
  cpu_time_seconds: number
  elapsed_time_seconds: number
  executions: number
  logical_reads: number
  physical_reads: number
  samples: number
}

interface AggregatedSessionRow {
  key: string
  sid: number
  serial_number: number
  username: string | null
  sql_id: string | null
  module: string | null
  machine: string | null
  event: string | null
  wait_class: string | null
  blocking_session: number | null
  cpu_time_seconds: number
  samples: number
  active_seconds: number
}

interface AggregatedWaitRow {
  event: string
  wait_time_seconds: number
  waits: number
  samples: number
}

const ranges: HistoryRange[] = [1, 6, 12, 24]

function preferredHistoryRange(): HistoryRange {
  const preference = authStore.user?.preferences.default_history_range
  const parsed = Number.parseInt(preference ?? '1h', 10)
  return ranges.includes(parsed as HistoryRange)
    ? parsed as HistoryRange
    : 1
}

const hours = ref<HistoryRange>(preferredHistoryRange())
const metric = ref<HistoryMetric>('active')
const selectedWindow = ref<[number, number] | null>(null)
const historyChart = ref<any>(null)
const showAllSql = ref(false)
const showAllSessions = ref(false)
const showAllWaits = ref(false)

let refreshTimer: ReturnType<typeof setInterval> | undefined

const history = computed(() => metricsStore.histories[props.connectionId])
const isOracle = computed(() => history.value?.engine === 'oracle')
const isSqlServer = computed(() => history.value?.engine === 'sqlserver')
const isMySql = computed(() => history.value?.engine === 'mysql')

const metricGroups: MetricGroupDefinition[] = [
  { key: 'workload', label: 'Workload' },
  { key: 'connections', label: 'Connections' },
  { key: 'performance', label: 'Performance' },
  { key: 'storage', label: 'Storage & capacity' },
  { key: 'jobs', label: 'Jobs' },
]

const defaultMetricDefinition: MetricDefinition = {
  key: 'active',
  label: 'Active',
  axis: 'Active sessions',
  group: 'workload',
}

const metricDefinitions: MetricDefinition[] = [
  defaultMetricDefinition,
  { key: 'blocked', label: 'Blocked', axis: 'Blocked sessions', group: 'workload' },
  { key: 'long_running', label: 'Long-running requests', axis: 'Long-running requests', group: 'workload', sqlserverOnly: true },
  { key: 'mysql_long_running', label: 'Long-running sessions', axis: 'Sessions ≥ 60s', group: 'workload', mysqlOnly: true },
  { key: 'connections', label: 'Connections', axis: 'Connections', group: 'connections' },
  { key: 'connection_utilization', label: 'Connection utilization %', axis: 'Connections used (%)', group: 'connections', mysqlOnly: true },
  { key: 'aborted_connects_delta', label: 'Aborted connects ', axis: 'Aborted connects / sample', group: 'connections', mysqlOnly: true },
  { key: 'aborted_clients_delta', label: 'Aborted clients ', axis: 'Aborted clients / sample', group: 'connections', mysqlOnly: true },
  { key: 'latency', label: 'Connection latency', axis: 'Latency (ms)', group: 'performance' },
  { key: 'cpu', label: 'CPU time', axis: 'CPU seconds / sample', group: 'performance', oracleOnly: true },
  { key: 'executions', label: 'Executions', axis: 'Executions / sample', group: 'performance', oracleOnly: true },
  { key: 'logical_reads', label: 'Logical reads', axis: 'Logical reads / sample', group: 'performance', oracleOnly: true },
  { key: 'physical_reads', label: 'Physical reads', axis: 'Physical reads / sample', group: 'performance', oracleOnly: true },
  { key: 'slow_queries_delta', label: 'Slow queries ', axis: 'Slow queries / sample', group: 'performance', mysqlOnly: true },
  { key: 'log_used', label: 'Transaction log used %', axis: 'Transaction log used (%)', group: 'storage', sqlserverOnly: true },
  { key: 'tempdb_used', label: 'tempdb used %', axis: 'tempdb data used (%)', group: 'storage', sqlserverOnly: true },
  { key: 'buffer_pool_used', label: 'InnoDB buffer pool %', axis: 'Buffer pool data (%)', group: 'storage', mysqlOnly: true },
  { key: 'tmp_disk_interval', label: 'Temp tables → disk %', axis: 'Disk temp tables / sample (%)', group: 'storage', mysqlOnly: true },
  { key: 'storage_bytes', label: 'Logical storage', axis: 'Logical database size (bytes)', group: 'storage', mysqlOnly: true },
  { key: 'failed_jobs', label: 'Failed SQL Agent jobs', axis: 'Failed SQL Agent jobs', group: 'jobs', sqlserverOnly: true },
]

function presentationForMetric(item: MetricDefinition): MetricDefinition {
  const engine = history.value?.engine
  if (!engine || !['active', 'connections', 'blocked'].includes(item.key)) {
    return item
  }

  const label = overviewMetricLabel(
    engine,
    item.key as 'active' | 'connections' | 'blocked',
  )

  return {
    ...item,
    label,
    axis: label,
  }
}

const availableMetrics = computed(() =>
  metricDefinitions
    .filter((item) =>
      (!item.oracleOnly || isOracle.value) &&
      (!item.sqlserverOnly || isSqlServer.value) &&
      (!item.mysqlOnly || isMySql.value),
    )
    .map(presentationForMetric),
)

const availableMetricGroups = computed(() =>
  metricGroups
    .map((group) => ({
      ...group,
      items: availableMetrics.value.filter((item) => item.group === group.key),
    }))
    .filter((group) => group.items.length > 0),
)

watch([isOracle, isSqlServer, isMySql], () => {
  if (!availableMetrics.value.some((item) => item.key === metric.value)) {
    metric.value = 'active'
  }
})

const localTimeFormatter = new Intl.DateTimeFormat(undefined, {
  hour: '2-digit',
  minute: '2-digit',
})

const localDateTimeFormatter = new Intl.DateTimeFormat(undefined, {
  year: 'numeric',
  month: 'short',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
  second: '2-digit',
})

function parseUtcTimestamp(value: string): number {
  const timestamp = value.replace(/(\.\d{3})\d+/, '$1')
  const hasTimezone = /(?:Z|[+-]\d{2}:\d{2})$/i.test(timestamp)
  return Date.parse(hasTimezone ? timestamp : `${timestamp}Z`)
}

function numberOrZero(value: unknown): number {
  return typeof value === 'number' && Number.isFinite(value) ? value : 0
}

function formatNumber(value: number, maximumFractionDigits = 1): string {
  return new Intl.NumberFormat(undefined, { maximumFractionDigits }).format(value)
}

function formatBytes(value: number | null | undefined): string {
  const bytes = numberOrZero(value)
  if (bytes <= 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  let amount = bytes
  let index = 0
  while (amount >= 1024 && index < units.length - 1) {
    amount /= 1024
    index += 1
  }
  return `${formatNumber(amount, amount >= 100 ? 0 : 1)} ${units[index]}`
}

const rangeLabel = computed(() => hours.value === 1 ? '1 hour' : `${hours.value} hours`)

const chartExtent = computed<[number, number] | null>(() => {
  const items = history.value?.items ?? []
  const firstItem = items[0]
  const lastItem = items[items.length - 1]
  if (!firstItem || !lastItem) return null

  const first = parseUtcTimestamp(firstItem.collected_at)
  const last = parseUtcTimestamp(lastItem.collected_at)
  if (!Number.isFinite(first) || !Number.isFinite(last)) return null
  return [first, last]
})

const selectedItems = computed(() => {
  const items = history.value?.items ?? []
  if (!selectedWindow.value) return items
  const [from, to] = selectedWindow.value
  return items.filter((item) => {
    const timestamp = parseUtcTimestamp(item.collected_at)
    return Number.isFinite(timestamp) && timestamp >= from && timestamp <= to
  })
})

const selectedRangeLabel = computed(() => {
  if (!selectedWindow.value) return rangeLabel.value
  return `${localDateTimeFormatter.format(selectedWindow.value[0])} – ${localDateTimeFormatter.format(selectedWindow.value[1])}`
})

const latestSampleTime = computed(() => {
  const items = selectedItems.value
  const latest = items[items.length - 1]
  if (!latest) return '—'
  const timestamp = parseUtcTimestamp(latest.collected_at)
  return Number.isFinite(timestamp) ? localDateTimeFormatter.format(timestamp) : '—'
})

const availabilityPercent = computed(() => {
  if (!selectedItems.value.length) return null
  const available = selectedItems.value.filter((item) => item.status !== 'unreachable').length
  return available / selectedItems.value.length * 100
})

const selectedCpuSeconds = computed(() =>
  selectedItems.value.reduce(
    (total, item) => total + numberOrZero(item.oracle?.system_deltas?.cpu_time_seconds),
    0,
  ),
)

const selectedMySqlSlowQueries = computed(() =>
  selectedItems.value.reduce(
    (total, item) => total + numberOrZero(item.mysql?.slow_queries_delta),
    0,
  ),
)

const selectedMySqlAbortedConnections = computed(() =>
  selectedItems.value.reduce(
    (total, item) =>
      total +
      numberOrZero(item.mysql?.aborted_connects_delta) +
      numberOrZero(item.mysql?.aborted_clients_delta),
    0,
  ),
)

const currentMetric = computed<MetricDefinition>(() =>
  availableMetrics.value.find((item) => item.key === metric.value)
  ?? presentationForMetric(defaultMetricDefinition),
)

type MetricPoint = [number, number | null]

function getMetricValue(item: DatabaseMetricSample): number | null {
  if (item.status === 'unreachable') return null

  switch (metric.value) {
    case 'active':
      return item.sqlserver?.active ?? item.active
    case 'connections':
      return item.connections
    case 'blocked':
      return item.sqlserver?.blocked ?? item.blocked
    case 'latency':
      return item.response_time_ms
    case 'cpu':
      return item.oracle?.system_deltas?.cpu_time_seconds ?? null
    case 'executions':
      return item.oracle?.system_deltas?.execute_count ?? null
    case 'logical_reads':
      return item.oracle?.system_deltas?.logical_reads ?? null
    case 'physical_reads':
      return item.oracle?.system_deltas?.physical_reads ?? null
    case 'log_used':
      return item.sqlserver?.log_used_percent ?? null
    case 'long_running':
      return item.sqlserver?.long_running ?? null
    case 'tempdb_used':
      return item.sqlserver?.tempdb_used_percent ?? null
    case 'failed_jobs':
      return item.sqlserver?.agent_failed_jobs ?? null
    case 'connection_utilization':
      return item.mysql?.connection_utilization_percent ?? null
    case 'mysql_long_running':
      return item.mysql?.long_running_sessions ?? null
    case 'slow_queries_delta':
      return item.mysql?.slow_queries_delta ?? null
    case 'aborted_connects_delta':
      return item.mysql?.aborted_connects_delta ?? null
    case 'aborted_clients_delta':
      return item.mysql?.aborted_clients_delta ?? null
    case 'buffer_pool_used':
      return item.mysql?.buffer_pool_used_percent ?? null
    case 'tmp_disk_interval':
      return item.mysql?.temporary_disk_percent_interval ?? null
    case 'storage_bytes':
      return item.mysql?.storage?.total_bytes ?? null
  }
}

const metricSeriesData = computed<MetricPoint[]>(() => {
  const items = history.value?.items ?? []
  const intervalSeconds = history.value?.sample_interval_seconds ?? 60
  const expectedIntervalMs = Math.max(intervalSeconds * 1000, 1000)
  const gapThresholdMs = expectedIntervalMs * 2.5
  const points: MetricPoint[] = []
  let previousTimestamp: number | null = null

  for (const item of items) {
    const timestamp = parseUtcTimestamp(item.collected_at)
    if (!Number.isFinite(timestamp)) continue

    if (previousTimestamp !== null && timestamp - previousTimestamp > gapThresholdMs) {
      points.push([previousTimestamp + (timestamp - previousTimestamp) / 2, null])
    }

    points.push([timestamp, getMetricValue(item)])
    previousTimestamp = timestamp
  }

  return points
})

function cssVariable(name: string) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim()
}

const chartOption = computed(() => {
  void uiStore.resolvedTheme
  void uiStore.accent

  const textColor = cssVariable('--color-text-secondary')
  const purple = cssVariable('--color-purple')

  return {
    animation: false,
    useUTC: false,
    grid: { left: 65, right: 24, top: 30, bottom: 75 },
    tooltip: {
      trigger: 'axis',
      valueFormatter: (value: number | null) => {
        if (value === null || value === undefined) return 'Unavailable'
        if (metric.value === 'latency') return `${formatNumber(value, 1)} ms`
        if (metric.value === 'cpu') return `${formatNumber(value, 3)} s`
        if (['log_used', 'tempdb_used', 'connection_utilization', 'buffer_pool_used', 'tmp_disk_interval'].includes(metric.value)) return `${formatNumber(value, 1)}%`
        if (metric.value === 'storage_bytes') return formatBytes(value)
        return formatNumber(value, 1)
      },
    },
    xAxis: {
      type: 'time',
      axisLabel: {
        color: textColor,
        formatter: (value: number) => localTimeFormatter.format(value),
      },
    },
    yAxis: {
      type: 'value',
      min: 0,
      minInterval: ['active', 'connections', 'blocked', 'executions', 'logical_reads', 'physical_reads', 'long_running', 'failed_jobs', 'mysql_long_running', 'slow_queries_delta', 'aborted_connects_delta', 'aborted_clients_delta'].includes(metric.value) ? 1 : undefined,
      max: ['log_used', 'tempdb_used', 'connection_utilization', 'buffer_pool_used', 'tmp_disk_interval'].includes(metric.value) ? 100 : undefined,
      name: currentMetric.value.axis,
      axisLabel: {
        color: textColor,
        formatter: metric.value === 'storage_bytes'
          ? (value: number) => formatBytes(value)
          : undefined,
      },
    },
    dataZoom: [
      { id: 'history-inside', type: 'inside', start: 0, end: 100 },
      { id: 'history-slider', type: 'slider', start: 0, end: 100, height: 22, bottom: 15 },
    ],
    series: [
      {
        name: currentMetric.value.label,
        type: 'line',
        showSymbol: false,
        smooth: false,
        connectNulls: false,
        lineStyle: { width: 2, color: purple },
        itemStyle: { color: purple },
        data: metricSeriesData.value,
      },
    ],
  }
})

function handleDataZoom(event: any) {
  const extent = chartExtent.value
  if (!extent) return

  const payload = event?.batch?.[0] ?? event ?? {}
  const startPercent = Number(payload.start ?? 0)
  const endPercent = Number(payload.end ?? 100)

  if (!Number.isFinite(startPercent) || !Number.isFinite(endPercent)) return
  if (startPercent <= 0.05 && endPercent >= 99.95) {
    selectedWindow.value = null
    return
  }

  const span = Math.max(extent[1] - extent[0], 0)
  selectedWindow.value = [
    extent[0] + span * startPercent / 100,
    extent[0] + span * endPercent / 100,
  ]
}

function resetZoom() {
  selectedWindow.value = null
  historyChart.value?.setOption?.({
    dataZoom: [
      { id: 'history-inside', start: 0, end: 100 },
      { id: 'history-slider', start: 0, end: 100 },
    ],
  })
}

const sqlTextByKey = computed(() => {
  const exact = new Map<string, string>()
  const bySqlId = new Map<string, string>()
  for (const item of history.value?.oracle_sql_texts ?? []) {
    exact.set(`${item.sql_id}:${item.child_number}`, item.sql_text)
    if (!bySqlId.has(item.sql_id)) bySqlId.set(item.sql_id, item.sql_text)
  }
  return { exact, bySqlId }
})

const topSqlRows = computed<AggregatedSqlRow[]>(() => {
  const rows = new Map<string, AggregatedSqlRow>()

  for (const sample of selectedItems.value) {
    for (const item of sample.oracle?.top_sql ?? []) {
      const key = `${item.sql_id}:${item.child_number}`
      let row = rows.get(key)
      if (!row) {
        row = {
          key,
          sql_id: item.sql_id,
          child_number: item.child_number,
          parsing_schema_name: item.parsing_schema_name ?? null,
          module: item.module ?? null,
          sql_text: sqlTextByKey.value.exact.get(key) ?? sqlTextByKey.value.bySqlId.get(item.sql_id) ?? null,
          cpu_time_seconds: 0,
          elapsed_time_seconds: 0,
          executions: 0,
          logical_reads: 0,
          physical_reads: 0,
          samples: 0,
        }
        rows.set(key, row)
      }

      row.parsing_schema_name = item.parsing_schema_name ?? row.parsing_schema_name
      row.module = item.module ?? row.module
      row.cpu_time_seconds += numberOrZero(item.delta_cpu_time_us) / 1_000_000
      row.elapsed_time_seconds += numberOrZero(item.delta_elapsed_time_us) / 1_000_000
      row.executions += numberOrZero(item.delta_executions)
      row.logical_reads += numberOrZero(item.delta_buffer_gets)
      row.physical_reads += numberOrZero(item.delta_disk_reads)
      if (!item.baseline) row.samples += 1
    }
  }

  return [...rows.values()].sort((left, right) =>
    right.cpu_time_seconds - left.cpu_time_seconds ||
    right.elapsed_time_seconds - left.elapsed_time_seconds ||
    right.executions - left.executions,
  )
})

const visibleTopSqlRows = computed(() => showAllSql.value ? topSqlRows.value : topSqlRows.value.slice(0, 5))

const topSessionRows = computed<AggregatedSessionRow[]>(() => {
  const rows = new Map<string, AggregatedSessionRow>()

  for (const sample of selectedItems.value) {
    for (const item of sample.oracle?.top_sessions ?? []) {
      const key = `${item.sid}:${item.serial_number}`
      let row = rows.get(key)
      if (!row) {
        row = {
          key,
          sid: item.sid,
          serial_number: item.serial_number,
          username: item.username ?? null,
          sql_id: item.sql_id ?? null,
          module: item.module ?? null,
          machine: item.machine ?? null,
          event: item.event ?? null,
          wait_class: item.wait_class ?? null,
          blocking_session: item.blocking_session ?? null,
          cpu_time_seconds: 0,
          samples: 0,
          active_seconds: 0,
        }
        rows.set(key, row)
      }

      row.username = item.username ?? row.username
      row.sql_id = item.sql_id ?? row.sql_id
      row.module = item.module ?? row.module
      row.machine = item.machine ?? row.machine
      row.event = item.event ?? row.event
      row.wait_class = item.wait_class ?? row.wait_class
      row.blocking_session = item.blocking_session ?? row.blocking_session
      row.cpu_time_seconds += numberOrZero(item.cpu_time_seconds)
      row.active_seconds = Math.max(row.active_seconds, numberOrZero(item.active_seconds))
      row.samples += 1
    }
  }

  return [...rows.values()].sort((left, right) =>
    right.cpu_time_seconds - left.cpu_time_seconds ||
    right.samples - left.samples ||
    right.active_seconds - left.active_seconds,
  )
})

const visibleTopSessionRows = computed(() => showAllSessions.value ? topSessionRows.value : topSessionRows.value.slice(0, 5))

const topWaitRows = computed<AggregatedWaitRow[]>(() => {
  const rows = new Map<string, AggregatedWaitRow>()

  for (const sample of selectedItems.value) {
    for (const item of sample.oracle?.top_waits ?? []) {
      let row = rows.get(item.event)
      if (!row) {
        row = { event: item.event, wait_time_seconds: 0, waits: 0, samples: 0 }
        rows.set(item.event, row)
      }
      row.wait_time_seconds += numberOrZero(item.wait_time_seconds)
      row.waits += numberOrZero(item.waits)
      if (!item.baseline) row.samples += 1
    }
  }

  return [...rows.values()].sort((left, right) =>
    right.wait_time_seconds - left.wait_time_seconds || right.waits - left.waits,
  )
})

const visibleTopWaitRows = computed(() => showAllWaits.value ? topWaitRows.value : topWaitRows.value.slice(0, 5))

const latestStorage = computed(() => {
  const items = [...selectedItems.value].reverse()
  for (const item of items) {
    if (item.oracle?.storage) return item.oracle.storage
  }
  return null
})

const fullestTablespaces = computed(() =>
  [...(latestStorage.value?.tablespaces ?? [])]
    .sort((left, right) => numberOrZero(right.used_percent) - numberOrZero(left.used_percent))
    .slice(0, 8),
)

function handleMetricChange(event: Event) {
  const value = (event.target as HTMLSelectElement).value as HistoryMetric
  if (!availableMetrics.value.some((item) => item.key === value)) return
  metric.value = value
}

function handleRangeChange(event: Event) {
  const value = Number((event.target as HTMLSelectElement).value)
  if (![1, 6, 12, 24].includes(value)) return
  void loadHistory(value as HistoryRange)
}

async function loadHistory(selectedHours: HistoryRange, resetView = true) {
  hours.value = selectedHours
  if (resetView) {
    selectedWindow.value = null
    showAllSql.value = false
    showAllSessions.value = false
    showAllWaits.value = false
  }

  try {
    await metricsStore.loadHistory(props.connectionId, selectedHours)
  } catch {
  }
}

onMounted(async () => {
  await loadHistory(hours.value)
  refreshTimer = setInterval(() => {
    if (!selectedWindow.value) void loadHistory(hours.value, false)
  }, 60_000)
})

onUnmounted(() => {
  if (refreshTimer) clearInterval(refreshTimer)
})
</script>

<template>
  <section class="database-history-panel">
    <div class="utility-toolbar">
      <div>
        <h2>24-hour history</h2>
        <p>
          Collector-backed telemetry only. Drag the chart range to inspect the
          exact incident window; Oracle detail tables follow that selection when available.
        </p>
      </div>

      <button
        type="button"
        class="secondary-button"
        :disabled="metricsStore.loading"
        @click="loadHistory(hours)"
      >
        {{ metricsStore.loading ? 'Refreshing...' : 'Refresh' }}
      </button>
    </div>

    <p v-if="metricsStore.error" class="login-error">
      {{ metricsStore.error }}
    </p>

    <div v-else-if="metricsStore.loading && !history" class="empty-state">
      Loading historical metrics...
    </div>

    <div
      v-else-if="!history || history.items.length === 0"
      class="database-empty-state"
    >
      <h2>No historical samples yet</h2>
      <p>DBAChum has not collected metrics for this time range.</p>
    </div>

    <template v-else>
      <div class="database-history-summary history-summary-grid">
        <span>
          Selected samples
          <strong>{{ selectedItems.length }} / {{ history.count }}</strong>
        </span>

        <span>
          Window
          <strong>{{ selectedRangeLabel }}</strong>
        </span>

        <span>
          Availability
          <strong>
            {{ availabilityPercent === null ? '—' : `${formatNumber(availabilityPercent, 1)}%` }}
          </strong>
        </span>

        <span>
          Latest
          <strong>{{ latestSampleTime }}</strong>
        </span>

        <span v-if="isOracle">
          Oracle CPU time
          <strong>{{ formatNumber(selectedCpuSeconds, 2) }} s</strong>
        </span>

        <span v-if="isMySql">
          Slow queries · window
          <strong>{{ formatNumber(selectedMySqlSlowQueries, 0) }}</strong>
        </span>

        <span v-if="isMySql">
          Aborted connections · window
          <strong>{{ formatNumber(selectedMySqlAbortedConnections, 0) }}</strong>
        </span>
      </div>

      <div class="history-control-row">
        <label class="history-metric-control history-control-select">
          <span class="history-control-label">Metric</span>
          <select :value="metric" @change="handleMetricChange">
            <optgroup
              v-for="group in availableMetricGroups"
              :key="group.key"
              :label="group.label"
            >
              <option
                v-for="item in group.items"
                :key="item.key"
                :value="item.key"
              >
                {{ item.label }}
              </option>
            </optgroup>
          </select>
        </label>

        <div class="history-range-control">
          <button
            v-if="selectedWindow"
            type="button"
            class="secondary-button history-reset-zoom"
            @click="resetZoom"
          >
            Reset selection
          </button>

          <label class="history-control-select">
            <span class="history-control-label">Range</span>
            <select :value="hours" @change="handleRangeChange">
              <option v-for="range in ranges" :key="range" :value="range">
                Last {{ range === 1 ? '1 hour' : `${range} hours` }}
              </option>
            </select>
          </label>
        </div>
      </div>

      <div class="history-chart-card">
        <div class="history-section-heading">
          <div>
            <h3>{{ currentMetric.label }}</h3>
            <p v-if="metric === 'cpu'">
              CPU time consumed during each collector interval; this is not an instantaneous CPU percentage.
            </p>
            <p v-else-if="['slow_queries_delta', 'aborted_connects_delta', 'aborted_clients_delta'].includes(metric)">
              Per-collector-interval delta from the server's cumulative GLOBAL STATUS counter. The first healthy sample after startup/recovery is a baseline.
            </p>
            <p v-else-if="metric === 'tmp_disk_interval'">
              Percentage of temporary tables created on disk during each collector interval; no temporary-table activity is shown as unavailable rather than 0%.
            </p>
            <p v-else-if="metric === 'storage_bytes'">
              Logical data + index size visible through INFORMATION_SCHEMA. This is not filesystem free-space capacity; server disk pressure remains a Server Assets metric.
            </p>
            <p v-else-if="metric === 'buffer_pool_used'">
              InnoDB buffer-pool data occupancy. High occupancy is normal and is graphed for context, not treated as a pressure alert by itself.
            </p>
            <p v-else>
              Gaps are kept visible when the target or collector did not return a sample.
            </p>
          </div>
        </div>

        <VChart
          ref="historyChart"
          class="database-history-chart"
          :option="chartOption"
          autoresize
          @datazoom="handleDataZoom"
        />
      </div>

      <template v-if="isOracle">
        <section class="history-detail-card">
          <div class="history-section-heading">
            <div>
              <h3>Top SQL · selected window</h3>
              <p>Ranks the collector's per-interval SQL deltas only inside the visible chart window.</p>
            </div>
            <button
              v-if="topSqlRows.length > 5"
              type="button"
              class="secondary-button"
              @click="showAllSql = !showAllSql"
            >
              {{ showAllSql ? 'Top 5' : `View all (${topSqlRows.length})` }}
            </button>
          </div>

          <ScrollableDataTable
            :empty="topSqlRows.length === 0"
            empty-message="No SQL delta telemetry exists in this selected window."
            max-height="26rem"
          >
            <template #header>
              <tr>
                <th>SQL ID</th>
                <th>Schema</th>
                <th>Module</th>
                <th>CPU</th>
                <th>Elapsed</th>
                <th>Execs</th>
                <th>Logical reads</th>
                <th>Physical reads</th>
                <th>SQL text</th>
              </tr>
            </template>
            <tr v-for="row in visibleTopSqlRows" :key="row.key">
              <td>
                <strong>{{ row.sql_id }}</strong>
                <small>child {{ row.child_number }}</small>
              </td>
              <td>{{ row.parsing_schema_name || '—' }}</td>
              <td>{{ row.module || '—' }}</td>
              <td>{{ formatNumber(row.cpu_time_seconds, 3) }} s</td>
              <td>{{ formatNumber(row.elapsed_time_seconds, 3) }} s</td>
              <td>{{ formatNumber(row.executions, 0) }}</td>
              <td>{{ formatNumber(row.logical_reads, 0) }}</td>
              <td>{{ formatNumber(row.physical_reads, 0) }}</td>
              <td class="history-sql-text" :title="row.sql_text || ''">
                {{ row.sql_text || 'SQL text no longer present in the 24h cache.' }}
              </td>
            </tr>
          </ScrollableDataTable>
        </section>

        <section class="history-detail-card">
          <div class="history-section-heading">
            <div>
              <h3>Top sessions · selected window</h3>
              <p>Ranks active/problem sessions by CPU consumed while they appeared in collector samples.</p>
            </div>
            <button
              v-if="topSessionRows.length > 5"
              type="button"
              class="secondary-button"
              @click="showAllSessions = !showAllSessions"
            >
              {{ showAllSessions ? 'Top 5' : `View all (${topSessionRows.length})` }}
            </button>
          </div>

          <ScrollableDataTable
            :empty="topSessionRows.length === 0"
            empty-message="No active/problem session telemetry exists in this selected window."
            max-height="24rem"
          >
            <template #header>
              <tr>
                <th>User / SID</th>
                <th>CPU</th>
                <th>Samples</th>
                <th>SQL ID</th>
                <th>Module / machine</th>
                <th>Wait / event</th>
                <th>Blocked by</th>
              </tr>
            </template>
            <tr v-for="row in visibleTopSessionRows" :key="row.key">
              <td>
                <strong>{{ row.username || 'UNKNOWN' }}</strong>
                <small>{{ row.sid }},{{ row.serial_number }}</small>
              </td>
              <td>{{ formatNumber(row.cpu_time_seconds, 3) }} s</td>
              <td>{{ row.samples }}</td>
              <td>{{ row.sql_id || '—' }}</td>
              <td>
                {{ row.module || '—' }}
                <small>{{ row.machine || '' }}</small>
              </td>
              <td>
                {{ row.wait_class || '—' }}
                <small>{{ row.event || '' }}</small>
              </td>
              <td>{{ row.blocking_session ?? '—' }}</td>
            </tr>
          </ScrollableDataTable>
        </section>

        <section class="history-detail-card history-two-column">
          <div>
            <div class="history-section-heading">
              <div>
                <h3>Top waits · selected window</h3>
                <p>Non-idle system wait deltas captured by the collector.</p>
              </div>
              <button
                v-if="topWaitRows.length > 5"
                type="button"
                class="secondary-button"
                @click="showAllWaits = !showAllWaits"
              >
                {{ showAllWaits ? 'Top 5' : `View all (${topWaitRows.length})` }}
              </button>
            </div>

            <ScrollableDataTable
              :empty="topWaitRows.length === 0"
              empty-message="No wait telemetry exists in this selected window."
              max-height="22rem"
            >
              <template #header>
                <tr>
                  <th>Event</th>
                  <th>Wait time</th>
                  <th>Waits</th>
                </tr>
              </template>
              <tr v-for="row in visibleTopWaitRows" :key="row.event">
                <td><strong>{{ row.event }}</strong></td>
                <td>{{ formatNumber(row.wait_time_seconds, 3) }} s</td>
                <td>{{ formatNumber(row.waits, 0) }}</td>
              </tr>
            </ScrollableDataTable>
          </div>

          <div>
            <div class="history-section-heading">
              <div>
                <h3>Latest storage snapshot</h3>
                <p>Most recent 5-minute Oracle storage sample inside the selected window.</p>
              </div>
            </div>

            <div v-if="!latestStorage" class="database-empty-state compact-history-empty">
              <p>No storage snapshot exists in this selected window.</p>
            </div>

            <template v-else>
              <div v-if="latestStorage.fra" class="history-fra-summary">
                <span>FRA</span>
                <strong>{{ formatNumber(latestStorage.fra.used_percent ?? 0, 1) }}%</strong>
                <small>
                  {{ formatBytes(latestStorage.fra.used_bytes) }} / {{ formatBytes(latestStorage.fra.limit_bytes) }}
                </small>
              </div>

              <ScrollableDataTable
                :empty="fullestTablespaces.length === 0"
                empty-message="No tablespace usage was available."
                max-height="22rem"
              >
                <template #header>
                  <tr>
                    <th>Tablespace</th>
                    <th>Status</th>
                    <th>Used</th>
                    <th>Capacity</th>
                    <th>Usage</th>
                  </tr>
                </template>
                <tr v-for="item in fullestTablespaces" :key="item.name">
                  <td><strong>{{ item.name }}</strong></td>
                  <td>{{ item.status || '—' }}</td>
                  <td>{{ formatBytes(item.used_bytes) }}</td>
                  <td>{{ formatBytes(item.capacity_bytes) }}</td>
                  <td>{{ formatNumber(item.used_percent ?? 0, 1) }}%</td>
                </tr>
              </ScrollableDataTable>
            </template>
          </div>
        </section>
      </template>
    </template>
  </section>
</template>

<style scoped>
.history-summary-grid {
  grid-template-columns: repeat(auto-fit, minmax(10rem, 1fr));
}

.history-summary-grid span {
  min-width: 0;
}

.history-summary-grid strong {
  overflow-wrap: anywhere;
}

.history-control-select {
  display: flex;
  flex-direction: column;
  gap: .3rem;
}

.history-control-label {
  color: var(--text-muted);
  font-size: .78rem;
  font-weight: 600;
}

.history-metric-control select {
  min-width: 15rem;
  max-width: 22rem;
  padding: .55rem 2rem .55rem .75rem;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-small);
  background: var(--color-surface);
  color: var(--color-text);
}

.history-reset-zoom {
  align-self: flex-end;
  margin-left: auto;
}

.history-chart-card,
.history-detail-card {
  margin-top: 1rem;
  border: 1px solid var(--border);
  border-radius: .85rem;
  padding: .9rem;
  background: var(--surface);
  min-width: 0;
}

.history-section-heading {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 1rem;
  margin-bottom: .7rem;
}

.history-section-heading h3,
.history-section-heading p {
  margin: 0;
}

.history-section-heading p {
  margin-top: .25rem;
  color: var(--text-muted);
  font-size: .88rem;
}

.history-two-column {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  gap: 1rem;
}

.history-sql-text {
  max-width: 30rem;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.history-fra-summary {
  display: grid;
  grid-template-columns: auto auto 1fr;
  gap: .65rem;
  align-items: baseline;
  border: 1px solid var(--border);
  border-radius: .7rem;
  padding: .65rem;
  margin-bottom: .7rem;
}

.history-fra-summary span,
.history-fra-summary small {
  color: var(--text-muted);
}

.compact-history-empty {
  min-height: 6rem;
}

:deep(td small) {
  display: block;
  color: var(--text-muted);
  margin-top: .15rem;
}

@media (max-width: 980px) {
  .history-two-column {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 680px) {
  .history-section-heading {
    flex-direction: column;
  }

  .history-metric-control,
  .history-metric-control select,
  .history-range-control label,
  .history-range-control select {
    width: 100%;
    max-width: none;
  }

  .history-range-control {
    align-items: stretch;
  }

  .history-reset-zoom {
    align-self: stretch;
    margin-left: 0;
  }
}
</style>
