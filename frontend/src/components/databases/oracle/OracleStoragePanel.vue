<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import VChart from 'vue-echarts'

import '@/charts/echarts'

import ScrollableDataTable from '@/components/common/ScrollableDataTable.vue'
import FloatingActionMenu from '@/components/common/FloatingActionMenu.vue'
import { hasPermission } from '@/core/permissions'
import { useAuthStore } from '@/stores/auth'
import { useAnalyticsStore } from '@/stores/analytics'
import { useDatabaseOperationsStore } from '@/stores/databaseOperations'
import { useOracleDbaStore, type OracleDatafile } from '@/stores/oracleDba'
import { formDialog, showToast } from '@/ui/feedback'

const props = defineProps<{ connectionId: string }>()
const oracleStore = useOracleDbaStore()
const operations = useDatabaseOperationsStore()
const authStore = useAuthStore()
const analyticsStore = useAnalyticsStore()
const storage = computed(() => oracleStore.storage[props.connectionId])
const canOperate = computed(() => hasPermission(authStore.user, 'database:operate'))
const selectedTablespaceName = ref<string | null>(null)
const selectedTablespace = computed(() =>
  storage.value?.tablespaces.find((item) => item.name === selectedTablespaceName.value) ?? null,
)
const selectedDatafiles = computed(() =>
  (storage.value?.datafiles ?? []).filter((file) => file.tablespace_name === selectedTablespaceName.value),
)
const trendDays = ref(90)
const trendLoading = ref(false)
const trendError = ref<string | null>(null)
const growthData = computed(() => analyticsStore.tablespaceGrowth[props.connectionId] ?? null)
const selectedGrowthSeries = computed(() =>
  growthData.value?.series.find((item) => item.name === selectedTablespaceName.value) ?? null,
)
const selectedAllocatedBytes = computed(() =>
  selectedDatafiles.value.reduce((sum, file) => sum + Number(file.size_bytes || 0), 0),
)
const selectedHardMaxBytes = computed(() =>
  selectedDatafiles.value.reduce((sum, file) => {
    const size = Number(file.size_bytes || 0)
    const maximum = file.autoextensible && file.max_bytes != null
      ? Math.max(size, Number(file.max_bytes))
      : size
    return sum + maximum
  }, 0),
)

function formatBytes(bytes: number | null) {
  if (bytes == null) return '—'
  if (bytes === 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB', 'TB', 'PB']
  const index = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1)
  return `${(bytes / Math.pow(1024, index)).toFixed(1)} ${units[index]}`
}

function bytesToGb(value: number | null | undefined) {
  return value == null ? null : Number((value / 1024 / 1024 / 1024).toFixed(3))
}

async function loadTablespaceTrend() {
  trendLoading.value = true
  trendError.value = null
  try {
    await analyticsStore.loadOracleTablespaceGrowth(props.connectionId, trendDays.value)
  } catch (cause) {
    trendError.value = cause instanceof Error ? cause.message : 'Unable to load tablespace growth history.'
  } finally {
    trendLoading.value = false
  }
}

const tablespaceTrendOption = computed(() => {
  const points = selectedGrowthSeries.value?.points ?? []
  return {
    animation: false,
    tooltip: {
      trigger: 'axis',
      valueFormatter: (value: number) => `${Number(value).toFixed(2)} GB`,
    },
    legend: { data: ['Used', 'Allocated', 'Hard max'] },
    grid: { left: 62, right: 28, top: 48, bottom: 48 },
    xAxis: {
      type: 'category',
      boundaryGap: false,
      data: points.map((point) => point.day),
    },
    yAxis: {
      type: 'value',
      name: 'GB',
      min: 0,
    },
    series: [
      {
        name: 'Used',
        type: 'line',
        smooth: true,
        symbol: 'circle',
        data: points.map((point) => bytesToGb(point.used_bytes)),
      },
      {
        name: 'Allocated',
        type: 'line',
        smooth: true,
        symbol: 'none',
        data: points.map((point) => bytesToGb(point.allocated_bytes ?? point.capacity_bytes)),
      },
      {
        name: 'Hard max',
        type: 'line',
        smooth: true,
        symbol: 'none',
        lineStyle: { type: 'dashed' },
        data: points.map((point) => bytesToGb(point.max_bytes)),
      },
    ],
  }
})

