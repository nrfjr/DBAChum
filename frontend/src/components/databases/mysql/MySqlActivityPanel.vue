<script setup lang="ts">
import { computed, onMounted } from 'vue'

import ScrollableDataTable from '@/components/common/ScrollableDataTable.vue'
import { useMySqlDbaStore } from '@/stores/mysqlDba'

const props = defineProps<{ connectionId: string }>()
const mysqlStore = useMySqlDbaStore()
const activity = computed(() => mysqlStore.activity[props.connectionId])

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

function waitLabel(event: string | null, object: string | null) {
  if (!event && !object) return '—'
  return [event, object].filter(Boolean).join(' · ')
}

onMounted(() => {
  void mysqlStore.loadActivity(props.connectionId)
})
</script>

<template>
  <section>
    <div class="utility-toolbar">
      <div>
        <h2>Activity</h2>
        <p>Active statements, InnoDB transactions, lock blockers, and wait context when available.</p>
      </div>
      <button
        type="button"
        class="secondary-button"
        :disabled="mysqlStore.loadingActivity[connectionId]"
        @click="mysqlStore.loadActivity(connectionId)"
      >
        {{ mysqlStore.loadingActivity[connectionId] ? 'Refreshing...' : 'Refresh' }}
      </button>
    </div>

    <p v-if="mysqlStore.activityError[connectionId]" class="login-error">
      {{ mysqlStore.activityError[connectionId] }}
    </p>

    <template v-else-if="activity">
      <div v-for="warning in activity.warnings" :key="warning" class="utility-warning">
        {{ warning }}
      </div>

      <div v-if="!activity.available" class="utility-warning">
        {{ activity.warning ?? 'MySQL/MariaDB activity is unavailable.' }}
      </div>

      <template v-else>
        <p class="database-monitoring-note">
          {{ activity.scope === 'database' ? `Database scope · ${activity.database_name}` : 'Instance scope' }}
          · source: {{ activity.processlist_source ?? 'server processlist' }}
        </p>

        <ScrollableDataTable
          :empty="activity.items.length === 0"
          empty-message="No active MySQL/MariaDB statements."
          max-height="36rem"
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
              <th>InnoDB transaction</th>
              <th>Wait</th>
              <th>Blocked by</th>
              <th>SQL</th>
            </tr>
          </template>

          <tr v-for="item in activity.items" :key="item.connection_id">
            <td>{{ item.connection_id }}</td>
            <td>{{ item.user ?? '—' }}</td>
            <td>{{ item.host ?? '—' }}</td>
            <td>{{ item.database ?? '—' }}</td>
            <td>{{ item.command ?? '—' }}</td>
            <td>{{ formatDuration(item.elapsed_seconds) }}</td>
            <td>{{ item.transaction_state ?? item.state ?? '—' }}</td>
            <td>{{ item.transaction_id ?? '—' }}</td>
            <td class="utility-sql-text" :title="waitLabel(item.wait_event, item.wait_object)">
              {{ waitLabel(item.wait_event, item.wait_object) }}
            </td>
            <td>{{ item.blocking_connection_id ?? '—' }}</td>
            <td class="utility-sql-text" :title="item.sql_text ?? ''">
              {{ item.sql_text ?? '—' }}
            </td>
          </tr>
        </ScrollableDataTable>
      </template>
    </template>
  </section>
</template>
