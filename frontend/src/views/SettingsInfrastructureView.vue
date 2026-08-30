<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'

import ScrollableDataTable from '@/components/common/ScrollableDataTable.vue'
import { useConnectionsStore } from '@/stores/connections'
import {
  useServersStore,
  type Server,
  type ServerInput,
  type ServerOsFamily,
  type ServerType,
} from '@/stores/servers'
import {
  useSshAccessStore,
  type SshAccessProfile,
  type SshAccessProfileInput,
  type SshAuthType,
} from '@/stores/sshAccess'
import {
  useTerminalShortcutsStore,
  type TerminalShortcut,
  type TerminalShortcutInput,
  type TerminalShortcutMode,
} from '@/stores/terminalShortcuts'

const serversStore = useServersStore()
const sshStore = useSshAccessStore()
const connectionsStore = useConnectionsStore()
const terminalShortcutsStore = useTerminalShortcutsStore()

const activeTab = ref<'servers' | 'ssh' | 'shortcuts'>('servers')
const serverFormOpen = ref(false)
const sshFormOpen = ref(false)
const shortcutFormOpen = ref(false)
const editingServerId = ref<string | null>(null)
const editingSshId = ref<string | null>(null)
const editingShortcutId = ref<string | null>(null)
const serverFormError = ref<string | null>(null)
const sshFormError = ref<string | null>(null)
const shortcutFormError = ref<string | null>(null)
const serverFilter = ref('')
const sshFilter = ref('')
const shortcutFilter = ref('')
const shortcutServerFilter = ref('')

interface ServerForm {
  name: string
  hostname: string
  ip_address: string
  server_type: ServerType
  os_family: ServerOsFamily
  os_version: string
  environment: string
  owner: string
  tags: string
  notes: string
  ssh_profile_id: string
  database_connection_ids: string[]
  enabled: boolean
}

interface SshForm {
  name: string
  username: string
  port: number
  auth_type: SshAuthType
  password: string
  private_key: string
  passphrase: string
  notes: string
  enabled: boolean
}

interface ShortcutForm {
  name: string
  category: string
  command: string
  mode: TerminalShortcutMode
  scope: 'all' | 'selected'
  server_ids: string[]
  sort_order: number
  enabled: boolean
}

function emptyServerForm(): ServerForm {
  return {
    name: '',
    hostname: '',
    ip_address: '',
    server_type: 'database',
    os_family: 'linux',
    os_version: '',
    environment: '',
    owner: '',
    tags: '',
    notes: '',
    ssh_profile_id: '',
    database_connection_ids: [],
    enabled: true,
  }
}

function emptySshForm(): SshForm {
  return {
    name: '',
    username: '',
    port: 22,
    auth_type: 'password',
    password: '',
    private_key: '',
    passphrase: '',
    notes: '',
    enabled: true,
  }
}

function emptyShortcutForm(): ShortcutForm {
  return {
    name: '',
    category: 'General',
    command: '',
    mode: 'execute',
    scope: 'all',
    server_ids: [],
    sort_order: 100,
    enabled: true,
  }
}

const serverForm = reactive<ServerForm>(emptyServerForm())
const sshForm = reactive<SshForm>(emptySshForm())
const shortcutForm = reactive<ShortcutForm>(emptyShortcutForm())

const filteredServers = computed(() => {
  const q = serverFilter.value.trim().toLowerCase()
  if (!q) return serversStore.servers
  return serversStore.servers.filter((server) =>
    [
      server.name,
      server.hostname,
      server.ip_address,
      server.environment,
      server.owner,
      server.server_type,
      ...server.tags,
    ]
      .filter(Boolean)
      .some((value) => String(value).toLowerCase().includes(q)),
  )
})

const filteredSshProfiles = computed(() => {
  const q = sshFilter.value.trim().toLowerCase()
  if (!q) return sshStore.profiles
  return sshStore.profiles.filter((profile) =>
    [profile.name, profile.username, profile.notes]
      .filter(Boolean)
      .some((value) => String(value).toLowerCase().includes(q)),
  )
})

