<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import ScrollableDataTable from '@/components/common/ScrollableDataTable.vue'
import FloatingActionMenu from '@/components/common/FloatingActionMenu.vue'
import { engineLabel } from '@/core/databasePresentation'
import { hasPermission } from '@/core/permissions'
import { useAuthStore } from '@/stores/auth'
import {
  useConnectionsStore,
  type DatabaseEngine,
} from '@/stores/connections'
import {
  useRecordsStore,
  type DbaRecord,
  type DbaRecordInput,
  type RecordStatus,
  type RecordType,
} from '@/stores/records'
import { useServersStore } from '@/stores/servers'
import { confirmDialog, showToast } from '@/ui/feedback'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()
const recordsStore = useRecordsStore()
const connectionsStore = useConnectionsStore()
const serversStore = useServersStore()

const query = ref('')
const typeFilter = ref<RecordType | ''>('')
const engineFilter = ref<DatabaseEngine | ''>('')
const environmentFilter = ref('')
const statusFilter = ref<RecordStatus | ''>('')
const sortBy = ref<'updated' | 'name' | 'environment'>('updated')

const formOpen = ref(false)
const editingId = ref<string | null>(null)
const formError = ref<string | null>(null)

interface RecordForm {
  name: string
  record_type: RecordType
  status: RecordStatus
  engine: DatabaseEngine | ''
  hostname: string
  ip_address: string
  port: number | null
  environment: string
  version: string
  username: string
  password: string
  application: string
  owner: string
  url: string
  notes: string
  tags: string
  custom_fields: string
  connection_id: string
  server_id: string
}

function emptyForm(): RecordForm {
  return {
    name: '',
    record_type: 'database',
    status: 'active',
    engine: '',
    hostname: '',
    ip_address: '',
    port: null,
    environment: '',
    version: '',
    username: '',
    password: '',
    application: '',
    owner: '',
    url: '',
    notes: '',
    tags: '',
    custom_fields: '',
    connection_id: '',
    server_id: '',
  }
}

const form = reactive<RecordForm>(emptyForm())
const canManage = computed(() => hasPermission(authStore.user, 'records:manage'))

const recordTypeOptions: Array<{ value: RecordType; label: string }> = [
  { value: 'database', label: 'Database' },
  { value: 'server', label: 'Server' },
  { value: 'application', label: 'Application' },
  { value: 'credential', label: 'Credential / account' },
  { value: 'url', label: 'URL / web resource' },
  { value: 'other', label: 'Other' },
]

const statusOptions: Array<{ value: RecordStatus; label: string }> = [
  { value: 'active', label: 'Active' },
  { value: 'standby', label: 'Standby' },
  { value: 'disabled', label: 'Disabled' },
  { value: 'retired', label: 'Retired' },
  { value: 'unknown', label: 'Unknown' },
]

function typeLabel(type: RecordType) {
  return recordTypeOptions.find((item) => item.value === type)?.label ?? type
}

function statusLabel(status: RecordStatus) {
  return statusOptions.find((item) => item.value === status)?.label ?? status
}

