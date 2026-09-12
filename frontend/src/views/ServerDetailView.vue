<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRoute } from 'vue-router'

import ScrollableDataTable from '@/components/common/ScrollableDataTable.vue'
import { useServersStore, type Server, type ServerOsFamily, type ServerType } from '@/stores/servers'
import {
  useServerMonitoringStore,
  type ServerFilesystemSnapshot,
} from '@/stores/serverMonitoring'
import type { DatabaseConnection } from '@/stores/connections'
import { useAuthStore } from '@/stores/auth'
import { hasPermission } from '@/core/permissions'
import { useTerminalSessionsStore } from '@/stores/terminalSessions'
import { confirmDialog, showToast } from '@/ui/feedback'

const route = useRoute()
const serversStore = useServersStore()
const monitoringStore = useServerMonitoringStore()
const authStore = useAuthStore()
const terminalStore = useTerminalSessionsStore()

const server = ref<Server | null>(null)
const databases = ref<DatabaseConnection[]>([])
const loading = ref(true)
const error = ref<string | null>(null)
const terminalError = ref<string | null>(null)
const activeTab = ref<'overview' | 'metrics' | 'databases'>('overview')
const actionMenuOpen = ref(false)

const serverId = computed(() => String(route.params.id ?? ''))
const canManageServers = computed(() => hasPermission(authStore.user, 'servers:manage'))
const canTestConnections = computed(() => hasPermission(authStore.user, 'connections:test'))
const canOpenTerminal = computed(() => hasPermission(authStore.user, 'terminal:use'))
const sshConfigured = computed(() => Boolean(server.value?.ssh_profile_id))
const sshTrusted = computed(() => Boolean(server.value?.ssh_host_key_fingerprint))
const canCollectHostMetrics = computed(() => {
  const family = server.value?.os_family
  return family === 'linux' || family === 'aix' || family === 'unix'
})
const health = computed(() => {
  const snapshot = monitoringStore.healthByServer[serverId.value] ?? null
  const target = (server.value?.ip_address || server.value?.hostname || '').trim()
  if (!sshTrusted.value || !canCollectHostMetrics.value || snapshot?.target !== target) return null
  return snapshot
})
const sshTest = computed(() => monitoringStore.sshTestByServer[serverId.value] ?? null)
const healthLoading = computed(() => monitoringStore.healthLoadingByServer[serverId.value] ?? false)
const sshTestLoading = computed(() => monitoringStore.testLoadingByServer[serverId.value] ?? false)
const monitoringError = computed(() => monitoringStore.errorByServer[serverId.value] ?? null)
const highestFilesystem = computed(() => {
  const filesystems = health.value?.filesystems ?? []
  return [...filesystems].sort((left, right) => right.used_percent - left.used_percent)[0] ?? null
})

const serverReachabilityTone = computed<'reachable' | 'unreachable' | 'unknown'>(() => {
  if (!server.value?.enabled) return 'unknown'

  if (health.value) return 'reachable'

  if (monitoringError.value) return 'unreachable'

  return 'unknown'
})

function selectTab(tab: 'overview' | 'metrics' | 'databases') {
  activeTab.value = tab
  actionMenuOpen.value = false
}

function closeActionMenu() {
  actionMenuOpen.value = false
}

function serverTypeLabel(value: ServerType) {
  return {
    database: 'Database server',
    application: 'Application server',
    utility: 'Utility server',
    other: 'Other',
  }[value]
}

function osLabel(value: ServerOsFamily) {
  return { windows: 'Windows', linux: 'Linux', aix: 'AIX', unix: 'Unix', other: 'Other' }[value]
}

function engineLabel(engine: DatabaseConnection['engine']) {
  return { oracle: 'Oracle', sqlserver: 'SQL Server', mysql: 'MySQL' }[engine]
}

function formatBytes(value: number | null | undefined) {
  if (value == null || !Number.isFinite(value)) return '—'
  const units = ['B', 'KB', 'MB', 'GB', 'TB', 'PB']
  let size = Math.max(value, 0)
  let index = 0
  while (size >= 1024 && index < units.length - 1) {
    size /= 1024
    index += 1
  }
  const digits = index >= 3 ? 1 : 0
  return `${size.toFixed(digits)} ${units[index]}`
}