const filteredShortcuts = computed(() => {
  const q = shortcutFilter.value.trim().toLowerCase()
  if (!q) return terminalShortcutsStore.shortcuts
  return terminalShortcutsStore.shortcuts.filter((shortcut) =>
    [shortcut.name, shortcut.category, shortcut.command, shortcut.scope_label]
      .some((value) => String(value).toLowerCase().includes(q)),
  )
})

const shortcutServerOptions = computed(() => {
  const q = shortcutServerFilter.value.trim().toLowerCase()
  return serversStore.servers.filter((server) => {
    const currentlyAssigned = shortcutForm.server_ids.includes(server.id)
    const terminalCapable = server.enabled && Boolean(server.ssh_profile_id)
    if (!terminalCapable && !currentlyAssigned) return false
    if (!q) return true
    return [
      server.name,
      server.hostname,
      server.ip_address,
      server.environment,
      server.ssh_profile_name,
    ]
      .filter(Boolean)
      .some((value) => String(value).toLowerCase().includes(q))
  })
})

function shortcutScopeLabel(shortcut: TerminalShortcut) {
  if (!shortcut.server_ids.length) return 'All SSH-enabled servers'
  const names = shortcut.server_ids
    .map((serverId) => serversStore.servers.find((server) => server.id === serverId)?.name)
    .filter((name): name is string => Boolean(name))
  if (!names.length) return shortcut.scope_label
  if (names.length <= 3) return names.join(', ')
  return `${names.slice(0, 3).join(', ')} +${names.length - 3}`
}

function setShortcutScope(scope: 'all' | 'selected') {
  shortcutForm.scope = scope
}

function clearShortcutServers() {
  shortcutForm.server_ids = []
}

function formatAuditDuration(seconds: number | null) {
  if (seconds == null) return '—'
  if (seconds < 60) return `${Math.round(seconds)}s`
  const minutes = Math.floor(seconds / 60)
  const remaining = Math.round(seconds % 60)
  return `${minutes}m ${remaining}s`
}

function resetServerForm() {
  Object.assign(serverForm, emptyServerForm())
  editingServerId.value = null
  serverFormError.value = null
}

function openAddServer() {
  resetServerForm()
  serverFormOpen.value = true
}

function editServer(server: Server) {
  editingServerId.value = server.id
  serverFormError.value = null
  Object.assign(serverForm, {
    name: server.name,
    hostname: server.hostname,
    ip_address: server.ip_address ?? '',
    server_type: server.server_type,
    os_family: server.os_family,
    os_version: server.os_version ?? '',
    environment: server.environment ?? '',
    owner: server.owner ?? '',
    tags: server.tags.join(', '),
    notes: server.notes ?? '',
    ssh_profile_id: server.ssh_profile_id ?? '',
    database_connection_ids: [...server.database_connection_ids],
    enabled: server.enabled,
  })
  serverFormOpen.value = true
}

function closeServerForm() {
  serverFormOpen.value = false
  resetServerForm()
}

function buildServerPayload(): ServerInput {
  return {
    name: serverForm.name.trim(),
    hostname: serverForm.hostname.trim(),
    ip_address: serverForm.ip_address.trim() || null,
    server_type: serverForm.server_type,
    os_family: serverForm.os_family,
    os_version: serverForm.os_version.trim() || null,
    environment: serverForm.environment.trim() || null,
    owner: serverForm.owner.trim() || null,
    tags: serverForm.tags.split(',').map((tag) => tag.trim()).filter(Boolean),
    notes: serverForm.notes.trim() || null,
    ssh_profile_id: serverForm.ssh_profile_id || null,
    database_connection_ids: [...serverForm.database_connection_ids],
    enabled: serverForm.enabled,
  }
}

async function saveServer() {
  serverFormError.value = null
  try {
    const payload = buildServerPayload()
    if (editingServerId.value) {
      await serversStore.update(editingServerId.value, payload)
    } else {
      await serversStore.create(payload)
    }
    await connectionsStore.load()
    closeServerForm()
  } catch (error) {
    serverFormError.value = error instanceof Error ? error.message : 'Unable to save server.'
  }
}