function isSafeWebUrl(value: string | null) {
  return Boolean(value && /^https?:\/\//i.test(value))
}

const environments = computed(() =>
  Array.from(
    new Set(
      recordsStore.records
        .map((record) => record.environment)
        .filter((value): value is string => Boolean(value)),
    ),
  ).sort((a, b) => a.localeCompare(b)),
)

const filteredRecords = computed(() => {
  const q = query.value.trim().toLowerCase()
  const result = recordsStore.records.filter((record) => {
    if (typeFilter.value && record.record_type !== typeFilter.value) return false
    if (engineFilter.value && record.engine !== engineFilter.value) return false
    if (environmentFilter.value && record.environment !== environmentFilter.value) return false
    if (statusFilter.value && record.status !== statusFilter.value) return false

    if (!q) return true

    return [
      record.name,
      record.record_type,
      record.status,
      record.engine,
      record.hostname,
      record.ip_address,
      record.port,
      record.environment,
      record.version,
      record.username,
      record.application,
      record.owner,
      record.url,
      record.notes,
      record.connection_name,
      record.server_name,
      ...record.tags,
      ...record.custom_fields.flatMap((item) => [item.key, item.value]),
    ]
      .filter((value) => value != null)
      .some((value) => String(value).toLowerCase().includes(q))
  })

  return [...result].sort((a, b) => {
    if (sortBy.value === 'name') return a.name.localeCompare(b.name)
    if (sortBy.value === 'environment') {
      return (a.environment ?? '').localeCompare(b.environment ?? '')
        || a.name.localeCompare(b.name)
    }
    return new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime()
  })
})

const databaseCount = computed(() =>
  recordsStore.records.filter((record) => record.record_type === 'database').length,
)
const linkedCount = computed(() =>
  recordsStore.records.filter((record) => record.connection_id || record.server_id).length,
)
const environmentCount = computed(() => environments.value.length)

function resetForm() {
  Object.assign(form, emptyForm())
  editingId.value = null
  formError.value = null
}

function openAdd() {
  resetForm()
  formOpen.value = true
}

function customFieldsToText(record: DbaRecord) {
  return record.custom_fields
    .map((item) => `${item.key}=${item.value}`)
    .join('\n')
}

function editRecord(record: DbaRecord) {
  editingId.value = record.id
  formError.value = null
  Object.assign(form, {
    name: record.name,
    record_type: record.record_type,
    status: record.status,
    engine: record.engine ?? '',
    hostname: record.hostname ?? '',
    ip_address: record.ip_address ?? '',
    port: record.port,
    environment: record.environment ?? '',
    version: record.version ?? '',
    username: record.username ?? '',
    password: '',
    application: record.application ?? '',
    owner: record.owner ?? '',
    url: record.url ?? '',
    notes: record.notes ?? '',
    tags: record.tags.join(', '),
    custom_fields: customFieldsToText(record),
    connection_id: record.connection_id ?? '',
    server_id: record.server_id ?? '',
  })
  formOpen.value = true
}

function closeForm() {
  formOpen.value = false
  resetForm()
  if (route.query.edit) {
    const nextQuery = { ...route.query }
    delete nextQuery.edit
    void router.replace({ path: '/records', query: nextQuery })
  }
}

function parseCustomFields(value: string) {
  return value
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => {
      const separator = line.indexOf('=')
      if (separator === -1) {
        return { key: line, value: '' }
      }
      return {
        key: line.slice(0, separator).trim(),
        value: line.slice(separator + 1).trim(),
      }
    })
}

function buildPayload(): DbaRecordInput {
  const payload: DbaRecordInput = {
    name: form.name.trim(),
    record_type: form.record_type,
    status: form.status,
    engine: form.record_type === 'database' && form.engine
      ? form.engine
      : null,
    hostname: form.hostname.trim() || null,
    ip_address: form.ip_address.trim() || null,
    port: form.port ? Number(form.port) : null,
    environment: form.environment.trim() || null,
    version: form.version.trim() || null,
    username: form.username.trim() || null,
    application: form.application.trim() || null,
    owner: form.owner.trim() || null,
    url: form.url.trim() || null,
    notes: form.notes.trim() || null,
    tags: form.tags.split(',').map((tag) => tag.trim()).filter(Boolean),
    custom_fields: parseCustomFields(form.custom_fields),
    connection_id: form.connection_id || null,
    server_id: form.server_id || null,
  }
  if (form.password) payload.password = form.password
  return payload
}

async function saveRecord() {
  formError.value = null
  try {
    const payload = buildPayload()
    const updated = Boolean(editingId.value)
    if (editingId.value) {
      await recordsStore.update(editingId.value, payload)
    } else {
      await recordsStore.create(payload)
    }
    const name = payload.name
    closeForm()
    showToast({ title: updated ? 'Record updated' : 'Record created', message: name, tone: 'success' })
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Unable to save record.'
    formError.value = message
    showToast({ title: 'Unable to save record', message, tone: 'danger' })
  }
}

