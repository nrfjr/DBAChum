<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import VChart from 'vue-echarts'

import '@/charts/echarts'

import { hasPermission } from '@/core/permissions'
import { useAnalyticsStore, type DatabaseAnalyticsItem, type ServerAnalyticsItem } from '@/stores/analytics'
import { useAuthStore } from '@/stores/auth'
import { useConnectionsStore } from '@/stores/connections'
import { useSystemSettingsStore } from '@/stores/systemSettings'
import { useUiStore } from '@/stores/ui'
import { showToast } from '@/ui/feedback'

const route = useRoute()
const router = useRouter()
const analyticsStore = useAnalyticsStore()
const authStore = useAuthStore()
const connectionsStore = useConnectionsStore()
const systemSettingsStore = useSystemSettingsStore()
const uiStore = useUiStore()
const accentColor = ref('#7557c7')

const engine = ref('')
const osFamily = ref('')
const months = ref(12)
const importOpen = ref(false)
const importFile = ref<File | null>(null)
const importPreview = ref<Awaited<ReturnType<typeof analyticsStore.previewGrowth>> | null>(null)
const importLoading = ref(false)
const importError = ref<string | null>(null)
const databaseColumn = ref('')
const dateColumn = ref('')
const sizeColumn = ref('')
const unitColumn = ref('')
const defaultUnit = ref('GB')
const databaseMap = ref<Record<string, string>>({})

type SizeUnitChoice = 'auto' | 'MB' | 'GB' | 'TB'
type SizeChartKey = 'databaseSize' | 'growth' | 'backupSize' | 'oracleMemory' | 'serverDisk' | 'serverMemory'
const sizeUnits = reactive<Record<SizeChartKey, SizeUnitChoice>>({
  databaseSize: 'auto',
  growth: 'auto',
  backupSize: 'auto',
  oracleMemory: 'auto',
  serverDisk: 'auto',
  serverMemory: 'auto',
})
const sizeUnitOptions: { value: SizeUnitChoice; label: string }[] = [
  { value: 'auto', label: 'Auto' },
  { value: 'MB', label: 'MB' },
  { value: 'GB', label: 'GB' },
  { value: 'TB', label: 'TB' },
]

const mode = computed<'databases' | 'servers'>(() => String(route.query.type ?? '') === 'servers' ? 'servers' : 'databases')
const canImport = computed(() => hasPermission(authStore.user, 'connections:manage'))
const databaseData = computed(() => analyticsStore.databases)
const serverData = computed(() => analyticsStore.servers)

const engineOptions = [
  { value: '', label: 'All engines' },
  { value: 'oracle', label: 'Oracle' },
  { value: 'sqlserver', label: 'SQL Server' },
  { value: 'mysql', label: 'MySQL / MariaDB' },
]

const osOptions = [
  { value: '', label: 'All operating systems' },
  { value: 'linux', label: 'Linux' },
  { value: 'windows', label: 'Windows' },
  { value: 'aix', label: 'AIX' },
  { value: 'unix', label: 'Unix' },
  { value: 'other', label: 'Other' },
]

function bytes(value: number | null | undefined) {
  if (value == null || !Number.isFinite(value)) return '—'
  const units = ['B', 'KB', 'MB', 'GB', 'TB', 'PB']
  let size = Math.max(value, 0)
  let index = 0
  while (size >= 1024 && index < units.length - 1) {
    size /= 1024
    index += 1
  }
  const digits = index >= 3 ? 1 : size >= 100 ? 0 : 1
  return `${size.toFixed(digits)} ${units[index]}`
}

function percent(value: number | null | undefined) {
  return value == null || !Number.isFinite(value) ? '—' : `${value.toFixed(1)}%`
}

function ageLabel(days: number | null | undefined) {
  if (days == null || !Number.isFinite(days)) return 'No recent backup data'
  if (days < 1 / 24) return 'Less than 1 hour ago'
  if (days < 1) return `${Math.max(1, Math.round(days * 24))}h ago`
  return `${Math.round(days)}d ago`
}

function engineLabel(value: string) {
  return { oracle: 'Oracle', sqlserver: 'SQL Server', mysql: 'MySQL / MariaDB' }[value] ?? value
}

function osLabel(value: string) {
  return { linux: 'Linux', windows: 'Windows', aix: 'AIX', unix: 'Unix', other: 'Other' }[value] ?? value
}

const SIZE_FACTORS = { MB: 1024 ** 2, GB: 1024 ** 3, TB: 1024 ** 4 } as const

type FixedSizeUnit = keyof typeof SIZE_FACTORS

function resolveSizeUnit(choice: SizeUnitChoice, values: (number | null | undefined)[]): FixedSizeUnit {
  if (choice !== 'auto') return choice
  const max = Math.max(0, ...values.map((value) => Number(value ?? 0)))
  if (max >= SIZE_FACTORS.TB) return 'TB'
  if (max >= SIZE_FACTORS.GB) return 'GB'
  return 'MB'
}

function sizeInUnit(value: number | null | undefined, unit: FixedSizeUnit) {
  if (value == null || !Number.isFinite(value)) return '—'
  const converted = value / SIZE_FACTORS[unit]
  const digits = converted >= 100 ? 0 : converted >= 10 ? 1 : 2
  return `${converted.toFixed(digits)} ${unit}`
}