async function resizeDatafile(file: OracleDatafile) {
  const currentMb = Math.round(file.size_bytes / 1024 / 1024)
  const result = await formDialog({
    title: 'Resize Oracle datafile',
    message: `${file.file_name} · current size ${formatBytes(file.size_bytes)}`,
    confirmLabel: 'Resize datafile',
    fields: [
      {
        name: 'size_mb',
        label: 'New size',
        type: 'size-gb',
        value: currentMb,
        presetsGb: [10, 20, 30],
        minMb: currentMb,
        hint: '',
      },
    ],
  })
  if (!result) return
  try {
    await operations.runStorage(props.connectionId, {
      action: 'resize_file',
      size_mb: Number(result.size_mb),
      file_id: file.file_id,
    })
    await oracleStore.loadStorage(props.connectionId)
    showToast({ title: 'Datafile resized', message: file.file_name, tone: 'success' })
  } catch (cause) {
    showToast({ title: 'Unable to resize datafile', message: cause instanceof Error ? cause.message : operations.error ?? undefined, tone: 'danger' })
  }
}

async function createTablespace() {
  const result = await formDialog({
    title: 'Create Oracle tablespace',
    message: '',
    confirmLabel: 'Create tablespace',
    fields: [
      { name: 'tablespace', label: 'Tablespace name', type: 'text', required: true, placeholder: 'USERS_DATA' },
      { name: 'physical_name', label: 'Initial datafile path', type: 'text', placeholder: '/u02/oradata/DB/users_data01.dbf' },
      { name: 'size_mb', label: 'Initial size', type: 'size-gb', value: 10240, presetsGb: [10, 20, 30] },
      {
        name: 'growth_mb', label: 'Autoextend NEXT', type: 'select', value: '128',
        options: [
          { label: '128 MB', value: '128' },
          { label: '256 MB', value: '256' },
          { label: '512 MB', value: '512' },
          { label: '1 GB', value: '1024' },
        ],
      },
      {
        name: 'max_size_mb', label: 'Maximum size', type: 'select', value: '',
        options: [
          { label: 'Unlimited', value: '' },
          { label: '20 GB', value: String(20 * 1024) },
          { label: '30 GB', value: String(30 * 1024) },
          { label: '50 GB', value: String(50 * 1024) },
        ],
      },
    ],
  })
  if (!result) return

  const sizeMb = Number(result.size_mb)
  const maxSizeMb = result.max_size_mb ? Number(result.max_size_mb) : null
  if (maxSizeMb != null && maxSizeMb < sizeMb) {
    showToast({ title: 'Maximum size is too small', message: 'MAXSIZE must be at least the initial datafile size.', tone: 'danger' })
    return
  }

  try {
    await operations.runStorage(props.connectionId, {
      action: 'create_tablespace',
      size_mb: sizeMb,
      tablespace_name: String(result.tablespace).trim(),
      physical_name: String(result.physical_name ?? '').trim() || null,
      autoextend: true,
      growth_mb: Number(result.growth_mb),
      max_size_mb: maxSizeMb,
    })
    await oracleStore.loadStorage(props.connectionId)
    showToast({ title: 'Tablespace created', message: String(result.tablespace), tone: 'success' })
  } catch (cause) {
    showToast({ title: 'Unable to create tablespace', message: cause instanceof Error ? cause.message : operations.error ?? undefined, tone: 'danger' })
  }
}