async function removeServer(server: Server) {
  if (!window.confirm(`Delete server asset "${server.name}"? Database connections will remain and only the relationship is removed.`)) return
  try {
    await serversStore.remove(server.id)
    await connectionsStore.load()
  } catch (error) {
    serverFormError.value = error instanceof Error ? error.message : 'Unable to delete server.'
  }
}

function resetSshForm() {
  Object.assign(sshForm, emptySshForm())
  editingSshId.value = null
  sshFormError.value = null
}

function openAddSshProfile() {
  resetSshForm()
  sshFormOpen.value = true
}

function editSshProfile(profile: SshAccessProfile) {
  editingSshId.value = profile.id
  sshFormError.value = null
  Object.assign(sshForm, {
    name: profile.name,
    username: profile.username,
    port: profile.port,
    auth_type: profile.auth_type,
    password: '',
    private_key: '',
    passphrase: '',
    notes: profile.notes ?? '',
    enabled: profile.enabled,
  })
  sshFormOpen.value = true
}

function closeSshForm() {
  sshFormOpen.value = false
  resetSshForm()
}

function buildSshPayload(): SshAccessProfileInput {
  const payload: SshAccessProfileInput = {
    name: sshForm.name.trim(),
    username: sshForm.username.trim(),
    port: Number(sshForm.port),
    auth_type: sshForm.auth_type,
    notes: sshForm.notes.trim() || null,
    enabled: sshForm.enabled,
  }
  if (sshForm.password) payload.password = sshForm.password
  if (sshForm.private_key) payload.private_key = sshForm.private_key
  if (sshForm.passphrase) payload.passphrase = sshForm.passphrase
  return payload
}

async function saveSshProfile() {
  sshFormError.value = null
  try {
    const payload = buildSshPayload()
    if (editingSshId.value) {
      await sshStore.update(editingSshId.value, payload)
    } else {
      await sshStore.create(payload)
    }
    await serversStore.load()
    closeSshForm()
  } catch (error) {
    sshFormError.value = error instanceof Error ? error.message : 'Unable to save SSH access profile.'
  }
}

async function removeSshProfile(profile: SshAccessProfile) {
  if (!window.confirm(`Delete SSH access profile "${profile.name}"?`)) return
  try {
    await sshStore.remove(profile.id)
  } catch (error) {
    sshFormError.value = error instanceof Error ? error.message : 'Unable to delete SSH access profile.'
  }
}

function resetShortcutForm() {
  Object.assign(shortcutForm, emptyShortcutForm())
  shortcutServerFilter.value = ''
  editingShortcutId.value = null
  shortcutFormError.value = null
}

function openAddShortcut() {
  resetShortcutForm()
  shortcutFormOpen.value = true
}

function editShortcut(shortcut: TerminalShortcut) {
  editingShortcutId.value = shortcut.id
  shortcutFormError.value = null
  Object.assign(shortcutForm, {
    name: shortcut.name,
    category: shortcut.category,
    command: shortcut.command,
    mode: shortcut.mode,
    scope: shortcut.server_ids.length ? 'selected' : 'all',
    server_ids: [...shortcut.server_ids],
    sort_order: shortcut.sort_order,
    enabled: shortcut.enabled,
  })
  shortcutFormOpen.value = true
}

function closeShortcutForm() {
  shortcutFormOpen.value = false
  resetShortcutForm()
}

function buildShortcutPayload(): TerminalShortcutInput {
  return {
    name: shortcutForm.name.trim(),
    category: shortcutForm.category.trim() || 'General',
    command: shortcutForm.command.trim(),
    mode: shortcutForm.mode,
    server_ids: shortcutForm.scope === 'selected' ? [...shortcutForm.server_ids] : [],
    sort_order: Number(shortcutForm.sort_order),
    enabled: shortcutForm.enabled,
  }
}

