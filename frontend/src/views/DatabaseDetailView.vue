<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useDatabasesStore } from '@/stores/databases'

import DatabaseSessionsPanel from '@/components/databases/DatabaseSessionsPanel.vue'
import DatabaseStoragePanel from '@/components/databases/DatabaseStoragePanel.vue'
import DatabaseActivityPanel from '@/components/databases/DatabaseActivityPanel.vue'
import DatabaseHistoryPanel from '@/components/databases/DatabaseHistoryPanel.vue'
import { useServersStore } from '@/stores/servers'

import {
  useConnectionsStore,
  type DatabaseEngine,
} from '@/stores/connections'

const route = useRoute()
const router = useRouter()
const connectionsStore = useConnectionsStore()
const databasesStore = useDatabasesStore()
const serversStore = useServersStore()

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

type DatabaseTab =
  | 'overview'
  | 'history'
  | 'sessions'
  | 'storage'
  | 'activity'

const activeTab = ref<DatabaseTab>('overview')

const supportsDbaUtilities = computed(() =>
  ['oracle', 'sqlserver', 'mysql'].includes(
    connection.value?.engine ?? '',
  ),
)

const relatedServers = computed(() => {
  if (!connection.value) {
    return []
  }

  const ids =
    connection.value.server_ids ?? []

  return serversStore.servers.filter(
    (server) =>
      ids.includes(server.id),
  )
})

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

function statusLabel(status?: string) {
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

onMounted(async () => {
  if (
    connectionsStore.connections.length === 0
  ) {
    await connectionsStore.load()
  }

  if (
    serversStore.servers.length === 0
  ) {
    await serversStore.load()
  }

  await databasesStore.loadOne(
    connectionId.value
  )
})
</script>

<template>
  <div class="database-workspace">
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

        <span
          class="database-state"
          :class="overview?.status ?? 'unknown'"
        >
          {{ statusLabel(overview?.status) }}
        </span>
      </section>

      <nav class="database-tabs">
        <button :class="{
          active: activeTab === 'overview',
        }" @click="activeTab = 'overview'">
          Overview
        </button>

        <button :class="{
          active: activeTab === 'history',
        }" @click="activeTab = 'history'">
          History
        </button>

        <button :disabled="!supportsDbaUtilities" :class="{
          active: activeTab === 'sessions',
        }" @click="activeTab = 'sessions'">
          Sessions
        </button>

        <button :disabled="!supportsDbaUtilities" :class="{
          active: activeTab === 'storage',
        }" @click="activeTab = 'storage'">
          Storage
        </button>

        <button :disabled="!supportsDbaUtilities" :class="{
          active: activeTab === 'activity',
        }" @click="activeTab = 'activity'">
          Activity
        </button>
      </nav>

      <section v-if="activeTab === 'overview'" class="database-preview-grid database-detail-metrics">
        <div>
          <span>Active</span>

          <strong>
            {{ overview?.active ?? '—' }}
          </strong>
        </div>

        <div>
          <span>Connections</span>

          <strong>
            {{ overview?.connections ?? '—' }}
          </strong>
        </div>

        <div>
          <span>Blocked</span>

          <strong>
            {{ overview?.blocked ?? '—' }}
          </strong>
        </div>

        <div>
          <span>Uptime</span>

          <strong>
            {{
              overview?.uptime_seconds
              ?? '—'
            }}
          </strong>
        </div>
      </section>

      <DatabaseHistoryPanel v-else-if="activeTab === 'history'" :connection-id="connection.id" />

      <DatabaseSessionsPanel v-else-if="activeTab === 'sessions'" :connection-id="connection.id"
        :engine="connection.engine" />

      <DatabaseStoragePanel v-else-if="activeTab === 'storage'" :connection-id="connection.id"
        :engine="connection.engine" />

      <DatabaseActivityPanel v-else-if="activeTab === 'activity'" :connection-id="connection.id"
        :engine="connection.engine" />

      <section v-if="activeTab === 'overview'" class="panel database-overview-panel">
        <div class="panel-header">
          <div>
            <h2>Database information</h2>
            <div v-if="relatedServers.length">
              <dt>Servers</dt>

              <dd>
                {{
                  relatedServers
                    .map((server) => server.name)
                    .join(', ')
                }}
              </dd>
            </div>

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
  </div>
</template>