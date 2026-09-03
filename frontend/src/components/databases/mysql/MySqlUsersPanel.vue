<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import ScrollableDataTable from '@/components/common/ScrollableDataTable.vue'
import {
  useMySqlDbaStore,
  type MySqlSecurityAccount,
} from '@/stores/mysqlDba'

const props = defineProps<{
  connectionId: string
}>()

const store = useMySqlDbaStore()
const search = ref('')
const filter = ref<'all' | 'current' | 'wildcard' | 'anonymous' | 'roles'>('all')

const security = computed(() => store.security[props.connectionId])

const accounts = computed(() => {
  const term = search.value.trim().toLowerCase()
  return (security.value?.accounts ?? []).filter((account) => {
    if (filter.value === 'current' && !account.current_identity) return false
    if (filter.value === 'wildcard' && !account.wildcard_host) return false
    if (filter.value === 'anonymous' && account.user) return false
    if (filter.value === 'roles' && !account.is_role) return false
    if (!term) return true
    return [
      account.account,
      account.auth_plugin,
      account.default_role,
      account.ssl_type,
      ...account.roles,
    ]
      .filter(Boolean)
      .some((value) => String(value).toLowerCase().includes(term))
  })
})

function formatDate(value: string | null) {
  if (!value) return '—'
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString()
}

function stateLabel(account: MySqlSecurityAccount) {
  if (account.account_locked === true) return 'Locked'
  if (account.password_expired === true) return 'Password expired'
  if (account.is_role) return 'Role'
  return 'Enabled'
}

onMounted(() => {
  void store.loadSecurity(props.connectionId)
})
</script>

<template>
  <section>
    <div class="utility-toolbar">
      <div>
        <h2>Users &amp; Hosts</h2>
        <p>MySQL/MariaDB accounts are host-qualified identities. DBAChum never reads or returns password/authentication hashes.</p>
      </div>

      <button
        type="button"
        class="secondary-button"
        :disabled="store.loadingSecurity[connectionId]"
        @click="store.loadSecurity(connectionId, true)"
      >
        {{ store.loadingSecurity[connectionId] ? 'Refreshing...' : 'Refresh' }}
      </button>
    </div>

    <p v-if="store.securityError[connectionId]" class="login-error">
      {{ store.securityError[connectionId] }}
    </p>

    <template v-else-if="security">
      <div v-for="warning in security.warnings" :key="warning" class="utility-warning">
        {{ warning }}
      </div>

      <div class="mysql-security-source">
        <span>Account source <strong>{{ security.metadata_source ?? '—' }}</strong></span>
        <span>Grant source <strong>{{ security.grants_source }}</strong></span>
        <span>Scope <strong>Instance</strong></span>
      </div>

      <div class="utility-summary">
        <button type="button" :class="{ active: filter === 'all' }" @click="filter = 'all'">
          <span>Visible accounts</span><strong>{{ security.account_count }}</strong>
        </button>
        <button type="button" :class="{ active: filter === 'current' }" @click="filter = 'current'">
          <span>Connected identity</span><strong>{{ security.accounts.filter((item) => item.current_identity).length }}</strong>
        </button>
        <button type="button" :class="{ active: filter === 'wildcard' }" @click="filter = 'wildcard'">
          <span>Wildcard hosts</span><strong>{{ security.wildcard_host_count }}</strong>
        </button>
        <button type="button" :class="{ active: filter === 'anonymous' }" @click="filter = 'anonymous'">
          <span>Anonymous</span><strong>{{ security.anonymous_account_count }}</strong>
        </button>
        <button type="button" :class="{ active: filter === 'roles' }" @click="filter = 'roles'">
          <span>Role accounts</span><strong>{{ security.role_account_count }}</strong>
        </button>
      </div>

      <div class="mysql-security-toolbar">
        <span>{{ security.complete_account_list ? 'Full account inventory visible' : 'Limited account inventory' }}</span>
        <input v-model="search" type="search" placeholder="Search user, host, plugin, role..." />
      </div>

      <ScrollableDataTable :empty="accounts.length === 0" empty-message="No matching MySQL/MariaDB accounts." max-height="34rem">
        <template #header>
          <tr>
            <th>Account</th>
            <th>Authentication</th>
            <th>Default role</th>
            <th>SSL</th>
            <th>State</th>
            <th>Grants</th>
            <th>Password changed</th>
          </tr>
        </template>
        <tr v-for="account in accounts" :key="account.account">
          <td>
            <strong>{{ account.account }}</strong>
            <small v-if="account.current_identity" class="mysql-account-note">Connected identity</small>
            <small v-if="account.login_identity" class="mysql-account-note">Login: {{ account.login_identity }}</small>
          </td>
          <td>{{ account.auth_plugin ?? 'Not exposed' }}</td>
          <td>{{ account.default_role ?? (account.roles.length ? account.roles.join(', ') : '—') }}</td>
          <td>{{ account.ssl_type || '—' }}</td>
          <td>
            <span :class="['mysql-security-state', { danger: account.account_locked || account.password_expired }]">
              {{ stateLabel(account) }}
            </span>
          </td>
          <td>{{ account.grants_visible ? account.grants.length : 'Limited' }}</td>
          <td>{{ formatDate(account.password_last_changed) }}</td>
        </tr>
      </ScrollableDataTable>
    </template>
  </section>
</template>
