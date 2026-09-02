<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import ScrollableDataTable from '@/components/common/ScrollableDataTable.vue'
import {
  useSqlServerDbaStore,
  type SqlServerSession,
} from '@/stores/sqlServerDba'

const props = defineProps<{
  connectionId: string
}>()

const sqlServerStore = useSqlServerDbaStore()

type SessionFilter = 'all' | 'active' | 'blocked' | 'long'
const filter = ref<SessionFilter>('all')

const sessions = computed(() => sqlServerStore.sessions[props.connectionId])

function isActive(session: SqlServerSession) {
  const status = (session.request_status ?? '').toLowerCase()
  return Boolean(status) && !['sleeping', 'background', 'dormant'].includes(status)
}

const filteredSessions = computed(() => {
  const items = sessions.value?.items ?? []
  const thresholdMs = (sessions.value?.long_running_threshold_seconds ?? 60) * 1000

  switch (filter.value) {
    case 'active':
      return items.filter(isActive)
    case 'blocked':
      return items.filter((session) => session.blocking_session_id != null)
    case 'long':
      return items.filter(
        (session) => isActive(session) && (session.elapsed_ms ?? 0) >= thresholdMs,
      )
    default:
      return items
  }
})

function formatDurationMs(milliseconds: number | null) {
  if (milliseconds == null) return '—'

  const seconds = Math.max(0, Math.floor(milliseconds / 1000))
  const hours = Math.floor(seconds / 3600)
  const minutes = Math.floor((seconds % 3600) / 60)
  const remaining = seconds % 60

  if (hours > 0) return `${hours}h ${minutes}m`
  if (minutes > 0) return `${minutes}m ${remaining}s`
  return `${remaining}s`
}

function clientLabel(session: SqlServerSession) {
  return session.program_name || session.host_name || '—'
}

onMounted(() => {
  void sqlServerStore.loadSessions(props.connectionId)
})
</script>

<template>
  <section>
    <div class="utility-toolbar">
      <div>
        <h2>Sessions</h2>
        <p>Current SQL Server user sessions and requests.</p>
      </div>

      <button
        type="button"
        class="secondary-button"
        :disabled="sqlServerStore.loadingSessions[connectionId]"
        @click="sqlServerStore.loadSessions(connectionId)"
      >
        {{ sqlServerStore.loadingSessions[connectionId] ? 'Refreshing...' : 'Refresh' }}
      </button>
    </div>

    <p v-if="sqlServerStore.sessionsError[connectionId]" class="login-error">
      {{ sqlServerStore.sessionsError[connectionId] }}
    </p>

    <template v-else-if="sessions">
      <div
        v-for="warning in sessions.warnings"
        :key="warning"
        class="utility-warning"
      >
        {{ warning }}
      </div>

      <div v-if="!sessions.available" class="utility-warning">
        SQL Server session monitoring is unavailable for this connection.
      </div>

      <template v-else>
        <div class="utility-summary">
          <button type="button" :class="{ active: filter === 'all' }" @click="filter = 'all'">
            <span>Total</span>
            <strong>{{ sessions.total ?? '—' }}</strong>
          </button>

          <button type="button" :class="{ active: filter === 'active' }" @click="filter = 'active'">
            <span>Active</span>
            <strong>{{ sessions.active ?? '—' }}</strong>
          </button>

          <button type="button" :class="{ active: filter === 'blocked' }" @click="filter = 'blocked'">
            <span>Blocked</span>
            <strong>{{ sessions.blocked ?? '—' }}</strong>
          </button>

          <button type="button" :class="{ active: filter === 'long' }" @click="filter = 'long'">
            <span>Long running</span>
            <strong>{{ sessions.long_running ?? '—' }}</strong>
          </button>
        </div>

        <ScrollableDataTable
          :empty="filteredSessions.length === 0"
          empty-message="No matching SQL Server sessions."
          max-height="34rem"
        >
          <template #header>
            <tr>
              <th>SPID</th>
              <th>Login</th>
              <th>Status</th>
              <th>Client</th>
              <th>Command</th>
              <th>Elapsed</th>
              <th>CPU</th>
              <th>Wait</th>
              <th>Blocked by</th>
              <th>SQL</th>
            </tr>
          </template>

          <tr v-for="session in filteredSessions" :key="session.session_id">
            <td>{{ session.session_id }}</td>
            <td>{{ session.login_name ?? '—' }}</td>
            <td>{{ session.request_status ?? session.status ?? '—' }}</td>
            <td>{{ clientLabel(session) }}</td>
            <td>{{ session.command ?? '—' }}</td>
            <td>{{ formatDurationMs(session.elapsed_ms) }}</td>
            <td>{{ formatDurationMs(session.cpu_ms) }}</td>
            <td>{{ session.wait_type ?? '—' }}</td>
            <td>{{ session.blocking_session_id ?? '—' }}</td>
            <td class="utility-sql-text" :title="session.sql_text ?? ''">
              {{ session.sql_text ?? '—' }}
            </td>
          </tr>
        </ScrollableDataTable>
      </template>
    </template>
  </section>
</template>
