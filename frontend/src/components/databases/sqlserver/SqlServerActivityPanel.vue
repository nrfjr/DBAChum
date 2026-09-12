<script setup lang="ts">
import { computed, onMounted } from 'vue'

import ScrollableDataTable from '@/components/common/ScrollableDataTable.vue'
import FloatingActionMenu from '@/components/common/FloatingActionMenu.vue'
import { hasPermission } from '@/core/permissions'
import { useAuthStore } from '@/stores/auth'
import { useDatabaseOperationsStore } from '@/stores/databaseOperations'
import { useSqlServerDbaStore, type SqlServerActivityItem } from '@/stores/sqlServerDba'
import { confirmDialog, showToast } from '@/ui/feedback'

const props = defineProps<{ connectionId: string }>()
const sqlServerStore = useSqlServerDbaStore()
const operations = useDatabaseOperationsStore()
const authStore = useAuthStore()
const activity = computed(() => sqlServerStore.activity[props.connectionId])
const canOperate = computed(() => hasPermission(authStore.user, 'database:operate'))


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

async function terminate(item: SqlServerActivityItem) {
  const confirmed = await confirmDialog({ title: 'Kill SQL Server session', message: `SPID ${item.session_id}`, confirmLabel: 'Kill SPID', destructive: true, tone: 'danger' })
  if (!confirmed) return
  try {
    await operations.runSession(props.connectionId, { action: 'terminate', session_id: item.session_id })
    await sqlServerStore.loadActivity(props.connectionId)
    showToast({ title: `SPID ${item.session_id} killed`, tone: 'success' })
  } catch (cause) {
    showToast({ title: 'Unable to kill SQL Server session', message: cause instanceof Error ? cause.message : operations.error ?? undefined, tone: 'danger' })
  }
}

onMounted(() => {
  void sqlServerStore.loadActivity(props.connectionId)
})

</script>

<template>
  <section>
    <div class="utility-toolbar">
      <div title="Requests currently executing on SQL Server."><h2>Current activity</h2></div>
      <button type="button" class="secondary-button refresh-button" :disabled="sqlServerStore.loadingActivity[connectionId]" @click="sqlServerStore.loadActivity(connectionId)">
        {{ sqlServerStore.loadingActivity[connectionId] ? 'Refreshing' : 'Refresh' }}
        <p v-if="sqlServerStore.loadingActivity[connectionId]" class="loading"></p>
      </button>
    </div>
    <p v-if="operations.error" class="login-error">{{ operations.error }}</p>
    <p v-if="sqlServerStore.activityError[connectionId]" class="login-error">{{ sqlServerStore.activityError[connectionId] }}</p>

    <template v-else-if="activity">
      <div v-if="activity.warning" class="utility-warning">{{ activity.warning }}</div>
      <div v-if="!activity.available" class="utility-warning">SQL Server activity monitoring is unavailable for this connection.</div>
      <ScrollableDataTable v-else :empty="activity.items.length === 0" empty-message="No active SQL Server requests right now." max-height="34rem">
        <template #header><tr><th>SPID</th><th>Login</th><th>Database</th><th>Status</th><th>Command</th><th>Elapsed</th><th>CPU</th><th>Wait</th><th>Wait time</th><th>Blocked by</th><th>SQL</th><th v-if="canOperate" class="user-actions-column">Actions</th></tr></template>
        <tr v-for="item in activity.items" :key="item.session_id">
          <td>{{ item.session_id }}</td><td>{{ item.login_name ?? '—' }}</td><td>{{ item.database_name ?? '—' }}</td><td>{{ item.status ?? '—' }}</td><td>{{ item.command ?? '—' }}</td>
          <td>{{ formatDurationMs(item.elapsed_ms) }}</td><td>{{ formatDurationMs(item.cpu_ms) }}</td><td>{{ item.wait_type ?? '—' }}</td><td>{{ formatDurationMs(item.wait_ms) }}</td><td>{{ item.blocking_session_id ?? '—' }}</td>
          <td class="utility-sql-text" :title="item.sql_text ?? ''">{{ item.sql_text ?? '—' }}</td>
          <td v-if="canOperate" class="user-actions-cell">
            <FloatingActionMenu :label="`Actions for SPID ${item.session_id}`" :disabled="operations.busy">
              <button type="button" role="menuitem" class="danger-menu-item" @click="terminate(item)">
                <FontAwesomeIcon icon="plug-circle-xmark" />
                Kill SPID
              </button>
            </FloatingActionMenu>
          </td>
        </tr>
      </ScrollableDataTable>
    </template>
  </section>
</template>
