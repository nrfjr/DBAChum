<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import { useServersStore, type ServerOsFamily, type ServerType } from '@/stores/servers'
import { useAuthStore } from '@/stores/auth'
import { hasPermission } from '@/core/permissions'

const serversStore = useServersStore()
const authStore = useAuthStore()
const router = useRouter()

const canManageServers = computed(() => hasPermission(authStore.user, 'servers:manage'))

const search = ref('')
const environmentFilter = ref('')
const typeFilter = ref<'' | ServerType>('')

const environments = computed(() =>
  [...new Set(
    serversStore.servers
      .map((server) => server.environment)
      .filter((value): value is string => Boolean(value)),
  )].sort((a, b) => a.localeCompare(b)),
)

const filteredServers = computed(() => {
  const q = search.value.trim().toLowerCase()

  return serversStore.servers.filter((server) => {
    if (environmentFilter.value && server.environment !== environmentFilter.value) return false
    if (typeFilter.value && server.server_type !== typeFilter.value) return false
    if (!q) return true

    return [
      server.name,
      server.hostname,
      server.ip_address,
      server.environment,
      server.owner,
      server.server_type,
      server.os_family,
      ...server.tags,
    ]
      .filter(Boolean)
      .some((value) => String(value).toLowerCase().includes(q))
  })
})

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

function openServer(id: string) {
  router.push({ name: 'server-detail', params: { id } })
}

onMounted(() => {
  if (serversStore.servers.length === 0) serversStore.load()
})
</script>

<template>
  <section class="page-header">
    <div>
      <h1>Servers</h1>
      <p>Operational infrastructure workspace. Configuration and credentials live under Settings → Infrastructure.</p>
    </div>
    <RouterLink v-if="canManageServers" class="secondary-button" to="/settings/infrastructure">Infrastructure settings</RouterLink>
  </section>

  <div class="server-workspace-filters">
    <input v-model="search" placeholder="Search server, hostname, owner or tag..." />
    <select v-model="environmentFilter">
      <option value="">All environments</option>
      <option v-for="environment in environments" :key="environment" :value="environment">{{ environment }}</option>
    </select>
    <select v-model="typeFilter">
      <option value="">All server types</option>
      <option value="database">Database server</option>
      <option value="application">Application server</option>
      <option value="utility">Utility server</option>
      <option value="other">Other</option>
    </select>
    <button type="button" class="secondary-button" :disabled="serversStore.loading" @click="serversStore.load()">
      {{ serversStore.loading ? 'Refreshing...' : 'Refresh' }}
    </button>
  </div>

  <p v-if="serversStore.error" class="login-error">{{ serversStore.error }}</p>

  <div v-if="serversStore.loading && serversStore.servers.length === 0" class="database-empty-state">
    <h2>Loading servers...</h2>
  </div>

  <div v-else-if="filteredServers.length === 0" class="database-empty-state">
    <h2>No server assets found</h2>
    <p>Add or update server assets from Settings → Infrastructure.</p>
  </div>

  <div v-else class="server-grid">
    <button
      v-for="server in filteredServers"
      :key="server.id"
      type="button"
      class="server-card server-card-button"
      @click="openServer(server.id)"
    >
      <div class="server-card-header">
        <div>
          <strong>{{ server.name }}</strong>
          <span>{{ serverTypeLabel(server.server_type) }} · {{ osLabel(server.os_family) }}<template v-if="server.os_version"> · {{ server.os_version }}</template></span>
        </div>
        <span>{{ server.enabled ? 'Enabled' : 'Disabled' }}</span>
      </div>

      <div class="server-card-host">
        {{ server.hostname }}<template v-if="server.ip_address"> · {{ server.ip_address }}</template>
      </div>

      <div class="server-metadata">
        <span>Environment: {{ server.environment ?? '—' }}</span>
        <span>Owner: {{ server.owner ?? '—' }}</span>
        <span>Databases: {{ server.database_count }}</span>
        <span>SSH: {{ server.ssh_profile_name ?? 'Not configured' }}</span>
      </div>

      <div v-if="server.tags.length" class="server-tags">
        <span v-for="tag in server.tags" :key="tag">{{ tag }}</span>
      </div>
    </button>
  </div>
</template>
