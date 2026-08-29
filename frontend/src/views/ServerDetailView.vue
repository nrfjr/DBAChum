<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'

import ScrollableDataTable from '@/components/common/ScrollableDataTable.vue'
import { useServersStore, type Server, type ServerOsFamily, type ServerType } from '@/stores/servers'
import type { DatabaseConnection } from '@/stores/connections'
import { useAuthStore } from '@/stores/auth'
import { hasPermission } from '@/core/permissions'

const route = useRoute()
const serversStore = useServersStore()
const authStore = useAuthStore()

const server = ref<Server | null>(null)
const databases = ref<DatabaseConnection[]>([])
const loading = ref(true)
const error = ref<string | null>(null)

const serverId = computed(() => String(route.params.id ?? ''))
const canManageServers = computed(() => hasPermission(authStore.user?.role, 'servers:manage'))

function serverTypeLabel(value: ServerType) {
  return {
    database: 'Database server',
    application: 'Application server',
    utility: 'Utility server',
    other: 'Other',
  }[value]
}

function osLabel(value: ServerOsFamily) {
  return { windows: 'Windows', linux: 'Linux', aix: 'AIX', unix: 'Unix', other: 'Other' }[value]
}

function engineLabel(engine: DatabaseConnection['engine']) {
  return { oracle: 'Oracle', sqlserver: 'SQL Server', mysql: 'MySQL' }[engine]
}

async function load() {
  loading.value = true
  error.value = null
  try {
    const [serverResult, databaseResult] = await Promise.all([
      serversStore.loadOne(serverId.value),
      serversStore.loadDatabases(serverId.value),
    ])
    server.value = serverResult
    databases.value = databaseResult
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Unable to load server.'
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <section class="page-header server-detail-header">
    <div>
      <RouterLink to="/servers" class="text-link">← Servers</RouterLink>
      <h1>{{ server?.name ?? 'Server' }}</h1>
      <p v-if="server">{{ server.hostname }}<template v-if="server.ip_address"> · {{ server.ip_address }}</template></p>
    </div>
    <div class="server-detail-actions">
      <button type="button" class="secondary-button" :disabled="loading" @click="load">Refresh</button>
      <RouterLink v-if="server && canManageServers" class="secondary-button" to="/settings/infrastructure">Configure</RouterLink>
    </div>
  </section>

  <p v-if="error" class="login-error">{{ error }}</p>
  <p v-else-if="loading && !server" class="empty-state">Loading server...</p>

  <template v-else-if="server">
    <div class="server-detail-grid">
      <section class="detail-card">
        <h2>Server profile</h2>
        <dl class="detail-list">
          <div><dt>Type</dt><dd>{{ serverTypeLabel(server.server_type) }}</dd></div>
          <div><dt>Operating system</dt><dd>{{ osLabel(server.os_family) }}{{ server.os_version ? ` · ${server.os_version}` : '' }}</dd></div>
          <div><dt>Environment</dt><dd>{{ server.environment ?? '—' }}</dd></div>
          <div><dt>Owner / team</dt><dd>{{ server.owner ?? '—' }}</dd></div>
          <div><dt>Status</dt><dd>{{ server.enabled ? 'Enabled' : 'Disabled' }}</dd></div>
        </dl>
      </section>

      <section class="detail-card">
        <h2>SSH access</h2>
        <template v-if="server.ssh_profile_name">
          <strong>{{ server.ssh_profile_name }}</strong>
          <p>An encrypted SSH access profile is assigned. Phase 5C will use it for connectivity checks, host metrics and the built-in terminal.</p>
        </template>
        <template v-else>
          <strong>Not configured</strong>
          <p>Assign an SSH access profile from Settings → Infrastructure when this host should support SSH operations.</p>
        </template>
      </section>

      <section class="detail-card server-detail-notes">
        <h2>Notes & tags</h2>
        <p>{{ server.notes ?? 'No notes.' }}</p>
        <div v-if="server.tags.length" class="server-tags">
          <span v-for="tag in server.tags" :key="tag">{{ tag }}</span>
        </div>
      </section>
    </div>

    <section class="server-related-section">
      <div class="section-toolbar">
        <div>
          <h2>Related databases</h2>
          <p>Relationships are configuration metadata; the database connections remain independent assets.</p>
        </div>
        <span class="count-badge">{{ databases.length }}</span>
      </div>

      <ScrollableDataTable
        :loading="loading"
        :empty="databases.length === 0"
        empty-message="No database connections are related to this server."
        max-height="28rem"
      >
        <template #header>
          <tr>
            <th>Database</th>
            <th>Engine</th>
            <th>Endpoint</th>
            <th>Monitoring</th>
            <th></th>
          </tr>
        </template>
        <tr v-for="database in databases" :key="database.id">
          <td><strong>{{ database.name }}</strong></td>
          <td>{{ engineLabel(database.engine) }}</td>
          <td>{{ database.host }}:{{ database.port }}</td>
          <td>{{ database.monitor_enabled ? 'Enabled' : 'Off' }}</td>
          <td><RouterLink class="text-link" :to="`/databases/${database.id}`">Open database →</RouterLink></td>
        </tr>
      </ScrollableDataTable>
    </section>
  </template>
</template>
