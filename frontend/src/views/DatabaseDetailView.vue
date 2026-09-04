<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useDatabasesStore } from '@/stores/databases'

import DatabaseSessionsPanel from '@/components/databases/DatabaseSessionsPanel.vue'
import DatabaseStoragePanel from '@/components/databases/DatabaseStoragePanel.vue'
import DatabaseActivityPanel from '@/components/databases/DatabaseActivityPanel.vue'
import DatabaseHistoryPanel from '@/components/databases/DatabaseHistoryPanel.vue'
import DatabaseBackupsPanel from '@/components/databases/DatabaseBackupsPanel.vue'
import DatabaseUsersPanel from '@/components/databases/DatabaseUsersPanel.vue'
import DatabaseAccessPanel from '@/components/databases/DatabaseAccessPanel.vue'
import DatabaseMonitoringNotice from '@/components/databases/DatabaseMonitoringNotice.vue'
import SqlServerHealthPanel from '@/components/databases/sqlserver/SqlServerHealthPanel.vue'
import MySqlHealthPanel from '@/components/databases/mysql/MySqlHealthPanel.vue'
import { useServersStore } from '@/stores/servers'
import { useAuthStore } from '@/stores/auth'
import { hasPermission } from '@/core/permissions'
import {
  engineLabel,
  engineProductLabel,
  formatMetric,
  formatUptime,
  overviewMetricLabel,
  statusLabel,
} from '@/core/databasePresentation'

import { useConnectionsStore } from '@/stores/connections'

const route = useRoute()
const router = useRouter()
const connectionsStore = useConnectionsStore()
const databasesStore = useDatabasesStore()
const serversStore = useServersStore()
const authStore = useAuthStore()

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
  | 'backups'
  | 'health'
  | 'sessions'
  | 'storage'
  | 'activity'
  | 'users'
  | 'access'

const activeTab = ref<DatabaseTab>('overview')

const visitedTabs = reactive<Record<DatabaseTab, boolean>>({
  overview: true,
  history: false,
  backups: false,
  health: false,
  sessions: false,
  storage: false,
  activity: false,
  users: false,
  access: false,
})

function selectTab(tab: DatabaseTab) {
  visitedTabs[tab] = true
  activeTab.value = tab
}

function applyTabFromRoute() {
  if (String(route.query.tab ?? '') !== 'history') return
  visitedTabs.history = true
  activeTab.value = 'history'
}

function resetVisitedTabs() {
  activeTab.value = 'overview'
  for (const tab of Object.keys(visitedTabs) as DatabaseTab[]) {
    visitedTabs[tab] = tab === 'overview'
  }
}

watch(connectionId, () => {
  resetVisitedTabs()
  applyTabFromRoute()
})

watch(
  () => route.query.tab,
  () => applyTabFromRoute(),
)

const supportsDbaUtilities = computed(() =>
  ['oracle', 'sqlserver', 'mysql'].includes(
    connection.value?.engine ?? '',
  ),
)

const supportsOperationalHealth = computed(() =>
  ['sqlserver', 'mysql'].includes(connection.value?.engine ?? ''),
)

const supportsUsersAndSchemas = computed(() =>
  ['oracle', 'sqlserver', 'mysql'].includes(connection.value?.engine ?? '') &&
  hasPermission(
    authStore.user?.role,
    'database:operate',
  ),
)

