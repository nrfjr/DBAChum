<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import DatabaseAccessPanel from '@/components/databases/DatabaseAccessPanel.vue'
import DatabaseActivityPanel from '@/components/databases/DatabaseActivityPanel.vue'
import DatabaseJobsPanel from '@/components/databases/DatabaseJobsPanel.vue'
import DatabaseMaintenancePanel from '@/components/databases/DatabaseMaintenancePanel.vue'
import DatabaseBackupsPanel from '@/components/databases/DatabaseBackupsPanel.vue'
import DatabaseMetricsPanel from '@/components/databases/DatabaseMetricsPanel.vue'
import DatabaseMonitoringNotice from '@/components/databases/DatabaseMonitoringNotice.vue'
import DatabaseParametersPanel from '@/components/databases/DatabaseParametersPanel.vue'
import DatabaseSessionsPanel from '@/components/databases/DatabaseSessionsPanel.vue'
import DatabaseStoragePanel from '@/components/databases/DatabaseStoragePanel.vue'
import DatabaseUsersPanel from '@/components/databases/DatabaseUsersPanel.vue'
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
import { useDatabaseBackupsStore, type DatabaseBackupResponse } from '@/stores/databaseBackups'
import { useDatabaseMetricsStore, type DatabaseMetricHistory } from '@/stores/databaseMetrics'
import { useRecordsStore } from '@/stores/records'
import { useServersStore } from '@/stores/servers'
import type { Server } from '@/stores/servers'
import { useTerminalSessionsStore } from '@/stores/terminalSessions'

const route = useRoute()
const router = useRouter()
const connectionsStore = useConnectionsStore()
const databasesStore = useDatabasesStore()
const backupsStore = useDatabaseBackupsStore()
const metricsStore = useDatabaseMetricsStore()
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
  | 'metrics'
  | 'sessions'
  | 'storage'
  | 'backups'
  | 'users_access'
  | 'parameters'
  | 'jobs'
  | 'maintenance'

const validTabs = new Set<DatabaseTab>([
  'overview',
  'metrics',
  'sessions',
  'storage',
  'backups',
  'users_access',
  'parameters',
  'jobs',
  'maintenance',
])

const activeTab = ref<DatabaseTab>('overview')

const visitedTabs = reactive<Record<DatabaseTab, boolean>>({
  overview: true,
  metrics: false,
  sessions: false,
  storage: false,
  backups: false,
  users_access: false,
  parameters: false,
  jobs: false,
  maintenance: false,
})

const moreOpen = ref(false)

function selectTab(tab: DatabaseTab) {
  if (!tabIsAvailable(tab)) return
  visitedTabs[tab] = true
  activeTab.value = tab
  moreOpen.value = false
}

function applyTabFromRoute() {
  const raw = String(route.query.tab ?? '')
  // Keep old deep links useful while the workspace stays intentionally lean.
  const aliases: Record<string, DatabaseTab> = {
    history: 'metrics',
    performance: 'metrics',
    health: 'overview',
    activity: 'sessions',
    users: 'users_access',
    access: 'users_access',
  }
  const requested = (aliases[raw] ?? raw) as DatabaseTab
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
  if (['sessions', 'storage', 'parameters', 'jobs', 'maintenance'].includes(tab)) return supportsDbaUtilities.value
  if (tab === 'users_access') return supportsUsersAndSchemas.value || supportsAccessAndPrivileges.value
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

const overviewMetrics = ref<DatabaseMetricHistory | null>(null)
const overviewBackups = ref<DatabaseBackupResponse | null>(null)

const latestMetric = computed(() => {
  const items = overviewMetrics.value?.items ?? []
  return items[items.length - 1] ?? null
})

function formatAge(value: string | null | undefined) {
  if (!value) return 'No recent data'
  const timestamp = new Date(value).getTime()
  if (!Number.isFinite(timestamp)) return 'Unknown age'
  const minutes = Math.max(Math.floor((Date.now() - timestamp) / 60_000), 0)
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.floor(minutes / 60)
  if (hours < 48) return `${hours}h ago`
  return `${Math.floor(hours / 24)}d ago`
}

function formatBytes(bytes: number | null | undefined) {
  if (bytes == null) return '—'
  const units = ['B', 'KB', 'MB', 'GB', 'TB', 'PB']
  let value = Math.max(bytes, 0)
  let unit = 0
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024
    unit += 1
  }
  return `${value.toFixed(unit === 0 ? 0 : value >= 100 ? 0 : 1)} ${units[unit]}`
}