function rgbaAccent(alpha: number) {
  const value = accentColor.value.trim()
  const match = /^#([0-9a-f]{6})$/i.exec(value)
  if (!match) return value
  const hex = match[1]
  if (!hex) return value
  const r = Number.parseInt(hex.slice(0, 2), 16)
  const g = Number.parseInt(hex.slice(2, 4), 16)
  const b = Number.parseInt(hex.slice(4, 6), 16)
  return `rgba(${r}, ${g}, ${b}, ${alpha})`
}

function syncAccentColor() {
  accentColor.value = getComputedStyle(document.documentElement).getPropertyValue('--accent').trim() || '#7557c7'
}

function chartBase(useAccent = true) {
  return {
    animationDuration: 250,
    grid: { left: 18, right: 18, top: 20, bottom: 34, containLabel: true },
    tooltip: { trigger: 'axis' },
    ...(useAccent ? { color: [accentColor.value, rgbaAccent(.62), rgbaAccent(.38)] } : {}),
  }
}

const databaseSizeOption = computed(() => {
  const rows = [...(databaseData.value?.items ?? [])]
    .filter((item) => item.database_size_bytes != null)
    .sort((a, b) => Number(b.database_size_bytes ?? 0) - Number(a.database_size_bytes ?? 0))
  const values = rows.map((row) => row.database_size_bytes)
  const unit = resolveSizeUnit(sizeUnits.databaseSize, values)
  return {
    ...chartBase(),
    tooltip: { trigger: 'axis', valueFormatter: (value: number) => sizeInUnit(value, unit) },
    xAxis: { type: 'value', axisLabel: { formatter: (value: number) => sizeInUnit(value, unit) } },
    yAxis: { type: 'category', data: rows.map((row) => row.name), inverse: true },
    series: [{ type: 'bar', data: rows.map((row) => ({ value: row.database_size_bytes, connectionId: row.connection_id, engine: row.engine })) }],
  }
})

const databaseUtilizationOption = computed(() => {
  const rows = [...(databaseData.value?.items ?? [])]
    .filter((item) => item.storage_used_percent != null)
    .sort((a, b) => Number(b.storage_used_percent ?? 0) - Number(a.storage_used_percent ?? 0))
  return {
    ...chartBase(),
    xAxis: { type: 'value', min: 0, max: 100, axisLabel: { formatter: '{value}%' } },
    yAxis: { type: 'category', data: rows.map((row) => row.name), inverse: true },
    series: [{ type: 'bar', data: rows.map((row) => ({ value: row.storage_used_percent, connectionId: row.connection_id, engine: row.engine })) }],
  }
})

const backupRecencyOption = computed(() => {
  const rows = [...(databaseData.value?.items ?? [])]
    .filter((item) => item.last_backup_age_days != null)
    .sort((a, b) => Number(b.last_backup_age_days ?? 0) - Number(a.last_backup_age_days ?? 0))
  return {
    ...chartBase(),
    xAxis: { type: 'value', min: 0, name: 'Days' },
    yAxis: { type: 'category', data: rows.map((row) => row.name), inverse: true },
    series: [{ type: 'bar', data: rows.map((row) => ({ value: row.last_backup_age_days, connectionId: row.connection_id, engine: row.engine })) }],
  }
})

const backupSizeOption = computed(() => {
  const rows = [...(databaseData.value?.items ?? [])]
    .filter((item) => item.last_backup_size_bytes != null)
    .sort((a, b) => Number(b.last_backup_size_bytes ?? 0) - Number(a.last_backup_size_bytes ?? 0))
  const values = rows.map((row) => row.last_backup_size_bytes)
  const unit = resolveSizeUnit(sizeUnits.backupSize, values)
  return {
    ...chartBase(),
    tooltip: { trigger: 'axis', valueFormatter: (value: number) => sizeInUnit(value, unit) },
    xAxis: { type: 'value', axisLabel: { formatter: (value: number) => sizeInUnit(value, unit) } },
    yAxis: { type: 'category', data: rows.map((row) => row.name), inverse: true },
    series: [{ type: 'bar', data: rows.map((row) => ({ value: row.last_backup_size_bytes, connectionId: row.connection_id, engine: row.engine })) }],
  }
})

