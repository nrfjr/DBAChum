<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import ScrollableDataTable from '@/components/common/ScrollableDataTable.vue'
import FloatingActionMenu from '@/components/common/FloatingActionMenu.vue'
import { hasPermission } from '@/core/permissions'
import { useAuthStore } from '@/stores/auth'
import { useDatabaseOperationsStore } from '@/stores/databaseOperations'
import { useMySqlDbaStore, type MySqlSession } from '@/stores/mysqlDba'
import { confirmDialog, showToast } from '@/ui/feedback'

const props = defineProps<{ connectionId: string }>()
const mysqlStore = useMySqlDbaStore()
const operations = useDatabaseOperationsStore()
const authStore = useAuthStore()

type SessionFilter = 'all' | 'active' | 'blocked' | 'long'
const filter = ref<SessionFilter>('all')
const sessions = computed(() => mysqlStore.sessions[props.connectionId])
const canOperate = computed(() => hasPermission(authStore.user, 'database:operate'))

function isActive(session: MySqlSession) { return (session.command ?? '').toLowerCase() !== 'sleep' }
const filteredSessions = computed(() => {
  const items = sessions.value?.items ?? []
  const threshold = sessions.value?.long_running_threshold_seconds ?? 60
  switch (filter.value) {
    case 'active': return items.filter(isActive)
    case 'blocked': return items.filter((session) => session.blocking_connection_id != null)
    case 'long': return items.filter((session) => isActive(session) && session.elapsed_seconds >= threshold)
    default: return items
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
  return sessions.value.scope === 'database' ? `Database scope · ${sessions.value.database_name ?? 'selected database'}` : 'Instance scope · all visible databases'
}


async function runAction(session: MySqlSession, action: 'terminate' | 'cancel_query') {
  const label = action === 'cancel_query' ? 'cancel the current query for' : 'terminate'
  const confirmed = await confirmDialog({ title: action === 'cancel_query' ? 'Cancel query' : 'Kill connection', message: `MySQL/MariaDB connection ${session.connection_id}`, confirmLabel: action === 'cancel_query' ? 'Cancel query' : 'Kill connection', destructive: action === 'terminate', tone: action === 'terminate' ? 'danger' : 'warning' })
  if (!confirmed) return
  try {
    await operations.runSession(props.connectionId, { action, session_id: session.connection_id })
    await mysqlStore.loadSessions(props.connectionId)
    showToast({ title: action === 'cancel_query' ? 'Query cancelled' : 'Connection killed', tone: 'success' })
  } catch (cause) {
    showToast({ title: action === 'cancel_query' ? 'Unable to cancel query' : 'Unable to terminate connection', message: cause instanceof Error ? cause.message : operations.error ?? undefined, tone: 'danger' })
  }
}

onMounted(() => {
  void mysqlStore.loadSessions(props.connectionId)
})

</script>

<template>
  <section>
    <div class="utility-toolbar">
      <div title="Current MySQL/MariaDB client sessions and running statements."><h2>Sessions</h2></div>
      <button type="button" class="secondary-button refresh-button" :disabled="mysqlStore.loadingSessions[connectionId]" @click="mysqlStore.loadSessions(connectionId)">
        {{ mysqlStore.loadingSessions[connectionId] ? 'Refreshing' : 'Refresh' }}
        <p v-if="mysqlStore.loadingSessions[connectionId]" class="loading"></p>
      </button>
    </div>

    <p v-if="operations.error" class="login-error">{{ operations.error }}</p>
    <p v-if="mysqlStore.sessionsError[connectionId]" class="login-error">{{ mysqlStore.sessionsError[connectionId] }}</p>

    <template v-else-if="sessions">
      <div v-for="warning in sessions.warnings" :key="warning" class="utility-warning">{{ warning }}</div>
      <div v-if="!sessions.available" class="utility-warning">MySQL/MariaDB session monitoring is unavailable for this connection.</div>
      <template v-else>
        <div class="utility-summary">
          <button type="button" :class="{ active: filter === 'all' }" @click="filter = 'all'"><span>Total</span><strong>{{ sessions.total ?? '—' }}</strong></button>
          <button type="button" :class="{ active: filter === 'active' }" @click="filter = 'active'"><span>Active</span><strong>{{ sessions.active ?? '—' }}</strong></button>
          <button type="button" :class="{ active: filter === 'blocked' }" @click="filter = 'blocked'"><span>Blocked</span><strong>{{ sessions.blocked ?? '—' }}</strong></button>
          <button type="button" :class="{ active: filter === 'long' }" @click="filter = 'long'"><span>Long running</span><strong>{{ sessions.long_running ?? '—' }}</strong></button>
        </div>
        <p class="database-monitoring-note">{{ scopeLabel() }} · source: {{ sessions.processlist_source ?? 'server processlist' }}</p>

        <ScrollableDataTable :empty="filteredSessions.length === 0" empty-message="No matching MySQL/MariaDB sessions." max-height="34rem">
          <template #header>
            <tr><th>ID</th><th>User</th><th>Host</th><th>Database</th><th>Command</th><th>Elapsed</th><th>State</th><th>Blocked by</th><th>SQL</th><th v-if="canOperate">Actions</th></tr>
          </template>
          <tr v-for="session in filteredSessions" :key="session.connection_id">
            <td>{{ session.connection_id }}</td><td>{{ session.user ?? '—' }}</td><td>{{ session.host ?? '—' }}</td><td>{{ session.database ?? '—' }}</td><td>{{ session.command ?? '—' }}</td>
            <td>{{ formatDuration(session.elapsed_seconds) }}</td><td>{{ session.state ?? '—' }}</td><td>{{ session.blocking_connection_id ?? '—' }}</td><td class="utility-sql-text" :title="session.sql_text ?? ''">{{ session.sql_text ?? '—' }}</td>
            <td v-if="canOperate">
              <FloatingActionMenu :label="`Actions for connection ${session.connection_id}`" :disabled="operations.busy">
                <button v-if="isActive(session)" type="button" role="menuitem" @click="runAction(session, 'cancel_query')">
                  <FontAwesomeIcon icon="ban" />
                  Cancel query
                </button>
                <div v-if="isActive(session)" class="user-action-divider" />
                <button type="button" role="menuitem" class="danger-menu-item" @click="runAction(session, 'terminate')">
                  <FontAwesomeIcon icon="plug-circle-xmark" />
                  Kill connection
                </button>
              </FloatingActionMenu>
            </td>
          </tr>
        </ScrollableDataTable>
      </template>
    </template>
  </section>
</template>
