<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'

import ScrollableDataTable from '@/components/common/ScrollableDataTable.vue'
import { hasPermission } from '@/core/permissions'
import { useAuthStore } from '@/stores/auth'
import { useDatabaseOperationsStore } from '@/stores/databaseOperations'
import { useOracleDbaStore, type OracleSession } from '@/stores/oracleDba'
import { confirmDialog, showToast } from '@/ui/feedback'

const props = defineProps<{ connectionId: string }>()
const oracleStore = useOracleDbaStore()
const operations = useDatabaseOperationsStore()
const authStore = useAuthStore()

type SessionFilter = 'all' | 'active' | 'blocked' | 'long'
const filter = ref<SessionFilter>('all')
const sessions = computed(() => oracleStore.sessions[props.connectionId])
const canOperate = computed(() => hasPermission(authStore.user, 'database:operate'))
const actionMenuKey = ref<string | null>(null)

const filteredSessions = computed(() => {
  const items = sessions.value?.items ?? []
  switch (filter.value) {
    case 'active':
      return items.filter((session) => session.status === 'ACTIVE')
    case 'blocked':
      return items.filter((session) => session.blocking_session != null)
    case 'long':
      return items.filter(
        (session) => session.status === 'ACTIVE' && session.state_seconds >= (sessions.value?.long_running_threshold_seconds ?? 60),
      )
    default:
      return items
  }
})

function formatDuration(seconds: number) {
  const hours = Math.floor(seconds / 3600)
  const minutes = Math.floor((seconds % 3600) / 60)
  const remaining = seconds % 60
  if (hours > 0) return `${hours}h ${minutes}m`
  if (minutes > 0) return `${minutes}m ${remaining}s`
  return `${remaining}s`
}

function clientLabel(session: OracleSession) {
  return session.module || session.program || session.machine || '—'
}

function sessionKey(session: OracleSession) {
  return `${session.sid}-${session.serial_number}`
}

function toggleActionMenu(session: OracleSession, event: Event) {
  event.stopPropagation()
  const key = sessionKey(session)
  actionMenuKey.value = actionMenuKey.value === key ? null : key
}

function closeActionMenu() {
  actionMenuKey.value = null
}

async function runSessionAction(session: OracleSession, action: 'terminate' | 'disconnect') {
  const label = action === 'terminate' ? 'KILL' : 'DISCONNECT'
  const confirmed = await confirmDialog({ title: `${label} Oracle session`, message: `SID ${session.sid}, serial ${session.serial_number}`, confirmLabel: action === 'terminate' ? 'Kill session' : 'Disconnect session', destructive: true, tone: 'danger' })
  if (!confirmed) return
  try {
    await operations.runSession(props.connectionId, {
      action,
      session_id: session.sid,
      serial_number: session.serial_number,
    })
    await oracleStore.loadSessions(props.connectionId)
    showToast({ title: action === 'terminate' ? 'Session killed' : 'Session disconnected', tone: 'success' })
  } catch {
  }
}

onMounted(() => {
  document.addEventListener('click', closeActionMenu)
  void oracleStore.loadSessions(props.connectionId)
})

onUnmounted(() => {
  document.removeEventListener('click', closeActionMenu)
})
</script>

<template>
  <section>
    <div class="utility-toolbar">
      <div>
        <h2>Sessions</h2>
        <p>Current Oracle user sessions.</p>
      </div>
      <button type="button" class="secondary-button" :disabled="oracleStore.loadingSessions" @click="oracleStore.loadSessions(connectionId)">
        {{ oracleStore.loadingSessions ? 'Refreshing...' : 'Refresh' }}
      </button>
    </div>

    <p v-if="operations.error" class="login-error">{{ operations.error }}</p>
    <p v-if="oracleStore.sessionsError" class="login-error">{{ oracleStore.sessionsError }}</p>

    <template v-else-if="sessions">
      <div v-if="!sessions.available" class="utility-warning">
        Session monitoring is unavailable.
        <div>{{ sessions.warning }}</div>
      </div>

      <template v-else>
        <div class="utility-summary">
          <button type="button" :class="{ active: filter === 'all' }" @click="filter = 'all'"><span>Total</span><strong>{{ sessions.total }}</strong></button>
          <button type="button" :class="{ active: filter === 'active' }" @click="filter = 'active'"><span>Active</span><strong>{{ sessions.active }}</strong></button>
          <button type="button" :class="{ active: filter === 'blocked' }" @click="filter = 'blocked'"><span>Blocked</span><strong>{{ sessions.blocked }}</strong></button>
          <button type="button" :class="{ active: filter === 'long' }" @click="filter = 'long'"><span>Long running</span><strong>{{ sessions.long_running }}</strong></button>
        </div>

        <ScrollableDataTable :empty="filteredSessions.length === 0" empty-message="No matching sessions." max-height="34rem">
          <template #header>
            <tr>
              <th>SID</th><th>User</th><th>Status</th><th>Client</th><th>SQL ID</th><th>State time</th><th>Blocking SID</th>
              <th v-if="canOperate">Actions</th>
            </tr>
          </template>
          <tr v-for="session in filteredSessions" :key="`${session.sid}-${session.serial_number}`">
            <td>{{ session.sid }}</td>
            <td>{{ session.username ?? '—' }}</td>
            <td>{{ session.status }}</td>
            <td>{{ clientLabel(session) }}</td>
            <td>{{ session.sql_id ?? '—' }}</td>
            <td>{{ formatDuration(session.state_seconds) }}</td>
            <td>{{ session.blocking_session ?? '—' }}</td>
            <td v-if="canOperate">
              <div class="user-action-menu-wrap" @click.stop>
                <button
                  type="button"
                  class="user-action-button user-menu-button"
                  :aria-expanded="actionMenuKey === sessionKey(session)"
                  :aria-label="`Actions for session ${session.sid}`"
                  :disabled="operations.busy"
                  @click="toggleActionMenu(session, $event)"
                >
                  <FontAwesomeIcon icon="ellipsis-vertical" />
                </button>
                <div v-if="actionMenuKey === sessionKey(session)" class="user-action-dropdown" role="menu">
                  <button type="button" role="menuitem" @click="closeActionMenu(); runSessionAction(session, 'disconnect')">Disconnect</button>
                  <div class="user-action-divider" />
                  <button type="button" role="menuitem" class="danger-menu-item" @click="closeActionMenu(); runSessionAction(session, 'terminate')">Kill session</button>
                </div>
              </div>
            </td>
          </tr>
        </ScrollableDataTable>
      </template>
    </template>
  </section>
</template>
