<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'

import ScrollableDataTable from '@/components/common/ScrollableDataTable.vue'
import {
  useOracleDbaStore,
  type OracleAdvisorCandidate,
  type OracleAdvisorSection,
} from '@/stores/oracleDba'

const props = defineProps<{ connectionId: string }>()
const oracleStore = useOracleDbaStore()
const selectedKey = ref('')
const selectedCandidate = ref<OracleAdvisorCandidate | null>(null)

const result = computed(() => oracleStore.advisors[props.connectionId] ?? null)
const sections = computed(() => result.value?.sections ?? [])
const availableSections = computed(() => sections.value.filter((section) => section.available && section.items.length))
const selectedSection = computed<OracleAdvisorSection | null>(() =>
  sections.value.find((section) => section.key === selectedKey.value) ?? null,
)
const currentCandidate = computed(() =>
  selectedSection.value?.items.find((item) => item.current) ?? null,
)

interface AdvisorColumn {
  key: string
  label: string
  format: (item: OracleAdvisorCandidate) => string
}

const columns = computed<AdvisorColumn[]>(() => {
  switch (selectedSection.value?.key) {
    case 'sga':
      return [
        { key: 'db-time', label: 'DB Time', format: (item) => formatCount(item.estimated_db_time) },
        { key: 'db-time-factor', label: 'DB Time Factor', format: (item) => formatFactor(item.estimated_db_time_factor) },
        { key: 'reads', label: 'Physical Reads', format: (item) => formatCount(item.estimated_physical_reads) },
      ]
    case 'pga':
      return [
        { key: 'cache-hit', label: 'Cache Hit', format: (item) => formatPercent(item.estimated_cache_hit_percent) },
        { key: 'extra-io', label: 'Extra I/O', format: (item) => formatBytes(item.estimated_extra_bytes_rw) },
        { key: 'overalloc', label: 'Overalloc', format: (item) => formatCount(item.estimated_overalloc_count) },
      ]
    case 'buffer_cache':
      return [
        { key: 'reads', label: 'Physical Reads', format: (item) => formatCount(item.estimated_physical_reads) },
        { key: 'read-factor', label: 'Read Factor', format: (item) => formatFactor(item.estimated_physical_read_factor) },
      ]
    case 'shared_pool':
    case 'java_pool':
      return [
        { key: 'load-time', label: 'Load Time', format: (item) => formatDuration(item.estimated_lc_load_time) },
        { key: 'load-factor', label: 'Load Factor', format: (item) => formatFactor(item.estimated_lc_load_time_factor) },
        { key: 'time-saved', label: 'Time Saved', format: (item) => formatDuration(item.estimated_lc_time_saved) },
      ]
    case 'memory_target':
      return [
        { key: 'db-time', label: 'DB Time', format: (item) => formatCount(item.estimated_db_time) },
        { key: 'db-time-factor', label: 'DB Time Factor', format: (item) => formatFactor(item.estimated_db_time_factor) },
      ]
    case 'streams_pool':
      return [
        { key: 'spills', label: 'Spills', format: (item) => formatCount(item.estimated_spill_count) },
        { key: 'unspills', label: 'Unspills', format: (item) => formatCount(item.estimated_unspill_count) },
        { key: 'spill-time', label: 'Spill Time', format: (item) => formatDuration(totalSpillTime(item)) },
      ]
    case 'mttr':
      return [
        { key: 'cache-writes', label: 'Cache Writes', format: (item) => formatCount(item.estimated_cache_writes) },
        { key: 'total-writes', label: 'Total Writes', format: (item) => formatCount(item.estimated_total_writes) },
        { key: 'total-io', label: 'Total I/O', format: (item) => formatCount(item.estimated_total_ios) },
      ]
    default:
      return []
  }
})