async function addDatafile(tablespace: string) {
  if (!tablespace) return
  const result = await formDialog({
    title: `Add datafile to ${tablespace}`,
    message: '',
    confirmLabel: 'Add datafile',
    fields: [
      { name: 'physical_name', label: 'Datafile path', type: 'text', placeholder: '/u02/oradata/DB/users_data02.dbf' },
      { name: 'size_mb', label: 'Initial size', type: 'size-gb', value: 10240, presetsGb: [10, 20, 30] },
      {
        name: 'growth_mb', label: 'Autoextend NEXT', type: 'select', value: '128',
        options: [
          { label: '128 MB', value: '128' },
          { label: '256 MB', value: '256' },
          { label: '512 MB', value: '512' },
          { label: '1 GB', value: '1024' },
        ],
      },
    ],
  })
  if (!result) return

  try {
    await operations.runStorage(props.connectionId, {
      action: 'add_file',
      size_mb: Number(result.size_mb),
      tablespace_name: tablespace,
      physical_name: String(result.physical_name ?? '').trim() || null,
      autoextend: true,
      growth_mb: Number(result.growth_mb),
    })
    await oracleStore.loadStorage(props.connectionId)
    showToast({ title: 'Datafile added', message: tablespace, tone: 'success' })
  } catch (cause) {
    showToast({ title: 'Unable to add datafile', message: cause instanceof Error ? cause.message : operations.error ?? undefined, tone: 'danger' })
  }
}

function inspectTablespace(name: string) {
  selectedTablespaceName.value = selectedTablespaceName.value === name ? null : name
}

watch(selectedTablespaceName, (name) => {
  if (name) void loadTablespaceTrend()
})

watch(trendDays, () => {
  if (selectedTablespaceName.value) void loadTablespaceTrend()
})

onMounted(() => {
  void oracleStore.loadStorage(props.connectionId)
})

</script>

