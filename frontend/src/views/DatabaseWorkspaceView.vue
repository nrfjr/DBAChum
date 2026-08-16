<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'

import {
  useConnectionsStore,
  type DatabaseConnection,
  type DatabaseEngine,
} from '@/stores/connections'

const router = useRouter()
const connectionsStore = useConnectionsStore()

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

onMounted(() => {
  connectionsStore.load()
})
</script>

<template>
  <section class="page-header">
    <div>
      <h1>Databases</h1>
      <p>
        Monitor and work with configured databases from one place.
      </p>
    </div>
  </section>

  <div
    v-if="connectionsStore.loading"
    class="empty-state"
  >
    Loading databases...
  </div>

  <div
    v-else-if="connectionsStore.error"
    class="login-error"
  >
    {{ connectionsStore.error }}
  </div>

  <div
    v-else-if="enabledConnections.length === 0"
    class="database-empty-state"
  >
    <h2>No monitored databases</h2>

    <p>
      Add or enable a database connection from Settings.
    </p>

    <RouterLink
      to="/settings/connections"
      class="primary-button"
    >
      Open connection settings
    </RouterLink>
  </div>

  <div
    v-else
    class="database-grid"
  >
    <button
      v-for="connection in enabledConnections"
      :key="connection.id"
      type="button"
      class="database-card"
      @click="openDatabase(connection)"
    >
      <div class="database-card-header">
        <div>
          <strong>{{ connection.name }}</strong>
          <span>{{ engineLabel(connection.engine) }}</span>
        </div>

        <span class="database-state unknown">
          Not checked
        </span>
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
          <strong>—</strong>
        </div>

        <div>
          <span>Connections</span>
          <strong>—</strong>
        </div>

        <div>
          <span>Blocked</span>
          <strong>—</strong>
        </div>

        <div>
          <span>Size</span>
          <strong>—</strong>
        </div>
      </div>
    </button>
  </div>
</template>