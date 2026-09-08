<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import ScrollableDataTable from '@/components/common/ScrollableDataTable.vue'
import { hasPermission } from '@/core/permissions'
import { useAuthStore } from '@/stores/auth'
import { useDatabaseOperationsStore } from '@/stores/databaseOperations'
import { useSqlServerDbaStore, type SqlServerDatabaseUser, type SqlServerLogin } from '@/stores/sqlServerDba'
import { confirmDialog, formDialog, showToast } from '@/ui/feedback'

const props = defineProps<{ connectionId: string }>()
const store = useSqlServerDbaStore()
const operations = useDatabaseOperationsStore()
const authStore = useAuthStore()
const search = ref('')
const view = ref<'users' | 'logins'>('users')
const issueFilter = ref<'all' | 'orphaned' | 'disabled'>('all')
const security = computed(() => store.security[props.connectionId])
const canOperate = computed(() => hasPermission(authStore.user, 'database:operate'))

function contains(values: Array<string | null | undefined>) {
  const term = search.value.trim().toLowerCase()
  return !term || values.filter(Boolean).some((value) => String(value).toLowerCase().includes(term))
}
const users = computed(() => (security.value?.database_users ?? []).filter((user) => {
  if (issueFilter.value === 'orphaned' && !user.orphaned) return false
  if (issueFilter.value === 'disabled') return false
  return contains([user.name, user.principal_type, user.login_name, user.default_schema, user.authentication_type, ...user.roles])
}))
const logins = computed(() => (security.value?.logins ?? []).filter((login) => {
  if (issueFilter.value === 'disabled' && !login.disabled) return false
  if (issueFilter.value === 'orphaned') return false
  return contains([login.name, login.principal_type, login.default_database, ...login.roles])
}))
function roleList(value: SqlServerDatabaseUser | SqlServerLogin) { return value.roles.length ? value.roles.join(', ') : '—' }
function formatDate(value: string | null) { if (!value) return '—'; const parsed = new Date(value); return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString() }
function isSqlLogin(login: SqlServerLogin) { return login.principal_type.toUpperCase().includes('SQL') }

async function setLoginState(login: SqlServerLogin) {
  const action = login.disabled ? 'enable' : 'disable'
  const confirmed = await confirmDialog({ title: `${action === 'enable' ? 'Enable' : 'Disable'} SQL Server login`, message: login.name, confirmLabel: action === 'enable' ? 'Enable login' : 'Disable login', tone: action === 'disable' ? 'warning' : 'default' })
  if (!confirmed) return
  try {
    await operations.runAccount(props.connectionId, { action, account_name: login.name })
    await store.loadSecurity(props.connectionId, true)
    showToast({ title: `Login ${action === 'enable' ? 'enabled' : 'disabled'}`, message: login.name, tone: 'success' })
  } catch {}
}

async function resetPassword(login: SqlServerLogin) {
  const result = await formDialog({
    title: 'Reset SQL Server login password',
    message: login.name,
    confirmLabel: 'Reset password',
    tone: 'warning',
    fields: [{ name: 'password', label: 'New password', type: 'password', required: true }],
  })
  if (!result) return
  try {
    await operations.runAccount(props.connectionId, { action: 'reset_password', account_name: login.name, password: String(result.password) })
    await store.loadSecurity(props.connectionId, true)
    showToast({ title: 'Password reset', message: login.name, tone: 'success' })
  } catch {}
}


onMounted(() => void store.loadSecurity(props.connectionId))
</script>

