<script setup lang="ts">
import { computed, onMounted } from 'vue'
import {
  useDatabaseBackupsStore,
  type DatabaseBackupItem,
} from '@/stores/databaseBackups'

const props = defineProps<{
  connectionId: string
}>()

const store = useDatabaseBackupsStore()
const result = computed(() => store.results[props.connectionId])
const loading = computed(() => Boolean(store.loadingIds[props.connectionId]))
const error = computed(() => store.errors[props.connectionId])

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
  return `${Math.floor(hours / 24)}d ago`
}

function formatDuration(seconds: number | null | undefined) {
  if (seconds == null) return '—'
  const hours = Math.floor(seconds / 3600)
  const minutes = Math.floor((seconds % 3600) / 60)
  const secs = seconds % 60
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
  return `${value.toFixed(index === 0 ? 0 : 1)} ${units[index]}`
}

function latestFinish(item: DatabaseBackupItem | null | undefined) {
  return item?.finished_at ?? item?.started_at ?? null
}

function diffOrIncremental(summary: {
  last_differential: DatabaseBackupItem | null
  last_incremental: DatabaseBackupItem | null
}) {
  return summary.last_differential ?? summary.last_incremental
}

function kindLabel(item: DatabaseBackupItem) {
  return item.native_type || item.kind.replace('_', ' ')
}

function refresh() {
  store.load(props.connectionId).catch(() => undefined)
}

onMounted(refresh)
</script>

<template>
  <section class="utility-section">
    <div class="utility-toolbar">
      <div>
        <h2>Backup Health</h2>
        <p v-if="result">
          {{ result.source }} · {{ result.scope }} scope
        </p>
        <p v-else>
          Native and provider-backed backup history for this target.
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

      <div
        v-for="note in result.notes"
        :key="note"
        class="backup-note"
      >
        {{ note }}
      </div>

      <div v-if="!result.available" class="empty-state">
        Backup history is not available through the current provider.
      </div>

      <template v-if="result.summaries.length">
        <div class="panel-header backup-section-header">
          <div>
            <h2>Backup summary</h2>
            <p>Latest recorded backup by database and backup class.</p>
          </div>
        </div>

        <div class="utility-table-wrap">
          <table class="utility-table">
            <thead>
              <tr>
                <th>Database</th>
                <th>Recovery</th>
                <th>Last Full</th>
                <th>Last Diff / Incr</th>
                <th>Last Log / Archive</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="summary in result.summaries"
                :key="summary.database_name"
              >
                <td><strong>{{ summary.database_name }}</strong></td>
                <td>{{ summary.recovery_model ?? '—' }}</td>
                <td>
                  <div>{{ formatDate(latestFinish(summary.last_full)) }}</div>
                  <small>{{ formatAge(latestFinish(summary.last_full)) }}</small>
                </td>
                <td>
                  <div>{{ formatDate(latestFinish(diffOrIncremental(summary))) }}</div>
                  <small>{{ formatAge(latestFinish(diffOrIncremental(summary))) }}</small>
                </td>
                <td>
                  <div>{{ formatDate(latestFinish(summary.last_log)) }}</div>
                  <small>{{ formatAge(latestFinish(summary.last_log)) }}</small>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </template>

      <template v-if="result.items.length">
        <div class="panel-header backup-section-header">
          <div>
            <h2>Recent backup history</h2>
            <p>Newest recorded jobs or backup sets first.</p>
          </div>
        </div>

        <div class="utility-table-wrap">
          <table class="utility-table">
            <thead>
              <tr>
                <th>Database</th>
                <th>Type</th>
                <th>Finished</th>
                <th>Age</th>
                <th>Duration</th>
                <th>Size</th>
                <th>Destination / Device</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in result.items" :key="`${item.backup_id}-${item.native_type}`">
                <td>{{ item.database_name ?? '—' }}</td>
                <td>{{ kindLabel(item) }}</td>
                <td>{{ formatDate(item.finished_at ?? item.started_at) }}</td>
                <td>{{ formatAge(item.finished_at ?? item.started_at) }}</td>
                <td>{{ formatDuration(item.duration_seconds) }}</td>
                <td>{{ formatBytes(item.backup_size_bytes ?? item.output_bytes) }}</td>
                <td class="backup-destination">
                  {{ item.destinations.join(', ') || item.device_type || '—' }}
                </td>
                <td>
                  <span class="backup-status" :class="item.status">
                    {{ item.status }}
                  </span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </template>
    </template>
  </section>
</template>