const comparison = computed(() => {
  const current = currentCandidate.value
  const selected = selectedCandidate.value
  if (!current || !selected) return null
  if (selected.current) {
    return { primary: 'Baseline', secondary: '' }
  }

  switch (selectedSection.value?.key) {
    case 'sga':
    case 'memory_target':
      return {
        primary: formatReduction(current.estimated_db_time, selected.estimated_db_time),
        secondary: 'DB time',
      }
    case 'pga':
      return {
        primary: formatPointChange(current.estimated_cache_hit_percent, selected.estimated_cache_hit_percent),
        secondary: `${formatReduction(current.estimated_extra_bytes_rw, selected.estimated_extra_bytes_rw)} extra I/O`,
      }
    case 'buffer_cache':
      return {
        primary: formatReduction(current.estimated_physical_reads, selected.estimated_physical_reads),
        secondary: 'physical reads',
      }
    case 'shared_pool':
    case 'java_pool':
      return {
        primary: formatReduction(current.estimated_lc_load_time, selected.estimated_lc_load_time),
        secondary: 'load time',
      }
    case 'streams_pool':
      return {
        primary: formatReduction(totalSpillTime(current), totalSpillTime(selected)),
        secondary: 'spill time',
      }
    case 'mttr':
      return {
        primary: formatReduction(current.estimated_total_ios, selected.estimated_total_ios),
        secondary: 'total I/O',
      }
    default:
      return { primary: '—', secondary: '' }
  }
})

function totalSpillTime(item: OracleAdvisorCandidate) {
  if (item.estimated_spill_time == null && item.estimated_unspill_time == null) return null
  return Number(item.estimated_spill_time ?? 0) + Number(item.estimated_unspill_time ?? 0)
}

function formatCount(value: number | null) {
  return value == null ? '—' : new Intl.NumberFormat().format(value)
}

function formatPercent(value: number | null) {
  return value == null ? '—' : `${value.toFixed(1)}%`
}

function formatFactor(value: number | null) {
  return value == null ? '—' : `${value.toFixed(2)}×`
}

function formatDuration(value: number | null) {
  if (value == null) return '—'
  if (value >= 3600) return `${(value / 3600).toFixed(1)} h`
  if (value >= 60) return `${(value / 60).toFixed(1)} min`
  return `${value.toFixed(value >= 10 ? 0 : 1)} s`
}

function formatBytes(value: number | null) {
  if (value == null) return '—'
  const units = ['B', 'KB', 'MB', 'GB', 'TB', 'PB']
  let size = Math.max(value, 0)
  let unit = 0
  while (size >= 1024 && unit < units.length - 1) {
    size /= 1024
    unit += 1
  }
  return `${size.toFixed(size >= 100 || unit === 0 ? 0 : 1)} ${units[unit]}`
}

function formatMemory(value: number | null) {
  if (value == null) return '—'
  if (value >= 1024) return `${(value / 1024).toFixed(value >= 10240 ? 0 : 1)} GB`
  return `${value.toFixed(value >= 100 ? 0 : 1)} MB`
}

function formatTarget(item: OracleAdvisorCandidate) {
  if (selectedSection.value?.key === 'mttr') {
    return item.mttr_target_seconds == null ? '—' : `${item.mttr_target_seconds} s`
  }
  return formatMemory(item.size_mb)
}

function targetChange(item: OracleAdvisorCandidate) {
  const current = currentCandidate.value
  if (!current) return '—'
  if (item.current) return 'Current'

  if (selectedSection.value?.key === 'mttr') {
    if (item.mttr_target_seconds == null || current.mttr_target_seconds == null) return '—'
    const delta = item.mttr_target_seconds - current.mttr_target_seconds
    return `${delta > 0 ? '+' : ''}${delta} s`
  }

  if (item.size_mb == null || current.size_mb == null) return '—'
  const delta = item.size_mb - current.size_mb
  const sign = delta > 0 ? '+' : delta < 0 ? '-' : ''
  return `${sign}${formatMemory(Math.abs(delta))}`
}

function formatReduction(current: number | null, selected: number | null) {
  if (current == null || selected == null || current === 0) return '—'
  const value = ((current - selected) / current) * 100
  return `${value > 0 ? '+' : ''}${value.toFixed(1)}%`
}

function formatPointChange(current: number | null, selected: number | null) {
  if (current == null || selected == null) return '—'
  const value = selected - current
  return `${value > 0 ? '+' : ''}${value.toFixed(1)} pp`
}

function selectCandidate(item: OracleAdvisorCandidate) {
  selectedCandidate.value = item
}

function syncSelection() {
  const selected = sections.value.find((section) => section.key === selectedKey.value)
  if (!selected?.available || !selected.items.length) {
    selectedKey.value = availableSections.value[0]?.key ?? ''
  }
  selectedCandidate.value = null
}

async function refresh() {
  await oracleStore.loadAdvisors(props.connectionId)
  syncSelection()
}

watch(selectedKey, () => {
  selectedCandidate.value = null
})

