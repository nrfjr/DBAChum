<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useDatabasesStore } from '@/stores/databases'

import {
  useConnectionsStore,
  type DatabaseEngine,
} from '@/stores/connections'

const route = useRoute()
const router = useRouter()
const connectionsStore = useConnectionsStore()
const databasesStore = useDatabasesStore()

const connectionId = computed(
  () => route.params.id as string,
)

const connection = computed(() =>
  connectionsStore.connections.find(
    (item) => item.id === connectionId.value,
  ),
)

const overview = computed(() =>
  databasesStore.overviews[
  connectionId.value
  ],
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

onMounted(async () => {
  if (
    connectionsStore.connections.length === 0
  ) {
    await connectionsStore.load()
  }

  await databasesStore.loadOne(
    connectionId.value
  )
})
</script>

<template>
  <div v-if="connectionsStore.loading" class="empty-state">
    Loading database...
  </div>

  <div v-else-if="!connection" class="database-empty-state">
    <h1>Database not found</h1>

    <button type="button" class="secondary-button" @click="router.push('/databases')">
      Back to databases
    </button>
  </div>

  <template v-else>
    <section class="database-detail-header">
      <div>
        <button type="button" class="database-back-button" @click="router.push('/databases')">
          ← Databases
        </button>

        <h1>{{ connection.name }}</h1>

        <p>
          {{ engineLabel(connection.engine) }}
          ·
          {{ connection.host }}:{{ connection.port }}
        </p>
      </div>

      <span class="database-state unknown">
        Not checked
      </span>
    </section>

    <nav class="database-tabs">
      <button class="active">
        Overview
      </button>

      <button disabled>
        Sessions
      </button>

      <button disabled>
        Storage
      </button>

      <button disabled>
        Performance
      </button>
    </nav>

    <section class="database-preview-grid database-detail-metrics">
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
    </section>

    <section class="panel database-overview-panel">
      <div class="panel-header">
        <div>
          <h2>Database information</h2>

          <p>
            Connection identity and monitoring context.
          </p>
        </div>
      </div>

      <dl class="database-info-grid">
        <div>
          <dt>Engine</dt>
          <dd>{{ engineLabel(connection.engine) }}</dd>
        </div>

        <div>
          <dt>Host</dt>
          <dd>{{ connection.host }}</dd>
        </div>

        <div>
          <dt>Port</dt>
          <dd>{{ connection.port }}</dd>
        </div>

        <div>
          <dt>Username</dt>
          <dd>{{ connection.username }}</dd>
        </div>

        <div v-if="connection.engine === 'oracle'">
          <dt>
            {{
              connection.oracle_identifier_type === 'sid'
                ? 'SID'
                : 'Service name'
            }}
          </dt>

          <dd>
            {{ connection.oracle_identifier }}
          </dd>
        </div>

        <div v-else>
          <dt>Database</dt>

          <dd>
            {{ connection.database ?? 'Default' }}
          </dd>
        </div>
        <div v-if="overview?.version">
          <dt>Version</dt>
          <dd>{{ overview.version }}</dd>
        </div>

        <div v-if="overview?.database_name">
          <dt>Database</dt>
          <dd>{{ overview.database_name }}</dd>
        </div>

        <div v-if="overview?.container_name">
          <dt>Container</dt>
          <dd>{{ overview.container_name }}</dd>
        </div>

        <div v-if="overview?.service_name">
          <dt>Service</dt>
          <dd>{{ overview.service_name }}</dd>
        </div>

        <div v-if="overview?.instance_name">
          <dt>Instance</dt>
          <dd>{{ overview.instance_name }}</dd>
        </div>
      </dl>
    </section>
  </template>
</template>