const storageSummary = computed(() => {
  const sample = latestMetric.value
  if (!sample) return { primary: 'No storage sample', secondary: 'Open Storage for live detail' }

  if (connection.value?.engine === 'oracle') {
    const tablespaces = sample.oracle?.storage?.tablespaces ?? []
    const fullest = [...tablespaces].sort((left, right) => (right.used_percent ?? 0) - (left.used_percent ?? 0))[0]
    if (fullest) {
      return {
        primary: `${fullest.used_percent ?? 0}% used`,
        secondary: `${fullest.name} · highest tablespace`,
      }
    }
    const fra = sample.oracle?.storage?.fra
    if (fra?.used_percent != null) return { primary: `${fra.used_percent}% FRA`, secondary: 'Fast Recovery Area usage' }
  }

  if (connection.value?.engine === 'sqlserver') {
    const log = sample.sqlserver?.log_used_percent
    const tempdb = sample.sqlserver?.tempdb_used_percent
    if (log != null) return { primary: `${log}% log used`, secondary: tempdb != null ? `TempDB ${tempdb}% used` : 'Transaction log usage' }
  }

  if (connection.value?.engine === 'mysql') {
    const total = sample.mysql?.storage?.total_bytes
    if (total != null) return { primary: formatBytes(total), secondary: 'Tracked database storage' }
  }

  return { primary: 'Storage available', secondary: 'Open Storage for details' }
})

const latestBackup = computed(() => overviewBackups.value?.latest_backup ?? null)
const backupSummary = computed(() => {
  const backup = latestBackup.value
  if (!backup) return { primary: 'No recent backup', secondary: overviewBackups.value?.available === false ? 'Backup provider unavailable' : 'No backup found in the last 7 days' }
  const time = backup.finished_at ?? backup.started_at
  const kind = backup.kind.replace('_', ' ')
  return { primary: formatAge(time), secondary: `${kind} · ${backup.status}` }
})

const metricsSummary = computed(() => ({
  primary: formatAge(latestMetric.value?.collected_at),
  secondary: latestMetric.value ? `Collector ${latestMetric.value.status}` : 'No collector sample in the last hour',
}))

