<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useDatabasesStore } from '@/stores/databases'

import {
  useConnectionsStore,
  type DatabaseConnection,
  type DatabaseEngine,
} from '@/stores/connections'

const router = useRouter()
const connectionsStore = useConnectionsStore()
const databasesStore = useDatabasesStore()

const enabledConnections = computed(() =>
  connectionsStore.connections.filter(
    (connection) => connection.enabled,
  ),
)

function engineLabel(engine: DatabaseEngine) {
  switch (engine) {
    case 'oracle':
      return 'Oracle'
    case 'sqlserver':
      return 'SQL Server'
    case 'mysql':
      return 'MySQL'
  }
}

function databaseIdentity(
  connection: DatabaseConnection,
) {
  if (connection.engine === 'oracle') {
    return connection.oracle_identifier ?? 'Oracle database'
  }

  return connection.database ?? 'Default database'
}

function openDatabase(connection: DatabaseConnection) {
  router.push({
    name: 'database-detail',
    params: {
      id: connection.id,
    },
  })
}

function overviewFor(id: string) {
  return databasesStore.overviews[id]
}

function statusLabel(
  status?: string,
) {
  switch (status) {
    case 'online':
      return 'Online'
    case 'limited':
      return 'Limited'
    case 'unreachable':
      return 'Unreachable'
    case 'disabled':
      return 'Disabled'
    default:
      return 'Not checked'
  }
}

function metricValue(
  value: number | null | undefined,
) {
  if (value == null) {
    return '—'
  }

  return new Intl.NumberFormat().format(value)
}

function formatUptime(
  seconds: number | null | undefined,
) {
  if (seconds == null) {
    return '—'
  }

  const days = Math.floor(
    seconds / 86400
  )

  const hours = Math.floor(
    (seconds % 86400) / 3600
  )

  if (days > 0) {
    return `${days}d ${hours}h`
  }

  const minutes = Math.floor(
    (seconds % 3600) / 60
  )

  if (hours > 0) {
    return `${hours}h ${minutes}m`
  }

  return `${minutes}m`
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

  <div v-else-if="enabledConnections.length === 0" class="database-empty-state">
    <h2>No monitored databases</h2>

    <p>
      Add or enable a database connection from Settings.
    </p>

    <RouterLink to="/settings/connections" class="primary-button">
      Open connection settings
    </RouterLink>
  </div>

  <div v-else class="database-grid">
    <button v-for="connection in enabledConnections" :key="connection.id" type="button" class="database-card"
      @click="openDatabase(connection)">
      <div class="database-card-header">
        <div>
          <strong>{{ connection.name }}</strong>
          <span>{{ engineLabel(connection.engine) }}</span>
        </div>

        <span class="database-state" :class="overviewFor(connection.id)?.status ??
          'unknown'
          ">
          {{
            statusLabel(
              overviewFor(connection.id)?.status,
            )
          }}
        </span>
        <small v-if="
          overviewFor(connection.id)
            ?.response_time_ms != null
        " class="database-latency">
          {{
            overviewFor(connection.id)
              ?.response_time_ms
          }} ms
        </small>
      </div>

      <div class="database-endpoint">
        {{ connection.host }}:{{ connection.port }}
      </div>

      <div class="database-identity">
        {{ databaseIdentity(connection) }}
      </div>

      <div class="database-preview-grid">
        <div>
          <span>Active</span>

          <strong>
            {{
              metricValue(
                overviewFor(connection.id)?.active,
              )
            }}
          </strong>
        </div>

        <div>
          <span>Connections</span>

          <strong>
            {{
              metricValue(
                overviewFor(connection.id)
                  ?.connections,
              )
            }}
          </strong>
        </div>

        <div>
          <span>Blocked</span>

          <strong>
            {{
              metricValue(
                overviewFor(connection.id)?.blocked,
              )
            }}
          </strong>
        </div>

        <div>
          <span>Uptime</span>

          <strong>
            {{
              formatUptime(
                overviewFor(connection.id)
                  ?.uptime_seconds,
              )
            }}
          </strong>
        </div>
      </div>
    </button>
  </div>
</template>