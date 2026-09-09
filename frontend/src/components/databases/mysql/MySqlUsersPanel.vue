<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import ScrollableDataTable from '@/components/common/ScrollableDataTable.vue'
import { hasPermission } from '@/core/permissions'
import { useAuthStore } from '@/stores/auth'
import { useDatabaseOperationsStore } from '@/stores/databaseOperations'
import { useMySqlDbaStore, type MySqlSecurityAccount } from '@/stores/mysqlDba'
import { confirmDialog, formDialog, showToast } from '@/ui/feedback'

const props = defineProps<{ connectionId: string }>()
const store = useMySqlDbaStore()
const operations = useDatabaseOperationsStore()
const authStore = useAuthStore()
const search = ref('')
const filter = ref<'all' | 'current' | 'wildcard' | 'anonymous' | 'roles'>('all')
const security = computed(() => store.security[props.connectionId])
const canOperate = computed(() => hasPermission(authStore.user, 'database:operate'))

const accounts = computed(() => {
  const term = search.value.trim().toLowerCase()
  return (security.value?.accounts ?? []).filter((account) => {
    if (filter.value === 'current' && !account.current_identity) return false
    if (filter.value === 'wildcard' && !account.wildcard_host) return false
    if (filter.value === 'anonymous' && account.user) return false
    if (filter.value === 'roles' && !account.is_role) return false
    return !term || [account.account, account.auth_plugin, account.default_role, account.ssl_type, ...account.roles].filter(Boolean).some((value) => String(value).toLowerCase().includes(term))
  })
})
function formatDate(value: string | null) { if (!value) return '—'; const parsed = new Date(value); return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString() }
function stateLabel(account: MySqlSecurityAccount) { if (account.account_locked === true) return 'Locked'; if (account.password_expired === true) return 'Password expired'; if (account.is_role) return 'Role'; return 'Enabled' }

async function toggleAccount(account: MySqlSecurityAccount) {
  const action = account.account_locked ? 'enable' : 'disable'
  const confirmed = await confirmDialog({ title: `${action === 'enable' ? 'Unlock' : 'Lock'} account`, message: account.account, confirmLabel: action === 'enable' ? 'Unlock account' : 'Lock account', tone: action === 'disable' ? 'warning' : 'default' })
  if (!confirmed) return
  try {
    await operations.runAccount(props.connectionId, { action, account_name: account.user, host: account.host })
    await store.loadSecurity(props.connectionId, true)
    showToast({ title: action === 'enable' ? 'Account unlocked' : 'Account locked', message: account.account, tone: 'success' })
  } catch {}
}
async function resetPassword(account: MySqlSecurityAccount) {
  const result = await formDialog({
    title: 'Reset MySQL / MariaDB password',
    message: account.account,
    confirmLabel: 'Reset password',
    tone: 'warning',
    fields: [{ name: 'password', label: 'New password', type: 'password', required: true }],
  })
  if (!result) return
  try {
    await operations.runAccount(props.connectionId, { action: 'reset_password', account_name: account.user, host: account.host, password: String(result.password) })
    await store.loadSecurity(props.connectionId, true)
    showToast({ title: 'Password reset', message: account.account, tone: 'success' })
  } catch {}
}


onMounted(() => void store.loadSecurity(props.connectionId))
</script>

<template>
  <section>
    <div class="utility-toolbar"><div><h2>Users &amp; Hosts</h2></div><button type="button" class="secondary-button" :disabled="store.loadingSecurity[connectionId]" @click="store.loadSecurity(connectionId, true)">{{ store.loadingSecurity[connectionId] ? 'Refreshing...' : 'Refresh' }}</button></div>
    <p v-if="operations.error" class="login-error">{{ operations.error }}</p>
    <p v-if="store.securityError[connectionId]" class="login-error">{{ store.securityError[connectionId] }}</p>

    <template v-else-if="security">
      <div v-for="warning in security.warnings" :key="warning" class="utility-warning">{{ warning }}</div>
      <div class="mysql-security-source"><span>Account source <strong>{{ security.metadata_source ?? '—' }}</strong></span><span>Grant source <strong>{{ security.grants_source }}</strong></span><span>Scope <strong>Instance</strong></span></div>
      <div class="utility-summary">
        <button type="button" :class="{ active: filter === 'all' }" @click="filter = 'all'"><span>Visible accounts</span><strong>{{ security.account_count }}</strong></button><button type="button" :class="{ active: filter === 'current' }" @click="filter = 'current'"><span>Connected identity</span><strong>{{ security.accounts.filter((item) => item.current_identity).length }}</strong></button><button type="button" :class="{ active: filter === 'wildcard' }" @click="filter = 'wildcard'"><span>Wildcard hosts</span><strong>{{ security.wildcard_host_count }}</strong></button><button type="button" :class="{ active: filter === 'anonymous' }" @click="filter = 'anonymous'"><span>Anonymous</span><strong>{{ security.anonymous_account_count }}</strong></button><button type="button" :class="{ active: filter === 'roles' }" @click="filter = 'roles'"><span>Role accounts</span><strong>{{ security.role_account_count }}</strong></button>
      </div>
      <div class="mysql-security-toolbar"><span>{{ security.complete_account_list ? 'Full account inventory visible' : 'Limited account inventory' }}</span><input class="utility-search-input" v-model="search" type="search" placeholder="Search user, host, plugin, role..." /></div>
      <ScrollableDataTable :empty="accounts.length === 0" empty-message="No matching MySQL/MariaDB accounts." max-height="34rem">
        <template #header><tr><th>Account</th><th>Authentication</th><th>Default role</th><th>SSL</th><th>State</th><th>Grants</th><th>Password changed</th><th v-if="canOperate">Actions</th></tr></template>
        <tr v-for="account in accounts" :key="account.account">
          <td><strong>{{ account.account }}</strong><small v-if="account.current_identity" class="mysql-account-note">Connected identity</small><small v-if="account.login_identity" class="mysql-account-note">Login: {{ account.login_identity }}</small></td><td>{{ account.auth_plugin ?? 'Not exposed' }}</td><td>{{ account.default_role ?? (account.roles.length ? account.roles.join(', ') : '—') }}</td><td>{{ account.ssl_type || '—' }}</td><td><span :class="['mysql-security-state', { danger: account.account_locked || account.password_expired }]">{{ stateLabel(account) }}</span></td><td>{{ account.grants_visible ? account.grants.length : 'Limited' }}</td><td>{{ formatDate(account.password_last_changed) }}</td>
          <td v-if="canOperate"><div v-if="!account.is_role" class="database-inline-actions"><button type="button" class="secondary-button" :disabled="operations.busy" @click="toggleAccount(account)">{{ account.account_locked ? 'Unlock' : 'Lock' }}</button><button type="button" class="secondary-button" :disabled="operations.busy" @click="resetPassword(account)">Reset password</button></div></td>
        </tr>
      </ScrollableDataTable>
    </template>
  </section>
</template>
