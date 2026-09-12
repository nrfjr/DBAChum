<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import ScrollableDataTable from '@/components/common/ScrollableDataTable.vue'
import FloatingActionMenu from '@/components/common/FloatingActionMenu.vue'
import { hasPermission } from '@/core/permissions'
import { useAuthStore } from '@/stores/auth'
import { useDatabaseOperationsStore } from '@/stores/databaseOperations'
import { useOracleDbaStore, type OracleActiveSql } from '@/stores/oracleDba'
import { confirmDialog, showToast } from '@/ui/feedback'

const props = defineProps<{ connectionId: string }>()
const oracleStore = useOracleDbaStore()
const operations = useDatabaseOperationsStore()
const authStore = useAuthStore()
const activity = computed(() => oracleStore.activity[props.connectionId])
const canOperate = computed(() => hasPermission(authStore.user, 'database:operate'))

function sessionKey(item: OracleActiveSql) {
  return `${item.sid}-${item.serial_number}`
}


function formatDuration(seconds: number) {
  const minutes = Math.floor(seconds / 60)
  const remaining = seconds % 60
  return minutes > 0 ? `${minutes}m ${remaining}s` : `${remaining}s`
}

async function terminate(item: OracleActiveSql) {
  const confirmed = await confirmDialog({ title: 'Kill Oracle session', message: `SID ${item.sid}, serial ${item.serial_number} · SQL ${item.sql_id}`, confirmLabel: 'Kill session', destructive: true, tone: 'danger' })
  if (!confirmed) return
  try {
    await operations.runSession(props.connectionId, {
      action: 'terminate',
      session_id: item.sid,
      serial_number: item.serial_number,
    })
    await oracleStore.loadActivity(props.connectionId)
    showToast({ title: 'Session killed', tone: 'success' })
  } catch (cause) {
    showToast({ title: 'Unable to kill Oracle session', message: cause instanceof Error ? cause.message : operations.error ?? undefined, tone: 'danger' })
  }
}

onMounted(() => {
  void oracleStore.loadActivity(props.connectionId)
})

</script>

<template>
  <section>
    <div class="utility-toolbar">
      <div title="SQL currently associated with active Oracle sessions."><h2>Current activity</h2></div>
      <button type="button" class="secondary-button refresh-button" :disabled="oracleStore.loadingActivity" @click="oracleStore.loadActivity(connectionId)">
        {{ oracleStore.loadingActivity ? 'Refreshing' : 'Refresh' }}
        <p v-if="oracleStore.loadingActivity " class="loading"></p>
      </button>
    </div>

    <p v-if="operations.error" class="login-error">{{ operations.error }}</p>
    <p v-if="oracleStore.activityError" class="login-error">{{ oracleStore.activityError }}</p>

    <template v-else-if="activity">
      <div v-if="!activity.available" class="utility-warning">Activity information is unavailable.<div>{{ activity.warning }}</div></div>
      <ScrollableDataTable v-else :empty="activity.items.length === 0" empty-message="No active SQL right now." max-height="34rem">
        <template #header><tr><th>SID</th><th>User</th><th>SQL ID</th><th>Active</th><th>Module</th><th>Wait</th><th>SQL</th><th v-if="canOperate" class="user-actions-column">Actions</th></tr></template>
        <tr v-for="item in activity.items" :key="`${item.sid}-${item.serial_number}`">
          <td>{{ item.sid }}</td><td>{{ item.username ?? '—' }}</td><td>{{ item.sql_id }}</td><td>{{ formatDuration(item.active_seconds) }}</td><td>{{ item.module ?? '—' }}</td><td>{{ item.event ?? '—' }}</td>
          <td class="utility-sql-text" :title="item.sql_text ?? ''">{{ item.sql_text ?? '—' }}</td>
          <td v-if="canOperate" class="user-actions-cell">
            <FloatingActionMenu :label="`Actions for session ${item.sid}`" :disabled="operations.busy">
              <button type="button" role="menuitem" class="danger-menu-item" @click="terminate(item)">
                <FontAwesomeIcon icon="plug-circle-xmark" />
                Kill session
              </button>
            </FloatingActionMenu>
          </td>
        </tr>
      </ScrollableDataTable>
    </template>
  </section>
</template>