<template>
  <section>
    <div class="utility-toolbar">
      <div><h2>Users &amp; Principals</h2><p>Database users and server logins visible to the connected SQL Server account.</p></div>
      <button type="button" class="secondary-button" :disabled="store.loadingSecurity[connectionId]" @click="store.loadSecurity(connectionId, true)">{{ store.loadingSecurity[connectionId] ? 'Refreshing...' : 'Refresh' }}</button>
    </div>
    <p v-if="operations.error" class="login-error">{{ operations.error }}</p>
    <p v-if="store.securityError[connectionId]" class="login-error">{{ store.securityError[connectionId] }}</p>

    <template v-else-if="security">
      <div v-for="warning in security.warnings" :key="warning" class="utility-warning">{{ warning }}</div>
      <div class="utility-summary">
        <button type="button" :class="{ active: view === 'users' && issueFilter === 'all' }" @click="view = 'users'; issueFilter = 'all'"><span>Database users</span><strong>{{ security.database_user_count }}</strong></button>
        <button type="button" :class="{ active: view === 'logins' && issueFilter === 'all' }" @click="view = 'logins'; issueFilter = 'all'"><span>Server logins</span><strong>{{ security.login_count }}</strong></button>
        <button type="button" :class="{ active: view === 'users' && issueFilter === 'orphaned' }" @click="view = 'users'; issueFilter = 'orphaned'"><span>Orphaned users</span><strong>{{ security.orphaned_user_count }}</strong></button>
        <button type="button" :class="{ active: view === 'logins' && issueFilter === 'disabled' }" @click="view = 'logins'; issueFilter = 'disabled'"><span>Disabled logins</span><strong>{{ security.disabled_login_count }}</strong></button>
      </div>
      <div class="sqlserver-security-toolbar"><div class="sqlserver-security-switch"><button type="button" :class="{ active: view === 'users' }" @click="view = 'users'; issueFilter = 'all'">Database users</button><button type="button" :class="{ active: view === 'logins' }" @click="view = 'logins'; issueFilter = 'all'">Server logins</button></div><input v-model="search" type="search" placeholder="Search users, logins, roles..." /></div>

      <ScrollableDataTable v-if="view === 'users'" :empty="users.length === 0" empty-message="No matching database users." max-height="34rem">
        <template #header><tr><th>User</th><th>Type</th><th>Mapped login</th><th>Default schema</th><th>Authentication</th><th>Database roles</th><th>State</th><th>Created</th></tr></template>
        <tr v-for="user in users" :key="user.name"><td><strong>{{ user.name }}</strong></td><td>{{ user.principal_type }}</td><td>{{ user.login_name ?? '—' }}</td><td>{{ user.default_schema ?? '—' }}</td><td>{{ user.authentication_type ?? '—' }}</td><td class="sqlserver-security-roles" :title="roleList(user)">{{ roleList(user) }}</td><td><span :class="['sqlserver-security-state', { danger: user.orphaned }]">{{ user.orphaned ? 'Orphaned' : 'Mapped' }}</span></td><td>{{ formatDate(user.created_at) }}</td></tr>
      </ScrollableDataTable>

      <ScrollableDataTable v-else :empty="logins.length === 0" empty-message="No matching server logins." max-height="34rem">
        <template #header><tr><th>Login</th><th>Type</th><th>Default database</th><th>Server roles</th><th>State</th><th>Created</th><th>Modified</th><th v-if="canOperate">Actions</th></tr></template>
        <tr v-for="login in logins" :key="login.name">
          <td><strong>{{ login.name }}</strong></td><td>{{ login.principal_type }}</td><td>{{ login.default_database ?? '—' }}</td><td class="sqlserver-security-roles" :title="roleList(login)">{{ roleList(login) }}</td><td><span :class="['sqlserver-security-state', { danger: login.disabled }]">{{ login.disabled ? 'Disabled' : 'Enabled' }}</span></td><td>{{ formatDate(login.created_at) }}</td><td>{{ formatDate(login.modified_at) }}</td>
          <td v-if="canOperate"><div class="database-inline-actions"><button type="button" class="secondary-button" :disabled="operations.busy" @click="setLoginState(login)">{{ login.disabled ? 'Enable' : 'Disable' }}</button><button v-if="isSqlLogin(login)" type="button" class="secondary-button" :disabled="operations.busy" @click="resetPassword(login)">Reset password</button></div></td>
        </tr>
      </ScrollableDataTable>
    </template>
  </section>
</template>