watch(
  () => props.connectionId,
  () => {
    selectedKey.value = ''
    selectedCandidate.value = null
    void refresh()
  },
)

onMounted(() => {
  void refresh()
})
</script>

<template>
  <section class="oracle-advisor-panel">
    <div class="utility-toolbar">
      <div>
        <h2>Advisor</h2>
      </div>
      <div class="advisor-toolbar-actions">
        <select v-model="selectedKey" class="utility-select-input" :disabled="oracleStore.loadingAdvisors || sections.length === 0">
          <option v-for="section in sections" :key="section.key" :value="section.key" :disabled="!section.available">
            {{ section.label }}{{ section.available ? '' : ' — unavailable' }}
          </option>
        </select>
        <button type="button" class="secondary-button refresh-button" :disabled="oracleStore.loadingAdvisors" @click="refresh">
          {{ oracleStore.loadingAdvisors ? 'Refreshing' : 'Refresh' }}
          <p v-if="oracleStore.loadingAdvisors" class="loading"></p>
        </button>
      </div>
    </div>

    <p v-if="oracleStore.advisorsError" class="login-error">{{ oracleStore.advisorsError }}</p>

    <div v-if="oracleStore.loadingAdvisors && !result" class="advisor-state">Loading...</div>
    <div v-else-if="result && !result.available" class="advisor-state">No advisor data available.</div>

    <template v-else-if="selectedSection">
      <ScrollableDataTable
        :empty="selectedSection.items.length === 0"
        empty-message="No advisor data available."
        max-height="38rem"
        :paginate="false"
      >
        <template #header>
          <tr>
            <th>{{ selectedSection.key === 'mttr' ? 'Target' : 'Size' }}</th>
            <th>Change</th>
            <th v-for="column in columns" :key="column.key">{{ column.label }}</th>
          </tr>
        </template>
        <tr
          v-for="(item, index) in selectedSection.items"
          :key="`${selectedSection.key}-${item.size_mb ?? item.mttr_target_seconds ?? index}`"
          class="advisor-row"
          :class="{ 'advisor-row--current': item.current, 'advisor-row--selected': selectedCandidate === item }"
          @click="selectCandidate(item)"
        >
          <td>
            <strong>{{ formatTarget(item) }}</strong>
            <span v-if="item.current" class="advisor-current-label">Current</span>
          </td>
          <td>{{ targetChange(item) }}</td>
          <td v-for="column in columns" :key="column.key">{{ column.format(item) }}</td>
        </tr>
      </ScrollableDataTable>

      <div v-if="selectedCandidate && currentCandidate && comparison" class="utility-summary advisor-comparison">
        <div>
          <span>Current</span>
          <strong>{{ formatTarget(currentCandidate) }}</strong>
        </div>
        <div>
          <span>Selected</span>
          <strong>{{ formatTarget(selectedCandidate) }}</strong>
        </div>
        <div>
          <span>Change</span>
          <strong>{{ targetChange(selectedCandidate) }}</strong>
        </div>
        <div>
          <span>Benefit</span>
          <strong>{{ comparison.primary }}</strong>
          <small v-if="comparison.secondary">{{ comparison.secondary }}</small>
        </div>
      </div>
    </template>
  </section>
</template>

<style scoped>
.oracle-advisor-panel {
  width: 100%;
}

.advisor-state {
  padding: 1rem;
  border: 1px dashed var(--border);
  border-radius: .75rem;
  color: var(--text-muted);
}

.advisor-toolbar-actions {
  display: flex;
  align-items: center;
  gap: .65rem;
}

.advisor-row {
  cursor: pointer;
}

.advisor-row--current > td {
  background: color-mix(in srgb, var(--accent) 5%, transparent);
}

.advisor-row--selected > td {
  background: color-mix(in srgb, var(--accent) 10%, transparent);
}

.advisor-current-label {
  display: block;
  margin-top: .2rem;
  color: var(--accent);
  font-size: .75rem;
}

.advisor-comparison {
  margin-top: .25rem;
}

.advisor-comparison span,
.advisor-comparison small {
  color: var(--text-muted);
}

@media (max-width: 720px) {
  .advisor-state {
  padding: 1rem;
  border: 1px dashed var(--border);
  border-radius: .75rem;
  color: var(--text-muted);
}

.advisor-toolbar-actions {
    width: 100%;
    align-items: stretch;
    flex-direction: column;
  }

  .advisor-toolbar-actions .utility-select-input {
    width: 100%;
  }
}
</style>
