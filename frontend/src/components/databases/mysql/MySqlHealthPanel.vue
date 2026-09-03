<script setup lang="ts">
import { computed, onMounted } from 'vue'

import { useMySqlDbaStore } from '@/stores/mysqlDba'

const props = defineProps<{ connectionId: string }>()
const mysqlStore = useMySqlDbaStore()
const health = computed(() => mysqlStore.health[props.connectionId])

function formatBytes(bytes: number | null) {
  if (bytes == null) return '—'
  if (bytes === 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB', 'TB', 'PB']
  const index = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1)
  const value = bytes / Math.pow(1024, index)
  return `${value.toFixed(value >= 100 ? 0 : 1)} ${units[index]}`
}

function formatDuration(seconds: number | null) {
  if (seconds == null) return '—'
  const value = Math.max(0, Math.floor(seconds))
  const days = Math.floor(value / 86400)
  const hours = Math.floor((value % 86400) / 3600)
  const minutes = Math.floor((value % 3600) / 60)
  if (days) return `${days}d ${hours}h`
  if (hours) return `${hours}h ${minutes}m`
  return `${minutes}m`
}

function formatPercent(value: number | null) {
  return value == null ? '—' : `${value}%`
}

onMounted(() => {
  void mysqlStore.loadHealth(props.connectionId)
})
</script>

<template>
  <section>
    <div class="utility-toolbar">
      <div>
        <h2>Operational health</h2>
        <p>Connections, workload, InnoDB, temporary tables, and server runtime state.</p>
      </div>
      <button
        type="button"
        class="secondary-button"
        :disabled="mysqlStore.loadingHealth[connectionId]"
        @click="mysqlStore.loadHealth(connectionId, true)"
      >
        {{ mysqlStore.loadingHealth[connectionId] ? 'Refreshing...' : 'Refresh' }}
      </button>
    </div>

    <p v-if="mysqlStore.healthError[connectionId]" class="login-error">
      {{ mysqlStore.healthError[connectionId] }}
    </p>

    <template v-else-if="health">
      <div v-for="warning in health.warnings" :key="warning" class="utility-warning">
        {{ warning }}
      </div>

      <div class="utility-summary">
        <div>
          <span>Connections</span>
          <strong>{{ health.connections.current ?? '—' }} / {{ health.connections.maximum ?? '—' }}</strong>
        </div>
        <div>
          <span>Connection usage</span>
          <strong>{{ formatPercent(health.connections.utilization_percent) }}</strong>
        </div>
        <div>
          <span>Running threads</span>
          <strong>{{ health.workload.threads_running ?? '—' }}</strong>
        </div>
        <div>
          <span>Blocked transactions</span>
          <strong>{{ health.innodb.blocked_transactions ?? '—' }}</strong>
        </div>
        <div>
          <span>Buffer pool data</span>
          <strong>{{ formatPercent(health.innodb.buffer_pool_used_percent) }}</strong>
        </div>
        <div>
          <span>Slow queries</span>
          <strong>{{ health.workload.slow_queries?.toLocaleString() ?? '—' }}</strong>
        </div>
        <div>
          <span>Uptime</span>
          <strong>{{ formatDuration(health.server.uptime_seconds) }}</strong>
        </div>
        <div>
          <span>Performance Schema</span>
          <strong>{{ health.performance_schema_enabled ? 'Enabled' : 'Disabled' }}</strong>
        </div>
      </div>

      <section class="utility-section">
        <h3>Connection health</h3>
        <div class="database-info-grid">
          <div><dt>Current / max</dt><dd>{{ health.connections.current ?? '—' }} / {{ health.connections.maximum ?? '—' }}</dd></div>
          <div><dt>Max used</dt><dd>{{ health.connections.max_used ?? '—' }} ({{ formatPercent(health.connections.max_used_percent) }})</dd></div>
          <div><dt>Total since startup</dt><dd>{{ health.connections.total_since_startup?.toLocaleString() ?? '—' }}</dd></div>
          <div><dt>Aborted connects</dt><dd>{{ health.connections.aborted_connects?.toLocaleString() ?? '—' }}</dd></div>
          <div><dt>Aborted clients</dt><dd>{{ health.connections.aborted_clients?.toLocaleString() ?? '—' }}</dd></div>
          <div><dt>Processlist source</dt><dd>{{ health.processlist_source ?? '—' }}</dd></div>
        </div>
      </section>

      <section class="utility-section">
        <h3>Workload &amp; InnoDB</h3>
        <div class="database-info-grid">
          <div><dt>Running threads</dt><dd>{{ health.workload.threads_running ?? '—' }}</dd></div>
          <div><dt>Longest active</dt><dd>{{ formatDuration(health.workload.longest_active_seconds) }}</dd></div>
          <div>
            <dt>Long-running sessions</dt>
            <dd>
              {{ health.workload.long_running_sessions ?? '—' }}
              <span v-if="health.workload.long_running_threshold_seconds != null">
                ≥ {{ health.workload.long_running_threshold_seconds }}s
              </span>
            </dd>
          </div>
          <div><dt>Questions</dt><dd>{{ health.workload.questions?.toLocaleString() ?? '—' }}</dd></div>
          <div><dt>Threads created</dt><dd>{{ health.workload.threads_created?.toLocaleString() ?? '—' }}</dd></div>
          <div><dt>Active transactions</dt><dd>{{ health.innodb.active_transactions ?? '—' }}</dd></div>
          <div><dt>Oldest transaction</dt><dd>{{ formatDuration(health.innodb.oldest_transaction_seconds) }}</dd></div>
          <div><dt>Buffer pool data</dt><dd>{{ formatBytes(health.innodb.buffer_pool_data_bytes) }} / {{ formatBytes(health.innodb.buffer_pool_size_bytes) }}</dd></div>
          <div><dt>Disk temp tables</dt><dd>{{ health.temporary_tables.created_on_disk?.toLocaleString() ?? '—' }} / {{ health.temporary_tables.created?.toLocaleString() ?? '—' }} ({{ formatPercent(health.temporary_tables.disk_percent) }})</dd></div>
        </div>
      </section>

      <section class="utility-section">
        <h3>Server settings</h3>
        <div class="database-info-grid">
          <div><dt>Product</dt><dd>{{ health.product ?? '—' }}</dd></div>
          <div><dt>Generation</dt><dd>{{ health.generation ?? '—' }}</dd></div>
          <div><dt>Scope</dt><dd>{{ health.scope === 'database' ? (health.database_name ?? 'Database') : 'Instance' }}</dd></div>
          <div><dt>Read only</dt><dd>{{ health.server.read_only == null ? '—' : health.server.read_only ? 'Yes' : 'No' }}</dd></div>
          <div><dt>Slow query log</dt><dd>{{ health.server.slow_query_log == null ? '—' : health.server.slow_query_log ? 'Enabled' : 'Disabled' }}</dd></div>
          <div><dt>Long query time</dt><dd>{{ health.server.long_query_time_seconds != null ? `${health.server.long_query_time_seconds}s` : '—' }}</dd></div>
        </div>
      </section>
    </template>
  </section>
</template>
