<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'

import ScrollableDataTable from '@/components/common/ScrollableDataTable.vue'
import { hasPermission } from '@/core/permissions'
import { useAuthStore } from '@/stores/auth'
import { useDatabaseOperationsStore } from '@/stores/databaseOperations'
import {
  useMySqlDbaStore,
  type MySqlSecurityAccount,
} from '@/stores/mysqlDba'
import { formDialog, showToast } from '@/ui/feedback'

const props = defineProps<{
  connectionId: string
}>()

const store = useMySqlDbaStore()
const operations = useDatabaseOperationsStore()
const authStore = useAuthStore()
const selectedAccount = ref('')
const search = ref('')
const elevatedOpen = ref(false)

const security = computed(() => store.security[props.connectionId])
const canOperate = computed(() => hasPermission(authStore.user, 'database:operate'))
const selected = computed<MySqlSecurityAccount | undefined>(() =>
  security.value?.accounts.find((item) => item.account === selectedAccount.value),
)

const privileges = computed(() => {
  const term = search.value.trim().toLowerCase()
  const rows = selected.value?.privileges ?? []
  if (!term) return rows
  return rows.filter((item) =>
    [item.privilege, item.scope].some((value) => value.toLowerCase().includes(term)),
  )
})

function chooseDefaultAccount() {
  if (!security.value?.accounts.length) {
    selectedAccount.value = ''
    return
  }
  if (security.value.accounts.some((item) => item.account === selectedAccount.value)) return
  selectedAccount.value =
    security.value.accounts.find((item) => item.current_identity)?.account ??
    security.value.accounts.at(0)?.account ?? ''
}

watch(security, chooseDefaultAccount, { immediate: true })

async function roleOperation(action: 'grant_role' | 'revoke_role') {
  if (!selected.value) return
  const result = await formDialog({
    title: action === 'grant_role' ? 'Grant MySQL / MariaDB role' : 'Revoke MySQL / MariaDB role',
    message: selected.value.account,
    confirmLabel: action === 'grant_role' ? 'Grant role' : 'Revoke role',
    tone: action === 'revoke_role' ? 'warning' : 'default',
    fields: [{ name: 'role_name', label: 'Role account name', type: 'text', required: true, hint: 'Enter the role name without @host.' }],
  })
  if (!result) return
  try {
    await operations.runAccess(props.connectionId, {
      action,
      principal: selected.value.user,
      host: selected.value.host,
      role_name: String(result.role_name).trim(),
    })
    await store.loadSecurity(props.connectionId, true)
    showToast({ title: action === 'grant_role' ? 'Role granted' : 'Role revoked', tone: 'success' })
  } catch {}
}

async function privilegeOperation(action: 'grant_privilege' | 'revoke_privilege') {
  if (!selected.value) return
  const result = await formDialog({
    title: action === 'grant_privilege' ? 'Grant MySQL / MariaDB privilege' : 'Revoke MySQL / MariaDB privilege',
    message: selected.value.account,
    confirmLabel: action === 'grant_privilege' ? 'Grant privilege' : 'Revoke privilege',
    tone: action === 'revoke_privilege' ? 'warning' : 'default',
    fields: [
      { name: 'privilege', label: 'Privilege', type: 'text', required: true, placeholder: 'SELECT, INSERT, UPDATE' },
      { name: 'object_name', label: 'Scope', type: 'text', required: true, placeholder: 'mydb.* or mydb.table' },
    ],
  })
  if (!result) return
  try {
    await operations.runAccess(props.connectionId, {
      action,
      principal: selected.value.user,
      host: selected.value.host,
      privilege: String(result.privilege).trim(),
      object_name: String(result.object_name).trim(),
    })
    await store.loadSecurity(props.connectionId, true)
    showToast({ title: action === 'grant_privilege' ? 'Privilege granted' : 'Privilege revoked', tone: 'success' })
  } catch {}
}


onMounted(() => {
  void store.loadSecurity(props.connectionId)
})
</script>

