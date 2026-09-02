<script setup lang="ts">
import { computed, onMounted } from 'vue'

import ScrollableDataTable from '@/components/common/ScrollableDataTable.vue'
import { useSqlServerDbaStore } from '@/stores/sqlServerDba'

const props = defineProps<{
  connectionId: string
}>()

const sqlServerStore = useSqlServerDbaStore()
const activity = computed(() => sqlServerStore.activity[props.connectionId])

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

onMounted(() => {
  void sqlServerStore.loadActivity(props.connectionId)
})
</script>

<template>
  <section>
    <div class="utility-toolbar">
      <div>
        <h2>Current activity</h2>
        <p>Requests currently executing on SQL Server.</p>
      </div>

      <button
        type="button"
        class="secondary-button"
        :disabled="sqlServerStore.loadingActivity[connectionId]"
        @click="sqlServerStore.loadActivity(connectionId)"
      >
        {{ sqlServerStore.loadingActivity[connectionId] ? 'Refreshing...' : 'Refresh' }}
      </button>
    </div>

    <p v-if="sqlServerStore.activityError[connectionId]" class="login-error">
      {{ sqlServerStore.activityError[connectionId] }}
    </p>

    <template v-else-if="activity">
      <div v-if="activity.warning" class="utility-warning">
        {{ activity.warning }}
      </div>

      <div v-if="!activity.available" class="utility-warning">
        SQL Server activity monitoring is unavailable for this connection.
      </div>

      <ScrollableDataTable
        v-else
        :empty="activity.items.length === 0"
        empty-message="No active SQL Server requests right now."
        max-height="34rem"
      >
        <template #header>
          <tr>
            <th>SPID</th>
            <th>Login</th>
            <th>Database</th>
            <th>Status</th>
            <th>Command</th>
            <th>Elapsed</th>
            <th>CPU</th>
            <th>Wait</th>
            <th>Wait time</th>
            <th>Blocked by</th>
            <th>SQL</th>
          </tr>
        </template>

        <tr v-for="item in activity.items" :key="item.session_id">
          <td>{{ item.session_id }}</td>
          <td>{{ item.login_name ?? '—' }}</td>
          <td>{{ item.database_name ?? '—' }}</td>
          <td>{{ item.status ?? '—' }}</td>
          <td>{{ item.command ?? '—' }}</td>
          <td>{{ formatDurationMs(item.elapsed_ms) }}</td>
          <td>{{ formatDurationMs(item.cpu_ms) }}</td>
          <td>{{ item.wait_type ?? '—' }}</td>
          <td>{{ formatDurationMs(item.wait_ms) }}</td>
          <td>{{ item.blocking_session_id ?? '—' }}</td>
          <td class="utility-sql-text" :title="item.sql_text ?? ''">
            {{ item.sql_text ?? '—' }}
          </td>
        </tr>
      </ScrollableDataTable>
    </template>
  </section>
</template>