async function removeRecord(record: DbaRecord) {
  const confirmed = await confirmDialog({
    title: 'Delete record',
    message: `Delete ${record.name}? Linked Connections and Servers will not be deleted.`,
    confirmLabel: 'Delete record',
    destructive: true,
    tone: 'danger',
  })
  if (!confirmed) return
  try {
    await recordsStore.remove(record.id)
    showToast({ title: 'Record deleted', message: record.name, tone: 'success' })
  } catch (error) {
    showToast({ title: 'Unable to delete record', message: error instanceof Error ? error.message : undefined, tone: 'danger' })
  }
}

function applyConnectionDetails() {
  if (!form.connection_id) return
  const connection = connectionsStore.connections.find(
    (item) => item.id === form.connection_id,
  )
  if (!connection) return

  if (!form.name) form.name = connection.name
  if (form.record_type === 'database') form.engine = connection.engine
  if (!form.hostname) form.hostname = connection.host
  if (!form.port) form.port = connection.port
  if (!form.username) form.username = connection.username
  if (!form.server_id && connection.server_ids.length === 1) {
    form.server_id = connection.server_ids[0] ?? ''
    applyServerDetails()
  }
}

function applyServerDetails() {
  if (!form.server_id) return
  const server = serversStore.servers.find((item) => item.id === form.server_id)
  if (!server) return

  if (!form.hostname) form.hostname = server.hostname
  if (!form.ip_address) form.ip_address = server.ip_address ?? ''
  if (!form.environment) form.environment = server.environment ?? ''
  if (!form.owner) form.owner = server.owner ?? ''
  if (!form.version) form.version = server.os_version ?? ''
}

function clearFilters() {
  query.value = ''
  typeFilter.value = ''
  engineFilter.value = ''
  environmentFilter.value = ''
  statusFilter.value = ''
  sortBy.value = 'updated'
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(new Date(value))
}

async function openEditFromRoute() {
  const editId = typeof route.query.edit === 'string' ? route.query.edit : ''
  if (!editId || !canManage.value) return
  let record = recordsStore.byId(editId)
  if (!record) {
    try {
      record = await recordsStore.loadOne(editId)
    } catch {
      return
    }
  }
  editRecord(record)
}

watch(
  () => route.query.edit,
  () => void openEditFromRoute(),
)

onMounted(async () => {
  const requestedType = String(route.query.type ?? '')
  if (recordTypeOptions.some((item) => item.value === requestedType)) {
    typeFilter.value = requestedType as RecordType
  }
  const requestedEngine = String(route.query.engine ?? '')
  if (['oracle', 'sqlserver', 'mysql'].includes(requestedEngine)) {
    engineFilter.value = requestedEngine as DatabaseEngine
  }

  await Promise.all([
    recordsStore.load(),
    connectionsStore.load(),
    serversStore.load(),
  ])
  await openEditFromRoute()
})

</script>

