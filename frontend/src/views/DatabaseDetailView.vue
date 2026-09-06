<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import DatabaseAccessPanel from '@/components/databases/DatabaseAccessPanel.vue'
import DatabaseActivityPanel from '@/components/databases/DatabaseActivityPanel.vue'
import DatabaseBackupsPanel from '@/components/databases/DatabaseBackupsPanel.vue'
import DatabaseHistoryPanel from '@/components/databases/DatabaseHistoryPanel.vue'
import DatabaseMonitoringNotice from '@/components/databases/DatabaseMonitoringNotice.vue'
import DatabaseSessionsPanel from '@/components/databases/DatabaseSessionsPanel.vue'
import DatabaseStoragePanel from '@/components/databases/DatabaseStoragePanel.vue'
import DatabaseUsersPanel from '@/components/databases/DatabaseUsersPanel.vue'
import MySqlHealthPanel from '@/components/databases/mysql/MySqlHealthPanel.vue'
import SqlServerHealthPanel from '@/components/databases/sqlserver/SqlServerHealthPanel.vue'
import { hasPermission } from '@/core/permissions'
import {
  engineLabel,
  engineProductLabel,
  formatMetric,
  formatUptime,
  overviewMetricLabel,
  statusLabel,
} from '@/core/databasePresentation'
import { useAuthStore } from '@/stores/auth'
import { useConnectionsStore } from '@/stores/connections'
import { useDatabasesStore } from '@/stores/databases'
import { useRecordsStore } from '@/stores/records'
import { useServersStore } from '@/stores/servers'
import type { Server } from '@/stores/servers'
import { useTerminalSessionsStore } from '@/stores/terminalSessions'

const route = useRoute()
const router = useRouter()
const connectionsStore = useConnectionsStore()
const databasesStore = useDatabasesStore()
const serversStore = useServersStore()
const recordsStore = useRecordsStore()
const authStore = useAuthStore()
const terminalStore = useTerminalSessionsStore()

const refreshing = ref(false)
const testingConnection = ref(false)
const workspaceMessage = ref<string | null>(null)
const workspaceMessageTone = ref<'success' | 'error' | 'info'>('info')

const connectionId = computed(() => route.params.id as string)

const connection = computed(() =>
  connectionsStore.connections.find(
    (item) => item.id === connectionId.value,
  ),
)

const overview = computed(() =>
  databasesStore.overviews[connectionId.value],
)

type DatabaseTab =
  | 'overview'
  | 'health'
  | 'sessions'
  | 'storage'
  | 'activity'
  | 'users'
  | 'access'
  | 'backups'
  | 'history'

const validTabs = new Set<DatabaseTab>([
  'overview',
  'health',
  'sessions',
  'storage',
  'activity',
  'users',
  'access',
  'backups',
  'history',
])

const activeTab = ref<DatabaseTab>('overview')

const visitedTabs = reactive<Record<DatabaseTab, boolean>>({
  overview: true,
  health: false,
  sessions: false,
  storage: false,
  activity: false,
  users: false,
  access: false,
  backups: false,
  history: false,
})

function selectTab(tab: DatabaseTab) {
  if (!tabIsAvailable(tab)) return
  visitedTabs[tab] = true
  activeTab.value = tab
}

function applyTabFromRoute() {
  const requested = String(route.query.tab ?? '') as DatabaseTab
  if (!validTabs.has(requested) || !tabIsAvailable(requested)) return
  visitedTabs[requested] = true
  activeTab.value = requested
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
  supportsDbaUtilities.value
  && hasPermission(authStore.user, 'database:inspect'),
)

const supportsAccessAndPrivileges = computed(() =>
  supportsDbaUtilities.value
  && hasPermission(authStore.user, 'database:inspect'),
)

const canTestConnection = computed(() =>
  hasPermission(authStore.user, 'connections:test'),
)

const canManageConnections = computed(() =>
  hasPermission(authStore.user, 'connections:manage'),
)

const canUseTerminal = computed(() =>
  hasPermission(authStore.user, 'terminal:use'),
)

