<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import ScrollableDataTable from '@/components/common/ScrollableDataTable.vue'
import FloatingActionMenu from '@/components/common/FloatingActionMenu.vue'
import { hasPermission } from '@/core/permissions'
import { useAuthStore } from '@/stores/auth'
import { useDatabaseOperationsStore } from '@/stores/databaseOperations'
import { useMySqlDbaStore, type MySqlActivityItem } from '@/stores/mysqlDba'
import { confirmDialog, showToast } from '@/ui/feedback'

const props = defineProps<{ connectionId: string }>()
const mysqlStore = useMySqlDbaStore()
const operations = useDatabaseOperationsStore()
const authStore = useAuthStore()
const activity = computed(() => mysqlStore.activity[props.connectionId])
const canOperate = computed(() => hasPermission(authStore.user, 'database:operate'))

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
function waitLabel(event: string | null, object: string | null) { return [event, object].filter(Boolean).join(' · ') || '—' }


async function runAction(item: MySqlActivityItem, action: 'cancel_query' | 'terminate') {
  const message = action === 'cancel_query' ? `Cancel query on connection ${item.connection_id}?` : `Kill connection ${item.connection_id}?`
  const confirmed = await confirmDialog({ title: action === 'cancel_query' ? 'Cancel query' : 'Kill connection', message, confirmLabel: action === 'cancel_query' ? 'Cancel query' : 'Kill connection', destructive: action === 'terminate', tone: action === 'terminate' ? 'danger' : 'warning' })
  if (!confirmed) return
  try {
    await operations.runSession(props.connectionId, { action, session_id: item.connection_id })
    await mysqlStore.loadActivity(props.connectionId)
    showToast({ title: action === 'cancel_query' ? 'Query cancelled' : 'Connection killed', tone: 'success' })
  } catch (cause) {
    showToast({ title: action === 'cancel_query' ? 'Unable to cancel query' : 'Unable to terminate connection', message: cause instanceof Error ? cause.message : operations.error ?? undefined, tone: 'danger' })
  }
}

onMounted(() => {
  void mysqlStore.loadActivity(props.connectionId)
})

</script>

<template>
  <section>
    <div class="utility-toolbar">
      <div><h2>Activity</h2></div>
      <button type="button" class="secondary-button refresh-button" :disabled="mysqlStore.loadingActivity[connectionId]" @click="mysqlStore.loadActivity(connectionId)">
        {{ mysqlStore.loadingActivity[connectionId] ? 'Refreshing' : 'Refresh' }}
        <p v-if="mysqlStore.loadingActivity[connectionId]" class="loading"></p>
      </button>
    </div>
    <p v-if="operations.error" class="login-error">{{ operations.error }}</p>
    <p v-if="mysqlStore.activityError[connectionId]" class="login-error">{{ mysqlStore.activityError[connectionId] }}</p>

    <template v-else-if="activity">
      <div v-for="warning in activity.warnings" :key="warning" class="utility-warning">{{ warning }}</div>
      <div v-if="!activity.available" class="utility-warning">{{ activity.warning ?? 'MySQL/MariaDB activity is unavailable.' }}</div>
      <template v-else>
        <p class="database-monitoring-note">{{ activity.scope === 'database' ? `Database scope · ${activity.database_name}` : 'Instance scope' }} · source: {{ activity.processlist_source ?? 'server processlist' }}</p>
        <ScrollableDataTable :empty="activity.items.length === 0" empty-message="No active MySQL/MariaDB statements." max-height="36rem">
          <template #header><tr><th>ID</th><th>User</th><th>Host</th><th>Database</th><th>Command</th><th>Elapsed</th><th>State</th><th>InnoDB transaction</th><th>Wait</th><th>Blocked by</th><th>SQL</th><th v-if="canOperate" class="user-actions-column">Actions</th></tr></template>
          <tr v-for="item in activity.items" :key="item.connection_id">
            <td>{{ item.connection_id }}</td><td>{{ item.user ?? '—' }}</td><td>{{ item.host ?? '—' }}</td><td>{{ item.database ?? '—' }}</td><td>{{ item.command ?? '—' }}</td><td>{{ formatDuration(item.elapsed_seconds) }}</td>
            <td>{{ item.transaction_state ?? item.state ?? '—' }}</td><td>{{ item.transaction_id ?? '—' }}</td><td class="utility-sql-text" :title="waitLabel(item.wait_event, item.wait_object)">{{ waitLabel(item.wait_event, item.wait_object) }}</td>
            <td>{{ item.blocking_connection_id ?? '—' }}</td><td class="utility-sql-text" :title="item.sql_text ?? ''">{{ item.sql_text ?? '—' }}</td>
            <td v-if="canOperate" class="user-actions-cell">
              <FloatingActionMenu :label="`Actions for connection ${item.connection_id}`" :disabled="operations.busy">
                <button type="button" role="menuitem" @click="runAction(item, 'cancel_query')">
                  <FontAwesomeIcon icon="ban" />
                  Cancel query
                </button>
                <div class="user-action-divider" />
                <button type="button" role="menuitem" class="danger-menu-item" @click="runAction(item, 'terminate')">
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
