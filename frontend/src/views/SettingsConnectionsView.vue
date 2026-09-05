<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import DatabaseConnectionsPanel from '@/components/settings/DatabaseConnectionsPanel.vue'
import { hasPermission } from '@/core/permissions'
import { useAuthStore } from '@/stores/auth'
import { useConnectionsStore } from '@/stores/connections'
import { useProvisioningStore } from '@/stores/provisioning'
import { useServersStore } from '@/stores/servers'
import { useSshAccessStore } from '@/stores/sshAccess'
import SettingsInfrastructureView from '@/views/SettingsInfrastructureView.vue'
import SettingsLdapView from '@/views/SettingsLdapView.vue'
import SettingsProvisioningView from '@/views/SettingsProvisioningView.vue'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()
const connectionsStore = useConnectionsStore()
const serversStore = useServersStore()
const sshStore = useSshAccessStore()
const provisioningStore = useProvisioningStore()
const overviewSearch = ref('')

type ConnectionSection = 'all' | 'databases' | 'servers' | 'ldap' | 'provisioning'

interface ConnectionSectionOption {
  key: ConnectionSection
  label: string
  description: string
  available: boolean
}

const canAccessDatabases = computed(() => hasPermission(authStore.user, 'connections:test'))
const canAccessServers = computed(() => hasPermission(authStore.user, 'servers:manage'))
const canAccessLdap = computed(() => hasPermission(authStore.user, 'ldap:manage'))
const canAccessProvisioning = computed(() => hasPermission(authStore.user, 'provisioning:manage'))

const sectionOptions = computed<ConnectionSectionOption[]>(() => [
  {
    key: 'all',
    label: 'All',
    description: 'Overview of connection definitions DBAChum can use',
    available: true,
  },
  {
    key: 'databases',
    label: 'Databases',
    description: 'Oracle, SQL Server and MySQL / MariaDB endpoints',
    available: canAccessDatabases.value,
  },
  {
    key: 'servers',
    label: 'Servers / SSH',
    description: 'Server assets, reusable SSH access and terminal shortcuts',
    available: canAccessServers.value,
  },
  {
    key: 'ldap',
    label: 'LDAP',
    description: 'Reusable directory endpoints used by provisioning',
    available: canAccessLdap.value,
  },
  {
    key: 'provisioning',
    label: 'Provisioning',
    description: 'Reusable application/database provisioning definitions',
    available: canAccessProvisioning.value,
  },
])

const availableSections = computed(() => sectionOptions.value.filter((item) => item.available))

const activeType = computed<ConnectionSection>(() => {
  const requested = String(route.query.type ?? 'all') as ConnectionSection
  return availableSections.value.some((item) => item.key === requested) ? requested : 'all'
})

const activeOption = computed(() =>
  availableSections.value.find((item) => item.key === activeType.value) ?? availableSections.value[0],
)

async function selectType(type: ConnectionSection) {
  await router.replace({
    name: 'settings-connections',
    query: type === 'all' ? {} : { type },
  })
}

watch(
  () => route.query.type,
  async () => {
    const requested = String(route.query.type ?? 'all') as ConnectionSection
    if (!availableSections.value.some((item) => item.key === requested)) {
      await selectType('all')
    }
  },
  { immediate: true },
)

interface UnifiedConnectionRow {
  key: string
  name: string
  type: string
  endpoint: string
  status: string
  detail: string
  section: ConnectionSection
}

const unifiedRows = computed<UnifiedConnectionRow[]>(() => {
  const rows: UnifiedConnectionRow[] = []

  if (canAccessDatabases.value) {
    for (const connection of connectionsStore.connections) {
      rows.push({
        key: `database-${connection.id}`,
        name: connection.name,
        type: connection.engine === 'oracle'
          ? 'Oracle database'
          : connection.engine === 'sqlserver'
            ? 'SQL Server database'
            : 'MySQL / MariaDB database',
        endpoint: `${connection.host}:${connection.port}`,
        status: connection.active ? 'Enabled' : 'Disabled',
        detail: connection.monitor_enabled ? 'Monitoring enabled' : 'Monitoring disabled',
        section: 'databases',
      })
    }
  }

  if (canAccessServers.value) {
    for (const server of serversStore.servers) {
      rows.push({
        key: `server-${server.id}`,
        name: server.name,
        type: 'Server',
        endpoint: server.ip_address ? `${server.hostname} · ${server.ip_address}` : server.hostname,
        status: server.enabled ? 'Enabled' : 'Disabled',
        detail: server.ssh_profile_name ? `SSH: ${server.ssh_profile_name}` : 'SSH not assigned',
        section: 'servers',
      })
    }

    for (const profile of sshStore.profiles) {
      rows.push({
        key: `ssh-${profile.id}`,
        name: profile.name,
        type: 'SSH access profile',
        endpoint: `${profile.username} · port ${profile.port}`,
        status: profile.enabled ? 'Enabled' : 'Disabled',
        detail: `Used by ${profile.server_count} server${profile.server_count === 1 ? '' : 's'}`,
        section: 'servers',
      })
    }
  }

  if (canAccessLdap.value) {
    for (const profile of provisioningStore.ldapProfiles) {
      rows.push({
        key: `ldap-${profile.id}`,
        name: profile.name,
        type: 'LDAP',
        endpoint: `${profile.host || 'No host'}:${profile.port}`,
        status: !profile.enabled ? 'Disabled' : profile.configured ? 'Configured' : 'Incomplete',
        detail: profile.use_ssl ? 'LDAPS / SSL' : 'LDAP',
        section: 'ldap',
      })
    }
  }

  if (canAccessProvisioning.value) {
    for (const profile of provisioningStore.profiles) {
      rows.push({
        key: `provisioning-${profile.id}`,
        name: profile.name,
        type: 'Provisioning profile',
        endpoint: `${profile.table_steps.length} table step${profile.table_steps.length === 1 ? '' : 's'}`,
        status: !profile.enabled ? 'Disabled' : profile.ready ? 'Ready' : 'Needs attention',
        detail: profile.ldap_enabled ? 'LDAP enabled' : 'LDAP off',
        section: 'provisioning',
      })
    }
  }

  return rows.sort((a, b) => a.name.localeCompare(b.name))
})