async function loadOverviewSummaries() {
  const [metricsResult, backupsResult] = await Promise.allSettled([
    metricsStore.loadHistory(connectionId.value, 1),
    backupsStore.load(connectionId.value, { window: '7d' }),
  ])
  if (metricsResult.status === 'fulfilled') overviewMetrics.value = metricsResult.value
  if (backupsResult.status === 'fulfilled') overviewBackups.value = backupsResult.value
}

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
      loadOverviewSummaries(),
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
    loadOverviewSummaries(),
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
        <button :class="{ active: activeTab === 'overview' }" @click="selectTab('overview')">Overview</button>
        <button :class="{ active: activeTab === 'metrics' }" @click="selectTab('metrics')">Metrics</button>
        <button :disabled="!supportsDbaUtilities" :class="{ active: activeTab === 'sessions' }" @click="selectTab('sessions')">Sessions</button>
        <button :disabled="!supportsDbaUtilities" :class="{ active: activeTab === 'storage' }" @click="selectTab('storage')">Storage</button>
        <button :class="{ active: activeTab === 'backups' }" @click="selectTab('backups')">Backups</button>
        <button v-if="supportsUsersAndSchemas || supportsAccessAndPrivileges" :class="{ active: activeTab === 'users_access' }" @click="selectTab('users_access')">Users / Access</button>
        <button :disabled="!supportsDbaUtilities" :class="{ active: activeTab === 'parameters' }" @click="selectTab('parameters')">Parameters</button>

        <div v-if="supportsDbaUtilities" class="database-more-menu">
          <button
            type="button"
            class="database-more-menu__trigger"
            :class="{ active: activeTab === 'jobs' || activeTab === 'maintenance' }"
            :aria-expanded="moreOpen"
            @click="moreOpen = !moreOpen"
          >
            More <span aria-hidden="true">▾</span>
          </button>
          <div v-if="moreOpen" class="database-more-menu__popover">
            <button type="button" :class="{ active: activeTab === 'jobs' }" @click="selectTab('jobs')">Jobs</button>
            <button type="button" :class="{ active: activeTab === 'maintenance' }" @click="selectTab('maintenance')">Maintenance</button>
          </div>
        </div>
      </nav>

      <section v-if="activeTab === 'overview'" class="database-overview-summary-grid">
        <button type="button" class="database-overview-summary-card" @click="selectTab('metrics')">
          <span>Metrics</span>
          <strong>{{ metricsSummary.primary }}</strong>
          <small>{{ metricsSummary.secondary }}</small>
        </button>

        <button type="button" class="database-overview-summary-card" :disabled="!supportsDbaUtilities" @click="selectTab('sessions')">
          <span>Sessions</span>
          <strong>{{ formatMetric(overview?.active) }} active</strong>
          <small>{{ formatMetric(overview?.blocked) }} blocked · {{ formatMetric(overview?.connections) }} connections</small>
        </button>

        <button type="button" class="database-overview-summary-card" :disabled="!supportsDbaUtilities" @click="selectTab('storage')">
          <span>Storage</span>
          <strong>{{ storageSummary.primary }}</strong>
          <small>{{ storageSummary.secondary }}</small>
        </button>

        <button type="button" class="database-overview-summary-card" @click="selectTab('backups')">
          <span>Backups</span>
          <strong>{{ backupSummary.primary }}</strong>
          <small>{{ backupSummary.secondary }}</small>
        </button>

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
      <div v-if="visitedTabs.metrics" v-show="activeTab === 'metrics'" class="database-tab-panel">
        <DatabaseMetricsPanel
          :key="`metrics-${connection.id}`"
          :connection-id="connection.id"
          :engine="connection.engine"
        />
      </div>

      <div v-if="visitedTabs.backups" v-show="activeTab === 'backups'" class="database-tab-panel">
        <DatabaseBackupsPanel
          :key="`backups-${connection.id}`"
          :connection-id="connection.id"
        />
      </div>


      <div v-if="visitedTabs.sessions" v-show="activeTab === 'sessions'" class="database-tab-panel">
        <DatabaseSessionsPanel
          :key="`sessions-${connection.id}`"
          :connection-id="connection.id"
          :engine="connection.engine"
        />
        <DatabaseActivityPanel
          :key="`activity-${connection.id}`"
          :connection-id="connection.id"
          :engine="connection.engine"
        />
      </div>

      <div v-if="visitedTabs.storage" v-show="activeTab === 'storage'" class="database-tab-panel">
        <DatabaseStoragePanel
          :key="`storage-${connection.id}`"
          :connection-id="connection.id"
          :engine="connection.engine"
        />
      </div>


      <div v-if="visitedTabs.parameters" v-show="activeTab === 'parameters'" class="database-tab-panel">
        <DatabaseParametersPanel
          :key="`parameters-${connection.id}`"
          :connection-id="connection.id"
          :engine="connection.engine"
        />
      </div>

      <div v-if="visitedTabs.jobs" v-show="activeTab === 'jobs'" class="database-tab-panel">
        <DatabaseJobsPanel
          :key="`jobs-${connection.id}`"
          :connection-id="connection.id"
          :engine="connection.engine"
        />
      </div>

      <div v-if="visitedTabs.maintenance" v-show="activeTab === 'maintenance'" class="database-tab-panel">
        <DatabaseMaintenancePanel
          :key="`maintenance-${connection.id}`"
          :connection-id="connection.id"
          :engine="connection.engine"
        />
      </div>

      <div v-if="visitedTabs.users_access" v-show="activeTab === 'users_access'" class="database-tab-panel">
        <DatabaseUsersPanel
          v-if="supportsUsersAndSchemas"
          :key="`users-${connection.id}`"
          :connection-id="connection.id"
          :engine="connection.engine"
          :active="activeTab === 'users_access'"
        />
        <DatabaseAccessPanel
          v-if="supportsAccessAndPrivileges"
          :key="`access-${connection.id}`"
          :connection-id="connection.id"
          :engine="connection.engine"
        />
      </div>

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