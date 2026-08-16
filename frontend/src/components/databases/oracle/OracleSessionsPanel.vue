<script setup lang="ts">
import {
  computed,
  onMounted,
  ref,
} from 'vue'

import {
  useOracleDbaStore,
  type OracleSession,
} from '@/stores/oracleDba'

const props = defineProps<{
  connectionId: string
}>()

const oracleStore = useOracleDbaStore()

type SessionFilter =
  | 'all'
  | 'active'
  | 'blocked'
  | 'long'

const filter = ref<SessionFilter>('all')

const sessions = computed(
  () =>
    oracleStore.sessions[
      props.connectionId
    ],
)

const filteredSessions = computed(() => {
  const items =
    sessions.value?.items ?? []

  switch (filter.value) {
    case 'active':
      return items.filter(
        (session) =>
          session.status === 'ACTIVE',
      )

    case 'blocked':
      return items.filter(
        (session) =>
          session.blocking_session != null,
      )

    case 'long':
      return items.filter(
        (session) =>
          session.status === 'ACTIVE' &&
          session.state_seconds >=
            (
              sessions.value
                ?.long_running_threshold_seconds
              ?? 60
            ),
      )

    default:
      return items
  }
})

function formatDuration(seconds: number) {
  const hours = Math.floor(seconds / 3600)

  const minutes = Math.floor(
    (seconds % 3600) / 60,
  )

  const remaining = seconds % 60

  if (hours > 0) {
    return `${hours}h ${minutes}m`
  }

  if (minutes > 0) {
    return `${minutes}m ${remaining}s`
  }

  return `${remaining}s`
}

function clientLabel(session: OracleSession) {
  return (
    session.module ||
    session.program ||
    session.machine ||
    '—'
  )
}

onMounted(() => {
  oracleStore.loadSessions(
    props.connectionId,
  )
})
</script>

<template>
  <section>
    <div class="utility-toolbar">
      <div>
        <h2>Sessions</h2>
        <p>
          Current Oracle user sessions.
        </p>
      </div>

      <button
        type="button"
        class="secondary-button"
        :disabled="
          oracleStore.loadingSessions
        "
        @click="
          oracleStore.loadSessions(
            connectionId,
          )
        "
      >
        {{
          oracleStore.loadingSessions
            ? 'Refreshing...'
            : 'Refresh'
        }}
      </button>
    </div>

    <p
      v-if="oracleStore.sessionsError"
      class="login-error"
    >
      {{ oracleStore.sessionsError }}
    </p>

    <template v-else-if="sessions">
      <div
        v-if="!sessions.available"
        class="utility-warning"
      >
        Session monitoring is unavailable.

        <div>
          {{ sessions.warning }}
        </div>
      </div>

      <template v-else>
        <div class="utility-summary">
          <button
            type="button"
            :class="{
              active: filter === 'all',
            }"
            @click="filter = 'all'"
          >
            <span>Total</span>
            <strong>
              {{ sessions.total }}
            </strong>
          </button>

          <button
            type="button"
            :class="{
              active:
                filter === 'active',
            }"
            @click="filter = 'active'"
          >
            <span>Active</span>
            <strong>
              {{ sessions.active }}
            </strong>
          </button>

          <button
            type="button"
            :class="{
              active:
                filter === 'blocked',
            }"
            @click="filter = 'blocked'"
          >
            <span>Blocked</span>
            <strong>
              {{ sessions.blocked }}
            </strong>
          </button>

          <button
            type="button"
            :class="{
              active:
                filter === 'long',
            }"
            @click="filter = 'long'"
          >
            <span>Long running</span>
            <strong>
              {{ sessions.long_running }}
            </strong>
          </button>
        </div>

        <div class="utility-table-wrap">
          <table class="utility-table">
            <thead>
              <tr>
                <th>SID</th>
                <th>User</th>
                <th>Status</th>
                <th>Client</th>
                <th>SQL ID</th>
                <th>
                  State time
                </th>
                <th>Blocking SID</th>
              </tr>
            </thead>

            <tbody>
              <tr
                v-for="
                  session in filteredSessions
                "
                :key="
                  `${session.sid}-${session.serial_number}`
                "
              >
                <td>
                  {{ session.sid }}
                </td>

                <td>
                  {{
                    session.username ?? '—'
                  }}
                </td>

                <td>
                  {{ session.status }}
                </td>

                <td>
                  {{
                    clientLabel(session)
                  }}
                </td>

                <td>
                  {{
                    session.sql_id ?? '—'
                  }}
                </td>

                <td>
                  {{
                    formatDuration(
                      session.state_seconds,
                    )
                  }}
                </td>

                <td>
                  {{
                    session.blocking_session
                      ?? '—'
                  }}
                </td>
              </tr>

              <tr
                v-if="
                  filteredSessions.length === 0
                "
              >
                <td colspan="7">
                  No matching sessions.
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </template>
    </template>
  </section>
</template>