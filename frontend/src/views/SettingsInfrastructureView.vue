<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'

import ScrollableDataTable from '@/components/common/ScrollableDataTable.vue'
import FloatingActionMenu from '@/components/common/FloatingActionMenu.vue'
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
import { confirmDialog, showToast } from '@/ui/feedback'

import {
  useAuthStore,
} from '@/stores/auth'

import {
  hasPermission,
} from '@/core/permissions'

const serversStore = useServersStore()
const sshStore = useSshAccessStore()
const connectionsStore = useConnectionsStore()
const terminalShortcutsStore = useTerminalShortcutsStore()
const authStore = useAuthStore()

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

const canManageConnections = computed(
  () =>
    hasPermission(
      authStore.user,
      'connections:manage',
    ),
)

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
    const name = serverForm.name.trim()
    const updated = Boolean(editingServerId.value)
    closeServerForm()
    showToast({ title: updated ? 'Server updated' : 'Server created', message: name, tone: 'success' })
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Unable to save server.'
    serverFormError.value = message
    showToast({ title: 'Unable to save server', message, tone: 'danger' })
  }
}

async function removeServer(server: Server) {
  const confirmed = await confirmDialog({ title: 'Delete server asset', message: `${server.name}. Database connections remain; only the server asset and relationships are removed.`, confirmLabel: 'Delete server', destructive: true, tone: 'danger' })
  if (!confirmed) return
  try {
    await serversStore.remove(server.id)
    await connectionsStore.load()
    showToast({ title: 'Server deleted', message: server.name, tone: 'success' })
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Unable to delete server.'
    serverFormError.value = message
    showToast({ title: 'Unable to delete server', message, tone: 'danger' })
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
    const name = sshForm.name.trim()
    const updated = Boolean(editingSshId.value)
    closeSshForm()
    showToast({ title: updated ? 'SSH profile updated' : 'SSH profile created', message: name, tone: 'success' })
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Unable to save SSH access profile.'
    sshFormError.value = message
    showToast({ title: 'Unable to save SSH access profile', message, tone: 'danger' })
  }
}

async function removeSshProfile(profile: SshAccessProfile) {
  const confirmed = await confirmDialog({ title: 'Delete SSH access profile', message: profile.name, confirmLabel: 'Delete profile', destructive: true, tone: 'danger' })
  if (!confirmed) return
  try {
    await sshStore.remove(profile.id)
    showToast({ title: 'SSH profile deleted', message: profile.name, tone: 'success' })
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Unable to delete SSH access profile.'
    sshFormError.value = message
    showToast({ title: 'Unable to delete SSH access profile', message, tone: 'danger' })
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
    showToast({ title: 'Select at least one server', message: 'Choose a server or use All SSH-enabled servers.', tone: 'warning' })
    return
  }
  try {
    const payload = buildShortcutPayload()
    if (editingShortcutId.value) {
      await terminalShortcutsStore.update(editingShortcutId.value, payload)
    } else {
      await terminalShortcutsStore.create(payload)
    }
    const name = shortcutForm.name.trim()
    const updated = Boolean(editingShortcutId.value)
    closeShortcutForm()
    showToast({ title: updated ? 'Terminal shortcut updated' : 'Terminal shortcut created', message: name, tone: 'success' })
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Unable to save terminal shortcut.'
    shortcutFormError.value = message
    showToast({ title: 'Unable to save terminal shortcut', message, tone: 'danger' })
  }
}

