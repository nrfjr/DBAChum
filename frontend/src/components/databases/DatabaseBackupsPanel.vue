<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import {
  useDatabaseBackupsStore,
  type BackupWindow,
  type DatabaseBackupItem,
} from '@/stores/databaseBackups'

const props = defineProps<{
  connectionId: string
}>()

const store = useDatabaseBackupsStore()
const result = computed(() => store.results[props.connectionId])
const loading = computed(() => Boolean(store.loadingIds[props.connectionId]))
const error = computed(() => store.errors[props.connectionId])
const selectedWindow = ref<BackupWindow>('today')
const selectedItem = ref<DatabaseBackupItem | null>(null)

function dateInputValue(date: Date) {
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

const today = new Date()
const sevenDaysAgo = new Date(today)
sevenDaysAgo.setDate(today.getDate() - 6)
const customStart = ref(dateInputValue(sevenDaysAgo))
const customEnd = ref(dateInputValue(today))

const recoveryModel = computed(
  () => result.value?.summaries?.[0]?.recovery_model ?? null,
)

const customRangeInvalid = computed(
  () =>
    !customStart.value ||
    !customEnd.value ||
    customEnd.value < customStart.value,
)

function formatDate(value: string | null | undefined) {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(date)
}

function formatAge(value: string | null | undefined) {
  if (!value) return '—'
  const milliseconds = Date.now() - new Date(value).getTime()
  if (!Number.isFinite(milliseconds)) return '—'
  const minutes = Math.max(Math.floor(milliseconds / 60000), 0)
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.floor(minutes / 60)
  if (hours < 48) return `${hours}h ago`
  const days = Math.floor(hours / 24)
  if (days < 60) return `${days}d ago`
  return formatDate(value)
}

function formatDuration(seconds: number | null | undefined) {
  if (seconds == null) return '—'
  const hours = Math.floor(seconds / 3600)
  const minutes = Math.floor((seconds % 3600) / 60)
  const secs = Math.floor(seconds % 60)
  if (hours) return `${hours}h ${minutes}m ${secs}s`
  if (minutes) return `${minutes}m ${secs}s`
  return `${secs}s`
}

function formatBytes(bytes: number | null | undefined) {
  if (bytes == null) return '—'
  const units = ['B', 'KB', 'MB', 'GB', 'TB', 'PB']
  let value = Math.max(bytes, 0)
  let index = 0
  while (value >= 1024 && index < units.length - 1) {
    value /= 1024
    index += 1
  }
  return `${value.toFixed(index === 0 ? 0 : 2)} ${units[index]}`
}

function backupTime(item: DatabaseBackupItem | null | undefined) {
  return item?.finished_at ?? item?.started_at ?? null
}

function kindLabel(item: DatabaseBackupItem) {
  const labels: Record<string, string> = {
    full: 'Full',
    differential: 'Differential',
    incremental: 'Incremental',
    log: 'Transaction Log',
    archive_log: 'Archive Log',
    file: 'File',
    partial: 'Partial',
    controlfile: 'Control File',
    spfile: 'SPFILE',
    other: 'Other',
  }
  return labels[item.kind] ?? item.kind
}

function statusLabel(item: DatabaseBackupItem) {
  if (item.native_status) {
    return item.native_status
      .toLowerCase()
      .replace(/\b\w/g, (letter) => letter.toUpperCase())
  }

  if (item.status === 'successful') return 'Completed'
  return item.status.replace('_', ' ').replace(/\b\w/g, (letter) => letter.toUpperCase())
}

function humanizeKey(value: string) {
  return value
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (letter) => letter.toUpperCase())
    .replace(/Lsn/g, 'LSN')
    .replace(/Rman/g, 'RMAN')
}

function formatDetailValue(value: string | number | boolean | null) {
  if (value == null || value === '') return '—'
  if (typeof value === 'boolean') return value ? 'Yes' : 'No'
  return String(value)
}

async function load(window = selectedWindow.value) {
  selectedWindow.value = window
  await store
    .load(props.connectionId, {
      window,
      startDate: window === 'custom' ? customStart.value : undefined,
      endDate: window === 'custom' ? customEnd.value : undefined,
    })
    .catch(() => undefined)
}

