<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'

import ScrollableDataTable from '@/components/common/ScrollableDataTable.vue'
import {
  useMySqlDbaStore,
  type MySqlSecurityAccount,
} from '@/stores/mysqlDba'

const props = defineProps<{
  connectionId: string
}>()

const store = useMySqlDbaStore()
const selectedAccount = ref('')
const search = ref('')
const elevatedOpen = ref(false)

const security = computed(() => store.security[props.connectionId])
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