<template>
  <section>
    <div class="utility-toolbar">
      <div>
        <h2>Access &amp; Grants</h2>
      </div>

      <div class="database-inline-actions">
        <button v-if="canOperate && selected" type="button" class="secondary-button" :disabled="operations.busy" @click="roleOperation('grant_role')">Grant role</button>
        <button v-if="canOperate && selected" type="button" class="secondary-button" :disabled="operations.busy" @click="roleOperation('revoke_role')">Revoke role</button>
        <button v-if="canOperate && selected" type="button" class="secondary-button" :disabled="operations.busy" @click="privilegeOperation('grant_privilege')">Grant privilege</button>
        <button v-if="canOperate && selected" type="button" class="secondary-button" :disabled="operations.busy" @click="privilegeOperation('revoke_privilege')">Revoke privilege</button>
        <button type="button" class="secondary-button" :disabled="store.loadingSecurity[connectionId]" @click="store.loadSecurity(connectionId, true)">{{ store.loadingSecurity[connectionId] ? 'Refreshing...' : 'Refresh' }}</button>
      </div>
    </div>

    <p v-if="operations.error" class="login-error">{{ operations.error }}</p>
    <p v-if="store.securityError[connectionId]" class="login-error">
      {{ store.securityError[connectionId] }}
    </p>

    <template v-else-if="security">
      <div v-for="warning in security.warnings" :key="warning" class="utility-warning">
        {{ warning }}
      </div>

      <section class="mysql-elevated-card">
        <button type="button" class="mysql-elevated-toggle" @click="elevatedOpen = !elevatedOpen">
          <span>
            <strong>Elevated Access</strong>
            <small>Broad privileges and account patterns worth a DBA review.</small>
          </span>
          <span class="mysql-elevated-count">{{ security.elevated_findings.length }}</span>
          <span>{{ elevatedOpen ? '▾' : '▸' }}</span>
        </button>

        <div v-if="elevatedOpen" class="mysql-elevated-scroll">
          <div v-if="security.elevated_findings.length === 0" class="mysql-elevated-empty">
            No elevated-access findings are visible to this login.
          </div>
          <div
            v-for="finding in security.elevated_findings"
            :key="`${finding.principal}:${finding.source}:${finding.detail}`"
            class="mysql-elevated-item"
          >
            <span :class="['mysql-severity', finding.severity]">{{ finding.severity }}</span>
            <strong>{{ finding.principal }}</strong>
            <span>{{ finding.source }}</span>
            <span>{{ finding.detail }}</span>
          </div>
        </div>
      </section>

      <div class="mysql-security-toolbar">
        <label class="mysql-account-selector">
          <span>Inspect account</span>
          <select v-model="selectedAccount">
            <option v-for="account in security.accounts" :key="account.account" :value="account.account">
              {{ account.account }}{{ account.current_identity ? ' · connected' : '' }}
            </option>
          </select>
        </label>
        <input class="utility-search-input" v-model="search" type="search" placeholder="Filter privileges or scope..." />
      </div>

      <template v-if="selected">
        <div class="mysql-access-summary">
          <div><span>Account</span><strong>{{ selected.account }}</strong></div>
          <div><span>Authentication</span><strong>{{ selected.auth_plugin ?? 'Not exposed' }}</strong></div>
          <div><span>Host pattern</span><strong>{{ selected.host }}</strong></div>
          <div><span>Default role</span><strong>{{ selected.default_role ?? '—' }}</strong></div>
          <div><span>Grant visibility</span><strong>{{ selected.grants_visible ? 'Visible' : 'Limited' }}</strong></div>
        </div>

        <div v-if="selected.roles.length" class="mysql-role-list">
          <strong>Roles</strong>
          <span v-for="role in selected.roles" :key="role">{{ role }}</span>
        </div>

        <h3 class="mysql-security-heading">Privileges</h3>
        <ScrollableDataTable :empty="privileges.length === 0" empty-message="No directly visible privileges for this account." max-height="24rem">
          <template #header>
            <tr><th>Privilege</th><th>Scope</th><th>Grant option</th></tr>
          </template>
          <tr v-for="(item, index) in privileges" :key="`${item.privilege}:${item.scope}:${index}`">
            <td><strong>{{ item.privilege }}</strong></td>
            <td>{{ item.scope }}</td>
            <td>{{ item.grant_option ? 'Yes' : 'No' }}</td>
          </tr>
        </ScrollableDataTable>

        <h3 class="mysql-security-heading">Native grants</h3>
        <div v-if="!selected.grants_visible" class="utility-warning">
          SHOW GRANTS is not permitted for this account using the connected DBAChum login.
        </div>
        <div v-else-if="selected.grants.length" class="mysql-native-grants">
          <code v-for="grant in selected.grants" :key="grant">{{ grant }}</code>
        </div>
        <div v-else class="mysql-elevated-empty">No native grant statements were returned.</div>
      </template>
    </template>
  </section>
</template>
