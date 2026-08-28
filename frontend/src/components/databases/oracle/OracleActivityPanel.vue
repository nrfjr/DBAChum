<script setup lang="ts">
import {
  computed,
  onMounted,
} from 'vue'

import {
  useOracleDbaStore,
} from '@/stores/oracleDba'
import ScrollableDataTable from '@/components/common/ScrollableDataTable.vue'

const props = defineProps<{
  connectionId: string
}>()

const oracleStore = useOracleDbaStore()

const activity = computed(
  () =>
    oracleStore.activity[
      props.connectionId
    ],
)

function formatDuration(seconds: number) {
  const minutes = Math.floor(
    seconds / 60,
  )

  const remaining = seconds % 60

  if (minutes > 0) {
    return `${minutes}m ${remaining}s`
  }

  return `${remaining}s`
}

onMounted(() => {
  oracleStore.loadActivity(
    props.connectionId,
  )
})
</script>

<template>
  <section>
    <div class="utility-toolbar">
      <div>
        <h2>Current activity</h2>

        <p>
          SQL currently associated with
          active Oracle sessions.
        </p>
      </div>

      <button
        type="button"
        class="secondary-button"
        :disabled="
          oracleStore.loadingActivity
        "
        @click="
          oracleStore.loadActivity(
            connectionId,
          )
        "
      >
        {{
          oracleStore.loadingActivity
            ? 'Refreshing...'
            : 'Refresh'
        }}
      </button>
    </div>

    <p
      v-if="oracleStore.activityError"
      class="login-error"
    >
      {{ oracleStore.activityError }}
    </p>

    <template v-else-if="activity">
      <div
        v-if="!activity.available"
        class="utility-warning"
      >
        Activity information is unavailable.

        <div>
          {{ activity.warning }}
        </div>
      </div>

      <ScrollableDataTable
        v-else
        :empty="activity.items.length === 0"
        empty-message="No active SQL right now."
        max-height="34rem"
      >
        <template #header>
            <tr>
              <th>SID</th>
              <th>User</th>
              <th>SQL ID</th>
              <th>Active</th>
              <th>Module</th>
              <th>Wait</th>
              <th>SQL</th>
            </tr>
        </template>
            <tr
              v-for="
                item in activity.items
              "
              :key="
                `${item.sid}-${item.serial_number}`
              "
            >
              <td>
                {{ item.sid }}
              </td>

              <td>
                {{
                  item.username ?? '—'
                }}
              </td>

              <td>
                {{ item.sql_id }}
              </td>

              <td>
                {{
                  formatDuration(
                    item.active_seconds,
                  )
                }}
              </td>

              <td>
                {{ item.module ?? '—' }}
              </td>

              <td>
                {{ item.event ?? '—' }}
              </td>

              <td
                class="utility-sql-text"
                :title="
                  item.sql_text ?? ''
                "
              >
                {{
                  item.sql_text ?? '—'
                }}
              </td>
            </tr>
      </ScrollableDataTable>
    </template>
  </section>
</template>