const supportsAccessAndPrivileges = computed(() =>
  ['oracle', 'sqlserver', 'mysql'].includes(connection.value?.engine ?? '') &&
  hasPermission(
    authStore.user?.role,
    'database:operate',
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

onMounted(async () => {
  applyTabFromRoute()

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
            {{
              engineProductLabel(
                connection.engine,
                overview?.database_product,
              )
            }}
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
        }" @click="selectTab('overview')">
          Overview
        </button>

        <button :class="{
          active: activeTab === 'history',
        }" @click="selectTab('history')">
          History
        </button>

        <button :class="{
          active: activeTab === 'backups',
        }" @click="selectTab('backups')">
          Backups
        </button>

        <button
          v-if="supportsOperationalHealth"
          :class="{ active: activeTab === 'health' }"
          @click="selectTab('health')"
        >
          Health
        </button>

        <button :disabled="!supportsDbaUtilities" :class="{
          active: activeTab === 'sessions',
        }" @click="selectTab('sessions')">
          Sessions
        </button>

        <button :disabled="!supportsDbaUtilities" :class="{
          active: activeTab === 'storage',
        }" @click="selectTab('storage')">
          Storage
        </button>

        <button :disabled="!supportsDbaUtilities" :class="{
          active: activeTab === 'activity',
        }" @click="selectTab('activity')">
          Activity
        </button>

        <button
          v-if="supportsUsersAndSchemas"
          :class="{
            active: activeTab === 'users',
          }"
          @click="selectTab('users')"
        >
          {{ connection.engine === 'sqlserver' ? 'Users & Principals' : connection.engine === 'mysql' ? 'Users & Hosts' : 'Users & Schemas' }}
        </button>

        <button
          v-if="supportsAccessAndPrivileges"
          :class="{
            active: activeTab === 'access',
          }"
          @click="selectTab('access')"
        >
          {{ connection.engine === 'mysql' ? 'Access & Grants' : 'Access & Privileges' }}
        </button>
      </nav>

      <section v-if="activeTab === 'overview'" class="database-preview-grid database-detail-metrics">
        <div>
          <span>{{ overviewMetricLabel(connection.engine, 'active') }}</span>

          <strong>
            {{ formatMetric(overview?.active) }}
          </strong>
        </div>

        <div>
          <span>{{ overviewMetricLabel(connection.engine, 'connections') }}</span>

          <strong>
            {{ formatMetric(overview?.connections) }}
          </strong>
        </div>

        <div>
          <span>{{ overviewMetricLabel(connection.engine, 'blocked') }}</span>

          <strong>
            {{ formatMetric(overview?.blocked) }}
          </strong>
        </div>

        <div>
          <span>Uptime</span>

          <strong>
            {{ formatUptime(overview?.uptime_seconds) }}
          </strong>
        </div>
      </section>

      <DatabaseMonitoringNotice
        v-if="activeTab === 'overview'"
        :status="overview?.status"
        :warnings="overview?.warnings"
        :error="overview?.error"
      />

      <!--
        Panels are lazy-mounted the first time their tab is opened, then kept
        alive with v-show. This preserves filters, form inputs and search
        results while avoiding repeat API loads on every tab switch.
      -->
      <DatabaseHistoryPanel
        v-if="visitedTabs.history"
        v-show="activeTab === 'history'"
        :key="`history-${connection.id}`"
        :connection-id="connection.id"
      />

      <DatabaseBackupsPanel
        v-if="visitedTabs.backups"
        v-show="activeTab === 'backups'"
        :key="`backups-${connection.id}`"
        :connection-id="connection.id"
      />

      <SqlServerHealthPanel
        v-if="visitedTabs.health && connection.engine === 'sqlserver'"
        v-show="activeTab === 'health'"
        :key="`health-sqlserver-${connection.id}`"
        :connection-id="connection.id"
      />

      <MySqlHealthPanel
        v-if="visitedTabs.health && connection.engine === 'mysql'"
        v-show="activeTab === 'health'"
        :key="`health-mysql-${connection.id}`"
        :connection-id="connection.id"
      />

      <DatabaseSessionsPanel
        v-if="visitedTabs.sessions"
        v-show="activeTab === 'sessions'"
        :key="`sessions-${connection.id}`"
        :connection-id="connection.id"
        :engine="connection.engine"
      />

      <DatabaseStoragePanel
        v-if="visitedTabs.storage"
        v-show="activeTab === 'storage'"
        :key="`storage-${connection.id}`"
        :connection-id="connection.id"
        :engine="connection.engine"
      />

      <DatabaseActivityPanel
        v-if="visitedTabs.activity"
        v-show="activeTab === 'activity'"
        :key="`activity-${connection.id}`"
        :connection-id="connection.id"
        :engine="connection.engine"
      />

      <DatabaseUsersPanel
        v-if="visitedTabs.users"
        v-show="activeTab === 'users'"
        :key="`users-${connection.id}`"
        :connection-id="connection.id"
        :engine="connection.engine"
        :active="activeTab === 'users'"
      />

      <DatabaseAccessPanel
        v-if="visitedTabs.access"
        v-show="activeTab === 'access'"
        :key="`access-${connection.id}`"
        :connection-id="connection.id"
        :engine="connection.engine"
      />

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

          <div v-if="connection.engine === 'oracle'">
            <dt>Privilege mode</dt>
            <dd>
              {{
                connection.oracle_auth_mode === 'sysdba'
                  ? 'SYSDBA'
                  : 'Normal'
              }}
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

          <div v-if="overview?.generation">
            <dt>Generation</dt>
            <dd>{{ overview.generation }}</dd>
          </div>

          <div v-if="overview?.edition">
            <dt>Edition</dt>
            <dd>{{ overview.edition }}</dd>
          </div>

          <div v-if="overview?.product_level">
            <dt>Product level</dt>
            <dd>{{ overview.product_level }}</dd>
          </div>

          <div v-if="overview?.connection_provider">
            <dt>Connection provider</dt>
            <dd>
              {{ overview.connection_provider }}
              <template v-if="overview.connection_driver">
                · {{ overview.connection_driver }}
              </template>
            </dd>
          </div>

          <div v-if="overview?.connection_encrypt">
            <dt>Transport encryption</dt>
            <dd>{{ overview.connection_encrypt === 'yes' ? 'Enabled' : 'Disabled' }}</dd>
          </div>

          <template v-if="connection.engine === 'mysql'">
            <div v-if="overview?.database_product">
              <dt>Server product</dt>
              <dd>{{ overview.database_product }}</dd>
            </div>

            <div v-if="overview?.version_comment">
              <dt>Distribution</dt>
              <dd>{{ overview.version_comment }}</dd>
            </div>

            <div v-if="overview?.server_hostname">
              <dt>Server hostname</dt>
              <dd>{{ overview.server_hostname }}</dd>
            </div>

            <div v-if="overview?.server_port != null">
              <dt>Server-reported port</dt>
              <dd>{{ overview.server_port }}</dd>
            </div>

            <div v-if="overview?.database_count != null">
              <dt>Visible databases</dt>
              <dd>{{ overview.database_count }}</dd>
            </div>

            <div v-if="overview?.max_connections != null">
              <dt>Max connections</dt>
              <dd>{{ overview.max_connections }}</dd>
            </div>

            <div v-if="overview?.questions != null">
              <dt>Questions since startup</dt>
              <dd>{{ overview?.questions?.toLocaleString() ?? '—' }}</dd>
            </div>

            <div v-if="overview?.slow_queries != null">
              <dt>Slow queries since startup</dt>
              <dd>{{ overview?.slow_queries?.toLocaleString() ?? '—' }}</dd>
            </div>

            <div v-if="overview?.data_directory">
              <dt>Data directory</dt>
              <dd>{{ overview.data_directory }}</dd>
            </div>

            <div v-if="overview?.performance_schema_enabled != null">
              <dt>Performance Schema</dt>
              <dd>
                {{ overview.performance_schema_enabled ? 'Enabled' : 'Disabled' }}
                <template
                  v-if="
                    !overview.performance_schema_enabled
                    && overview.capabilities?.performance_schema_present
                  "
                >
                  · compatible fallbacks active
                </template>
              </dd>
            </div>
          </template>

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