async function saveShortcut() {
  shortcutFormError.value = null
  if (shortcutForm.scope === 'selected' && shortcutForm.server_ids.length === 0) {
    shortcutFormError.value = 'Select at least one server, or choose All SSH-enabled servers.'
    return
  }
  try {
    const payload = buildShortcutPayload()
    if (editingShortcutId.value) {
      await terminalShortcutsStore.update(editingShortcutId.value, payload)
    } else {
      await terminalShortcutsStore.create(payload)
    }
    closeShortcutForm()
  } catch (error) {
    shortcutFormError.value = error instanceof Error ? error.message : 'Unable to save terminal shortcut.'
  }
}

async function removeShortcut(shortcut: TerminalShortcut) {
  if (!window.confirm(`Delete terminal shortcut "${shortcut.name}"?`)) return
  try {
    await terminalShortcutsStore.remove(shortcut.id)
  } catch (error) {
    shortcutFormError.value = error instanceof Error ? error.message : 'Unable to delete terminal shortcut.'
  }
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

onMounted(async () => {
  await Promise.all([
    serversStore.load(),
    sshStore.load(),
    connectionsStore.load(),
    terminalShortcutsStore.load(),
    terminalShortcutsStore.loadAudit(),
  ])
})
</script>

<template>
  <section class="infrastructure-settings">
    <div class="workspace-tabs infrastructure-settings-tabs">
      <button type="button" :class="{ active: activeTab === 'servers' }" @click="activeTab = 'servers'">
        Server assets
      </button>
      <button type="button" :class="{ active: activeTab === 'ssh' }" @click="activeTab = 'ssh'">
        SSH access profiles
      </button>
      <button type="button" :class="{ active: activeTab === 'shortcuts' }" @click="activeTab = 'shortcuts'">
        Terminal shortcuts
      </button>
    </div>

    <template v-if="activeTab === 'servers'">
      <div class="section-toolbar">
        <div>
          <h3>Server assets</h3>
          <p>Configuration lives here; the Servers workspace is reserved for operational use.</p>
        </div>
        <button class="primary-button" type="button" @click="openAddServer">Add server</button>
      </div>

      <input v-model="serverFilter" class="table-filter-input" placeholder="Search hostname, environment, owner, tag..." />

      <p v-if="serversStore.error" class="login-error">{{ serversStore.error }}</p>

      <ScrollableDataTable
        :loading="serversStore.loading"
        :empty="!serversStore.loading && filteredServers.length === 0"
        empty-message="No server assets match this view."
        max-height="36rem"
      >
        <template #header>
          <tr>
            <th>Name</th>
            <th>Type</th>
            <th>Host</th>
            <th>Environment</th>
            <th>SSH access</th>
            <th>Databases</th>
            <th>Status</th>
            <th>Actions</th>
          </tr>
        </template>
        <tr v-for="server in filteredServers" :key="server.id">
          <td><strong>{{ server.name }}</strong><br /><small>{{ osLabel(server.os_family) }}{{ server.os_version ? ` · ${server.os_version}` : '' }}</small></td>
          <td>{{ serverTypeLabel(server.server_type) }}</td>
          <td>{{ server.hostname }}<br /><small>{{ server.ip_address ?? '—' }}</small></td>
          <td>{{ server.environment ?? '—' }}</td>
          <td>{{ server.ssh_profile_name ?? 'Not configured' }}</td>
          <td>{{ server.database_count }}</td>
          <td>{{ server.enabled ? 'Enabled' : 'Disabled' }}</td>
          <td class="table-actions-cell">
            <button type="button" class="secondary-button" @click="editServer(server)">Edit</button>
            <button type="button" class="secondary-button" @click="removeServer(server)">Delete</button>
          </td>
        </tr>
      </ScrollableDataTable>
    </template>

    <template v-else-if="activeTab === 'ssh'">
      <div class="section-toolbar">
        <div>
          <h3>SSH access profiles</h3>
          <p>Reusable encrypted authentication profiles. Passwords and private keys are never returned to the browser after saving.</p>
        </div>
        <button class="primary-button" type="button" @click="openAddSshProfile">Add SSH profile</button>
      </div>

      <div class="notice-card">
        These profiles are the credential foundation for SSH monitoring and future infrastructure operations. Saving a profile does not open an SSH connection by itself.
      </div>

      <input v-model="sshFilter" class="table-filter-input" placeholder="Search profile, username or notes..." />

      <p v-if="sshStore.error" class="login-error">{{ sshStore.error }}</p>

      <ScrollableDataTable
        :loading="sshStore.loading"
        :empty="!sshStore.loading && filteredSshProfiles.length === 0"
        empty-message="No SSH access profiles configured."
        max-height="32rem"
      >
        <template #header>
          <tr>
            <th>Profile</th>
            <th>Username</th>
            <th>Port</th>
            <th>Authentication</th>
            <th>Used by</th>
            <th>Status</th>
            <th>Actions</th>
          </tr>
        </template>
        <tr v-for="profile in filteredSshProfiles" :key="profile.id">
          <td><strong>{{ profile.name }}</strong></td>
          <td>{{ profile.username }}</td>
          <td>{{ profile.port }}</td>
          <td>
            {{ profile.auth_type === 'password' ? 'Password' : 'Private key' }}
            <small v-if="profile.auth_type === 'password'"> · {{ profile.has_password ? 'secret stored' : 'missing secret' }}</small>
            <small v-else> · {{ profile.has_private_key ? 'key stored' : 'missing key' }}</small>
          </td>
          <td>{{ profile.server_count }} server{{ profile.server_count === 1 ? '' : 's' }}</td>
          <td>{{ profile.enabled ? 'Enabled' : 'Disabled' }}</td>
          <td class="table-actions-cell">
            <button type="button" class="secondary-button" @click="editSshProfile(profile)">Edit</button>
            <button type="button" class="secondary-button" @click="removeSshProfile(profile)">Delete</button>
          </td>
        </tr>
      </ScrollableDataTable>
    </template>

    <template v-else>
      <div class="section-toolbar">
        <div>
          <h3>Terminal shortcuts</h3>
          <p>Reusable buttons for frequent shell navigation and tools. A shortcut can run immediately or only insert text at the prompt.</p>
        </div>
        <button class="primary-button" type="button" @click="openAddShortcut">Add shortcut</button>
      </div>

      <div class="notice-card">
        Leave the server assignment empty to make a shortcut available on every SSH-enabled server, or select specific assets for context-sensitive menus.
      </div>

      <input v-model="shortcutFilter" class="table-filter-input" placeholder="Search shortcut, category, command or scope..." />
      <p v-if="terminalShortcutsStore.error" class="login-error">{{ terminalShortcutsStore.error }}</p>

      <ScrollableDataTable
        :loading="terminalShortcutsStore.loading"
        :empty="!terminalShortcutsStore.loading && filteredShortcuts.length === 0"
        empty-message="No terminal shortcuts configured."
        max-height="30rem"
      >
        <template #header>
          <tr>
            <th>Shortcut</th>
            <th>Category</th>
            <th>Behavior</th>
            <th>Command</th>
            <th>Scope</th>
            <th>Status</th>
            <th>Actions</th>
          </tr>
        </template>
        <tr v-for="shortcut in filteredShortcuts" :key="shortcut.id">
          <td><strong>{{ shortcut.name }}</strong></td>
          <td>{{ shortcut.category }}</td>
          <td>{{ shortcut.mode === 'execute' ? 'Run now' : 'Insert only' }}</td>
          <td class="terminal-shortcut-command"><code>{{ shortcut.command }}</code></td>
          <td><span :title="shortcut.scope_label">{{ shortcutScopeLabel(shortcut) }}</span></td>
          <td>{{ shortcut.enabled ? 'Enabled' : 'Disabled' }}</td>
          <td class="table-actions-cell">
            <button type="button" class="secondary-button" @click="editShortcut(shortcut)">Edit</button>
            <button type="button" class="secondary-button" @click="removeShortcut(shortcut)">Delete</button>
          </td>
        </tr>
      </ScrollableDataTable>

      <div class="section-toolbar terminal-audit-heading">
        <div>
          <h3>Recent terminal sessions</h3>
          <p>Session metadata is audited without storing raw terminal keystrokes or password-prompt input.</p>
        </div>
        <button class="secondary-button" type="button" @click="terminalShortcutsStore.loadAudit()">Refresh audit</button>
      </div>

      <ScrollableDataTable
        :empty="terminalShortcutsStore.audit.length === 0"
        empty-message="No SSH terminal sessions have been audited yet."
        max-height="24rem"
      >
        <template #header>
          <tr>
            <th>Started</th>
            <th>DBAChum user</th>
            <th>Server</th>
            <th>SSH user</th>
            <th>Duration</th>
            <th>Shortcuts</th>
            <th>Status</th>
          </tr>
        </template>
        <tr v-for="entry in terminalShortcutsStore.audit" :key="entry.session_id">
          <td>{{ new Date(entry.started_at).toLocaleString() }}</td>
          <td>{{ entry.operator_username }}</td>
          <td><strong>{{ entry.server_name }}</strong><br /><small>{{ entry.target }}</small></td>
          <td>{{ entry.ssh_username }}</td>
          <td>{{ formatAuditDuration(entry.duration_seconds) }}</td>
          <td>{{ entry.shortcut_actions.length }}</td>
          <td>{{ entry.status }}</td>
        </tr>
      </ScrollableDataTable>
    </template>
  </section>

  <div v-if="serverFormOpen" class="modal-backdrop" @click.self="closeServerForm">
    <section class="modal-panel infrastructure-modal" role="dialog" aria-modal="true">
      <div class="modal-header">
        <div>
          <h2>{{ editingServerId ? 'Edit server asset' : 'Add server asset' }}</h2>
          <p>Inventory, relationships and optional SSH access assignment.</p>
        </div>
        <button type="button" class="modal-close" @click="closeServerForm">×</button>
      </div>

      <form class="connection-form" @submit.prevent="saveServer">
        <div class="connection-form-row">
          <label>Display name<input v-model="serverForm.name" required placeholder="Oracle PROD 01" /></label>
          <label>Server type
            <select v-model="serverForm.server_type">
              <option value="database">Database server</option>
              <option value="application">Application server</option>
              <option value="utility">Utility server</option>
              <option value="other">Other</option>
            </select>
          </label>
        </div>

        <div class="connection-form-row">
          <label>Hostname<input v-model="serverForm.hostname" required placeholder="dbprod01" /></label>
          <label>IP address<input v-model="serverForm.ip_address" placeholder="192.168.1.10" /></label>
        </div>

        <div class="connection-form-row">
          <label>Operating system
            <select v-model="serverForm.os_family">
              <option value="windows">Windows</option>
              <option value="linux">Linux</option>
              <option value="aix">AIX</option>
              <option value="unix">Unix</option>
              <option value="other">Other</option>
            </select>
          </label>
          <label>OS version<input v-model="serverForm.os_version" placeholder="RHEL 9 / AIX 7.2 / Windows Server" /></label>
        </div>

        <div class="connection-form-row">
          <label>Environment<input v-model="serverForm.environment" placeholder="Production" /></label>
          <label>Owner / team<input v-model="serverForm.owner" placeholder="Database Administrator" /></label>
        </div>

        <label>SSH access profile <span class="optional-label">Optional</span>
          <select v-model="serverForm.ssh_profile_id">
            <option value="">No SSH access profile</option>
            <option v-for="profile in sshStore.profiles" :key="profile.id" :value="profile.id" :disabled="!profile.enabled">
              {{ profile.name }} · {{ profile.username }}@SSH:{{ profile.port }}
            </option>
          </select>
          <small>The server stores only a reference to the reusable encrypted profile.</small>
        </label>

        <label>Related database connections <span class="optional-label">Optional</span>
          <select v-model="serverForm.database_connection_ids" multiple size="6">
            <option v-for="connection in connectionsStore.connections" :key="connection.id" :value="connection.id">
              {{ connection.name }} · {{ connection.engine }} · {{ connection.host }}
            </option>
          </select>
          <small>A database can be related to more than one host (for example cluster/RAC nodes).</small>
        </label>

        <label>Tags<input v-model="serverForm.tags" placeholder="oracle, production, erp" /><small>Separate tags with commas.</small></label>
        <label>Notes<textarea v-model="serverForm.notes" rows="3" /></label>
        <label class="connection-checkbox"><input v-model="serverForm.enabled" type="checkbox" /> Enable this server asset</label>

        <p v-if="serverFormError" class="login-error">{{ serverFormError }}</p>
        <div class="connection-form-actions">
          <button type="submit" class="primary-button" :disabled="serversStore.saving">{{ serversStore.saving ? 'Saving...' : 'Save server' }}</button>
          <button type="button" class="secondary-button" @click="closeServerForm">Cancel</button>
        </div>
      </form>
    </section>
  </div>

  <div v-if="sshFormOpen" class="modal-backdrop" @click.self="closeSshForm">
    <section class="modal-panel infrastructure-modal" role="dialog" aria-modal="true">
      <div class="modal-header">
        <div>
          <h2>{{ editingSshId ? 'Edit SSH access profile' : 'Add SSH access profile' }}</h2>
          <p>Reusable credentials encrypted with DBAChum's existing connection-encryption key.</p>
        </div>
        <button type="button" class="modal-close" @click="closeSshForm">×</button>
      </div>

      <form class="connection-form" @submit.prevent="saveSshProfile">
        <div class="connection-form-row">
          <label>Profile name<input v-model="sshForm.name" required placeholder="Linux DBA Production" /></label>
          <label>Username<input v-model="sshForm.username" required placeholder="oracle" /></label>
        </div>

        <div class="connection-form-row">
          <label>Port<input v-model.number="sshForm.port" type="number" min="1" max="65535" required /></label>
          <label>Authentication
            <select v-model="sshForm.auth_type">
              <option value="password">Password</option>
              <option value="private_key">Private key</option>
            </select>
          </label>
        </div>

        <label v-if="sshForm.auth_type === 'password'">Password
          <input v-model="sshForm.password" type="password" :required="!editingSshId" autocomplete="new-password" />
          <small v-if="editingSshId">Leave blank to keep the stored password.</small>
        </label>

        <template v-else>
          <label>Private key
            <textarea v-model="sshForm.private_key" rows="8" :required="!editingSshId" placeholder="-----BEGIN OPENSSH PRIVATE KEY-----" />
            <small v-if="editingSshId">Leave blank to keep the stored private key.</small>
          </label>
          <label>Private-key passphrase <span class="optional-label">Optional</span>
            <input v-model="sshForm.passphrase" type="password" autocomplete="new-password" />
            <small v-if="editingSshId">Leave blank to keep the existing passphrase.</small>
          </label>
        </template>

        <label>Notes<textarea v-model="sshForm.notes" rows="3" placeholder="Scope / account owner / intended server group" /></label>
        <label class="connection-checkbox"><input v-model="sshForm.enabled" type="checkbox" /> Enable this SSH access profile</label>

        <p v-if="sshFormError" class="login-error">{{ sshFormError }}</p>
        <div class="connection-form-actions">
          <button type="submit" class="primary-button" :disabled="sshStore.saving">{{ sshStore.saving ? 'Saving...' : 'Save SSH profile' }}</button>
          <button type="button" class="secondary-button" @click="closeSshForm">Cancel</button>
        </div>
      </form>
    </section>
  </div>

  <div v-if="shortcutFormOpen" class="modal-backdrop" @click.self="closeShortcutForm">
    <section class="modal-panel infrastructure-modal" role="dialog" aria-modal="true">
      <div class="modal-header">
        <div>
          <h2>{{ editingShortcutId ? 'Edit terminal shortcut' : 'Add terminal shortcut' }}</h2>
          <p>Define a useful button without hardcoding server-specific behavior into DBAChum.</p>
        </div>
        <button type="button" class="modal-close" @click="closeShortcutForm">×</button>
      </div>

      <form class="connection-form" @submit.prevent="saveShortcut">
        <div class="connection-form-row">
          <label>Shortcut name<input v-model="shortcutForm.name" required placeholder="SQL*Plus SYSDBA" /></label>
          <label>Category<input v-model="shortcutForm.category" required placeholder="Oracle" /></label>
        </div>

        <label>Command
          <textarea v-model="shortcutForm.command" rows="4" required placeholder="sqlplus / as sysdba" />
          <small>The command is sent to the active PTY exactly as configured.</small>
        </label>

        <div class="connection-form-row">
          <label>Behavior
            <select v-model="shortcutForm.mode">
              <option value="execute">Run immediately</option>
              <option value="insert">Insert at prompt only</option>
            </select>
          </label>
          <label>Sort order<input v-model.number="shortcutForm.sort_order" type="number" min="0" max="10000" /></label>
        </div>

        <fieldset class="terminal-shortcut-scope">
          <legend>Available on servers</legend>
          <p class="terminal-shortcut-scope__hint">
            Choose exactly where this shortcut appears. Server-specific shortcuts are also enforced by the backend when used.
          </p>

          <div class="terminal-shortcut-scope__modes">
            <label class="connection-checkbox">
              <input
                type="radio"
                name="terminal-shortcut-scope"
                value="all"
                :checked="shortcutForm.scope === 'all'"
                @change="setShortcutScope('all')"
              />
              All SSH-enabled servers
            </label>
            <label class="connection-checkbox">
              <input
                type="radio"
                name="terminal-shortcut-scope"
                value="selected"
                :checked="shortcutForm.scope === 'selected'"
                @change="setShortcutScope('selected')"
              />
              Only selected servers
            </label>
          </div>

          <div v-if="shortcutForm.scope === 'selected'" class="terminal-shortcut-server-picker">
            <div class="terminal-shortcut-server-picker__toolbar">
              <input
                v-model="shortcutServerFilter"
                type="search"
                placeholder="Search server, hostname, environment or SSH profile..."
              />
              <span>{{ shortcutForm.server_ids.length }} selected</span>
              <button
                v-if="shortcutForm.server_ids.length"
                type="button"
                class="secondary-button"
                @click="clearShortcutServers"
              >
                Clear
              </button>
            </div>

            <div class="terminal-shortcut-server-picker__list">
              <label
                v-for="item in shortcutServerOptions"
                :key="item.id"
                class="terminal-shortcut-server-option"
              >
                <input v-model="shortcutForm.server_ids" type="checkbox" :value="item.id" />
                <span>
                  <strong>{{ item.name }}</strong>
                  <small>
                    {{ item.hostname }}
                    <template v-if="item.environment"> · {{ item.environment }}</template>
                    <template v-if="item.ssh_profile_name"> · {{ item.ssh_profile_name }}</template>
                  </small>
                </span>
              </label>
              <p v-if="!shortcutServerOptions.length" class="empty-state">
                No SSH-enabled server assets match this search.
              </p>
            </div>
          </div>
        </fieldset>

        <label class="connection-checkbox"><input v-model="shortcutForm.enabled" type="checkbox" /> Enable this terminal shortcut</label>
        <p v-if="shortcutFormError" class="login-error">{{ shortcutFormError }}</p>
        <div class="connection-form-actions">
          <button type="submit" class="primary-button" :disabled="terminalShortcutsStore.saving">
            {{ terminalShortcutsStore.saving ? 'Saving...' : 'Save shortcut' }}
          </button>
          <button type="button" class="secondary-button" @click="closeShortcutForm">Cancel</button>
        </div>
      </form>
    </section>
  </div>
</template>
