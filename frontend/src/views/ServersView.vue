<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { useServersStore, type ServerOsFamily, type ServerType } from '@/stores/servers'
import { useAuthStore } from '@/stores/auth'
import { useAnalyticsStore } from '@/stores/analytics'
import { hasPermission } from '@/core/permissions'

const serversStore = useServersStore()
const authStore = useAuthStore()
const analyticsStore = useAnalyticsStore()
const route = useRoute()
const router = useRouter()

const canManageServers = computed(() => hasPermission(authStore.user, 'servers:manage'))
const search = ref('')
const environmentFilter = ref('')
const typeFilter = ref<'' | ServerType>('')
const osFamilies: ServerOsFamily[] = ['windows', 'linux', 'aix', 'unix', 'other']

const selectedOs = computed<ServerOsFamily | null>(() => {
  const value = String(route.query.os ?? '')
  return osFamilies.includes(value as ServerOsFamily) ? value as ServerOsFamily : null
})

const environments = computed(() =>
  [...new Set(
    serversStore.servers
      .filter((server) => !selectedOs.value || server.os_family === selectedOs.value)
      .map((server) => server.environment)
      .filter((value): value is string => Boolean(value)),
  )].sort((a, b) => a.localeCompare(b)),
)

const filteredServers = computed(() => {
  const q = search.value.trim().toLowerCase()

  return serversStore.servers.filter((server) => {
    if (selectedOs.value && server.os_family !== selectedOs.value) return false
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
      server.os_version,
      ...server.tags,
    ]
      .filter(Boolean)
      .some((value) => String(value).toLowerCase().includes(q))
  })
})

const pageHeading = computed(() => selectedOs.value ? `${osLabel(selectedOs.value)} servers` : '')

const serverStatus = computed(() => {
  const statuses = new Map<string, string>()
  for (const item of analyticsStore.servers?.items ?? []) statuses.set(item.server_id, item.status)
  return statuses
})

function statusClass(serverId: string, enabled: boolean) {
  if (!enabled) return 'disabled'
  return serverStatus.value.get(serverId) ?? 'unknown'
}

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
  router.push({ name: 'server-detail', params: { id }, query: selectedOs.value ? { os: selectedOs.value } : {} })
}

onMounted(() => {
  void Promise.allSettled([
    serversStore.servers.length === 0 ? serversStore.load() : Promise.resolve(),
    analyticsStore.loadServers(),
  ])
})
</script>

<template>
  <section class="page-header server-list-page-header">
    <div v-if="pageHeading !== ''" title="Host inventory and operating-system workspace.">
      <h1>{{ pageHeading }}</h1>
    </div>
    <div class="server-list-page-actions">
      <RouterLink v-if="canManageServers" class="secondary-button" :to="{ name: 'settings-connections', query: { type: 'servers' } }">Manage connections</RouterLink>
      <button type="button" class="secondary-button refresh-button" :disabled="serversStore.loading" @click="serversStore.load()">
        {{ serversStore.loading ? 'Refreshing' : 'Refresh' }}
        <p v-if="serversStore.loading" class="loading"></p>
      </button>
    </div>
  </section>

  <div class="server-workspace-filters">
    <input class="utility-search-input" v-model="search" placeholder="Search server, hostname, owner or tag..." />
    <select class="utility-select-input" v-model="environmentFilter">
      <option value="">All environments</option>
      <option v-for="environment in environments" :key="environment" :value="environment">{{ environment }}</option>
    </select>
    <select class="utility-select-input" v-model="typeFilter">
      <option value="">All server types</option>
      <option value="database">Database server</option>
      <option value="application">Application server</option>
      <option value="utility">Utility server</option>
      <option value="other">Other</option>
    </select>
  </div>

  <p v-if="serversStore.error" class="login-error">{{ serversStore.error }}</p>

  <div v-if="serversStore.loading && serversStore.servers.length === 0" class="database-empty-state">
    <h2>Loading servers...</h2>
  </div>

  <div v-else-if="filteredServers.length === 0" class="database-empty-state">
    <h2>No server assets found</h2>
    <p>Add or update server assets from Settings → Connections → Servers / SSH.</p>
  </div>

  <div v-else class="server-grid">
    <button v-for="server in filteredServers" :key="server.id" type="button" class="database-card server-card-button server-selection-card" @click="openServer(server.id)">
      <div class="server-selection-card__title">
        <strong>{{ server.name }}</strong>
        <span
          class="server-reachability-dot"
          :class="`server-reachability-dot--${statusClass(server.id, server.enabled)}`"
          :title="statusClass(server.id, server.enabled)"
        />
      </div>

      <div class="database-endpoint">{{ server.hostname }}<template v-if="server.ip_address"> · {{ server.ip_address }}</template></div>

      <div class="database-identity server-selection-card__meta">
        <span>{{ osLabel(server.os_family) }}<template v-if="server.os_version"> {{ server.os_version }}</template></span>
        <span>{{ serverTypeLabel(server.server_type) }}</span>
        <span v-if="server.environment">{{ server.environment }}</span>
        <span>{{ server.database_count }} {{ server.database_count === 1 ? 'database' : 'databases' }}</span>
      </div>
    </button>
  </div>
</template>

<style scoped>

.server-grid {
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
}
.server-selection-card {
  min-width: 0;
  text-align: left;
}
.server-selection-card__title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: .75rem;
}
.server-selection-card__meta {
  display: flex;
  flex-wrap: wrap;
  gap: .25rem .65rem;
}
.server-reachability-dot {
  width: .65rem;
  height: .65rem;
  flex: 0 0 auto;
  border-radius: 999px;
  background: var(--text-muted);
  opacity: .65;
}
.server-reachability-dot--online,
.server-reachability-dot--limited {
  background: #22c55e;
  opacity: 1;
}
.server-reachability-dot--unreachable {
  background: #ef4444;
  opacity: 1;
}
.server-reachability-dot--disabled {
  background: var(--text-muted);
}
.server-list-page-header,
.server-list-page-actions {
  display: flex;
  align-items: flex-end;
  gap: .75rem;
}
.server-list-page-header {
  justify-content: space-between;
  margin-bottom: 20px;
}
.server-list-page-actions {
  margin-left: auto;
  flex: 0 0 auto;
}
@media (max-width: 720px) {
  .server-list-page-header {
    align-items: stretch;
    flex-direction: column;
  }
  .server-list-page-actions {
    margin-left: 0;
    align-self: flex-end;
    flex-wrap: wrap;
  }
}
</style>