const filteredRows = computed(() => {
  const q = overviewSearch.value.trim().toLowerCase()
  if (!q) return unifiedRows.value
  return unifiedRows.value.filter((row) =>
    [row.name, row.type, row.endpoint, row.status, row.detail]
      .some((value) => value.toLowerCase().includes(q)),
  )
})

const overviewCards = computed(() => [
  {
    key: 'databases' as const,
    label: 'Databases',
    count: connectionsStore.connections.length,
    available: canAccessDatabases.value,
  },
  {
    key: 'servers' as const,
    label: 'Servers / SSH',
    count: serversStore.servers.length + sshStore.profiles.length,
    available: canAccessServers.value,
  },
  {
    key: 'ldap' as const,
    label: 'LDAP',
    count: provisioningStore.ldapProfiles.length,
    available: canAccessLdap.value,
  },
  {
    key: 'provisioning' as const,
    label: 'Provisioning',
    count: provisioningStore.profiles.length,
    available: canAccessProvisioning.value,
  },
].filter((card) => card.available))

async function loadOverview() {
  const jobs: Promise<unknown>[] = []
  if (canAccessDatabases.value) jobs.push(connectionsStore.load())
  if (canAccessServers.value) jobs.push(serversStore.load(), sshStore.load())
  if (canAccessLdap.value) jobs.push(provisioningStore.loadLdapProfiles())
  if (canAccessProvisioning.value) jobs.push(provisioningStore.loadProfiles())
  await Promise.allSettled(jobs)
}

onMounted(() => {
  void loadOverview()
})
</script>

<template>
  <div class="unified-connections">
    <section class="connections-intro">
      <div>
        <h3>Unified connections</h3>
        <p>
          Machine-readable endpoints and reusable connection definitions DBAChum actively uses. Human reference data belongs in Records.
        </p>
      </div>
    </section>

    <div class="connection-type-tabs" role="tablist" aria-label="Connection type">
      <button
        v-for="option in availableSections"
        :key="option.key"
        type="button"
        :class="{ active: activeType === option.key }"
        :title="option.description"
        @click="selectType(option.key)"
      >
        {{ option.label }}
      </button>
    </div>

    <section v-if="activeType === 'all'" class="connections-overview">
      <div class="connection-overview-cards">
        <button
          v-for="card in overviewCards"
          :key="card.key"
          type="button"
          class="connection-overview-card"
          @click="selectType(card.key)"
        >
          <strong>{{ card.count }}</strong>
          <span>{{ card.label }}</span>
          <small>Manage →</small>
        </button>
      </div>

      <section class="panel connection-overview-list">
        <div class="panel-header">
          <div>
            <h3>All connection definitions</h3>
            <p>One searchable index across the connection types you are allowed to administer.</p>
          </div>
          <button class="secondary-button" type="button" @click="loadOverview">Refresh</button>
        </div>

        <input
          v-model="overviewSearch"
          class="table-filter-input"
          type="search"
          placeholder="Search name, type, endpoint or status..."
        />

        <div v-if="filteredRows.length === 0" class="empty-state">No connection definitions match this view.</div>

        <div v-else class="unified-connection-list">
          <button
            v-for="row in filteredRows"
            :key="row.key"
            type="button"
            class="unified-connection-row"
            @click="selectType(row.section)"
          >
            <span class="unified-connection-row__identity">
              <strong>{{ row.name }}</strong>
              <small>{{ row.type }}</small>
            </span>
            <span>{{ row.endpoint }}</span>
            <span>{{ row.detail }}</span>
            <span class="status-pill" :class="{ disabled: row.status === 'Disabled' || row.status === 'Incomplete' || row.status === 'Needs attention' }">
              {{ row.status }}
            </span>
          </button>
        </div>
      </section>
    </section>

    <section v-else class="connection-section-host">
      <header class="connection-section-context">
        <h3>{{ activeOption?.label }}</h3>
        <p>{{ activeOption?.description }}</p>
      </header>

      <DatabaseConnectionsPanel v-if="activeType === 'databases' && canAccessDatabases" />
      <SettingsInfrastructureView v-else-if="activeType === 'servers' && canAccessServers" />
      <SettingsLdapView v-else-if="activeType === 'ldap' && canAccessLdap" />
      <SettingsProvisioningView v-else-if="activeType === 'provisioning' && canAccessProvisioning" />
    </section>
  </div>
</template>
