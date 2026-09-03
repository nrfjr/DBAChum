<script setup lang="ts">
import { computed, onMounted } from 'vue'

import ScrollableDataTable from '@/components/common/ScrollableDataTable.vue'
import { useSqlServerDbaStore } from '@/stores/sqlServerDba'

const props = defineProps<{
  connectionId: string
}>()

const sqlServerStore = useSqlServerDbaStore()
const health = computed(() => sqlServerStore.health[props.connectionId])

function formatBytes(bytes: number | null | undefined) {
  if (bytes == null) return '—'
  if (bytes === 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB', 'TB', 'PB']
  const index = Math.min(
    Math.floor(Math.log(bytes) / Math.log(1024)),
    units.length - 1,
  )
  const value = bytes / Math.pow(1024, index)
  return `${value.toFixed(value >= 100 ? 0 : 1)} ${units[index]}`
}

function formatDurationSeconds(seconds: number | null | undefined) {
  if (seconds == null) return '—'
  const value = Math.max(0, Math.floor(seconds))
  const hours = Math.floor(value / 3600)
  const minutes = Math.floor((value % 3600) / 60)
  const remaining = value % 60
  if (hours) return `${hours}h ${minutes}m`
  if (minutes) return `${minutes}m ${remaining}s`
  return `${remaining}s`
}

function formatDurationMs(milliseconds: number | null | undefined) {
  if (milliseconds == null) return '—'
  return formatDurationSeconds(milliseconds / 1000)
}

function formatServerLocalDate(value: string | null) {
  if (!value) return 'Never'
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return value
  return new Intl.DateTimeFormat(undefined, {
    year: 'numeric',
    month: 'short',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  }).format(parsed)
}

function statusLabel(value: string | null | undefined) {
  if (!value) return 'Unknown'
  return value.replaceAll('_', ' ').replace(/\b\w/g, (match) => match.toUpperCase())
}

function statusClass(value: string | null | undefined) {
  const normalized = (value ?? '').toLowerCase()
  if (['succeeded', 'online'].includes(normalized)) return 'healthy'
  if (['failed', 'canceled', 'suspect', 'recovery_pending', 'emergency', 'offline'].includes(normalized)) {
    return 'critical'
  }
  if (['retry', 'in_progress', 'restoring', 'recovering'].includes(normalized)) return 'warning'
  return 'neutral'
}

onMounted(() => {
  void sqlServerStore.loadHealth(props.connectionId)
})
</script>

<template>
  <section>
    <div class="utility-toolbar">
      <div>
        <h2>Operational health</h2>
        <p>Database state, transaction log, workload, tempdb, and SQL Server Agent.</p>
      </div>

      <button
        type="button"
        class="secondary-button"
        :disabled="sqlServerStore.loadingHealth[connectionId]"
        @click="sqlServerStore.loadHealth(connectionId, true)"
      >
        {{ sqlServerStore.loadingHealth[connectionId] ? 'Refreshing...' : 'Refresh' }}
      </button>
    </div>

    <p v-if="sqlServerStore.healthError[connectionId]" class="login-error">
      {{ sqlServerStore.healthError[connectionId] }}
    </p>

    <template v-else-if="health">
      <div
        v-for="warning in health.warnings"
        :key="warning"
        class="utility-warning"
      >
        {{ warning }}
      </div>

      <div class="sqlserver-health-summary">
        <div>
          <span>Database state</span>
          <strong :class="['sqlserver-health-value', statusClass(health.database.state)]">
            {{ health.database.state ?? '—' }}
          </strong>
          <small>{{ health.database.recovery_model ?? 'Recovery model unavailable' }}</small>
        </div>

        <div>
          <span>Transaction log</span>
          <strong>{{ health.transaction_log.used_percent != null ? `${health.transaction_log.used_percent}%` : '—' }}</strong>
          <small>{{ formatBytes(health.transaction_log.used_bytes) }} / {{ formatBytes(health.transaction_log.size_bytes) }}</small>
        </div>

        <div>
          <span>Active requests</span>
          <strong>{{ health.workload.active ?? '—' }}</strong>
          <small>Current database</small>
        </div>

        <div>
          <span>Blocked</span>
          <strong>{{ health.workload.blocked ?? '—' }}</strong>
          <small>Current database</small>
        </div>

        <div>
          <span>Long running</span>
          <strong>{{ health.workload.long_running ?? '—' }}</strong>
          <small>≥ {{ formatDurationSeconds(health.workload.long_running_threshold_seconds) }}</small>
        </div>

        <div>
          <span>Agent failures (instance)</span>
          <strong>{{ health.agent.failed_jobs ?? '—' }}</strong>
          <small>{{ health.agent.running_jobs ?? '—' }} running · {{ health.agent.enabled_jobs ?? '—' }} enabled</small>
        </div>

        <div>
          <span>tempdb data (instance)</span>
          <strong>{{ health.tempdb.used_percent != null ? `${health.tempdb.used_percent}%` : '—' }}</strong>
          <small>{{ formatBytes(health.tempdb.used_bytes) }} / {{ formatBytes(health.tempdb.allocated_bytes) }}</small>
        </div>
      </div>

      <section class="utility-section">
        <h3>Database health details</h3>
        <div class="sqlserver-health-details">
          <div><span>Database</span><strong>{{ health.database.name ?? health.database_name ?? '—' }}</strong></div>
          <div><span>State</span><strong>{{ health.database.state ?? '—' }}</strong></div>
          <div><span>Recovery model</span><strong>{{ health.database.recovery_model ?? '—' }}</strong></div>
          <div><span>Log reuse wait</span><strong>{{ health.database.log_reuse_wait ?? '—' }}</strong></div>
          <div><span>User access</span><strong>{{ health.database.user_access ?? '—' }}</strong></div>
          <div><span>Compatibility</span><strong>{{ health.database.compatibility_level ?? '—' }}</strong></div>
          <div><span>Page verify</span><strong>{{ health.database.page_verify ?? '—' }}</strong></div>
          <div><span>Read only</span><strong>{{ health.database.read_only == null ? '—' : health.database.read_only ? 'Yes' : 'No' }}</strong></div>
          <div><span>Auto close</span><strong>{{ health.database.auto_close == null ? '—' : health.database.auto_close ? 'On' : 'Off' }}</strong></div>
          <div><span>Auto shrink</span><strong>{{ health.database.auto_shrink == null ? '—' : health.database.auto_shrink ? 'On' : 'Off' }}</strong></div>
          <div><span>Longest request</span><strong>{{ formatDurationMs(health.workload.longest_request_ms) }}</strong></div>
          <div><span>Generation</span><strong>{{ health.generation ?? '—' }}</strong></div>
        </div>
      </section>

      <section class="utility-section">
        <div class="sqlserver-health-section-header">
          <div>
            <h3>SQL Server Agent jobs · instance</h3>
            <p>Latest job outcome visible to the DBAChum login. Run timestamps are SQL Server local time.</p>
          </div>
        </div>

        <div v-if="!health.agent.available" class="utility-warning">
          SQL Server Agent metadata is unavailable for this connection.
        </div>

        <ScrollableDataTable
          v-else
          :empty="health.agent.jobs.length === 0"
          empty-message="No SQL Server Agent jobs are visible to this login."
          max-height="32rem"
        >
          <template #header>
            <tr>
              <th>Job</th>
              <th>Enabled</th>
              <th>Latest status</th>
              <th>Last run (server)</th>
              <th>Duration</th>
              <th>Owner</th>
              <th>Message</th>
            </tr>
          </template>

          <tr v-for="job in health.agent.jobs" :key="job.job_id">
            <td>
              <strong>{{ job.name }}</strong>
              <small v-if="job.running" class="sqlserver-health-running">Currently running</small>
            </td>
            <td>{{ job.enabled ? 'Yes' : 'No' }}</td>
            <td>
              <span :class="['sqlserver-health-state', statusClass(job.last_status)]">
                {{ statusLabel(job.last_status) }}
              </span>
            </td>
            <td>{{ formatServerLocalDate(job.last_run_at) }}</td>
            <td>{{ formatDurationSeconds(job.last_duration_seconds) }}</td>
            <td>{{ job.owner ?? '—' }}</td>
            <td class="utility-sql-text" :title="job.last_message ?? job.description ?? ''">
              {{ job.last_message ?? job.description ?? '—' }}
            </td>
          </tr>
        </ScrollableDataTable>
      </section>

      <section class="utility-section">
        <h3>tempdb files · instance</h3>

        <ScrollableDataTable
          :empty="health.tempdb.files.length === 0"
          empty-message="No tempdb file metadata returned."
          max-height="26rem"
        >
          <template #header>
            <tr>
              <th>Name</th>
              <th>Type</th>
              <th>Allocated</th>
              <th>Used</th>
              <th>Free</th>
              <th>Used %</th>
              <th>Physical path</th>
            </tr>
          </template>

          <tr v-for="file in health.tempdb.files" :key="`${file.file_type}-${file.name}`">
            <td>{{ file.name }}</td>
            <td>{{ file.file_type }}</td>
            <td>{{ formatBytes(file.allocated_bytes) }}</td>
            <td>{{ formatBytes(file.used_bytes) }}</td>
            <td>{{ formatBytes(file.free_bytes) }}</td>
            <td>{{ file.used_percent != null ? `${file.used_percent}%` : '—' }}</td>
            <td class="utility-sql-text" :title="file.physical_name ?? ''">
              {{ file.physical_name ?? '—' }}
            </td>
          </tr>
        </ScrollableDataTable>
      </section>
    </template>
  </section>
</template>