function selectQuickWindow(window: Exclude<BackupWindow, 'custom'>) {
  void load(window)
}

function showCustomRange() {
  selectedWindow.value = 'custom'
}

function applyCustomRange() {
  if (customRangeInvalid.value) return
  void load('custom')
}

function refresh() {
  void load(selectedWindow.value)
}

onMounted(() => load('today'))
</script>

<template>
  <section class="utility-section">
    <div class="utility-toolbar backup-toolbar">
      <div>
        <h2>Backups</h2>
        <p v-if="result">
          {{ result.source }}
          <template v-if="result.generation"> · {{ result.generation }}</template>
        </p>
        <p v-else>
          Recent backup history reported by the database or configured provider.
        </p>
      </div>

      <button
        type="button"
        class="secondary-button"
        :disabled="loading"
        @click="refresh"
      >
        {{ loading ? 'Refreshing...' : 'Refresh' }}
      </button>
    </div>

    <div v-if="!result || result.available" class="backup-range-bar">
      <div class="backup-range-buttons" aria-label="Backup history range">
        <button
          type="button"
          :class="{ active: selectedWindow === 'today' }"
          @click="selectQuickWindow('today')"
        >
          Today
        </button>
        <button
          type="button"
          :class="{ active: selectedWindow === '3d' }"
          @click="selectQuickWindow('3d')"
        >
          Last 3 Days
        </button>
        <button
          type="button"
          :class="{ active: selectedWindow === '7d' }"
          @click="selectQuickWindow('7d')"
        >
          Last 7 Days
        </button>
        <button
          type="button"
          :class="{ active: selectedWindow === 'custom' }"
          @click="showCustomRange"
        >
          Custom Range
        </button>
      </div>

      <div v-if="selectedWindow === 'custom'" class="backup-custom-range">
        <label>
          <span>From</span>
          <input v-model="customStart" type="date" :max="customEnd || undefined" />
        </label>
        <label>
          <span>To</span>
          <input v-model="customEnd" type="date" :min="customStart || undefined" />
        </label>
        <button
          type="button"
          class="secondary-button"
          :disabled="loading || customRangeInvalid"
          @click="applyCustomRange"
        >
          Apply
        </button>
      </div>
    </div>

    <p v-if="error" class="login-error">
      {{ error }}
    </p>

    <div v-if="loading && !result" class="empty-state">
      Loading backup history...
    </div>

    <template v-else-if="result">
      <div
        v-for="warning in result.warnings"
        :key="warning"
        class="utility-warning"
      >
        {{ warning }}
      </div>

      <div v-if="result.latest_backup" class="backup-latest-card">
        <div class="backup-latest-main">
          <span class="backup-eyebrow">Latest recorded backup</span>
          <strong>{{ kindLabel(result.latest_backup) }}</strong>
          <span>
            {{ formatDate(backupTime(result.latest_backup)) }}
            · {{ formatAge(backupTime(result.latest_backup)) }}
          </span>
        </div>

        <div class="backup-latest-facts">
          <span>
            <small>Status</small>
            <strong class="backup-status" :class="result.latest_backup.status">
              {{ statusLabel(result.latest_backup) }}
            </strong>
          </span>
          <span>
            <small>Duration</small>
            <strong>{{ formatDuration(result.latest_backup.duration_seconds) }}</strong>
          </span>
          <span>
            <small>Input</small>
            <strong>{{ formatBytes(result.latest_backup.input_bytes) }}</strong>
          </span>
          <span>
            <small>Output</small>
            <strong>{{ formatBytes(result.latest_backup.output_bytes) }}</strong>
          </span>
          <span v-if="recoveryModel">
            <small>Recovery / log mode</small>
            <strong>{{ recoveryModel }}</strong>
          </span>
        </div>
      </div>

      <div
        v-for="note in result.notes"
        :key="note"
        class="backup-note"
      >
        {{ note }}
      </div>

      <div v-if="!result.available" class="database-empty-state">
        <h3>No backup provider configured</h3>
        <p>
          DBAChum cannot infer backup history when this engine has no native
          repository or configured provider. Nothing is reported as healthy or
          failed until a real provider supplies records.
        </p>
      </div>

      <template v-else>
        <div class="panel-header backup-section-header">
          <div>
            <h2>Backup history</h2>
            <p>
              {{ result.items.length }} record{{ result.items.length === 1 ? '' : 's' }}
              in the selected range.
            </p>
          </div>
        </div>

        <div v-if="!result.items.length" class="empty-state">
          No backups were recorded in this range.
        </div>

        <div v-else class="utility-table-wrap">
          <table class="utility-table backup-history-table">
            <thead>
              <tr>
                <th>Type</th>
                <th>Status</th>
                <th>Completed</th>
                <th>Duration</th>
                <th>Input</th>
                <th>Output</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="item in result.items"
                :key="`${item.backup_id}-${item.native_type}`"
              >
                <td>
                  <strong>{{ kindLabel(item) }}</strong>
                  <small v-if="item.native_type" class="backup-native-type">
                    {{ item.native_type }}
                  </small>
                </td>
                <td>
                  <span class="backup-status" :class="item.status">
                    {{ statusLabel(item) }}
                  </span>
                </td>
                <td>
                  <div>{{ formatDate(backupTime(item)) }}</div>
                  <small>{{ formatAge(backupTime(item)) }}</small>
                </td>
                <td>{{ formatDuration(item.duration_seconds) }}</td>
                <td>{{ formatBytes(item.input_bytes) }}</td>
                <td>{{ formatBytes(item.output_bytes) }}</td>
                <td class="backup-details-action">
                  <button
                    type="button"
                    class="secondary-button"
                    @click="selectedItem = item"
                  >
                    View details
                  </button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </template>
    </template>

    <div
      v-if="selectedItem"
      class="modal-backdrop"
      @click.self="selectedItem = null"
    >
      <section class="modal-panel backup-detail-modal">
        <header class="modal-header">
          <div>
            <h2>{{ kindLabel(selectedItem) }} backup details</h2>
            <p>{{ formatDate(backupTime(selectedItem)) }}</p>
          </div>
          <button
            type="button"
            class="modal-close"
            aria-label="Close backup details"
            @click="selectedItem = null"
          >
            ×
          </button>
        </header>

        <div class="backup-detail-grid">
          <div><span>Status</span><strong>{{ statusLabel(selectedItem) }}</strong></div>
          <div><span>Native type</span><strong>{{ selectedItem.native_type ?? '—' }}</strong></div>
          <div><span>Started</span><strong>{{ formatDate(selectedItem.started_at) }}</strong></div>
          <div><span>Completed</span><strong>{{ formatDate(selectedItem.finished_at) }}</strong></div>
          <div><span>Duration</span><strong>{{ formatDuration(selectedItem.duration_seconds) }}</strong></div>
          <div><span>Input size</span><strong>{{ formatBytes(selectedItem.input_bytes) }}</strong></div>
          <div><span>Output size</span><strong>{{ formatBytes(selectedItem.output_bytes) }}</strong></div>
          <div v-if="selectedItem.device_type"><span>Device</span><strong>{{ selectedItem.device_type }}</strong></div>
          <div v-if="selectedItem.owner"><span>Owner</span><strong>{{ selectedItem.owner }}</strong></div>
          <div v-if="selectedItem.label"><span>Label</span><strong>{{ selectedItem.label }}</strong></div>
        </div>

        <div v-if="selectedItem.destinations.length" class="backup-detail-section">
          <h3>Destination</h3>
          <div
            v-for="destination in selectedItem.destinations"
            :key="destination"
            class="backup-detail-path"
          >
            {{ destination }}
          </div>
        </div>

        <div v-if="Object.keys(selectedItem.details).length" class="backup-detail-section">
          <h3>Engine metadata</h3>
          <div class="backup-detail-grid">
            <div v-for="(value, key) in selectedItem.details" :key="key">
              <span>{{ humanizeKey(key) }}</span>
              <strong>{{ formatDetailValue(value) }}</strong>
            </div>
          </div>
        </div>
      </section>
    </div>
  </section>
</template>
