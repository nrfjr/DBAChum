<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useDatabasesStore } from '@/stores/databases'
import {
  engineLabel,
  engineProductLabel,
  formatMetric,
  formatUptime,
  overviewMetricLabel,
  statusLabel,
} from '@/core/databasePresentation'

import {
  useConnectionsStore,
  type DatabaseConnection,
  type DatabaseEngine,
} from '@/stores/connections'

const router = useRouter()
const connectionsStore = useConnectionsStore()
const databasesStore = useDatabasesStore()

const monitoredConnections = computed(() =>
  connectionsStore.connections.filter(
    (connection) => connection.active && connection.monitor_enabled,
  ),
)

const engineOrder: DatabaseEngine[] = ['oracle', 'sqlserver', 'mysql']

const groupedConnections = computed(() =>
  engineOrder
    .map((engine) => ({
      engine,
      label: engineLabel(engine),
      connections: monitoredConnections.value
        .filter((connection) => connection.engine === engine)
        .sort((a, b) => a.name.localeCompare(b.name)),
    }))
    .filter((group) => group.connections.length > 0),
)

function databaseIdentity(connection: DatabaseConnection) {
  if (connection.engine === 'oracle') {
    return connection.oracle_identifier ?? 'Oracle database'
  }

  return connection.database ?? 'Default database'
}

function openDatabase(connection: DatabaseConnection) {
  router.push({
    name: 'database-detail',
    params: { id: connection.id },
  })
}

function overviewFor(id: string) {
  return databasesStore.overviews[id]
}

onMounted(async () => {
  await Promise.all([
    connectionsStore.load(),
    databasesStore.loadAll(),
  ])
})
</script>

<template>
  <section class="page-header">
    <div>
      <h1>Databases</h1>
      <p>
        Monitor and work with configured databases
        from one place.
      </p>
    </div>

    <button type="button" class="secondary-button" :disabled="databasesStore.loading" @click="databasesStore.loadAll()">
      {{
        databasesStore.loading
          ? 'Refreshing...'
          : 'Refresh'
      }}
    </button>
  </section>

  <div v-if="connectionsStore.loading" class="empty-state">
    Loading databases...
  </div>

  <div v-else-if="connectionsStore.error" class="login-error">
    {{ connectionsStore.error }}
  </div>

  <div v-else-if="monitoredConnections.length === 0" class="database-empty-state">
    <h2>No monitored databases</h2>

    <p>
      Enable monitoring for a database connection from Settings.
    </p>

    <RouterLink to="/settings/connections" class="primary-button">
      Open connection settings
    </RouterLink>
  </div>

  <div v-else class="database-engine-groups">
    <section
      v-for="group in groupedConnections"
      :key="group.engine"
      class="database-engine-group"
    >
      <div class="database-engine-group__header">
        <div>
          <h2>{{ group.label }}</h2>
          <p>{{ group.connections.length }} monitored {{ group.connections.length === 1 ? 'connection' : 'connections' }}</p>
        </div>
        <span class="database-engine-badge">{{ group.label }}</span>
      </div>

      <div class="database-grid">
        <button
          v-for="connection in group.connections"
          :key="connection.id"
          type="button"
          class="database-card"
          @click="openDatabase(connection)"
        >
          <div class="database-card-header">
            <div>
              <strong>{{ connection.name }}</strong>
              <span>
                {{
                  engineProductLabel(
                    connection.engine,
                    overviewFor(connection.id)?.database_product,
                  )
                }}
              </span>
            </div>

            <div class="database-card-status">
              <span
                class="database-state"
                :class="overviewFor(connection.id)?.status ?? 'unknown'"
              >
                {{ statusLabel(overviewFor(connection.id)?.status) }}
              </span>
              <small
                v-if="overviewFor(connection.id)?.response_time_ms != null"
                class="database-latency"
              >
                {{ overviewFor(connection.id)?.response_time_ms }} ms
              </small>
            </div>
          </div>

          <div class="database-endpoint">
            {{ connection.host }}:{{ connection.port }}
          </div>

          <div class="database-identity">
            {{ databaseIdentity(connection) }}
          </div>

          <div class="database-preview-grid">
            <div>
              <span>{{ overviewMetricLabel(connection.engine, 'active') }}</span>
              <strong>{{ formatMetric(overviewFor(connection.id)?.active) }}</strong>
            </div>

            <div>
              <span>{{ overviewMetricLabel(connection.engine, 'connections') }}</span>
              <strong>{{ formatMetric(overviewFor(connection.id)?.connections) }}</strong>
            </div>

            <div>
              <span>{{ overviewMetricLabel(connection.engine, 'blocked') }}</span>
              <strong>{{ formatMetric(overviewFor(connection.id)?.blocked) }}</strong>
            </div>

            <div>
              <span>Uptime</span>
              <strong>{{ formatUptime(overviewFor(connection.id)?.uptime_seconds) }}</strong>
            </div>
          </div>
        </button>
      </div>
    </section>
  </div>
</template>