function formatPercent(value: number | null | undefined) {
  return value == null ? '—' : `${value.toFixed(1)}%`
}

function formatUptime(seconds: number | null | undefined) {
  if (seconds == null) return '—'
  const days = Math.floor(seconds / 86400)
  const hours = Math.floor((seconds % 86400) / 3600)
  const minutes = Math.floor((seconds % 3600) / 60)
  if (days > 0) return `${days}d ${hours}h ${minutes}m`
  if (hours > 0) return `${hours}h ${minutes}m`
  return `${minutes}m`
}

function formatCheckedAt(value: string | null | undefined) {
  if (!value) return 'Never'
  return new Date(value).toLocaleString()
}

function filesystemState(filesystem: ServerFilesystemSnapshot) {
  if (filesystem.used_percent >= 90) return 'critical'
  if (filesystem.used_percent >= 80) return 'warning'
  return 'healthy'
}

async function load() {
  loading.value = true
  error.value = null
  try {
    const [serverResult, databaseResult] = await Promise.all([
      serversStore.loadOne(serverId.value),
      serversStore.loadDatabases(serverId.value),
    ])
    server.value = serverResult
    databases.value = databaseResult
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Unable to load server.'
  } finally {
    loading.value = false
  }
}

async function initializeMonitoring() {
  if (!server.value?.ssh_profile_id) return

  try {
    if (server.value.ssh_host_key_fingerprint && canCollectHostMetrics.value) {
      await monitoringStore.loadHealth(serverId.value)
    } else if (canTestConnections.value) {
      await monitoringStore.testSsh(serverId.value)
    }
  } catch {
  }
}

async function testSsh() {
  try {
    const result = await monitoringStore.testSsh(serverId.value)
    showToast({
      title: result.state === 'connected' ? 'SSH connection test passed' : 'SSH host key verification required',
      message: result.message,
      tone: result.state === 'connected' ? 'success' : 'warning',
    })
  } catch (cause) {
    const message = cause instanceof Error ? cause.message : monitoringError.value ?? 'Unable to test SSH connection.'
    showToast({ title: 'SSH connection test failed', message, tone: 'danger' })
  }
}

async function trustHostKey() {
  const candidate = sshTest.value
  if (!candidate || candidate.state !== 'untrusted') return

  const confirmed = await confirmDialog({
    title: 'Trust SSH host key',
    message: `Trust ${candidate.fingerprint} for ${candidate.target}:${candidate.port}? Verify this fingerprint against the server before continuing.`,
    confirmLabel: 'Trust host key',
    tone: 'warning',
  })
  if (!confirmed) return

  try {
    await monitoringStore.trustHostKey(serverId.value, candidate.fingerprint)
    server.value = await serversStore.loadOne(serverId.value)
    if (canCollectHostMetrics.value) await monitoringStore.loadHealth(serverId.value)
    showToast({ title: 'SSH host key trusted', message: candidate.fingerprint, tone: 'success' })
  } catch (cause) {
    const message = cause instanceof Error ? cause.message : monitoringError.value ?? 'Unable to trust SSH host key.'
    showToast({ title: 'Unable to trust SSH host key', message, tone: 'danger' })
  }
}

async function refreshHost() {
  try {
    await monitoringStore.loadHealth(serverId.value)
    showToast({ title: 'Server metrics refreshed', tone: 'success' })
  } catch (cause) {
    const message = cause instanceof Error ? cause.message : monitoringError.value ?? 'Unable to refresh server metrics.'
    showToast({ title: 'Unable to refresh server metrics', message, tone: 'danger' })
  }
}

async function refreshAll() {
  await load()
  await initializeMonitoring()
  showToast({ title: 'Server refreshed', tone: 'success' })
}

function openTerminal() {
  terminalError.value = null
  if (!server.value) return
  if (!server.value.ssh_profile_id || !server.value.ssh_host_key_fingerprint) {
    terminalError.value = 'Test SSH and trust the server host key before opening a terminal.'
    showToast({ title: 'SSH trust required', message: terminalError.value, tone: 'warning' })
    return
  }
  try {
    terminalStore.open(server.value)
  } catch (err) {
    terminalError.value = err instanceof Error ? err.message : 'Unable to open SSH terminal.'
    showToast({ title: 'Unable to open SSH terminal', message: terminalError.value, tone: 'danger' })
  }
}

