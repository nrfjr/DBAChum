<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import ScrollableDataTable from '@/components/common/ScrollableDataTable.vue'
import {
  useMySqlDbaStore,
  type MySqlSession,
} from '@/stores/mysqlDba'

const props = defineProps<{ connectionId: string }>()
const mysqlStore = useMySqlDbaStore()

type SessionFilter = 'all' | 'active' | 'blocked' | 'long'
const filter = ref<SessionFilter>('all')
const sessions = computed(() => mysqlStore.sessions[props.connectionId])

function isActive(session: MySqlSession) {
  return (session.command ?? '').toLowerCase() !== 'sleep'
}

const filteredSessions = computed(() => {
  const items = sessions.value?.items ?? []
  const threshold = sessions.value?.long_running_threshold_seconds ?? 60

  switch (filter.value) {
    case 'active':
      return items.filter(isActive)
    case 'blocked':
      return items.filter((session) => session.blocking_connection_id != null)
    case 'long':
      return items.filter(
        (session) => isActive(session) && session.elapsed_seconds >= threshold,
      )
    default:
      return items
  }
})

function formatDuration(seconds: number | null) {
  if (seconds == null) return '—'
  const value = Math.max(0, Math.floor(seconds))
  const hours = Math.floor(value / 3600)
  const minutes = Math.floor((value % 3600) / 60)
  const remaining = value % 60
  if (hours) return `${hours}h ${minutes}m`
  if (minutes) return `${minutes}m ${remaining}s`
  return `${remaining}s`
}

function scopeLabel() {
  if (!sessions.value) return ''
  return sessions.value.scope === 'database'
    ? `Database scope · ${sessions.value.database_name ?? 'selected database'}`
    : 'Instance scope · all visible databases'
}

onMounted(() => {
  void mysqlStore.loadSessions(props.connectionId)
})
</script>

<template>
  <section>
    <div class="utility-toolbar">
      <div>
        <h2>Sessions</h2>
        <p>Current MySQL/MariaDB client sessions and running statements.</p>
      </div>

      <button
        type="button"
        class="secondary-button"
        :disabled="mysqlStore.loadingSessions[connectionId]"
        @click="mysqlStore.loadSessions(connectionId)"
      >
        {{ mysqlStore.loadingSessions[connectionId] ? 'Refreshing...' : 'Refresh' }}
      </button>
    </div>

    <p v-if="mysqlStore.sessionsError[connectionId]" class="login-error">
      {{ mysqlStore.sessionsError[connectionId] }}
    </p>

    <template v-else-if="sessions">
      <div v-for="warning in sessions.warnings" :key="warning" class="utility-warning">
        {{ warning }}
      </div>

      <div v-if="!sessions.available" class="utility-warning">
        MySQL/MariaDB session monitoring is unavailable for this connection.
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

        <p class="database-monitoring-note">
          {{ scopeLabel() }} · source: {{ sessions.processlist_source ?? 'server processlist' }}
        </p>

        <ScrollableDataTable
          :empty="filteredSessions.length === 0"
          empty-message="No matching MySQL/MariaDB sessions."
          max-height="34rem"
        >
          <template #header>
            <tr>
              <th>ID</th>
              <th>User</th>
              <th>Host</th>
              <th>Database</th>
              <th>Command</th>
              <th>Elapsed</th>
              <th>State</th>
              <th>Blocked by</th>
              <th>SQL</th>
            </tr>
          </template>

          <tr v-for="session in filteredSessions" :key="session.connection_id">
            <td>{{ session.connection_id }}</td>
            <td>{{ session.user ?? '—' }}</td>
            <td>{{ session.host ?? '—' }}</td>
            <td>{{ session.database ?? '—' }}</td>
            <td>{{ session.command ?? '—' }}</td>
            <td>{{ formatDuration(session.elapsed_seconds) }}</td>
            <td>{{ session.state ?? '—' }}</td>
            <td>{{ session.blocking_connection_id ?? '—' }}</td>
            <td class="utility-sql-text" :title="session.sql_text ?? ''">
              {{ session.sql_text ?? '—' }}
            </td>
          </tr>
        </ScrollableDataTable>
      </template>
    </template>
  </section>
</template>