const growthOption = computed(() => {
  const points = databaseData.value?.growth ?? []
  const currentSizes = new Map((databaseData.value?.items ?? []).map((item) => [item.connection_id, Number(item.database_size_bytes ?? 0)]))
  const selectedIds = [...new Set(points.map((point) => point.connection_id))]
    .sort((a, b) => (currentSizes.get(b) ?? 0) - (currentSizes.get(a) ?? 0))
    .slice(0, 10)
  const monthsFound = [...new Set(points.filter((point) => selectedIds.includes(point.connection_id)).map((point) => point.month))].sort()
  const byTarget = new Map<string, Map<string, number>>()
  for (const point of points) {
    if (!selectedIds.includes(point.connection_id)) continue
    if (!byTarget.has(point.connection_id)) byTarget.set(point.connection_id, new Map())
    byTarget.get(point.connection_id)?.set(point.month, point.size_bytes)
  }
  const names = new Map(points.map((point) => [point.connection_id, point.name]))
  const engines = new Map((databaseData.value?.items ?? []).map((item) => [item.connection_id, item.engine]))
  const values = points.filter((point) => selectedIds.includes(point.connection_id)).map((point) => point.size_bytes)
  const unit = resolveSizeUnit(sizeUnits.growth, values)
  return {
    ...chartBase(false),
    tooltip: { trigger: 'axis', valueFormatter: (value: number) => sizeInUnit(value, unit) },
    legend: { type: 'scroll', top: 0 },
    grid: { left: 18, right: 18, top: 54, bottom: 34, containLabel: true },
    xAxis: { type: 'category', boundaryGap: false, data: monthsFound },
    yAxis: { type: 'value', axisLabel: { formatter: (value: number) => sizeInUnit(value, unit) } },
    series: selectedIds.map((id) => ({
      type: 'line',
      name: names.get(id) ?? id,
      connectNulls: false,
      showSymbol: true,
      data: monthsFound.map((month) => {
        const value = byTarget.get(id)?.get(month)
        return value == null ? null : { value, connectionId: id, engine: engines.get(id) }
      }),
    })),
  }
})

const engineDistributionOption = computed(() => ({
  ...chartBase(),
  xAxis: { type: 'category', data: (databaseData.value?.engine_distribution ?? []).map((item) => engineLabel(item.engine)) },
  yAxis: { type: 'value', minInterval: 1 },
  series: [{ type: 'bar', data: (databaseData.value?.engine_distribution ?? []).map((item) => item.count) }],
}))

const oracleMemoryOption = computed(() => {
  const rows = (databaseData.value?.items ?? []).filter((item) => item.engine === 'oracle' && (item.sga_bytes || item.pga_allocated_bytes))
  const values = rows.flatMap((row) => [row.sga_bytes, row.pga_allocated_bytes])
  const unit = resolveSizeUnit(sizeUnits.oracleMemory, values)
  return {
    ...chartBase(),
    tooltip: { trigger: 'axis', valueFormatter: (value: number) => sizeInUnit(value, unit) },
    legend: { top: 0 },
    grid: { left: 18, right: 18, top: 44, bottom: 34, containLabel: true },
    xAxis: { type: 'category', data: rows.map((row) => row.name) },
    yAxis: { type: 'value', axisLabel: { formatter: (value: number) => sizeInUnit(value, unit) } },
    series: [
      { type: 'bar', name: 'SGA', stack: 'memory', data: rows.map((row) => row.sga_bytes ?? 0) },
      { type: 'bar', name: 'PGA allocated', stack: 'memory', data: rows.map((row) => row.pga_allocated_bytes ?? 0) },
    ],
  }
})

const serverDiskCapacityOption = computed(() => {
  const rows = [...(serverData.value?.items ?? [])].filter((item) => item.disk_total_bytes != null).sort((a, b) => Number(b.disk_total_bytes ?? 0) - Number(a.disk_total_bytes ?? 0))
  const values = rows.map((row) => row.disk_total_bytes)
  const unit = resolveSizeUnit(sizeUnits.serverDisk, values)
  return {
    ...chartBase(),
    tooltip: { trigger: 'axis', valueFormatter: (value: number) => sizeInUnit(value, unit) },
    xAxis: { type: 'value', axisLabel: { formatter: (value: number) => sizeInUnit(value, unit) } },
    yAxis: { type: 'category', data: rows.map((row) => row.name), inverse: true },
    series: [{ type: 'bar', data: rows.map((row) => ({ value: row.disk_total_bytes, serverId: row.server_id, osFamily: row.os_family })) }],
  }
})

const serverDiskUsageOption = computed(() => {
  const rows = [...(serverData.value?.items ?? [])].filter((item) => item.disk_used_percent != null).sort((a, b) => Number(b.disk_used_percent ?? 0) - Number(a.disk_used_percent ?? 0))
  return {
    ...chartBase(),
    xAxis: { type: 'value', min: 0, max: 100, axisLabel: { formatter: '{value}%' } },
    yAxis: { type: 'category', data: rows.map((row) => row.name), inverse: true },
    series: [{ type: 'bar', data: rows.map((row) => ({ value: row.disk_used_percent, serverId: row.server_id, osFamily: row.os_family })) }],
  }
})

const serverMemoryCapacityOption = computed(() => {
  const rows = [...(serverData.value?.items ?? [])].filter((item) => item.memory_total_bytes != null).sort((a, b) => Number(b.memory_total_bytes ?? 0) - Number(a.memory_total_bytes ?? 0))
  const values = rows.map((row) => row.memory_total_bytes)
  const unit = resolveSizeUnit(sizeUnits.serverMemory, values)
  return {
    ...chartBase(),
    tooltip: { trigger: 'axis', valueFormatter: (value: number) => sizeInUnit(value, unit) },
    xAxis: { type: 'value', axisLabel: { formatter: (value: number) => sizeInUnit(value, unit) } },
    yAxis: { type: 'category', data: rows.map((row) => row.name), inverse: true },
    series: [{ type: 'bar', data: rows.map((row) => ({ value: row.memory_total_bytes, serverId: row.server_id, osFamily: row.os_family })) }],
  }
})

