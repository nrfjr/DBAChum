<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { engineLabel } from '@/core/databasePresentation'
import { useDatabasesStore } from '@/stores/databases'
import {
  useConnectionsStore,
  type DatabaseConnection,
  type DatabaseEngine,
} from '@/stores/connections'

const route = useRoute()
const router = useRouter()
const connectionsStore = useConnectionsStore()
const databasesStore = useDatabasesStore()

const engineOrder: DatabaseEngine[] = ['oracle', 'sqlserver', 'mysql']

const selectedEngine = computed<DatabaseEngine | null>(() => {
  const value = String(route.query.engine ?? '')
  return engineOrder.includes(value as DatabaseEngine) ? value as DatabaseEngine : null
})

const monitoredConnections = computed(() =>
  connectionsStore.connections.filter(
    (connection) => connection.active && connection.monitor_enabled,
  ),
)

const groupedConnections = computed(() =>
  engineOrder
    .filter((engine) => !selectedEngine.value || selectedEngine.value === engine)
    .map((engine) => ({
      engine,
      label: engineLabel(engine),
      connections: monitoredConnections.value
        .filter((connection) => connection.engine === engine)
        .sort((a, b) => a.name.localeCompare(b.name)),
    }))
    .filter((group) => group.connections.length > 0),
)

const pageHeading = computed(() =>
  selectedEngine.value ? `${engineLabel(selectedEngine.value)} databases` : '',
)

function databaseIdentity(connection: DatabaseConnection) {
  if (connection.engine === 'oracle') return connection.oracle_identifier ?? 'Oracle database'
  return connection.database ?? 'Default database'
}

function openDatabase(connection: DatabaseConnection) {
  router.push({
    name: 'database-detail',
    params: { id: connection.id },
    query: { engine: connection.engine },
  })
}

function statusClass(connectionId: string) {
  return databasesStore.overviews[connectionId]?.status ?? 'unknown'
}

async function refresh() {
  await Promise.allSettled([connectionsStore.load(), databasesStore.loadAll()])
}

onMounted(() => {
  void refresh()
})
</script>

<template>
  <section class="page-header database-list-page-header">
    <div v-if="pageHeading !== ''">
      <h1>{{ pageHeading }}</h1>
    </div>

    <button type="button" class="secondary-button refresh-button" :disabled="databasesStore.loading" @click="refresh">
      {{ databasesStore.loading ? 'Refreshing' : 'Refresh' }}
      <p v-if="databasesStore.loading" class="loading"></p>
    </button>
  </section>

  <div v-if="connectionsStore.loading && connectionsStore.connections.length === 0" class="empty-state">
    Loading databases<p class="loading"></p>
  </div>

  <div v-else-if="connectionsStore.error" class="login-error">
    {{ connectionsStore.error }}
  </div>

  <div v-else-if="monitoredConnections.length === 0" class="database-empty-state">
    <h2>No monitored databases</h2>
    <RouterLink to="/settings/connections" class="primary-button">Open connection settings</RouterLink>
  </div>

  <div v-else-if="groupedConnections.length === 0" class="database-empty-state">
    <h2>No {{ selectedEngine ? engineLabel(selectedEngine) : '' }} databases found</h2>
  </div>

  <div v-else class="database-engine-groups" :class="{ 'database-engine-groups--single': selectedEngine }">
    <section v-for="group in groupedConnections" :key="group.engine" class="database-engine-group">
      <div v-if="!selectedEngine" class="database-engine-group__header">
        <div>
          <h2>{{ group.label }}</h2>
          <p>{{ group.connections.length }} monitored {{ group.connections.length === 1 ? 'database' : 'databases' }}</p>
        </div>
      </div>

      <div
        class="database-grid database-selection-grid"
        :class="selectedEngine ? 'database-selection-grid--wrap' : 'database-selection-grid--strip'"
      >
        <button
          v-for="connection in group.connections"
          :key="connection.id"
          type="button"
          class="database-card database-selection-card"
          @click="openDatabase(connection)"
        >
          <div class="database-selection-card__title">
            <strong>{{ connection.name }}</strong>
            <span
              class="database-reachability-dot"
              :class="`database-reachability-dot--${statusClass(connection.id)}`"
              :title="statusClass(connection.id)"
            />
          </div>

          <div class="database-endpoint">{{ connection.host }}:{{ connection.port }}</div>
          <div class="database-identity">{{ databaseIdentity(connection) }}</div>
        </button>
      </div>
    </section>
  </div>
</template>

<style scoped>
.database-list-page-header {
  display: flex;
  width: 100%;
  gap: 1rem;
}

.database-list-page-header > .secondary-button {
  margin-left: auto;
  flex: 0 0 auto;
  margin-top: auto;
}

.database-engine-groups--single {
  margin-top: .25rem;
}

.database-selection-grid {
  gap: 1rem;
}

.database-selection-grid--strip {
  display: grid;
  grid-auto-flow: column;
  grid-auto-columns: minmax(260px, 320px);
  grid-template-rows: 1fr;
  overflow-x: auto;
  overscroll-behavior-inline: contain;
  padding: .125rem .125rem .75rem;
  scroll-snap-type: inline proximity;
}

.database-selection-grid--wrap {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
}

.database-selection-card {
  min-width: 0;
  text-align: left;
  scroll-snap-align: start;
}

.database-selection-card__title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: .75rem;
}

.database-reachability-dot {
  width: .65rem;
  height: .65rem;
  flex: 0 0 auto;
  border-radius: 999px;
  background: var(--text-muted);
  opacity: .65;
}

.database-reachability-dot--online,
.database-reachability-dot--limited {
  background: #22c55e;
  opacity: 1;
}

.database-reachability-dot--unreachable {
  background: #ef4444;
  opacity: 1;
}

.database-reachability-dot--disabled {
  background: var(--text-muted);
}

@media (max-width: 640px) {
  .database-list-page-header {
    align-items: stretch;
    flex-direction: column;
  }

  .database-list-page-header > .secondary-button {
    margin-left: 0;
    align-self: flex-end;
  }

  .database-selection-grid--strip {
    grid-auto-columns: minmax(235px, 82vw);
  }
}
</style>
