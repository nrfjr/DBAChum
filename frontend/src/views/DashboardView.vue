<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'

import { useAlertsStore } from '@/stores/alerts'
import { useConnectionsStore } from '@/stores/connections'
import { useDatabasesStore } from '@/stores/databases'
import { useServersStore } from '@/stores/servers'
import { useUiStore } from '@/stores/ui'

interface HealthResponse {
  api: string
  mongodb: string
}

const health = ref<HealthResponse | null>(null)
const healthError = ref(false)
const uiStore = useUiStore()
const alertsStore = useAlertsStore()
const connectionsStore = useConnectionsStore()
const databasesStore = useDatabasesStore()
const serversStore = useServersStore()

const enabledDatabases = computed(() => connectionsStore.connections.filter((item) => item.active))
const monitoredDatabases = computed(() => connectionsStore.connections.filter((item) => item.active && item.monitor_enabled))
const enabledServers = computed(() => serversStore.servers.filter((item) => item.enabled))
const databaseHealthRows = computed(() =>
  enabledDatabases.value
    .map((connection) => ({ connection, overview: databasesStore.overviews[connection.id] }))
    .sort((left, right) => left.connection.name.localeCompare(right.connection.name)),
)

function statusText(status: string | undefined) {
  return status ? status.charAt(0).toUpperCase() + status.slice(1) : 'Not sampled'
}

async function checkHealth() {
  if (!uiStore.isOnline) {
    health.value = null
    healthError.value = false
    return
  }

  healthError.value = false

  try {
    const apiBaseUrl = import.meta.env.VITE_API_BASE_URL
    const response = await fetch(`${apiBaseUrl}/health`)
    if (!response.ok) throw new Error(`HTTP ${response.status}`)
    health.value = await response.json()
  } catch {
    health.value = null
    healthError.value = true
  }
}

async function loadWorkspaceSummary() {
  await Promise.allSettled([
    connectionsStore.load(),
    serversStore.load(),
    databasesStore.loadAll(),
    alertsStore.loadSummary(),
    alertsStore.load('active'),
    checkHealth(),
  ])
}

watch(
  () => uiStore.isOnline,
  (isOnline) => {
    if (!isOnline) {
      health.value = null
      healthError.value = false
      return
    }
    void checkHealth()
  },
)

onMounted(() => {
  void loadWorkspaceSummary()
})
</script>

<template>
  <div class="dashboard">
    <section class="metric-grid">
      <RouterLink to="/databases" class="metric-card metric-card--link">
        <span class="metric-card__label">Databases</span>
        <strong class="metric-card__value">{{ enabledDatabases.length }}</strong>
        <span class="metric-card__hint">{{ monitoredDatabases.length }} monitored</span>
      </RouterLink>

      <RouterLink to="/servers" class="metric-card metric-card--link">
        <span class="metric-card__label">Servers</span>
        <strong class="metric-card__value">{{ enabledServers.length }}</strong>
        <span class="metric-card__hint">{{ serversStore.servers.length }} configured</span>
      </RouterLink>

      <RouterLink to="/alerts" class="metric-card metric-card--link">
        <span class="metric-card__label">Warnings</span>
        <strong class="metric-card__value">{{ alertsStore.summary.warning }}</strong>
        <span class="metric-card__hint">Active warning alerts</span>
      </RouterLink>

      <RouterLink to="/alerts" class="metric-card metric-card--link">
        <span class="metric-card__label">Critical</span>
        <strong class="metric-card__value">{{ alertsStore.summary.critical }}</strong>
        <span class="metric-card__hint">Active critical alerts</span>
      </RouterLink>
    </section>

    <section class="dashboard-grid">
      <article class="panel">
        <div class="panel__header">
          <div>
            <h2 title="Current state of configured database connections.">Database health</h2>
          </div>
          <RouterLink class="text-link" to="/databases">View databases</RouterLink>
        </div>

        <div v-if="databaseHealthRows.length" class="dashboard-health-list">
          <RouterLink
            v-for="row in databaseHealthRows.slice(0, 8)"
            :key="row.connection.id"
            :to="{ name: 'database-detail', params: { id: row.connection.id }, query: { engine: row.connection.engine } }"
            class="dashboard-health-row"
          >
            <div>
              <strong>{{ row.connection.name }}</strong>
              <small>{{ row.connection.host }}:{{ row.connection.port }}</small>
            </div>
            <span class="resource-state-pill" :data-state="row.overview?.status ?? 'unknown'">
              {{ statusText(row.overview?.status) }}
            </span>
          </RouterLink>
        </div>

        <div v-else class="empty-state empty-state--small">
          <div class="empty-state__icon">DB</div>
          <strong>No databases configured</strong>
          <p>Add a database connection under Settings → Connections.</p>
        </div>
      </article>

      <article class="panel">
        <div class="panel__header">
          <div>
            <h2 title="DBAChum application services.">System status</h2>
          </div>
            <button type="button" class="secondary-button" @click="checkHealth">Refresh</button>
        </div>

        <div v-if="!uiStore.isOnline" class="status-message">Status unknown — device offline.</div>
        <div v-else-if="health" class="status-list">
          <div class="status-row"><span>FastAPI</span><span class="status status--healthy">● {{ health.api }}</span></div>
          <div class="status-row"><span>MongoDB</span><span class="status status--healthy">● {{ health.mongodb }}</span></div>
        </div>
        <div v-else-if="healthError" class="status-message status-message--error">Backend unavailable.</div>
        <div v-else class="status-message">Checking services...</div>
      </article>
    </section>

    <section class="panel">
      <div class="panel__header">
        <div>
          <h2 title="Active database and server conditions that need attention.">Recent alerts</h2>
        </div>
        <RouterLink class="text-link" to="/alerts">View all</RouterLink>
      </div>

      <div v-if="alertsStore.items.length" class="dashboard-alert-list">
        <RouterLink v-for="alert in alertsStore.items.slice(0, 5)" :key="alert.id" to="/alerts" class="dashboard-alert-row">
          <span class="alert-severity-badge" :class="alert.severity">{{ alert.severity }}</span>
          <div><strong>{{ alert.title }}</strong><small>{{ alert.source_name }}</small></div>
        </RouterLink>
      </div>

      <div v-else class="empty-state empty-state--small">
        <strong>No active alerts</strong>
      </div>
    </section>
  </div>
</template>