<template>
  <section>
    <div class="utility-toolbar">
      <div title="Oracle tablespaces, datafiles, and recovery area usage."><h2>Fast Recovery Area</h2></div>
      <div class="database-inline-actions">
        <button type="button" class="secondary-button refresh-button" :disabled="oracleStore.loadingStorage" @click="oracleStore.loadStorage(connectionId)">{{ oracleStore.loadingStorage ? 'Refreshing' : 'Refresh' }}<p v-if="oracleStore.loadingStorage" class="loading"></p></button>
      </div>
    </div>

    <p v-if="operations.error" class="login-error">{{ operations.error }}</p>
    <p v-if="oracleStore.storageError" class="login-error">{{ oracleStore.storageError }}</p>

    <template v-else-if="storage">
      <div v-for="warning in storage.warnings" :key="warning" class="utility-warning">{{ warning }}</div>

      <section v-if="storage.fra" class="utility-section">
        <div class="utility-summary">
          <div><span>Used</span><strong>{{ formatBytes(storage.fra.used_bytes) }}</strong></div>
          <div><span>Limit</span><strong>{{ formatBytes(storage.fra.limit_bytes) }}</strong></div>
          <div><span>Used %</span><strong>{{ storage.fra.used_percent != null ? `${storage.fra.used_percent}%` : '—' }}</strong></div>
          <div><span>Reclaimable</span><strong>{{ formatBytes(storage.fra.reclaimable_bytes) }}</strong></div>
        </div>
      </section>

      <section class="utility-section">
        <div class="utility-toolbar"><h3>Tablespaces</h3><button v-if="canOperate" type="button" class="primary-button" :disabled="operations.busy" @click="createTablespace">Create tablespace</button></div>
        <ScrollableDataTable v-if="storage.tablespaces_available" :empty="storage.tablespaces.length === 0" empty-message="No tablespaces returned." max-height="26rem">
          <template #header><tr><th>Tablespace</th><th>Type</th><th>Status</th><th>Used</th><th>Capacity</th><th>Usage</th><th>Details</th></tr></template>
          <tr v-for="tablespace in storage.tablespaces" :key="tablespace.name">
            <td><strong>{{ tablespace.name }}</strong></td>
            <td>{{ tablespace.contents }}</td>
            <td>{{ tablespace.status }}</td>
            <td>{{ formatBytes(tablespace.used_bytes) }}</td>
            <td>{{ formatBytes(tablespace.capacity_bytes) }}</td>
            <td>{{ tablespace.used_percent }}%</td>
            <td>
              <button type="button" class="secondary-button" @click="inspectTablespace(tablespace.name)">
                {{ selectedTablespaceName === tablespace.name ? ' Close' : 'Inspect' }}
              </button>
            </td>
          </tr>
        </ScrollableDataTable>
      </section>

      <section v-if="selectedTablespace" class="utility-section panel">
        <div class="utility-toolbar">
          <div>
            <h3>{{ selectedTablespace.name }} datafiles</h3>
          </div>
          <div class="database-inline-actions">
            <button
              v-if="canOperate"
              type="button"
              class="primary-button"
              :disabled="operations.busy"
              @click="addDatafile(selectedTablespace.name)"
            >
              Add datafile
            </button>
            <button type="button" class="secondary-button" @click="selectedTablespaceName = null">Close</button>
          </div>
        </div>

        <div class="tablespace-detailed-summary">
          <div><span>Used</span><strong>{{ formatBytes(selectedTablespace.used_bytes) }}</strong></div>
          <div><span>Allocated</span><strong>{{ formatBytes(selectedAllocatedBytes || selectedTablespace.capacity_bytes) }}</strong></div>
          <div><span>Hard max</span><strong>{{ formatBytes(selectedHardMaxBytes || selectedTablespace.capacity_bytes) }}</strong></div>
          <div><span>Usage</span><strong>{{ selectedTablespace.used_percent }}%</strong></div>
          <div><span>Files</span><strong>{{ selectedDatafiles.length }}</strong></div>
        </div>

        <section class="oracle-tablespace-trend">
          <div class="utility-toolbar">
            <div>
              <h4>Tablespace growth</h4>
            </div>
            <select v-model.number="trendDays" aria-label="Tablespace growth history range">
              <option :value="30">30 days</option>
              <option :value="90">90 days</option>
              <option :value="180">180 days</option>
              <option :value="365">1 year</option>
              <option :value="730">2 years</option>
            </select>
          </div>
          <div v-if="trendLoading" class="empty-state">Loading tablespace growth history...</div>
          <div v-else-if="trendError" class="utility-warning">{{ trendError }}</div>
          <VChart
            v-else-if="selectedGrowthSeries?.points.length"
            class="oracle-tablespace-trend-chart"
            :option="tablespaceTrendOption"
            autoresize
          />
          <div v-else class="empty-state">
            No daily growth history is available yet. The collector will populate this chart as new snapshots are recorded.
          </div>
        </section>

        <ScrollableDataTable
          v-if="storage.datafiles_available"
          :empty="selectedDatafiles.length === 0"
          empty-message="No datafiles returned for this tablespace."
          max-height="28rem"
        >
          <template #header><tr><th>ID</th><th>Size</th><th>Autoextend</th><th>Max</th><th>Path</th><th v-if="canOperate" class="user-actions-column">Actions</th></tr></template>
          <tr v-for="file in selectedDatafiles" :key="file.file_id">
            <td>{{ file.file_id }}</td>
            <td>{{ formatBytes(file.size_bytes) }}</td>
            <td>{{ file.autoextensible ? 'Yes' : 'No' }}</td>
            <td>{{ formatBytes(file.max_bytes) }}</td>
            <td class="utility-sql-text" :title="file.file_name">{{ file.file_name }}</td>
            <td v-if="canOperate" class="user-actions-cell">
              <FloatingActionMenu :label="`Actions for datafile ${file.file_id}`" :disabled="operations.busy">
                <button type="button" role="menuitem" @click="resizeDatafile(file)">
                  <FontAwesomeIcon icon="expand" />
                  Resize
                </button>
              </FloatingActionMenu>
            </td>
          </tr>
        </ScrollableDataTable>
      </section>
    </template>
  </section>
</template>