const serverMemoryOption = computed(() => {
  const rows = [...(serverData.value?.items ?? [])].filter((item) => item.memory_used_percent != null).sort((a, b) => Number(b.memory_used_percent ?? 0) - Number(a.memory_used_percent ?? 0))
  return {
    ...chartBase(),
    xAxis: { type: 'value', min: 0, max: 100, axisLabel: { formatter: '{value}%' } },
    yAxis: { type: 'category', data: rows.map((row) => row.name), inverse: true },
    series: [{ type: 'bar', data: rows.map((row) => ({ value: row.memory_used_percent, serverId: row.server_id, osFamily: row.os_family })) }],
  }
})

const serverCpuOption = computed(() => {
  const rows = [...(serverData.value?.items ?? [])].filter((item) => item.cpu_used_percent != null).sort((a, b) => Number(b.cpu_used_percent ?? 0) - Number(a.cpu_used_percent ?? 0))
  return {
    ...chartBase(),
    xAxis: { type: 'value', min: 0, max: 100, axisLabel: { formatter: '{value}%' } },
    yAxis: { type: 'category', data: rows.map((row) => row.name), inverse: true },
    series: [{ type: 'bar', data: rows.map((row) => ({ value: row.cpu_used_percent, serverId: row.server_id, osFamily: row.os_family })) }],
  }
})

const osDistributionOption = computed(() => ({
  ...chartBase(),
  xAxis: { type: 'category', data: (serverData.value?.os_distribution ?? []).map((item) => osLabel(item.os_family)) },
  yAxis: { type: 'value', minInterval: 1 },
  series: [{ type: 'bar', data: (serverData.value?.os_distribution ?? []).map((item) => item.count) }],
}))

function openDatabaseFromChart(params: any) {
  const data = params?.data
  if (!data?.connectionId) return
  void router.push({ path: `/databases/${data.connectionId}`, query: data.engine ? { engine: data.engine } : {} })
}

function openServerFromChart(params: any) {
  const data = params?.data
  if (!data?.serverId) return
  void router.push({ path: `/servers/${data.serverId}`, query: data.osFamily ? { os: data.osFamily } : {} })
}

function openDatabase(item: DatabaseAnalyticsItem) {
  void router.push({ path: `/databases/${item.connection_id}`, query: { engine: item.engine } })
}

function openServer(item: ServerAnalyticsItem) {
  void router.push({ path: `/servers/${item.server_id}`, query: { os: item.os_family } })
}

async function load() {
  if (mode.value === 'databases') await analyticsStore.loadDatabases(engine.value, months.value)
  else await analyticsStore.loadServers(osFamily.value, months.value)
}


function closeImport() {
  importOpen.value = false
  importFile.value = null
  importPreview.value = null
  importError.value = null
  databaseMap.value = {}
}

function chooseSuggestedColumn(headers: string[], names: string[]) {
  const lowered = headers.map((header) => ({ header, key: header.toLowerCase().replace(/[^a-z0-9]/g, '') }))
  return lowered.find((item) => names.some((name) => item.key.includes(name)))?.header ?? ''
}

async function handleImportFile(event: Event) {
  const file = (event.target as HTMLInputElement).files?.[0] ?? null
  importFile.value = file
  importPreview.value = null
  databaseMap.value = {}
  if (!file) return
  importLoading.value = true
  importError.value = null
  try {
    const preview = await analyticsStore.previewGrowth(file)
    importPreview.value = preview
    databaseColumn.value = chooseSuggestedColumn(preview.headers, ['database', 'dbname', 'db'])
    dateColumn.value = chooseSuggestedColumn(preview.headers, ['date', 'month', 'period', 'snapshot'])
    sizeColumn.value = chooseSuggestedColumn(preview.headers, ['size', 'allocated', 'total'])
    unitColumn.value = ''
    const values = preview.column_values[databaseColumn.value] ?? []
    const byName = new Map(connectionsStore.connections.map((connection) => [connection.name.toLowerCase(), connection.id]))
    databaseMap.value = Object.fromEntries(values.map((value) => [value, byName.get(value.toLowerCase()) ?? '']))
  } catch (error) {
    importError.value = error instanceof Error ? error.message : 'Unable to preview the file.'
  } finally {
    importLoading.value = false
  }
}

watch(databaseColumn, (column) => {
  if (!importPreview.value || !column) return
  const values = importPreview.value.column_values[column] ?? []
  const current = databaseMap.value
  const byName = new Map(connectionsStore.connections.map((connection) => [connection.name.toLowerCase(), connection.id]))
  databaseMap.value = Object.fromEntries(values.map((value) => [value, current[value] ?? byName.get(value.toLowerCase()) ?? '']))
})

async function submitImport() {
  if (!importFile.value || !importPreview.value) return
  importLoading.value = true
  importError.value = null
  try {
    const result = await analyticsStore.importGrowth(importFile.value, {
      database_column: databaseColumn.value,
      date_column: dateColumn.value,
      size_column: sizeColumn.value,
      unit_column: unitColumn.value,
      default_unit: defaultUnit.value,
      database_map: databaseMap.value,
    })
    showToast({ title: 'Growth history imported', message: `${result.imported} row${result.imported === 1 ? '' : 's'} imported · ${result.skipped} skipped`, tone: 'success' })
    closeImport()
    await analyticsStore.loadDatabases(engine.value, months.value)
  } catch (error) {
    importError.value = error instanceof Error ? error.message : 'Unable to import growth history.'
  } finally {
    importLoading.value = false
  }
}

