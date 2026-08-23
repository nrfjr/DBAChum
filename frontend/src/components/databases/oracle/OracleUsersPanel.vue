<script setup lang="ts">
import {
  computed,
  onMounted,
  ref,
} from 'vue'

import {
  useOracleDbaStore,
  type OracleDatabaseUser,
} from '@/stores/oracleDba'

const props = defineProps<{
  connectionId: string
}>()

const oracleStore = useOracleDbaStore()

const search = ref('')

type AccountFilter =
  | 'all'
  | 'open'
  | 'locked'
  | 'expired'

const filter = ref<AccountFilter>('all')

const users = computed(
  () =>
    oracleStore.users[
      props.connectionId
    ],
)

function matchesFilter(user: OracleDatabaseUser) {
  const status = user.status.toUpperCase()

  switch (filter.value) {
    case 'open':
      return status === 'OPEN'

    case 'locked':
      return status.includes('LOCKED')

    case 'expired':
      return status.includes('EXPIRED')

    default:
      return true
  }
}

const filteredUsers = computed(() => {
  const term = search.value
    .trim()
    .toLowerCase()

  return (users.value?.items ?? [])
    .filter(matchesFilter)
    .filter((user) => {
      if (!term) {
        return true
      }

      return [
        user.username,
        user.status,
        user.default_tablespace,
        user.temporary_tablespace,
        user.profile,
      ]
        .filter(Boolean)
        .some((value) =>
          String(value)
            .toLowerCase()
            .includes(term),
        )
    })
})

function formatDate(value: string | null) {
  if (!value) {
    return '—'
  }

  const parsed = new Date(value)

  if (Number.isNaN(parsed.getTime())) {
    return value
  }

  return parsed.toLocaleString()
}

onMounted(() => {
  oracleStore.loadUsers(
    props.connectionId,
  )
})
</script>

<template>
  <section>
    <div class="utility-toolbar">
      <div>
        <h2>Users &amp; Schemas</h2>
        <p>
          Oracle accounts, status and schema defaults.
        </p>
      </div>

      <button
        type="button"
        class="secondary-button"
        :disabled="oracleStore.loadingUsers"
        @click="oracleStore.loadUsers(connectionId)"
      >
        {{
          oracleStore.loadingUsers
            ? 'Refreshing...'
            : 'Refresh'
        }}
      </button>
    </div>

    <p
      v-if="oracleStore.usersError"
      class="login-error"
    >
      {{ oracleStore.usersError }}
    </p>

    <template v-else-if="users">
      <div
        v-if="!users.available"
        class="utility-warning"
      >
        User inventory is unavailable.

        <div>
          {{ users.warning }}
        </div>
      </div>

      <template v-else>
        <div class="utility-summary">
          <button
            type="button"
            :class="{ active: filter === 'all' }"
            @click="filter = 'all'"
          >
            <span>Total</span>
            <strong>{{ users.total }}</strong>
          </button>

          <button
            type="button"
            :class="{ active: filter === 'open' }"
            @click="filter = 'open'"
          >
            <span>Open</span>
            <strong>{{ users.open }}</strong>
          </button>

          <button
            type="button"
            :class="{ active: filter === 'locked' }"
            @click="filter = 'locked'"
          >
            <span>Locked</span>
            <strong>{{ users.locked }}</strong>
          </button>

          <button
            type="button"
            :class="{ active: filter === 'expired' }"
            @click="filter = 'expired'"
          >
            <span>Expired</span>
            <strong>{{ users.expired }}</strong>
          </button>
        </div>

        <div class="utility-filter-row">
          <label>
            <span>Find account</span>
            <input
              v-model="search"
              type="search"
              placeholder="Username, status, tablespace or profile"
            />
          </label>

          <span>
            {{ filteredUsers.length }} shown
          </span>
        </div>

        <div class="utility-table-wrap">
          <table class="utility-table">
            <thead>
              <tr>
                <th>Username</th>
                <th>Status</th>
                <th>Default tablespace</th>
                <th>Temporary tablespace</th>
                <th>Profile</th>
                <th>Created</th>
                <th>Expiry</th>
              </tr>
            </thead>

            <tbody>
              <tr
                v-for="user in filteredUsers"
                :key="user.username"
              >
                <td>
                  <strong>{{ user.username }}</strong>
                </td>

                <td>
                  {{ user.status }}
                </td>

                <td>
                  {{ user.default_tablespace ?? '—' }}
                </td>

                <td>
                  {{ user.temporary_tablespace ?? '—' }}
                </td>

                <td>
                  {{ user.profile ?? '—' }}
                </td>

                <td>
                  {{ formatDate(user.created_at) }}
                </td>

                <td>
                  {{ formatDate(user.expiry_date) }}
                </td>
              </tr>

              <tr v-if="filteredUsers.length === 0">
                <td colspan="7">
                  No matching database accounts.
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </template>
    </template>
  </section>
</template>