function tabIsAvailable(tab: DatabaseTab) {
  if (tab === 'health') return supportsOperationalHealth.value
  if (['sessions', 'storage', 'activity'].includes(tab)) return supportsDbaUtilities.value
  if (tab === 'users') return supportsUsersAndSchemas.value
  if (tab === 'access') return supportsAccessAndPrivileges.value
  return true
}

async function syncEngineContext() {
  const engine = connection.value?.engine
  if (!engine || route.query.engine === engine) return

  await router.replace({
    name: 'database-detail',
    params: { id: connectionId.value },
    query: { ...route.query, engine },
  })
}

function backToDatabases() {
  router.push({
    name: 'databases',
    query: connection.value?.engine ? { engine: connection.value.engine } : {},
  })
}

watch(
  () => connection.value?.engine,
  () => {
    void syncEngineContext()
  },
)

const relatedServers = computed(() => {
  if (!connection.value) return []
  const ids = connection.value.server_ids ?? []
  return serversStore.servers.filter((server) => ids.includes(server.id))
})

const linkedRecords = computed(() =>
  recordsStore.records.filter(
    (record) => record.connection_id === connectionId.value,
  ),
)

const primaryRecord = computed(() =>
  linkedRecords.value.find((record) => record.record_type === 'database')
  ?? linkedRecords.value[0]
  ?? null,
)

const workspaceEnvironment = computed(() =>
  primaryRecord.value?.environment ?? 'Environment not recorded',
)

const readyTerminalServers = computed(() =>
  relatedServers.value.filter(
    (server) => Boolean(server.ssh_profile_id && server.ssh_host_key_fingerprint),
  ),
)

function showWorkspaceMessage(
  message: string,
  tone: 'success' | 'error' | 'info' = 'info',
) {
  workspaceMessage.value = message
  workspaceMessageTone.value = tone
}

async function refreshWorkspace() {
  refreshing.value = true
  workspaceMessage.value = null

  try {
    await Promise.allSettled([
      databasesStore.loadOne(connectionId.value),
      serversStore.load(),
      recordsStore.load(),
    ])
    showWorkspaceMessage('Database workspace refreshed.', 'success')
  } finally {
    refreshing.value = false
  }
}

async function testDatabaseConnection() {
  if (!canTestConnection.value) return
  testingConnection.value = true
  workspaceMessage.value = null

  try {
    const result = await connectionsStore.test(connectionId.value)
    showWorkspaceMessage(
      result.success
        ? `Connection test succeeded${result.database_version ? ` · ${result.database_version}` : ''}.`
        : result.message,
      result.success ? 'success' : 'error',
    )
  } catch (error) {
    showWorkspaceMessage(
      error instanceof Error ? error.message : 'Connection test failed.',
      'error',
    )
  } finally {
    testingConnection.value = false
  }
}

function openSshTerminal(server: Server) {
  if (!canUseTerminal.value) return

  const existing = terminalStore.sessions.find(
    (session) => session.server_id === server.id,
  )

  if (existing) {
    terminalStore.restore(existing.client_id)
    return
  }

  try {
    terminalStore.open(server)
  } catch (error) {
    showWorkspaceMessage(
      error instanceof Error ? error.message : 'Unable to open SSH terminal.',
      'error',
    )
  }
}

onMounted(async () => {
  applyTabFromRoute()

  if (connectionsStore.connections.length === 0) {
    await connectionsStore.load()
  }

  await Promise.allSettled([
    serversStore.servers.length === 0 ? serversStore.load() : Promise.resolve(),
    recordsStore.records.length === 0 ? recordsStore.load() : Promise.resolve(),
    databasesStore.loadOne(connectionId.value),
  ])

  applyTabFromRoute()
  await syncEngineContext()
})
</script>

