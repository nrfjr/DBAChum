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
  const roleName = window.prompt('Role account name (without @host):')?.trim()
  if (!roleName) return
  if (!window.confirm(`${action === 'grant_role' ? 'Grant' : 'Revoke'} role ${roleName} ${action === 'grant_role' ? 'to' : 'from'} ${selected.value.account}?`)) return
  try {
    await operations.runAccess(props.connectionId, {
      action, principal: selected.value.user, host: selected.value.host, role_name: roleName,
    })
    await store.loadSecurity(props.connectionId, true)
  } catch {}
}

async function privilegeOperation(action: 'grant_privilege' | 'revoke_privilege') {
  if (!selected.value) return
  const privilege = window.prompt('Privilege (example: SELECT, INSERT, UPDATE):')?.trim()
  if (!privilege) return
  const objectName = window.prompt('Scope (example: mydb.* or mydb.table):')?.trim()
  if (!objectName) return
  if (!window.confirm(`${action === 'grant_privilege' ? 'Grant' : 'Revoke'} ${privilege} on ${objectName} ${action === 'grant_privilege' ? 'to' : 'from'} ${selected.value.account}?`)) return
  try {
    await operations.runAccess(props.connectionId, {
      action, principal: selected.value.user, host: selected.value.host, privilege, object_name: objectName,
    })
    await store.loadSecurity(props.connectionId, true)
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
        <p>Native role and privilege visibility with credential material redacted before it reaches the browser.</p>
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
        <input v-model="search" type="search" placeholder="Filter privileges or scope..." />
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
