<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
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

const serverId = computed(() => String(route.params.id ?? ''))
const canManageServers = computed(() => hasPermission(authStore.user?.role, 'servers:manage'))
const canOpenTerminal = computed(() => hasPermission(authStore.user?.role, 'database:operate'))
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
    } else {
      await monitoringStore.testSsh(serverId.value)
    }
  } catch {
    // The monitoring card owns the error state so server inventory still renders.
  }
}

async function testSsh() {
  try {
    await monitoringStore.testSsh(serverId.value)
  } catch {
    // Store exposes the error inline.
  }
}

async function trustHostKey() {
  const candidate = sshTest.value
  if (!candidate || candidate.state !== 'untrusted') return

  const confirmed = window.confirm(
    `Trust SSH host key ${candidate.fingerprint} for ${candidate.target}:${candidate.port}? Verify this fingerprint against the server before continuing.`,
  )
  if (!confirmed) return

  try {
    await monitoringStore.trustHostKey(serverId.value, candidate.fingerprint)
    server.value = await serversStore.loadOne(serverId.value)
    if (canCollectHostMetrics.value) await monitoringStore.loadHealth(serverId.value)
  } catch {
    // Store exposes the error inline.
  }
}

async function refreshHost() {
  try {
    await monitoringStore.loadHealth(serverId.value)
  } catch {
    // Store exposes the error inline.
  }
}

async function refreshAll() {
  await load()
  await initializeMonitoring()
}

function openTerminal() {
  terminalError.value = null
  if (!server.value) return
  if (!server.value.ssh_profile_id || !server.value.ssh_host_key_fingerprint) {
    terminalError.value = 'Test SSH and trust the server host key before opening a terminal.'
    return
  }
  try {
    terminalStore.open(server.value)
  } catch (err) {
    terminalError.value = err instanceof Error ? err.message : 'Unable to open SSH terminal.'
  }
}

onMounted(async () => {
  await load()
  await initializeMonitoring()
})
</script>