<template>
  <div class="database-workspace">
    <div v-if="connectionsStore.loading" class="empty-state">
      Loading database...
    </div>

    <div v-else-if="!connection" class="database-empty-state">
      <h1>Database not found</h1>

      <button type="button" class="secondary-button" @click="backToDatabases">
        Back to databases
      </button>
    </div>

    <template v-else>
      <section class="database-workspace-header">
        <div class="database-workspace-header__identity">
          <button type="button" class="database-back-button" @click="backToDatabases">
            ← Databases
          </button>

          <div class="database-workspace-title-row">
            <h1>{{ connection.name }}</h1>

            <span class="workspace-status-pill workspace-status-pill--engine">
              {{ engineLabel(connection.engine) }}
            </span>

            <span class="workspace-status-pill workspace-status-pill--muted">
              {{ workspaceEnvironment }}
            </span>

            <span
              class="database-state"
              :class="overview?.status ?? 'unknown'"
            >
              {{ statusLabel(overview?.status) }}
            </span>
          </div>

          <p>
            {{ engineProductLabel(connection.engine, overview?.database_product) }}
            · {{ connection.host }}:{{ connection.port }}
            <template v-if="overview?.instance_name"> · {{ overview.instance_name }}</template>
          </p>

          <div v-if="primaryRecord" class="database-workspace-context-line">
            <span v-if="primaryRecord.application">Application: {{ primaryRecord.application }}</span>
            <span v-if="primaryRecord.owner">Owner: {{ primaryRecord.owner }}</span>
            <RouterLink :to="{ name: 'record-detail', params: { id: primaryRecord.id } }">
              Open Record
            </RouterLink>
          </div>
        </div>

        <div class="database-workspace-header__actions">
          <button
            type="button"
            class="secondary-button"
            :disabled="refreshing"
            @click="refreshWorkspace"
          >
            {{ refreshing ? 'Refreshing…' : 'Refresh' }}
          </button>

          <button
            v-if="canTestConnection"
            type="button"
            class="secondary-button"
            :disabled="testingConnection"
            @click="testDatabaseConnection"
          >
            {{ testingConnection ? 'Testing…' : 'Test connection' }}
          </button>

          <template v-if="canUseTerminal && readyTerminalServers.length">
            <button
              v-for="server in readyTerminalServers"
              :key="`ssh-terminal-${server.id}`"
              type="button"
              class="primary-button"
              @click="openSshTerminal(server)"
            >
              SSH terminal
              <template v-if="readyTerminalServers.length > 1">
                · {{ server.name }}
              </template>
            </button>
          </template>

          <RouterLink
            v-if="canManageConnections"
            class="secondary-button"
            :to="{ name: 'settings-connections', query: { type: 'databases' } }"
          >
            Manage connection
          </RouterLink>
        </div>
      </section>

      <p
        v-if="workspaceMessage"
        class="database-workspace-message"
        :class="`database-workspace-message--${workspaceMessageTone}`"
      >
        {{ workspaceMessage }}
      </p>

      <nav class="database-tabs database-workspace-tabs">
        <button :class="{ active: activeTab === 'overview' }" @click="selectTab('overview')">
          Overview
        </button>

        <button
          v-if="supportsOperationalHealth"
          :class="{ active: activeTab === 'health' }"
          @click="selectTab('health')"
        >
          Health
        </button>

        <button
          :disabled="!supportsDbaUtilities"
          :class="{ active: activeTab === 'sessions' }"
          @click="selectTab('sessions')"
        >
          Sessions
        </button>

        <button
          :disabled="!supportsDbaUtilities"
          :class="{ active: activeTab === 'storage' }"
          @click="selectTab('storage')"
        >
          Storage
        </button>

        <button
          :disabled="!supportsDbaUtilities"
          :class="{ active: activeTab === 'activity' }"
          @click="selectTab('activity')"
        >
          Activity
        </button>

        <button :class="{ active: activeTab === 'backups' }" @click="selectTab('backups')">
          Backups
        </button>

        <button
          v-if="supportsUsersAndSchemas"
          :class="{ active: activeTab === 'users' }"
          @click="selectTab('users')"
        >
          {{ connection.engine === 'sqlserver' ? 'Users & Principals' : connection.engine === 'mysql' ? 'Users & Hosts' : 'Users & Schemas' }}
        </button>

        <button
          v-if="supportsAccessAndPrivileges"
          :class="{ active: activeTab === 'access' }"
          @click="selectTab('access')"
        >
          {{ connection.engine === 'mysql' ? 'Access & Grants' : 'Access & Privileges' }}
        </button>

        <button :class="{ active: activeTab === 'history' }" @click="selectTab('history')">
          History
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

        <div>
          <span>Response time</span>
          <strong>
            {{ overview?.response_time_ms != null ? `${overview.response_time_ms} ms` : '—' }}
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

      <section
        v-if="activeTab === 'overview'"
        class="database-context-grid"
      >
        <article class="panel database-context-card">
          <div class="panel-header">
            <div>
              <h2>Operational context</h2>
              <p>Human-facing ownership and application information from Records.</p>
            </div>
          </div>

          <dl class="database-context-list">
            <div>
              <dt>Environment</dt>
              <dd>{{ primaryRecord?.environment ?? 'Not recorded' }}</dd>
            </div>
            <div>
              <dt>Application</dt>
              <dd>{{ primaryRecord?.application ?? 'Not recorded' }}</dd>
            </div>
            <div>
              <dt>Owner / team</dt>
              <dd>{{ primaryRecord?.owner ?? 'Not recorded' }}</dd>
            </div>
            <div>
              <dt>Linked Records</dt>
              <dd>{{ linkedRecords.length }}</dd>
            </div>
          </dl>

          <div v-if="linkedRecords.length" class="database-context-links">
            <RouterLink
              v-for="record in linkedRecords.slice(0, 4)"
              :key="record.id"
              :to="{ name: 'record-detail', params: { id: record.id } }"
            >
              {{ record.name }}
            </RouterLink>
          </div>
          <RouterLink v-else class="text-link" :to="{ name: 'records' }">
            Open Records workspace
          </RouterLink>
        </article>

        <article class="panel database-context-card">
          <div class="panel-header">
            <div>
              <h2>Linked infrastructure</h2>
              <p>Server / SSH relationships used for host-level DBA work.</p>
            </div>
          </div>

          <div v-if="relatedServers.length" class="database-linked-server-list">
            <div v-for="server in relatedServers" :key="server.id" class="database-linked-server">
              <div>
                <RouterLink :to="{ name: 'server-detail', params: { id: server.id } }">
                  {{ server.name }}
                </RouterLink>
                <span>{{ server.ip_address || server.hostname }}</span>
              </div>
              <span
                class="workspace-status-pill"
                :class="server.ssh_profile_id && server.ssh_host_key_fingerprint
                  ? 'workspace-status-pill--success'
                  : 'workspace-status-pill--warning'"
              >
                {{ server.ssh_profile_id && server.ssh_host_key_fingerprint ? 'SSH ready' : 'SSH setup needed' }}
              </span>
            </div>
          </div>

          <div v-else class="database-workspace-empty database-workspace-empty--compact">
            <strong>No linked server</strong>
            <span>Link a Server / SSH entry to use host-level tools from this database.</span>
          </div>

        </article>
      </section>

      <section v-if="activeTab === 'overview'" class="panel database-overview-panel">
        <div class="panel-header">
          <div>
            <h2>Database information</h2>
            <p>
              Engine-aware connection identity, runtime state and compatibility context.
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

          <div v-if="overview?.database_state">
            <dt>Database state</dt>
            <dd>{{ overview.database_state }}</dd>
          </div>

          <div v-if="overview?.instance_status">
            <dt>Instance status</dt>
            <dd>{{ overview.instance_status }}</dd>
          </div>

          <div v-if="overview?.database_role">
            <dt>Database role</dt>
            <dd>{{ overview.database_role }}</dd>
          </div>

          <div v-if="overview?.log_mode">
            <dt>Log mode</dt>
            <dd>{{ overview.log_mode }}</dd>
          </div>

          <div v-if="overview?.recovery_model">
            <dt>Recovery model</dt>
            <dd>{{ overview.recovery_model }}</dd>
          </div>

          <div v-if="overview?.compatibility_level != null">
            <dt>Compatibility level</dt>
            <dd>{{ overview.compatibility_level }}</dd>
          </div>

          <div v-if="overview?.character_set">
            <dt>Character set</dt>
            <dd>{{ overview.character_set }}</dd>
          </div>

          <div v-if="overview?.collation">
            <dt>Collation</dt>
            <dd>{{ overview.collation }}</dd>
          </div>

          <div v-if="overview?.read_only != null">
            <dt>Read-only</dt>
            <dd>{{ overview.read_only ? 'Yes' : 'No' }}</dd>
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