<template>
  <section class="page-header records-page-header">
    <div>
    </div>
    <button v-if="canManage" type="button" class="primary-button" @click="openAdd">
      Add record
    </button>
  </section>

  <section class="records-summary-grid">
    <article class="panel records-summary-card">
      <span>Total records</span>
      <strong>{{ recordsStore.records.length }}</strong>
    </article>
    <article class="panel records-summary-card">
      <span>Database records</span>
      <strong>{{ databaseCount }}</strong>
    </article>
    <article class="panel records-summary-card">
      <span>Environments</span>
      <strong>{{ environmentCount }}</strong>
    </article>
    <article class="panel records-summary-card">
      <span>Linked records</span>
      <strong>{{ linkedCount }}</strong>
    </article>
  </section>

  <section class="panel records-workspace">
    <div class="section-toolbar records-workspace-heading">
      <div>
        <h2>Operational catalog</h2>
      </div>
      <span class="records-result-count">{{ filteredRecords.length }} shown</span>
    </div>

    <div class="records-engine-quickfilter" aria-label="Quick record filters">
      <button
        type="button"
        :class="{ active: !typeFilter && !engineFilter }"
        @click="typeFilter = ''; engineFilter = ''"
      >
        All records
      </button>
      <button
        type="button"
        :class="{ active: typeFilter === 'database' && !engineFilter }"
        @click="typeFilter = 'database'; engineFilter = ''"
      >
        All databases
      </button>
      <button
        type="button"
        :class="{ active: typeFilter === 'database' && engineFilter === 'oracle' }"
        @click="typeFilter = 'database'; engineFilter = 'oracle'"
      >
        Oracle
      </button>
      <button
        type="button"
        :class="{ active: typeFilter === 'database' && engineFilter === 'sqlserver' }"
        @click="typeFilter = 'database'; engineFilter = 'sqlserver'"
      >
        SQL Server
      </button>
      <button
        type="button"
        :class="{ active: typeFilter === 'database' && engineFilter === 'mysql' }"
        @click="typeFilter = 'database'; engineFilter = 'mysql'"
      >
        MySQL / MariaDB
      </button>
    </div>

    <div class="records-filter-grid">
      <input
        v-model="query"
        type="search"
        placeholder="Search names, hosts, applications, owners, notes, tags and custom fields."
        aria-label="Search Records"
      />

      <select v-model="typeFilter" aria-label="Filter by record type">
        <option value="">All types</option>
        <option v-for="option in recordTypeOptions" :key="option.value" :value="option.value">
          {{ option.label }}
        </option>
      </select>

      <select v-model="engineFilter" aria-label="Filter by database engine">
        <option value="">All engines</option>
        <option value="oracle">Oracle</option>
        <option value="sqlserver">SQL Server</option>
        <option value="mysql">MySQL / MariaDB</option>
      </select>

      <select v-model="environmentFilter" aria-label="Filter by environment">
        <option value="">All environments</option>
        <option v-for="environment in environments" :key="environment" :value="environment">
          {{ environment }}
        </option>
      </select>

      <select v-model="statusFilter" aria-label="Filter by status">
        <option value="">All statuses</option>
        <option v-for="option in statusOptions" :key="option.value" :value="option.value">
          {{ option.label }}
        </option>
      </select>

      <select v-model="sortBy" aria-label="Sort records">
        <option value="updated">Recently updated</option>
        <option value="name">Name</option>
        <option value="environment">Environment</option>
      </select>

      <button type="button" class="secondary-button" @click="clearFilters">Clear</button>
    </div>

    <div v-if="recordsStore.error" class="login-error records-load-error">
      {{ recordsStore.error }}
    </div>

    <ScrollableDataTable
      :loading="recordsStore.loading"
      :empty="!recordsStore.loading && filteredRecords.length === 0"
      empty-message="No Records match the current filters."
      max-height="42rem"
    >
      <template #header>
        <tr>
          <th>Record</th>
          <th>Type</th>
          <th>Environment</th>
          <th>Endpoint / resource</th>
          <th>Application / owner</th>
          <th>Status</th>
          <th>Updated</th>
          <th class="user-actions-column">Actions</th>
        </tr>
      </template>

      <tr v-for="record in filteredRecords" :key="record.id" class="records-table-row">
        <td>
          <RouterLink :to="`/records/${record.id}`" class="records-record-name">
            {{ record.name }}
          </RouterLink>
          <div class="records-table-subline">
            <span v-if="record.engine">{{ engineLabel(record.engine) }}</span>
            <span v-if="record.version">{{ record.version }}</span>
          </div>
          <div v-if="record.tags.length" class="records-inline-tags">
            <span v-for="tag in record.tags.slice(0, 3)" :key="tag">{{ tag }}</span>
            <span v-if="record.tags.length > 3">+{{ record.tags.length - 3 }}</span>
          </div>
        </td>
        <td>{{ typeLabel(record.record_type) }}</td>
        <td>{{ record.environment ?? '—' }}</td>
        <td>
          <div class="records-endpoint-cell">
            <span v-if="record.hostname">
              {{ record.hostname }}<template v-if="record.port">:{{ record.port }}</template>
            </span>
            <span v-else-if="record.ip_address">
              {{ record.ip_address }}<template v-if="record.port">:{{ record.port }}</template>
            </span>
            <a v-else-if="record.url && isSafeWebUrl(record.url)" :href="record.url" target="_blank" rel="noopener noreferrer">
              {{ record.url }}
            </a>
            <span v-else-if="record.url">{{ record.url }}</span>
            <span v-else>—</span>
            <small v-if="record.connection_name">Connection: {{ record.connection_name }}</small>
            <small v-if="record.server_name">Server: {{ record.server_name }}</small>
          </div>
        </td>
        <td>
          <div class="records-owner-cell">
            <span>{{ record.application ?? '—' }}</span>
            <small v-if="record.owner">{{ record.owner }}</small>
          </div>
        </td>
        <td>
          <span class="record-status-pill" :class="`record-status-pill--${record.status}`">
            {{ statusLabel(record.status) }}
          </span>
        </td>
        <td class="records-updated-cell">{{ formatDate(record.updated_at) }}</td>
        <td class="user-actions-cell">
          <FloatingActionMenu :label="`Actions for ${record.name}`">
            <button type="button" role="menuitem" @click="router.push(`/records/${record.id}`)">
              <FontAwesomeIcon icon="arrow-up-right-from-square" />
              Open
            </button>
            <button v-if="canManage" type="button" role="menuitem" @click="editRecord(record)">
              <FontAwesomeIcon icon="pen" />
              Edit
            </button>
            <div v-if="canManage" class="user-action-divider" />
            <button v-if="canManage" type="button" role="menuitem" class="danger-menu-item" @click="removeRecord(record)">
              <FontAwesomeIcon icon="trash-can" />
              Delete
            </button>
          </FloatingActionMenu>
        </td>
      </tr>
    </ScrollableDataTable>
  </section>

  <div v-if="formOpen" class="modal-backdrop" @click.self="closeForm">
    <section class="modal-panel records-modal" role="dialog" aria-modal="true">
      <div class="modal-header">
        <div>
          <h2>{{ editingId ? 'Edit record' : 'Add record' }}</h2>
        </div>
        <button type="button" class="modal-close" aria-label="Close" @click="closeForm">×</button>
      </div>

      <form class="connection-form records-form" @submit.prevent="saveRecord">
        <div class="records-form-grid records-form-grid--identity">
          <label>
            <span class="field-label">Name <span class="required-mark" aria-hidden="true">*</span></span>
            <input v-model="form.name" required maxlength="160" placeholder="DBPRD" />
          </label>

          <label>
            <span class="field-label">Type <span class="required-mark" aria-hidden="true">*</span></span>
            <select v-model="form.record_type" required>
              <option v-for="option in recordTypeOptions" :key="option.value" :value="option.value">
                {{ option.label }}
              </option>
            </select>
          </label>

          <label>
            <span class="field-label">Status <span class="required-mark" aria-hidden="true">*</span></span>
            <select v-model="form.status" required>
              <option v-for="option in statusOptions" :key="option.value" :value="option.value">
                {{ option.label }}
              </option>
            </select>
          </label>

          <label v-if="form.record_type === 'database'">
            <span>Database engine</span>
            <select v-model="form.engine">
              <option value="">Not specified</option>
              <option value="oracle">Oracle</option>
              <option value="sqlserver">SQL Server</option>
              <option value="mysql">MySQL / MariaDB</option>
            </select>
          </label>
        </div>

        <div class="records-form-section">
          <div>
            <h3>Link existing DBAChum objects (Optional)</h3>
          </div>
          <div class="records-form-grid">
            <label>
              <span>Database connection</span>
              <select v-model="form.connection_id" @change="applyConnectionDetails">
                <option value="">None</option>
                <option v-for="connection in connectionsStore.connections" :key="connection.id" :value="connection.id">
                  {{ connection.name }} · {{ engineLabel(connection.engine) }} · {{ connection.host }}:{{ connection.port }}
                </option>
              </select>
            </label>

            <label>
              <span>Server</span>
              <select v-model="form.server_id" @change="applyServerDetails">
                <option value="">None</option>
                <option v-for="server in serversStore.servers" :key="server.id" :value="server.id">
                  {{ server.name }} · {{ server.hostname }}
                </option>
              </select>
            </label>
          </div>
        </div>

        <div class="records-form-section">
          <div>
            <h3>Infrastructure & ownership</h3>
          </div>
          <div class="records-form-grid records-form-grid--three">
            <label>
              <span>Hostname</span>
              <input v-model="form.hostname" maxlength="255" placeholder="oradbprd01" />
            </label>
            <label>
              <span>IP address</span>
              <input v-model="form.ip_address" maxlength="64" placeholder="10.20.1.15" />
            </label>
            <label>
              <span>Port</span>
              <input v-model.number="form.port" type="number" min="1" max="65535" placeholder="1521" />
            </label>
            <label>
              <span>Environment</span>
              <input v-model="form.environment" maxlength="80" placeholder="Production" />
            </label>
            <label>
              <span>Version</span>
              <input v-model="form.version" maxlength="160" placeholder="Oracle 19c / RHEL 9 / v2.4" />
            </label>
            <label>
              <span>Application / system</span>
              <input v-model="form.application" maxlength="160" placeholder="Finance" />
            </label>
            <label>
              <span>Owner / team</span>
              <input v-model="form.owner" maxlength="160" placeholder="Finance Systems" />
            </label>
            <label class="records-form-span-two">
              <span>URL</span>
              <input v-model="form.url" type="url" maxlength="1000" placeholder="https://..." />
            </label>
          </div>
        </div>

        <div class="records-form-section">
          <div>
            <h3>Lookup credential (Optional)</h3>
          </div>
          <div class="records-form-grid">
            <label>
              <span>Username</span>
              <input v-model="form.username" maxlength="160" autocomplete="off" />
            </label>
            <label>
              <span>Password <small v-if="editingId">leave blank to keep existing</small></span>
              <input v-model="form.password" type="password" maxlength="512" autocomplete="new-password" />
            </label>
          </div>
        </div>

        <div class="records-form-section">
          <div>
            <h3>Notes & custom data</h3>
          </div>
          <label>
            <span>Tags  </span>
            <input v-model="form.tags" placeholder="finance, critical, monthly-close" />
          </label>
          <label>
            <span>Notes</span>
            <textarea v-model="form.notes" rows="5" maxlength="5000" placeholder="Operational notes, escalation context, maintenance notes..." />
          </label>
          <label>
            <span>Custom fields <small>one KEY=VALUE per line</small></span>
            <textarea v-model="form.custom_fields" rows="5" placeholder="DBID=123456789\nSupport Group=DBA\nPatch Window=Sunday 01:00" />
          </label>
        </div>

        <div v-if="formError" class="login-error">{{ formError }}</div>

        <div class="connection-form-actions records-form-actions">
          <button type="button" class="secondary-button" @click="closeForm">Cancel</button>
          <button type="submit" class="primary-button" :disabled="recordsStore.saving">
            {{ recordsStore.saving ? 'Saving...' : editingId ? 'Save changes' : 'Create record' }}
          </button>
        </div>
      </form>
    </section>
  </div>
</template>