async function removeShortcut(shortcut: TerminalShortcut) {
  const confirmed = await confirmDialog({ title: 'Delete terminal shortcut', message: shortcut.name, confirmLabel: 'Delete shortcut', destructive: true, tone: 'danger' })
  if (!confirmed) return
  try {
    await terminalShortcutsStore.remove(shortcut.id)
    showToast({ title: 'Terminal shortcut deleted', message: shortcut.name, tone: 'success' })
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Unable to delete terminal shortcut.'
    shortcutFormError.value = message
    showToast({ title: 'Unable to delete terminal shortcut', message, tone: 'danger' })
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
    <div class="workspace-tabs infrastructure-settings-tabs database-tabs">
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
      <div class="panel">
        <div class="section-toolbar">
          <div title="Configuration lives here; the Servers workspace is reserved for operational use.">
            <h3>Server connections</h3>
          </div>
          <button class="primary-button" type="button" @click="openAddServer">Add server</button>
        </div>

        <input v-model="serverFilter" class="table-filter-input utility-select-input"
          placeholder="Search hostname, environment, owner, tag..." />

        <p v-if="serversStore.error" class="login-error">{{ serversStore.error }}</p>

        <p v-if="serversStore.loading" class="empty-state">Loading server assets...</p>
        <div v-else-if="filteredServers.length === 0" class="empty-state">No server assets match this view.</div>
        <div v-else class="connection-list">
          <article v-for="server in filteredServers" :key="server.id" class="connection-item">
            <div>
              <div class="connection-title">
                <strong>{{ server.name }}</strong>
                <span class="status-pill" :class="{ disabled: !server.enabled }">{{ server.enabled ? 'Enabled' :
                  'Disabled' }}</span>
                <span v-if="server.ssh_profile_name" class="status-pill">SSH configured</span>
              </div>
              <p>{{ server.hostname }}<template v-if="server.ip_address"> · {{ server.ip_address }}</template></p>
              <small>{{ osLabel(server.os_family) }}{{ server.os_version ? ` · ${server.os_version}` : '' }} · {{
                serverTypeLabel(server.server_type) }}<template v-if="server.environment"> · {{ server.environment
                }}</template></small>
              <small v-if="server.ssh_profile_name">SSH profile: {{ server.ssh_profile_name }} · {{
                server.database_count }} linked
                database{{ server.database_count === 1 ? '' : 's' }}</small>
            </div>
            <FloatingActionMenu v-if="canManageConnections" :label="`Actions for ${server.name}`">
              <button type="button" role="menuitem" @click="editServer(server)">
                <FontAwesomeIcon icon="pen" />
                Edit
              </button>
              <button type="button" role="menuitem" class="danger-menu-item" @click="removeServer(server)">
                <FontAwesomeIcon icon="trash-can" />
                Delete
              </button>
            </FloatingActionMenu>
          </article>
        </div>
      </div>
    </template>

    <template v-else-if="activeTab === 'ssh'">
      <div class="panel">
        <div class="section-toolbar">
          <div title="Reusable encrypted authentication profiles. Passwords and private keys are never returned to the browser
            after saving.">
            <h3>SSH access profiles</h3>
          </div>
          <button class="primary-button" type="button" @click="openAddSshProfile">Add SSH profile</button>
        </div>

        <input v-model="sshFilter" class="table-filter-input utility-search-input"
          placeholder="Search profile, username or notes..." />

        <p v-if="sshStore.error" class="login-error">{{ sshStore.error }}</p>

        <p v-if="sshStore.loading" class="empty-state">Loading SSH access profiles...</p>
        <div v-else-if="filteredSshProfiles.length === 0" class="empty-state">No SSH access profiles configured.</div>
        <div v-else class="connection-list">
          <article v-for="profile in filteredSshProfiles" :key="profile.id" class="connection-item">
            <div>
              <div class="connection-title">
                <strong>{{ profile.name }}</strong>
                <span class="status-pill" :class="{ disabled: !profile.enabled }">{{ profile.enabled ? 'Enabled' :
                  'Disabled' }}</span>
                <span class="status-pill"
                  :class="{ disabled: profile.auth_type === 'password' ? !profile.has_password : !profile.has_private_key }">
                  {{ profile.auth_type === 'password' ? (profile.has_password ? 'Secret stored' : 'Secret missing') :
                    (profile.has_private_key ? 'Key stored' : 'Key missing') }}
                </span>
              </div>
              <p>{{ profile.username }}@SSH:{{ profile.port }}</p>
              <small>{{ profile.auth_type === 'password' ? 'Password authentication' : 'Private-key authentication' }} ·
                Used by {{ profile.server_count }} server{{ profile.server_count === 1 ? '' : 's' }}</small>
            </div>
            <FloatingActionMenu :label="`Actions for ${profile.name}`">
              <button type="button" role="menuitem" @click="editSshProfile(profile)">
                <FontAwesomeIcon icon="pen" />
                Edit
              </button>
              <button type="button" role="menuitem" class="danger-menu-item" @click="removeSshProfile(profile)">
                <FontAwesomeIcon icon="trash-can" />
                Delete
              </button>
            </FloatingActionMenu>
          </article>
        </div>
      </div>
    </template>

    <template v-else>
      <div class="panel">
        <div class="section-toolbar">
          <div title="Reusable buttons for frequent shell navigation and tools. A shortcut can run immediately or only insert
            text at the prompt.">
            <h3>Terminal shortcuts</h3>
          </div>
          <button class="primary-button" type="button" @click="openAddShortcut">Add shortcut</button>
        </div>

        <input v-model="shortcutFilter" class="table-filter-input utility-search-input"
          placeholder="Search shortcut, category, command or scope..." />
        <p v-if="terminalShortcutsStore.error" class="login-error">{{ terminalShortcutsStore.error }}</p>

        <ScrollableDataTable :loading="terminalShortcutsStore.loading"
          :empty="!terminalShortcutsStore.loading && filteredShortcuts.length === 0"
          empty-message="No terminal shortcuts configured." max-height="30rem">
          <template #header>
            <tr>
              <th>Shortcut</th>
              <th>Category</th>
              <th>Behavior</th>
              <th>Command</th>
              <th>Scope</th>
              <th>Status</th>
              <th class="user-actions-column">
  Actions
</th>
            </tr>
          </template>
          <tr v-for="shortcut in filteredShortcuts" :key="shortcut.id">
            <td><strong>{{ shortcut.name }}</strong></td>
            <td>{{ shortcut.category }}</td>
            <td>{{ shortcut.mode === 'execute' ? 'Run now' : 'Insert only' }}</td>
            <td class="terminal-shortcut-command"><code>{{ shortcut.command }}</code></td>
            <td><span :title="shortcut.scope_label">{{ shortcutScopeLabel(shortcut) }}</span></td>
            <td>{{ shortcut.enabled ? 'Enabled' : 'Disabled' }}</td>
            <td class="user-actions-cell">
              <FloatingActionMenu :label="`Actions for ${shortcut.name}`">
                <button type="button" role="menuitem" @click="editShortcut(shortcut)">
                  <FontAwesomeIcon icon="pen" />
                  Edit
                </button>
                <button type="button" role="menuitem" class="danger-menu-item" @click="removeShortcut(shortcut)">
                  <FontAwesomeIcon icon="trash-can" />
                  Delete
                </button>
              </FloatingActionMenu>
            </td>
          </tr>
        </ScrollableDataTable>

        <div class="section-toolbar terminal-audit-heading">
          <div title="Session metadata is audited without storing raw terminal keystrokes or password-prompt input.">
            <h3>Recent terminal sessions</h3>
          </div>
          <button class="secondary-button" type="button" @click="terminalShortcutsStore.loadAudit()">Refresh
            audit</button>
        </div>

        <ScrollableDataTable :empty="terminalShortcutsStore.audit.length === 0"
          empty-message="No SSH terminal sessions have been audited yet." max-height="24rem">
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
      </div>
    </template>
  </section>

  <div v-if="serverFormOpen" class="modal-backdrop" @click.self="closeServerForm">
    <section class="modal-panel infrastructure-modal" role="dialog" aria-modal="true">
      <div class="modal-header">
        <div>
          <h2>{{ editingServerId ? 'Edit server asset' : 'Add server asset' }}</h2>
        </div>
        <button type="button" class="modal-close" @click="closeServerForm">×</button>
      </div>

      <form class="connection-form server-asset-form" @submit.prevent="saveServer">
        <div class="connection-form-row">
          <label><span class="field-label">Display name <span class="required-mark"
                aria-hidden="true">*</span></span><input v-model="serverForm.name" required maxlength="100"
              placeholder="Oracle PROD 01" /></label>
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
          <label><span class="field-label">Hostname <span class="required-mark" aria-hidden="true">*</span></span><input
              v-model="serverForm.hostname" required maxlength="255" placeholder="dbprod01" /></label>
          <label>IP address<input v-model="serverForm.ip_address" maxlength="64" placeholder="192.168.1.10" /></label>
        </div>

        <div class="connection-form-row server-asset-form__os-row">
  <label>Operating system
            <select v-model="serverForm.os_family">
              <option value="windows">Windows</option>
              <option value="linux">Linux</option>
              <option value="aix">AIX</option>
              <option value="unix">Unix</option>
              <option value="other">Other</option>
            </select>
          </label>
          <label>OS version<input v-model="serverForm.os_version" maxlength="128"
              placeholder="RHEL 9 / AIX 7.2 / Windows Server" /></label>
        </div>

        <div class="connection-form-row">
          <label>Environment<input v-model="serverForm.environment" maxlength="64" placeholder="Production" /></label>
          <label>Owner / team<input v-model="serverForm.owner" maxlength="128"
              placeholder="Database Administrator" /></label>
        </div>

        <label class="server-asset-form__half">
          SSH access profile (Optional)
          <select v-model="serverForm.ssh_profile_id">
            <option value="">No SSH access profile</option>
            <option v-for="profile in sshStore.profiles" :key="profile.id" :value="profile.id"
              :disabled="!profile.enabled">
              {{ profile.name }} · {{ profile.username }}@SSH:{{ profile.port }}
            </option>
          </select>
        </label>

        <label>Related database connections (Optional)
          <select v-model="serverForm.database_connection_ids" multiple size="6">
            <option v-for="connection in connectionsStore.connections" :key="connection.id" :value="connection.id">
              {{ connection.name }} · {{ connection.engine }} · {{ connection.host }}
            </option>
          </select>
        </label>

        <label>Tags<input v-model="serverForm.tags"
            placeholder="Separate tags by commas. e.g.: oracle, production, erp" /></label>
        <label>Notes<textarea v-model="serverForm.notes" rows="3" /></label>
        <label class="connection-checkbox"><input v-model="serverForm.enabled" type="checkbox" class="toggle-switch"/> Enable this server
          asset</label>

        <p v-if="serverFormError" class="login-error">{{ serverFormError }}</p>
        <div class="connection-form-actions">
          <button type="submit" class="primary-button" :disabled="serversStore.saving">{{ serversStore.saving ?
            'Saving...' : 'Save server' }}</button>
          <button type="button" class="secondary-button" @click="closeServerForm">Cancel</button>
        </div>
      </form>
    </section>
  </div>

  <div v-if="sshFormOpen" class="modal-backdrop" @click.self="closeSshForm">
    <section class="modal-panel infrastructure-modal" role="dialog" aria-modal="true"  style="--modal-width: 500px">
      <div class="modal-header">
        <div>
          <h2>{{ editingSshId ? 'Edit SSH access profile' : 'Add SSH access profile' }}</h2>
        </div>
        <button type="button" class="modal-close" @click="closeSshForm">×</button>
      </div>

      <form class="connection-form" @submit.prevent="saveSshProfile">
        <div class="connection-form-row">
          <label><span class="field-label">Profile name <span class="required-mark"
                aria-hidden="true">*</span></span><input v-model="sshForm.name" required maxlength="100"
              placeholder="Linux DBA Production" /></label>
          <label>Authentication
            <select v-model="sshForm.auth_type">
              <option value="password">Password</option>
              <option value="private_key">Private key</option>
            </select>
          </label>
        </div>

        <div class="connection-form-row">
          <label><span class="field-label">Username <span class="required-mark" aria-hidden="true">*</span></span><input
              v-model="sshForm.username" required maxlength="128" placeholder="oracle" /></label>
          <label><span class="field-label">Port <span class="required-mark" aria-hidden="true">*</span></span><input
              v-model.number="sshForm.port" type="number" min="1" max="65535" required /></label>
        </div>

        <label v-if="sshForm.auth_type === 'password'"><span class="field-label">Password <span v-if="!editingSshId"
              class="required-mark" aria-hidden="true">*</span></span>
          <input v-model="sshForm.password" type="password" maxlength="4096" :required="!editingSshId"
            autocomplete="new-password" />
          <small v-if="editingSshId">Leave blank to keep the stored password.</small>
        </label>

        <template v-else>
          <label><span class="field-label">Private key <span v-if="!editingSshId" class="required-mark"
                aria-hidden="true">*</span></span>
            <textarea v-model="sshForm.private_key" rows="8" :required="!editingSshId"
              placeholder="-----BEGIN OPENSSH PRIVATE KEY-----" />
            <small v-if="editingSshId">Leave blank to keep the stored private key.</small>
          </label>
          <label>Private-key passphrase (Optional)
            <input v-model="sshForm.passphrase" type="password" maxlength="4096" autocomplete="new-password" />
            <small v-if="editingSshId">Leave blank to keep the existing passphrase.</small>
          </label>
        </template>

        <label>Notes<textarea v-model="sshForm.notes" rows="3" maxlength="2000"
            placeholder="Scope / account owner / intended server group" /></label>
        <label class="connection-checkbox"><input v-model="sshForm.enabled" type="checkbox" class="toggle-switch"/> Enable this SSH access
          profile</label>

        <p v-if="sshFormError" class="login-error">{{ sshFormError }}</p>
        <div class="connection-form-actions">
          <button type="submit" class="primary-button" :disabled="sshStore.saving">{{ sshStore.saving ? 'Saving...' :
            'Save SSH profile' }}</button>
          <button type="button" class="secondary-button" @click="closeSshForm">Cancel</button>
        </div>
      </form>
    </section>
  </div>

  <div v-if="shortcutFormOpen" class="modal-backdrop" @click.self="closeShortcutForm">
    <section class="modal-panel infrastructure-modal" role="dialog" aria-modal="true"  style="--modal-width: 500px">
      <div class="modal-header">
        <div>
          <h2>{{ editingShortcutId ? 'Edit terminal shortcut' : 'Add terminal shortcut' }}</h2>
        </div>
        <button type="button" class="modal-close" @click="closeShortcutForm">×</button>
      </div>

      <form class="connection-form" @submit.prevent="saveShortcut">
        <div class="connection-form-row">
          <label><span class="field-label">Shortcut name <span class="required-mark"
                aria-hidden="true">*</span></span><input v-model="shortcutForm.name" required maxlength="80"
              placeholder="Open SQLPLUS as SYSDBA" /></label>
          <label><span class="field-label">Category <span class="required-mark" aria-hidden="true">*</span></span><input
              v-model="shortcutForm.category" required placeholder="Oracle" /></label>
        </div>

        <label><span class="field-label">Command <span class="required-mark" aria-hidden="true">*</span></span>
          <textarea v-model="shortcutForm.command" rows="4" required placeholder="sqlplus / as sysdba" />
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

          <div class="terminal-shortcut-scope__modes">
            <label class="connection-checkbox">
              <input type="radio" name="terminal-shortcut-scope" value="all" :checked="shortcutForm.scope === 'all'"
                @change="setShortcutScope('all')" />
              All SSH-enabled servers
            </label>
            <label class="connection-checkbox">
              <input type="radio" name="terminal-shortcut-scope" value="selected"
                :checked="shortcutForm.scope === 'selected'" @change="setShortcutScope('selected')" />
              Only selected servers
            </label>
          </div>

          <div v-if="shortcutForm.scope === 'selected'" class="terminal-shortcut-server-picker">
            <div class="terminal-shortcut-server-picker__toolbar">
              <input v-model="shortcutServerFilter" type="search"
                placeholder="Search server, hostname, environment or SSH profile..." />
              <span>{{ shortcutForm.server_ids.length }} selected</span>
              <button v-if="shortcutForm.server_ids.length" type="button" class="secondary-button"
                @click="clearShortcutServers">
                Clear
              </button>
            </div>

            <div class="terminal-shortcut-server-picker__list">
              <label v-for="item in shortcutServerOptions" :key="item.id" class="terminal-shortcut-server-option">
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

        <label class="connection-checkbox"><input v-model="shortcutForm.enabled" type="checkbox" class="toggle-switch"/> Enable this terminal
          shortcut</label>
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
<style>
.server-asset-form .connection-form-row {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.server-asset-form .connection-form-row > label,
.server-asset-form input,
.server-asset-form select,
.server-asset-form textarea {
  min-width: 0;
}

.server-asset-form input,
.server-asset-form select,
.server-asset-form textarea {
  width: 100%;
  max-width: none;
  box-sizing: border-box;
}

.server-asset-form .server-asset-form__os-row {
  grid-template-columns: 19.5rem minmax(0, 1fr);
}

.server-asset-form__half {
  width: calc(50% - 0.375rem);
}
</style>
