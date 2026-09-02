<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import ScrollableDataTable from '@/components/common/ScrollableDataTable.vue'
import {
  useSqlServerDbaStore,
  type SqlServerPermission,
  type SqlServerRoleMembership,
} from '@/stores/sqlServerDba'

const props = defineProps<{
  connectionId: string
}>()

const store = useSqlServerDbaStore()
const search = ref('')
const elevatedOpen = ref(false)
const section = ref<'roles' | 'server' | 'database'>('roles')
const security = computed(() => store.security[props.connectionId])

function matches(values: Array<string | null | undefined>) {
  const term = search.value.trim().toLowerCase()
  if (!term) return true
  return values.filter(Boolean).some((value) => String(value).toLowerCase().includes(term))
}

const serverRoles = computed(() => (security.value?.server_roles ?? []).filter((item) => matches([item.principal, item.role])))
const databaseRoles = computed(() => (security.value?.database_roles ?? []).filter((item) => matches([item.principal, item.role])))
const serverPermissions = computed(() => (security.value?.server_permissions ?? []).filter((item) => matchesPermission(item)))
const databasePermissions = computed(() => (security.value?.database_permissions ?? []).filter((item) => matchesPermission(item)))
const findings = computed(() => (security.value?.elevated_findings ?? []).filter((item) => matches([item.principal, item.source, item.detail, item.severity])))

function matchesPermission(item: SqlServerPermission) {
  return matches([item.principal, item.state, item.permission, item.class_name, item.securable, item.grantor])
}

function roleKey(item: SqlServerRoleMembership) {
  return `${item.source}:${item.principal}:${item.role}`
}

function permissionKey(item: SqlServerPermission, index: number) {
  return `${item.scope}:${item.principal}:${item.permission}:${item.securable ?? ''}:${index}`
}

onMounted(() => {
  void store.loadSecurity(props.connectionId)
})
</script>

<template>
  <section>
    <div class="utility-toolbar">
      <div>
        <h2>Access &amp; Privileges</h2>
        <p>Role membership and direct permissions reported by SQL Server for this database and instance.</p>
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

      <div class="utility-summary">
        <div><span>Server roles</span><strong>{{ security.server_roles.length }}</strong></div>
        <div><span>Database roles</span><strong>{{ security.database_roles.length }}</strong></div>
        <div><span>Server grants</span><strong>{{ security.server_permissions.length }}</strong></div>
        <div><span>Database grants</span><strong>{{ security.database_permissions.length }}</strong></div>
      </div>

      <section class="sqlserver-elevated-card">
        <button type="button" class="sqlserver-elevated-toggle" @click="elevatedOpen = !elevatedOpen">
          <span>
            <strong>Elevated Access</strong>
            <small>Heuristic findings from powerful SQL Server roles and direct permissions.</small>
          </span>
          <span class="sqlserver-elevated-count">{{ security.elevated_findings.length }}</span>
          <span>{{ elevatedOpen ? 'Hide' : 'Show' }}</span>
        </button>

        <div v-if="elevatedOpen" class="sqlserver-elevated-scroll">
          <p v-if="findings.length === 0" class="empty-copy">No elevated-access findings matched the current filter.</p>
          <div v-for="finding in findings" :key="`${finding.principal}:${finding.source}:${finding.detail}`" class="sqlserver-elevated-item">
            <span :class="['sqlserver-severity', finding.severity]">{{ finding.severity }}</span>
            <strong>{{ finding.principal }}</strong>
            <span>{{ finding.source }}</span>
            <span>{{ finding.detail }}</span>
          </div>
        </div>
      </section>

      <div class="sqlserver-security-toolbar">
        <div class="sqlserver-security-switch">
          <button type="button" :class="{ active: section === 'roles' }" @click="section = 'roles'">Roles</button>
          <button type="button" :class="{ active: section === 'server' }" @click="section = 'server'">Server permissions</button>
          <button type="button" :class="{ active: section === 'database' }" @click="section = 'database'">Database permissions</button>
        </div>
        <input v-model="search" type="search" placeholder="Search principal, role, permission..." />
      </div>

      <template v-if="section === 'roles'">
        <h3 class="sqlserver-security-heading">Server role membership</h3>
        <ScrollableDataTable :empty="serverRoles.length === 0" empty-message="No matching server-role memberships." max-height="18rem">
          <template #header><tr><th>Principal</th><th>Server role</th><th>Source</th></tr></template>
          <tr v-for="item in serverRoles" :key="roleKey(item)">
            <td><strong>{{ item.principal }}</strong></td><td>{{ item.role }}</td><td>{{ item.source }}</td>
          </tr>
        </ScrollableDataTable>

        <h3 class="sqlserver-security-heading">Database role membership</h3>
        <ScrollableDataTable :empty="databaseRoles.length === 0" empty-message="No matching database-role memberships." max-height="18rem">
          <template #header><tr><th>Principal</th><th>Database role</th><th>Source</th></tr></template>
          <tr v-for="item in databaseRoles" :key="roleKey(item)">
            <td><strong>{{ item.principal }}</strong></td><td>{{ item.role }}</td><td>{{ item.source }}</td>
          </tr>
        </ScrollableDataTable>
      </template>

      <ScrollableDataTable v-else-if="section === 'server'" :empty="serverPermissions.length === 0" empty-message="No direct server permissions are visible for this connection." max-height="34rem">
        <template #header><tr><th>Principal</th><th>State</th><th>Permission</th><th>Class</th><th>Securable</th><th>Grantor</th></tr></template>
        <tr v-for="(item, index) in serverPermissions" :key="permissionKey(item, index)">
          <td><strong>{{ item.principal }}</strong></td><td>{{ item.state }}</td><td>{{ item.permission }}</td><td>{{ item.class_name ?? '—' }}</td><td>{{ item.securable ?? '—' }}</td><td>{{ item.grantor ?? '—' }}</td>
        </tr>
      </ScrollableDataTable>

      <ScrollableDataTable v-else :empty="databasePermissions.length === 0" empty-message="No direct database permissions are visible for this connection." max-height="34rem">
        <template #header><tr><th>Principal</th><th>State</th><th>Permission</th><th>Class</th><th>Securable</th><th>Grantor</th></tr></template>
        <tr v-for="(item, index) in databasePermissions" :key="permissionKey(item, index)">
          <td><strong>{{ item.principal }}</strong></td><td>{{ item.state }}</td><td>{{ item.permission }}</td><td>{{ item.class_name ?? '—' }}</td><td>{{ item.securable ?? '—' }}</td><td>{{ item.grantor ?? '—' }}</td>
        </tr>
      </ScrollableDataTable>
    </template>
  </section>
</template>