onMounted(async () => {
  document.addEventListener('click', closeActionMenu)
  await load()
  await initializeMonitoring()
})

onUnmounted(() => {
  document.removeEventListener('click', closeActionMenu)
})
</script>

<template>
  <div class="server-workspace">
    <p v-if="terminalError" class="login-error">{{ terminalError }}</p>
    <p v-if="error" class="login-error">{{ error }}</p>
    <div v-else-if="loading && !server" class="empty-state">
      Loading server
      <p class="loading"></p>
    </div>

    <template v-else-if="server">
      <section class="resource-context resource-context--sticky server-resource-context">
        <div class="resource-breadcrumbs" aria-label="Breadcrumb">
          <RouterLink to="/servers">Servers</RouterLink>
          <span>/</span>
          <strong>{{ server.name }}</strong>
          <span>/</span>
          <strong>{{ activeTab === 'overview' ? 'Overview' : activeTab === 'metrics' ? 'Metrics' : 'Databases'
          }}</strong>
        </div>

        <div class="resource-context__main">
          <div class="resource-context__identity">
            <div class="resource-context__title-row">
              <h1>{{ server.name }}</h1>
              <span class="server-overview-reachability-dot"
                :class="`server-overview-reachability-dot--${serverReachabilityTone}`" :title="serverReachabilityTone === 'reachable'
                  ? 'Online'
                  : serverReachabilityTone === 'unreachable'
                    ? 'Unreachable'
                    : 'Unknown'
                  " />
            </div>
            <p>{{ server.hostname }}<template v-if="server.ip_address"> · {{ server.ip_address }}</template></p>
          </div>

          <div class="resource-context__actions" @click.stop>
            <button type="button" class="secondary-button refresh-button" :disabled="loading || healthLoading"
              @click="refreshAll">
              {{ loading || healthLoading ? 'Refreshing' : 'Refresh' }}
              <p v-if="loading || healthLoading" class="loading"></p>
            </button>
            <div class="context-action-menu">
              <button type="button" class="icon-button context-action-menu__trigger" aria-label="Server actions"
                :aria-expanded="actionMenuOpen" @click="actionMenuOpen = !actionMenuOpen">
                <FontAwesomeIcon icon="ellipsis-vertical" />
              </button>
              <div v-if="actionMenuOpen" class="context-action-menu__popover">
                <button v-if="sshConfigured && canTestConnections" type="button" :disabled="sshTestLoading"
                  @click="testSsh(); actionMenuOpen = false">
                  {{ sshTestLoading ? 'Testing SSH' : 'Test SSH' }}
                  <p v-if="sshTestLoading" class="loading"></p>
                </button>
                <button v-if="canOpenTerminal && sshConfigured && sshTrusted" type="button"
                  @click="openTerminal(); actionMenuOpen = false">
                  Open terminal
                </button>
                <RouterLink v-if="canManageServers" :to="{ name: 'settings-connections', query: { type: 'servers' } }"
                  @click="actionMenuOpen = false">Manage server connection</RouterLink>
              </div>
            </div>
          </div>
        </div>

        <nav class="database-tabs resource-context__tabs server-workspace-tabs">
          <button :class="{ active: activeTab === 'overview' }" @click="selectTab('overview')">Overview</button>
          <button :class="{ active: activeTab === 'metrics' }" @click="selectTab('metrics')">Metrics</button>
          <button :class="{ active: activeTab === 'databases' }" @click="selectTab('databases')">Databases</button>
        </nav>
      </section>

      <template v-if="activeTab === 'overview'">
        <section class="database-overview-summary-grid server-overview-summary-grid">
          <button type="button" class="database-overview-summary-card" @click="selectTab('metrics')">
            <span>CPU</span>
            <strong>{{ health ? formatPercent(health.cpu_used_percent) : '—' }}</strong>
            <small>{{ health?.cpu_measurement ?? 'Current host sample' }}</small>
          </button>
          <button type="button" class="database-overview-summary-card" @click="selectTab('metrics')">
            <span>Memory</span>
            <strong>{{ health ? formatPercent(health.memory.used_percent) : '—' }}</strong>
            <small v-if="health">{{ formatBytes(health.memory.used_bytes) }} / {{ formatBytes(health.memory.total_bytes)
            }}</small>
            <small v-else>No current host sample</small>
          </button>
          <button type="button" class="database-overview-summary-card" @click="selectTab('metrics')">
            <span>Filesystem</span>
            <strong>{{ highestFilesystem ? formatPercent(highestFilesystem.used_percent) : '—' }}</strong>
            <small>{{ highestFilesystem ? `${highestFilesystem.mount_point} · highest usage` : 'No filesystem sample'
            }}</small>
          </button>
          <article class="database-overview-summary-card database-overview-summary-card--static">
            <span>Uptime</span>
            <strong>{{ health ? formatUptime(health.uptime_seconds) : '—' }}</strong>
            <small>{{ health?.remote_hostname ?? server.hostname }}</small>
          </article>
          <button type="button" class="database-overview-summary-card" @click="selectTab('databases')">
            <span>Databases</span>
            <strong>{{ databases.length }}</strong>
            <small>Linked database connections</small>
          </button>
        </section>

        <div class="server-detail-grid server-detail-grid--unified">
          <section class="detail-card">
            <div class="server-card-heading">
              <h2>Server information</h2>
            </div>
            <dl class="detail-list">
              <div>
                <dt>Type</dt>
                <dd>{{ serverTypeLabel(server.server_type) }}</dd>
              </div>
              <div>
                <dt>Operating system</dt>
                <dd>{{ osLabel(server.os_family) }}{{ server.os_version ? ` · ${server.os_version}` : '' }}</dd>
              </div>
              <div>
                <dt>Environment</dt>
                <dd>{{ server.environment ?? '—' }}</dd>
              </div>
              <div>
                <dt>Owner / team</dt>
                <dd>{{ server.owner ?? '—' }}</dd>
              </div>
              <div>
                <dt>Status</dt>
                <dd>{{ server.enabled ? 'Enabled' : 'Disabled' }}</dd>
              </div>
              <div>
                <dt>SSH profile</dt>
                <dd>{{ server.ssh_profile_name ?? 'Not configured' }}</dd>
              </div>
              <div>
                <dt>Host key</dt>
                <dd>{{ sshTrusted ? 'Trusted' : sshConfigured ? 'Not trusted yet' : '—' }}</dd>
              </div>
              <div v-if="health">
                <dt>Last checked</dt>
                <dd>{{ formatCheckedAt(health.checked_at) }}</dd>
              </div>
            </dl>
          </section>

          <section class="detail-card server-ssh-card">
            <div class="server-card-heading">
              <h2>SSH access</h2>
            </div>
            <template v-if="server.ssh_profile_name">
              <strong>{{ server.ssh_profile_name }}</strong>
              <dl class="detail-list compact-detail-list">
                <div>
                  <dt>Host key</dt>
                  <dd>{{ sshTrusted ? 'Trusted' : 'Not trusted yet' }}</dd>
                </div>
                <div v-if="server.ssh_host_key_fingerprint">
                  <dt>Fingerprint</dt>
                  <dd class="mono-wrap">{{ server.ssh_host_key_fingerprint }}</dd>
                </div>
                <div v-if="sshTest">
                  <dt>Last test</dt>
                  <dd>{{ sshTest.message }}</dd>
                </div>
              </dl>
              <div v-if="sshTest?.state === 'untrusted'" class="ssh-trust-panel">
                <strong>Verify host identity before authentication</strong>
                <code>{{ sshTest.fingerprint }}</code>
                <button v-if="canManageServers" type="button" class="primary-button" :disabled="sshTestLoading"
                  @click="trustHostKey">Trust this host key</button>
              </div>
            </template>
            <template v-else>
              <strong>Not configured</strong>
            </template>
          </section>

          <section class="detail-card server-detail-notes">
            <div class="server-card-heading">
              <h2>Notes & tags</h2>
            </div>
            <p>{{ server.notes ?? 'No notes.' }}</p>
            <div v-if="server.tags.length" class="server-tags">
              <span v-for="tag in server.tags" :key="tag">{{ tag }}</span>
            </div>
          </section>
        </div>
      </template>

      <section v-else-if="activeTab === 'metrics'" class="server-monitoring-section server-tab-panel">
        <div class="section-toolbar">
          <div>
            <h2>Host metrics</h2>
          </div>
          <div class="server-monitoring-actions">
            <span v-if="health" class="server-last-checked">Checked {{ formatCheckedAt(health.checked_at) }}</span>
            <button type="button" class="secondary-button refresh-button"
              :disabled="!sshConfigured || !sshTrusted || !canCollectHostMetrics || healthLoading" @click="refreshHost">
              {{ healthLoading ? 'Refreshing' : 'Refresh metrics' }}
              <p v-if="healthLoading" class="loading"></p>
            </button>
          </div>
        </div>

        <div v-if="!sshConfigured" class="notice-card">Assign an SSH access profile before host metrics can be
          collected.
        </div>
        <div v-else-if="!sshTrusted" class="notice-card">
          <template v-if="canTestConnections">Test SSH and verify the server fingerprint before DBAChum sends the stored
            SSH credential.</template>
          <template v-else>An operator or administrator must verify SSH connectivity; an administrator must trust the
            verified host key.</template>
        </div>
        <div v-else-if="!canCollectHostMetrics" class="notice-card">Host metrics are available for Linux, AIX and Unix
          assets.
        </div>
        <p v-if="monitoringError" class="login-error">{{ monitoringError }}</p>

        <template v-if="health">
          <div class="server-health-metrics">
            <article class="metric-card"><span class="metric-card__label">CPU used</span><strong
                class="metric-card__value">{{ formatPercent(health.cpu_used_percent) }}</strong><small
                class="metric-card__hint">{{ health.cpu_measurement ?? 'Current host sample' }}</small></article>
            <article class="metric-card"><span class="metric-card__label">Memory used</span><strong
                class="metric-card__value">{{ formatPercent(health.memory.used_percent) }}</strong><small
                class="metric-card__hint">{{ formatBytes(health.memory.used_bytes) }} / {{
                  formatBytes(health.memory.total_bytes) }}</small></article>
            <article class="metric-card"><span class="metric-card__label">Load average</span><strong
                class="metric-card__value">{{ health.load_1 ?? '—' }}</strong><small class="metric-card__hint">1m / 5m /
                15m · {{ health.load_1 ?? '—' }} / {{ health.load_5 ?? '—' }} / {{ health.load_15 ?? '—' }}</small>
            </article>
            <article class="metric-card"><span class="metric-card__label">Uptime</span><strong
                class="metric-card__value">{{ formatUptime(health.uptime_seconds) }}</strong><small
                class="metric-card__hint">{{ health.remote_hostname ?? health.target }}</small></article>
            <article class="metric-card"><span class="metric-card__label">Swap used</span><strong
                class="metric-card__value">{{ formatPercent(health.memory.swap_used_percent) }}</strong><small
                class="metric-card__hint">{{ formatBytes(health.memory.swap_used_bytes) }} / {{
                  formatBytes(health.memory.swap_total_bytes) }}</small></article>
            <article class="metric-card"><span class="metric-card__label">SSH</span><strong
                class="metric-card__value">{{ health.ssh_latency_ms != null ? `${health.ssh_latency_ms} ms` :
                  'Connected' }}</strong><small class="metric-card__hint">{{ health.target }}:{{ health.port }}</small>
            </article>
          </div>

          <div v-if="health.warnings.length" class="server-monitoring-warnings"><strong>Partial metrics</strong>
            <ul>
              <li v-for="warning in health.warnings" :key="warning">{{ warning }}</li>
            </ul>
          </div>

          <div class="server-monitoring-grid">
            <section class="detail-card">
              <div class="server-card-heading">
                <div>
                  <h2>Filesystems</h2>
                  <p>Highest utilization first.</p>
                </div><span class="count-badge">{{ health.filesystems.length }}</span>
              </div>
              <ScrollableDataTable :empty="health.filesystems.length === 0"
                empty-message="No filesystem metrics were returned by this host." max-height="25rem">
                <template #header>
                  <tr>
                    <th>Mount</th>
                    <th>Filesystem</th>
                    <th>Used</th>
                    <th>Available</th>
                    <th>Capacity</th>
                  </tr>
                </template>
                <tr v-for="filesystem in health.filesystems"
                  :key="`${filesystem.filesystem}:${filesystem.mount_point}`">
                  <td><strong>{{ filesystem.mount_point }}</strong></td>
                  <td class="mono-wrap">{{ filesystem.filesystem }}</td>
                  <td>{{ formatBytes(filesystem.used_bytes) }} / {{ formatBytes(filesystem.total_bytes) }}</td>
                  <td>{{ formatBytes(filesystem.available_bytes) }}</td>
                  <td><span class="filesystem-usage" :data-state="filesystemState(filesystem)">{{
                    formatPercent(filesystem.used_percent) }}</span></td>
                </tr>
              </ScrollableDataTable>
            </section>

            <section class="detail-card">
              <div class="server-card-heading">
                <div>
                  <h2>Service health</h2>
                  <p>{{ health.services.manager === 'systemd' ? 'systemd status' : 'Detected service-manager summary' }}
                  </p>
                </div><span class="service-state-pill" :data-state="health.services.state">{{ health.services.state
                }}</span>
              </div>
              <p v-if="health.services.note">{{ health.services.note }}</p>
              <div v-if="health.services.failed_services.length" class="failed-service-list"><code
                  v-for="service in health.services.failed_services" :key="service">{{ service }}</code></div>
              <p v-else-if="health.services.manager === 'systemd'" class="status-message">No failed systemd services
                reported.</p>
            </section>
          </div>

          <section class="detail-card server-process-section">
            <div class="server-card-heading">
              <div>
                <h2>Top processes</h2>
              </div><span class="count-badge">{{ health.top_processes.length }}</span>
            </div>
            <ScrollableDataTable :empty="health.top_processes.length === 0"
              empty-message="No process metrics were returned by this host." max-height="27rem">
              <template #header>
                <tr>
                  <th>PID</th>
                  <th>User</th>
                  <th>CPU</th>
                  <th>Memory</th>
                  <th>Elapsed</th>
                  <th>Command</th>
                </tr>
              </template>
              <tr v-for="process in health.top_processes" :key="process.pid">
                <td>{{ process.pid }}</td>
                <td>{{ process.user ?? '—' }}</td>
                <td>{{ formatPercent(process.cpu_percent) }}</td>
                <td>{{ formatPercent(process.memory_percent) }}</td>
                <td>{{ process.elapsed ?? '—' }}</td>
                <td class="server-process-command">{{ process.command }}</td>
              </tr>
            </ScrollableDataTable>
          </section>
        </template>
      </section>

      <section v-else class="server-related-section server-tab-panel">
        <div class="section-toolbar">
          <div>
            <h2>Related databases</h2>
          </div>
          <span class="count-badge">{{ databases.length }}</span>
        </div>
        <ScrollableDataTable :loading="loading" :empty="databases.length === 0"
          empty-message="No database connections are related to this server." max-height="32rem">
          <template #header>
            <tr>
              <th>Database</th>
              <th>Engine</th>
              <th>Endpoint</th>
              <th>Monitoring</th>
              <th></th>
            </tr>
          </template>
          <tr v-for="database in databases" :key="database.id">
            <td><strong>{{ database.name }}</strong></td>
            <td>{{ engineLabel(database.engine) }}</td>
            <td>{{ database.host }}:{{ database.port }}</td>
            <td>{{ database.monitor_enabled ? 'Enabled' : 'Off' }}</td>
            <td>
              <RouterLink class="text-link" :to="`/databases/${database.id}`">Open database →</RouterLink>
            </td>
          </tr>
        </ScrollableDataTable>
      </section>
    </template>
  </div>
</template>
<style>
.server-overview-reachability-dot {
  width: 0.62rem;
  height: 0.62rem;
  flex: 0 0 0.62rem;
  border-radius: 50%;
  background: var(--text-muted);

  box-shadow:
    0 0 0 3px color-mix(in srgb, var(--text-muted) 12%, transparent);
}

.server-overview-reachability-dot--reachable {
  background: var(--success);

  box-shadow:
    0 0 0 3px color-mix(in srgb, var(--success) 13%, transparent);
}

.server-overview-reachability-dot--unreachable {
  background: var(--danger);

  box-shadow:
    0 0 0 3px color-mix(in srgb, var(--danger) 13%, transparent);
}
</style>