watch([mode, engine, osFamily, months], () => { void load() })
watch([() => uiStore.accent, () => uiStore.resolvedTheme], syncAccentColor, { immediate: true })

onMounted(async () => {
  syncAccentColor()
  try {
    await systemSettingsStore.loadGeneral()
    months.value = systemSettingsStore.general?.default_analytics_months ?? months.value
  } catch {
  }
  await Promise.all([load(), canImport.value ? connectionsStore.load() : Promise.resolve()])
})
</script>

<template>
  <section class="analytics-report">
    <div class="analytics-report__toolbar">
      <div></div>

      <div class="analytics-report__filters">
        <label v-if="mode === 'databases'">
          <span>Engine</span>
          <select class="utility-select-input" v-model="engine">
            <option v-for="option in engineOptions" :key="option.value" :value="option.value">{{ option.label }}</option>
          </select>
        </label>
        <label v-else>
          <span>Operating system</span>
          <select class="utility-select-input" v-model="osFamily">
            <option v-for="option in osOptions" :key="option.value" :value="option.value">{{ option.label }}</option>
          </select>
        </label>
        <label v-if="mode === 'databases'">
          <span>Growth range</span>
          <select class="utility-select-input" v-model.number="months">
            <option :value="6">6 months</option>
            <option :value="12">12 months</option>
            <option :value="24">24 months</option>
            <option :value="36">36 months</option>
            <option :value="60">60 months</option>
          </select>
        </label>
        <button type="button" class="secondary-button" :disabled="analyticsStore.loading" @click="load">{{ analyticsStore.loading ? 'Refreshing…' : 'Refresh' }}</button>
      </div>
    </div>

    <p v-if="analyticsStore.error" class="login-error">{{ analyticsStore.error }}</p>

    <template v-if="mode === 'databases' && databaseData">
      <div class="analytics-summary-grid">
        <article class="analytics-summary-card"><span>Databases</span><strong>{{ databaseData.summary.database_count }}</strong><small>{{ databaseData.summary.online_count }} online · {{ databaseData.summary.unreachable_count }} unreachable</small></article>
        <article class="analytics-summary-card" title="Across the current filter"><span>Total database size</span><strong>{{ bytes(databaseData.summary.total_size_bytes) }}</strong></article>
        <article class="analytics-summary-card" title="Where the engine exposes used allocation"><span>Used data space</span><strong>{{ bytes(databaseData.summary.used_size_bytes) }}</strong></article>
        <article class="analytics-summary-card"><span>Report generated</span><strong>{{ new Date(databaseData.generated_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) }}</strong><small>{{ new Date(databaseData.generated_at).toLocaleDateString() }}</small></article>
      </div>

      <div class="analytics-report-grid">
        <article class="analytics-chart-card analytics-chart-card--wide">
          <header><div title="Current allocated database size across monitored targets."><h2>Database size</h2></div><label class="analytics-unit-select">Unit<select class="utility-select-input" v-model="sizeUnits.databaseSize"><option v-for="option in sizeUnitOptions" :key="option.value" :value="option.value">{{ option.label }}</option></select></label></header>
          <VChart v-if="databaseData.items.some((item) => item.database_size_bytes != null)" class="analytics-chart analytics-chart--tall" :option="databaseSizeOption" autoresize @click="openDatabaseFromChart" />
          <p v-else class="empty-state">Size telemetry has not been collected yet.</p>
        </article>

        <article class="analytics-chart-card analytics-chart-card--wide">
          <header><div title="Month-end size from DBAChum daily snapshots and imported history."><h2>Database Growth</h2></div><label class="analytics-unit-select">Unit<select class="utility-select-input" v-model="sizeUnits.growth"><option v-for="option in sizeUnitOptions" :key="option.value" :value="option.value">{{ option.label }}</option></select><button v-if="mode === 'databases' && canImport" type="button" class="secondary-button" @click="importOpen = true">Import</button></label></header>
          <VChart v-if="databaseData.growth.length" class="analytics-chart analytics-chart--tall" :option="growthOption" autoresize @click="openDatabaseFromChart" />
          <p v-else class="empty-state">Growth history begins after snapshots are collected or historical data is imported.</p>
        </article>

        <article class="analytics-chart-card">
          <header><div title="Used percentage where the engine exposes allocation and usage."><h2>Storage utilization</h2></div></header>
          <VChart v-if="databaseData.items.some((item) => item.storage_used_percent != null)" class="analytics-chart" :option="databaseUtilizationOption" autoresize @click="openDatabaseFromChart" />
          <p v-else class="empty-state">Storage utilization is not available yet.</p>
        </article>

        <article class="analytics-chart-card">
          <header><div title="Age of the latest backup discovered by the collector."><h2>Backup recency</h2></div></header>
          <VChart v-if="databaseData.items.some((item) => item.last_backup_age_days != null)" class="analytics-chart" :option="backupRecencyOption" autoresize @click="openDatabaseFromChart" />
          <p v-else class="empty-state">No backup history has been collected yet.</p>
        </article>

        <article class="analytics-chart-card">
          <header><div title="Most recent backup size where the engine/provider reports it."><h2>Latest backup size</h2></div><label class="analytics-unit-select">Unit<select class="utility-select-input" v-model="sizeUnits.backupSize"><option v-for="option in sizeUnitOptions" :key="option.value" :value="option.value">{{ option.label }}</option></select></label></header>
          <VChart v-if="databaseData.items.some((item) => item.last_backup_size_bytes != null)" class="analytics-chart" :option="backupSizeOption" autoresize @click="openDatabaseFromChart" />
          <p v-else class="empty-state">Backup size is unavailable for the current targets.</p>
        </article>

        <article class="analytics-chart-card">
          <header><div title="Configured monitored databases by engine."><h2>Engine distribution</h2></div></header>
          <VChart v-if="databaseData.engine_distribution.length" class="analytics-chart" :option="engineDistributionOption" autoresize />
          <p v-else class="empty-state">No monitored databases match this filter.</p>
        </article>

        <article v-if="engine === 'oracle'" class="analytics-chart-card analytics-chart-card--wide">
          <header><div title="SGA plus currently allocated PGA from the latest collected Oracle memory snapshot."><h2>Oracle memory footprint</h2></div><label class="analytics-unit-select">Unit<select class="utility-select-input" v-model="sizeUnits.oracleMemory"><option v-for="option in sizeUnitOptions" :key="option.value" :value="option.value">{{ option.label }}</option></select></label></header>
          <VChart v-if="databaseData.items.some((item) => item.sga_bytes || item.pga_allocated_bytes)" class="analytics-chart" :option="oracleMemoryOption" autoresize />
          <p v-else class="empty-state">Oracle memory telemetry has not been collected yet.</p>
        </article>
      </div>

      <section class="analytics-ranking-card">
        <header><div title="Latest collected state behind the report. Select a row to open the database workspace."><h2>Database estate</h2></div></header>
        <div class="analytics-ranking-list">
          <button v-for="item in databaseData.items" :key="item.connection_id" type="button" @click="openDatabase(item)">
            <span class="analytics-status-dot" :class="item.status === 'online' || item.status === 'limited' ? 'online' : item.status === 'unreachable' ? 'offline' : ''" />
            <strong>{{ item.name }}</strong>
            <span>{{ engineLabel(item.engine) }}</span>
            <span>{{ bytes(item.database_size_bytes) }}</span>
            <span>{{ percent(item.storage_used_percent) }} used</span>
            <span>{{ ageLabel(item.last_backup_age_days) }}</span>
          </button>
        </div>
      </section>
    </template>

    <template v-else-if="mode === 'servers' && serverData">
      <div class="analytics-summary-grid">
        <article class="analytics-summary-card"><span>Servers</span><strong>{{ serverData.summary.server_count }}</strong><small>{{ serverData.summary.online_count }} online · {{ serverData.summary.unreachable_count }} unreachable</small></article>
        <article class="analytics-summary-card"><span>Total storage</span><strong>{{ bytes(serverData.summary.total_disk_bytes) }}</strong><small>{{ bytes(serverData.summary.used_disk_bytes) }} used</small></article>
        <article class="analytics-summary-card" title="Across servers with telemetry"><span>Total memory</span><strong>{{ bytes(serverData.summary.total_memory_bytes) }}</strong></article>
        <article class="analytics-summary-card"><span>Report generated</span><strong>{{ new Date(serverData.generated_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) }}</strong><small>{{ new Date(serverData.generated_at).toLocaleDateString() }}</small></article>
      </div>

      <div class="analytics-report-grid">
        <article class="analytics-chart-card analytics-chart-card--wide">
          <header><div title="Total mounted filesystem capacity visible to DBAChum."><h2>Disk capacity</h2></div><label class="analytics-unit-select">Unit<select class="utility-select-input" v-model="sizeUnits.serverDisk"><option v-for="option in sizeUnitOptions" :key="option.value" :value="option.value">{{ option.label }}</option></select></label></header>
          <VChart v-if="serverData.items.some((item) => item.disk_total_bytes != null)" class="analytics-chart analytics-chart--tall" :option="serverDiskCapacityOption" autoresize @click="openServerFromChart" />
          <p v-else class="empty-state">Disk capacity telemetry has not been collected yet.</p>
        </article>
        <article class="analytics-chart-card">
          <header><div title="Aggregate used percentage across collected filesystems."><h2>Disk utilization</h2></div></header>
          <VChart v-if="serverData.items.some((item) => item.disk_used_percent != null)" class="analytics-chart" :option="serverDiskUsageOption" autoresize @click="openServerFromChart" />
          <p v-else class="empty-state">Disk utilization is not available yet.</p>
        </article>
        <article class="analytics-chart-card">
          <header><div title="Total physical memory reported by each monitored server."><h2>Memory capacity</h2></div><label class="analytics-unit-select">Unit<select class="utility-select-input" v-model="sizeUnits.serverMemory"><option v-for="option in sizeUnitOptions" :key="option.value" :value="option.value">{{ option.label }}</option></select></label></header>
          <VChart v-if="serverData.items.some((item) => item.memory_total_bytes != null)" class="analytics-chart" :option="serverMemoryCapacityOption" autoresize @click="openServerFromChart" />
          <p v-else class="empty-state">Memory capacity telemetry is not available yet.</p>
        </article>
        <article class="analytics-chart-card">
          <header><div title="Latest collected memory usage by server."><h2>Memory utilization</h2></div></header>
          <VChart v-if="serverData.items.some((item) => item.memory_used_percent != null)" class="analytics-chart" :option="serverMemoryOption" autoresize @click="openServerFromChart" />
          <p v-else class="empty-state">Memory telemetry is not available yet.</p>
        </article>
        <article class="analytics-chart-card">
          <header><div title="Latest collected CPU utilization by server."><h2>CPU utilization</h2></div></header>
          <VChart v-if="serverData.items.some((item) => item.cpu_used_percent != null)" class="analytics-chart" :option="serverCpuOption" autoresize @click="openServerFromChart" />
          <p v-else class="empty-state">CPU telemetry is not available yet.</p>
        </article>
        <article class="analytics-chart-card">
          <header><div title="Managed servers by operating-system family."><h2>OS distribution</h2></div></header>
          <VChart v-if="serverData.os_distribution.length" class="analytics-chart" :option="osDistributionOption" autoresize />
          <p v-else class="empty-state">No server assets match this filter.</p>
        </article>
      </div>

      <section class="analytics-ranking-card">
        <header><div title="Latest collected state behind the report. Select a row to open the server workspace."><h2>Server estate</h2></div></header>
        <div class="analytics-ranking-list">
          <button v-for="item in serverData.items" :key="item.server_id" type="button" @click="openServer(item)">
            <span class="analytics-status-dot" :class="item.status === 'online' || item.status === 'limited' ? 'online' : item.status === 'unreachable' ? 'offline' : ''" />
            <strong>{{ item.name }}</strong>
            <span>{{ osLabel(item.os_family) }}{{ item.os_version ? ` · ${item.os_version}` : '' }}</span>
            <span>{{ bytes(item.disk_total_bytes) }} disk</span>
            <span>{{ percent(item.memory_used_percent) }} memory</span>
            <span>{{ percent(item.cpu_used_percent) }} CPU</span>
          </button>
        </div>
      </section>
    </template>

    <p v-if="analyticsStore.loading && !(databaseData || serverData)" class="empty-state">Loading analytics…</p>
  </section>

  <div v-if="importOpen" class="modal-backdrop" @click.self="closeImport">
    <section class="modal-panel analytics-import-modal" role="dialog" aria-modal="true" aria-label="Import database growth history">
      <div class="modal-header"><div title="Map historical CSV/XLSX database-size rows to existing DBAChum database connections."><h2>Import database growth history</h2></div><button type="button" class="modal-close" @click="closeImport">×</button></div>
      <div class="analytics-import-body">
        <label class="analytics-import-file-field">
          <span class="field-label">CSV or XLSX file <span class="required-mark" aria-hidden="true">*</span></span>
          <input type="file" accept=".csv,.xlsx,.xlsm" required @change="handleImportFile" />
        </label>
        <p v-if="importLoading && !importPreview">Reading file…</p>
        <p v-if="importError" class="login-error">{{ importError }}</p>
        <template v-if="importPreview">
          <p class="notice-card">{{ importPreview.row_count }} data rows detected. Imported dates are normalized to daily snapshots and will join system growth history.</p>
          <div class="analytics-import-column-grid">
            <label>
              <span class="field-label">Database name column <span class="required-mark" aria-hidden="true">*</span></span>
              <select v-model="databaseColumn" required><option value="" disabled>Select column</option><option v-for="header in importPreview.headers" :key="header" :value="header">{{ header }}</option></select>
            </label>
            <label>
              <span class="field-label">Date/month column <span class="required-mark" aria-hidden="true">*</span></span>
              <select v-model="dateColumn" required><option value="" disabled>Select column</option><option v-for="header in importPreview.headers" :key="header" :value="header">{{ header }}</option></select>
            </label>
            <label>
              <span class="field-label">Size column <span class="required-mark" aria-hidden="true">*</span></span>
              <select v-model="sizeColumn" required><option value="" disabled>Select column</option><option v-for="header in importPreview.headers" :key="header" :value="header">{{ header }}</option></select>
            </label>
            <label>
              <span>Unit column <span class="optional-label">Optional</span></span>
              <select v-model="unitColumn"><option value="">Use one default unit</option><option v-for="header in importPreview.headers" :key="header" :value="header">{{ header }}</option></select>
            </label>
          </div>
          <label v-if="!unitColumn" class="analytics-import-default-unit">
            <span class="field-label">Default size unit <span class="required-mark" aria-hidden="true">*</span></span>
            <select v-model="defaultUnit" required><option>MB</option><option>GB</option><option>TB</option><option>Bytes</option></select>
          </label>
          <div class="analytics-import-mapping" title="Only mapped source names are imported. Exact connection-name matches are selected automatically.">
            <h3>Database mapping</h3>
            <label v-for="sourceName in importPreview.column_values[databaseColumn] ?? []" :key="sourceName">
              <span>{{ sourceName }}</span>
              <select v-model="databaseMap[sourceName]"><option value="">Skip this database</option><option v-for="connection in connectionsStore.connections" :key="connection.id" :value="connection.id">{{ connection.name }} · {{ engineLabel(connection.engine) }}</option></select>
            </label>
          </div>
        </template>
      </div>
      <div class="connection-form-actions"><button type="button" class="primary-button" :disabled="!importPreview || !databaseColumn || !dateColumn || !sizeColumn || importLoading" @click="submitImport">{{ importLoading ? 'Importing…' : 'Import history' }}</button><button type="button" class="secondary-button" @click="closeImport">Cancel</button></div>
    </section>
  </div>
