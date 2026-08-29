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

const serversStore = useServersStore()
const sshStore = useSshAccessStore()
const connectionsStore = useConnectionsStore()

const activeTab = ref<'servers' | 'ssh'>('servers')
const serverFormOpen = ref(false)
const sshFormOpen = ref(false)
const editingServerId = ref<string | null>(null)
const editingSshId = ref<string | null>(null)
const serverFormError = ref<string | null>(null)
const sshFormError = ref<string | null>(null)
const serverFilter = ref('')
const sshFilter = ref('')

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

const serverForm = reactive<ServerForm>(emptyServerForm())
const sshForm = reactive<SshForm>(emptySshForm())

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

    <template v-else>
      <div class="section-toolbar">
        <div>
          <h3>SSH access profiles</h3>
          <p>Reusable encrypted authentication profiles. Passwords and private keys are never returned to the browser after saving.</p>
        </div>
        <button class="primary-button" type="button" @click="openAddSshProfile">Add SSH profile</button>
      </div>

      <div class="notice-card">
        These profiles are the credential foundation for Phase 5C SSH monitoring and the built-in terminal. Saving a profile does not open an SSH connection yet.
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
</template>