<template>
  <section class="page-header server-detail-header">
    <div>
      <RouterLink to="/servers" class="text-link">← Servers</RouterLink>
      <h1>{{ server?.name ?? 'Server' }}</h1>
      <p v-if="server">{{ server.hostname }}<template v-if="server.ip_address"> · {{ server.ip_address }}</template></p>
    </div>
    <div class="server-detail-actions">
      <button
        v-if="server && canOpenTerminal"
        type="button"
        class="primary-button"
        :disabled="!sshConfigured || !sshTrusted"
        @click="openTerminal"
      >
        Open terminal
      </button>
      <button type="button" class="secondary-button" :disabled="loading" @click="refreshAll">Refresh profile</button>
      <RouterLink v-if="server && canManageServers" class="secondary-button" to="/settings/infrastructure">Configure</RouterLink>
    </div>
  </section>

  <p v-if="terminalError" class="login-error">{{ terminalError }}</p>
  <p v-if="error" class="login-error">{{ error }}</p>
  <p v-else-if="loading && !server" class="empty-state">Loading server...</p>

  <template v-else-if="server">
    <div class="server-detail-grid">
      <section class="detail-card">
        <h2>Server profile</h2>
        <dl class="detail-list">
          <div><dt>Type</dt><dd>{{ serverTypeLabel(server.server_type) }}</dd></div>
          <div><dt>Operating system</dt><dd>{{ osLabel(server.os_family) }}{{ server.os_version ? ` · ${server.os_version}` : '' }}</dd></div>
          <div><dt>Environment</dt><dd>{{ server.environment ?? '—' }}</dd></div>
          <div><dt>Owner / team</dt><dd>{{ server.owner ?? '—' }}</dd></div>
          <div><dt>Status</dt><dd>{{ server.enabled ? 'Enabled' : 'Disabled' }}</dd></div>
        </dl>
      </section>

      <section class="detail-card server-ssh-card">
        <div class="server-card-heading">
          <h2>SSH access</h2>
          <button
            v-if="sshConfigured"
            type="button"
            class="secondary-button"
            :disabled="sshTestLoading"
            @click="testSsh"
          >
            {{ sshTestLoading ? 'Testing...' : 'Test SSH' }}
          </button>
        </div>

        <template v-if="server.ssh_profile_name">
          <strong>{{ server.ssh_profile_name }}</strong>
          <p>Encrypted SSH credentials are resolved only by the backend.</p>

          <dl class="detail-list compact-detail-list">
            <div><dt>Host key</dt><dd>{{ sshTrusted ? 'Trusted' : 'Not trusted yet' }}</dd></div>
            <div v-if="server.ssh_host_key_fingerprint"><dt>Fingerprint</dt><dd class="mono-wrap">{{ server.ssh_host_key_fingerprint }}</dd></div>
            <div v-if="sshTest"><dt>Last test</dt><dd>{{ sshTest.message }}</dd></div>
          </dl>

          <div v-if="sshTest?.state === 'untrusted'" class="ssh-trust-panel">
            <strong>Verify host identity before authentication</strong>
            <code>{{ sshTest.fingerprint }}</code>
            <p>DBAChum reached the SSH endpoint but has not sent the stored credential yet.</p>
            <button v-if="canManageServers" type="button" class="primary-button" :disabled="sshTestLoading" @click="trustHostKey">
              Trust this host key
            </button>
            <small v-else>An administrator must trust the verified host key in DBAChum.</small>
          </div>
        </template>
        <template v-else>
          <strong>Not configured</strong>
          <p>Assign an SSH access profile from Settings → Infrastructure when this host should support SSH monitoring.</p>
        </template>
      </section>

      <section class="detail-card server-detail-notes">
        <h2>Notes & tags</h2>
        <p>{{ server.notes ?? 'No notes.' }}</p>
        <div v-if="server.tags.length" class="server-tags">
          <span v-for="tag in server.tags" :key="tag">{{ tag }}</span>
        </div>
      </section>
    </div>

    <section class="server-monitoring-section">
      <div class="section-toolbar">
        <div>
          <h2>Host monitoring</h2>
          <p>Read-only snapshot over SSH. No background SSH polling is performed in this phase.</p>
        </div>
        <div class="server-monitoring-actions">
          <span v-if="health" class="server-last-checked">Checked {{ formatCheckedAt(health.checked_at) }}</span>
          <button
            type="button"
            class="primary-button"
            :disabled="!sshConfigured || !sshTrusted || !canCollectHostMetrics || healthLoading"
            @click="refreshHost"
          >
            {{ healthLoading ? 'Refreshing...' : 'Refresh host' }}
          </button>
        </div>
      </div>

      <div v-if="!sshConfigured" class="notice-card">Assign an SSH access profile before host metrics can be collected.</div>
      <div v-else-if="!sshTrusted" class="notice-card">Test SSH and verify the server fingerprint before DBAChum sends the stored SSH credential.</div>
      <div v-else-if="!canCollectHostMetrics" class="notice-card">This first host-metrics collector supports Linux, AIX and Unix assets. SSH connectivity can still be tested for this server.</div>
      <p v-if="monitoringError" class="login-error">{{ monitoringError }}</p>

      <template v-if="health">
        <div class="server-health-metrics">
          <article class="metric-card">
            <span class="metric-card__label">CPU used</span>
            <strong class="metric-card__value">{{ formatPercent(health.cpu_used_percent) }}</strong>
            <small class="metric-card__hint">{{ health.cpu_measurement ?? 'Current host sample' }}</small>
          </article>
          <article class="metric-card">
            <span class="metric-card__label">Memory used</span>
            <strong class="metric-card__value">{{ formatPercent(health.memory.used_percent) }}</strong>
            <small class="metric-card__hint">{{ formatBytes(health.memory.used_bytes) }} / {{ formatBytes(health.memory.total_bytes) }}</small>
          </article>
          <article class="metric-card">
            <span class="metric-card__label">Load average</span>
            <strong class="metric-card__value">{{ health.load_1 ?? '—' }}</strong>
            <small class="metric-card__hint">1m / 5m / 15m · {{ health.load_1 ?? '—' }} / {{ health.load_5 ?? '—' }} / {{ health.load_15 ?? '—' }}</small>
          </article>
          <article class="metric-card">
            <span class="metric-card__label">Uptime</span>
            <strong class="metric-card__value">{{ formatUptime(health.uptime_seconds) }}</strong>
            <small class="metric-card__hint">{{ health.remote_hostname ?? health.target }}</small>
          </article>
          <article class="metric-card">
            <span class="metric-card__label">Swap used</span>
            <strong class="metric-card__value">{{ formatPercent(health.memory.swap_used_percent) }}</strong>
            <small class="metric-card__hint">{{ formatBytes(health.memory.swap_used_bytes) }} / {{ formatBytes(health.memory.swap_total_bytes) }}</small>
          </article>
          <article class="metric-card">
            <span class="metric-card__label">SSH</span>
            <strong class="metric-card__value">{{ health.ssh_latency_ms != null ? `${health.ssh_latency_ms} ms` : 'Connected' }}</strong>
            <small class="metric-card__hint">{{ health.target }}:{{ health.port }}</small>
          </article>
        </div>

        <div v-if="health.warnings.length" class="server-monitoring-warnings">
          <strong>Partial metrics</strong>
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
              </div>
              <span class="count-badge">{{ health.filesystems.length }}</span>
            </div>
            <ScrollableDataTable
              :empty="health.filesystems.length === 0"
              empty-message="No filesystem metrics were returned by this host."
              max-height="25rem"
            >
              <template #header>
                <tr>
                  <th>Mount</th>
                  <th>Filesystem</th>
                  <th>Used</th>
                  <th>Available</th>
                  <th>Capacity</th>
                </tr>
              </template>
              <tr v-for="filesystem in health.filesystems" :key="`${filesystem.filesystem}:${filesystem.mount_point}`">
                <td><strong>{{ filesystem.mount_point }}</strong></td>
                <td class="mono-wrap">{{ filesystem.filesystem }}</td>
                <td>{{ formatBytes(filesystem.used_bytes) }} / {{ formatBytes(filesystem.total_bytes) }}</td>
                <td>{{ formatBytes(filesystem.available_bytes) }}</td>
                <td>
                  <span class="filesystem-usage" :data-state="filesystemState(filesystem)">{{ formatPercent(filesystem.used_percent) }}</span>
                </td>
              </tr>
            </ScrollableDataTable>
          </section>

          <section class="detail-card">
            <div class="server-card-heading">
              <div>
                <h2>Service health</h2>
                <p>{{ health.services.manager === 'systemd' ? 'systemd status' : 'Detected service-manager summary' }}</p>
              </div>
              <span class="service-state-pill" :data-state="health.services.state">{{ health.services.state }}</span>
            </div>
            <p v-if="health.services.note">{{ health.services.note }}</p>
            <div v-if="health.services.failed_services.length" class="failed-service-list">
              <code v-for="service in health.services.failed_services" :key="service">{{ service }}</code>
            </div>
            <p v-else-if="health.services.manager === 'systemd'" class="status-message">No failed systemd services reported.</p>
          </section>
        </div>

        <section class="detail-card server-process-section">
          <div class="server-card-heading">
            <div>
              <h2>Top processes</h2>
              <p>Top 10 processes from the current SSH snapshot, sorted by reported CPU.</p>
            </div>
            <span class="count-badge">{{ health.top_processes.length }}</span>
          </div>
          <ScrollableDataTable
            :empty="health.top_processes.length === 0"
            empty-message="No process metrics were returned by this host."
            max-height="27rem"
          >
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

    <section class="server-related-section">
      <div class="section-toolbar">
        <div>
          <h2>Related databases</h2>
          <p>Relationships are configuration metadata; the database connections remain independent assets.</p>
        </div>
        <span class="count-badge">{{ databases.length }}</span>
      </div>

      <ScrollableDataTable
        :loading="loading"
        :empty="databases.length === 0"
        empty-message="No database connections are related to this server."
        max-height="28rem"
      >
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
          <td><RouterLink class="text-link" :to="`/databases/${database.id}`">Open database →</RouterLink></td>
        </tr>
      </ScrollableDataTable>
    </section>
  </template>
</template>