</template>

<style scoped>
.analytics-report { display: grid; gap: 1rem; min-width: 0; }
.analytics-report__toolbar { display: flex; align-items: end; justify-content: space-between; gap: 1rem; flex-wrap: wrap; }
.analytics-report__identity { display: grid; gap: .15rem; }
.analytics-report__identity strong { font-size: 1rem; }
.analytics-report__identity span { color: var(--text-muted); font-size: .75rem; }
.analytics-unit-select { display: flex; align-items: center; gap: .4rem; color: var(--text-muted); font-size: .72rem; white-space: nowrap; }
.analytics-unit-select select { min-width: 5rem; min-height: 2rem; }
.analytics-report__filters { display: flex; align-items: end; justify-content: flex-end; gap: .65rem; flex-wrap: wrap; }
.analytics-report__filters label { display: grid; gap: .3rem; min-width: 9rem; color: var(--text-muted); font-size: .75rem; }
.analytics-report__filters select { min-height: 2.35rem; }
.analytics-summary-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: .75rem; }
.analytics-summary-card { display: grid; gap: .25rem; padding: 1rem; border: 1px solid var(--border); border-radius: 12px; background: var(--surface); }
.analytics-summary-card span, .analytics-summary-card small { color: var(--text-muted); }
.analytics-summary-card strong { font-size: 1.45rem; }
.analytics-report-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: .85rem; min-width: 0; }
.analytics-chart-card, .analytics-ranking-card { min-width: 0; padding: 1rem; border: 1px solid var(--border); border-radius: 12px; background: var(--surface); }
.analytics-chart-card--wide { grid-column: 1 / -1; }
.analytics-chart-card header, .analytics-ranking-card header { display: flex; justify-content: space-between; gap: 1rem; margin-bottom: .75rem; }
.analytics-chart-card h2, .analytics-ranking-card h2 { margin: 0; font-size: 1rem; }
.analytics-chart-card p, .analytics-ranking-card p { margin: .2rem 0 0; color: var(--text-muted); font-size: .82rem; }
.analytics-chart { width: 100%; height: 21rem; }
.analytics-chart--tall { height: 25rem; }
.analytics-ranking-list { display: grid; }
.analytics-ranking-list button { display: grid; grid-template-columns: auto minmax(10rem, 1.3fr) minmax(8rem, 1fr) repeat(3, minmax(7rem, .8fr)); align-items: center; gap: .75rem; min-width: 0; padding: .7rem .25rem; border: 0; border-bottom: 1px solid var(--border); background: transparent; color: inherit; text-align: left; cursor: pointer; }
.analytics-ranking-list button:last-child { border-bottom: 0; }
.analytics-ranking-list button:hover { background: var(--surface-hover); }
.analytics-ranking-list button span:not(.analytics-status-dot) { color: var(--text-muted); font-size: .8rem; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.analytics-status-dot { width: .55rem; height: .55rem; border-radius: 50%; background: var(--text-muted); opacity: .55; }
.analytics-status-dot.online { background: #27b36a; opacity: 1; }
.analytics-status-dot.offline { background: #d85151; opacity: 1; }
.analytics-import-modal { width: min(100%, 900px); }
.analytics-import-body { display: grid; gap: .85rem; max-height: 65vh; overflow: auto; padding: .25rem .15rem; }
.analytics-import-body > label, .analytics-import-mapping label { display: grid; gap: .35rem; }
.analytics-import-mapping { display: grid; gap: .55rem; }
.analytics-import-mapping h3 { margin: .25rem 0 0; }
.analytics-import-mapping p { margin: 0 0 .25rem; color: var(--text-muted); }
.analytics-import-mapping label { grid-template-columns: minmax(9rem, .8fr) minmax(12rem, 1.2fr); align-items: center; }
@media (max-width: 1000px) { .analytics-summary-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } .analytics-ranking-list button { grid-template-columns: auto minmax(9rem, 1fr) minmax(8rem, 1fr) minmax(7rem, 1fr); } .analytics-ranking-list button span:nth-last-child(-n+2) { display: none; } }
@media (max-width: 720px) { .analytics-report-grid { grid-template-columns: 1fr; } .analytics-chart-card--wide { grid-column: auto; } .analytics-summary-grid { grid-template-columns: 1fr 1fr; } .analytics-report__filters { justify-content: flex-start; } .analytics-ranking-list { overflow-x: auto; } .analytics-ranking-list button { min-width: 42rem; } .analytics-import-mapping label { grid-template-columns: 1fr; } }
</style>
