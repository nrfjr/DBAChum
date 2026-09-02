<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useServersStore } from '@/stores/servers'

import {
  useAuthStore,
} from '@/stores/auth'

import {
  hasPermission,
} from '@/core/permissions'

import {
  useConnectionsStore,
  type DatabaseConnection,
  type DatabaseConnectionInput,
  type DatabaseEngine,
  type OracleAuthMode,
  type SqlServerEncrypt,
  type SqlServerProvider,
} from '@/stores/connections'

const connectionsStore = useConnectionsStore()

const editingId = ref<string | null>(null)
const formError = ref<string | null>(null)

const testingId = ref<string | null>(null)

const formOpen = ref(false)

const serversStore = useServersStore()

const authStore = useAuthStore()


const canTestConnections = computed(
  () =>
    hasPermission(
      authStore.user?.role,
      'connections:test',
    ),
)


const canManageConnections = computed(
  () =>
    hasPermission(
      authStore.user?.role,
      'connections:manage',
    ),
)

const testResults = reactive<
  Record<
    string,
    {
      success: boolean
      message: string
    }
  >
>({})

interface ConnectionForm {
  name: string
  engine: DatabaseEngine
  host: string
  port: number
  username: string
  password: string
  database: string
  oracle_identifier_type: 'service_name' | 'sid'
  oracle_identifier: string
  oracle_auth_mode: OracleAuthMode
  sqlserver_provider: SqlServerProvider
  sqlserver_driver: string
  sqlserver_encrypt: SqlServerEncrypt
  active: boolean
  monitor_enabled: boolean
  server_ids: string[]
}

function emptyForm(): ConnectionForm {
  return {
    name: '',
    engine: 'oracle',
    host: '',
    port: 1521,
    username: '',
    password: '',
    database: '',
    oracle_identifier_type: 'service_name',
    oracle_identifier: '',
    oracle_auth_mode: 'normal',
    sqlserver_provider: 'auto',
    sqlserver_driver: '',
    sqlserver_encrypt: 'auto',
    active: true,
    monitor_enabled: true,
    server_ids: [],
  }
}

const form = reactive<ConnectionForm>(emptyForm())

const isEditing = computed(() => editingId.value !== null)

function resetForm() {
  Object.assign(form, emptyForm())
  editingId.value = null
  formError.value = null
}

function openAddConnection() {
  resetForm()
  formOpen.value = true
}

function closeForm() {
  formOpen.value = false
  resetForm()
}

function changeEngine() {
  const ports: Record<DatabaseEngine, number> = {
    oracle: 1521,
    sqlserver: 1433,
    mysql: 3306,
  }

  form.port = ports[form.engine]

  if (form.engine === 'oracle') {
    form.database = ''
    form.oracle_auth_mode = 'normal'
  } else {
    form.oracle_identifier_type = 'service_name'
    form.oracle_identifier = ''
    form.oracle_auth_mode = 'normal'
  }
}

function editConnection(connection: DatabaseConnection) {
  editingId.value = connection.id
  formError.value = null

  Object.assign(form, {
    name: connection.name,
    engine: connection.engine,
    host: connection.host,
    port: connection.port,
    username: connection.username,
    password: '',
    database: connection.database ?? '',
    oracle_identifier_type:
      connection.oracle_identifier_type ?? 'service_name',
    oracle_identifier:
      connection.oracle_identifier ?? '',
    oracle_auth_mode:
      connection.oracle_auth_mode ?? 'normal',
    sqlserver_provider:
      connection.sqlserver_provider ?? 'auto',
    sqlserver_driver:
      connection.sqlserver_driver ?? '',
    sqlserver_encrypt:
      connection.sqlserver_encrypt ?? 'auto',
    active: connection.active,
    monitor_enabled: connection.monitor_enabled,
    server_ids: [...(connection.server_ids ?? []),],
  })

  formOpen.value = true
}

function buildPayload(): DatabaseConnectionInput {
  return {
    name: form.name.trim(),
    engine: form.engine,
    host: form.host.trim(),
    port: Number(form.port),
    username: form.username.trim(),
    password: form.password || undefined,
    database:
      form.engine === 'oracle'
        ? null
        : form.database.trim() || null,
    oracle_identifier_type:
      form.engine === 'oracle'
        ? form.oracle_identifier_type
        : null,
    oracle_identifier:
      form.engine === 'oracle'
        ? form.oracle_identifier.trim() || null
        : null,
    oracle_auth_mode:
      form.engine === 'oracle'
        ? form.oracle_auth_mode
        : null,
    sqlserver_provider:
      form.engine === 'sqlserver'
        ? form.sqlserver_provider
        : null,
    sqlserver_driver:
      form.engine === 'sqlserver'
        ? form.sqlserver_driver.trim() || null
        : null,
    sqlserver_encrypt:
      form.engine === 'sqlserver'
        ? form.sqlserver_encrypt
        : null,
    active: form.active,
    monitor_enabled: form.monitor_enabled,
    server_ids: [...form.server_ids],
  }
}

async function saveConnection() {
  formError.value = null

  if (!isEditing.value && !form.password) {
    formError.value =
      'Password is required for a new connection.'
    return
  }

  if (editingId.value && !form.password) {
    const existing = connectionsStore.connections.find(
      (connection) => connection.id === editingId.value,
    )

    if (
      existing
      && existing.username !== form.username.trim()
    ) {
      formError.value =
        'Password is required when changing the connection username.'
      return
    }
  }

  try {
    const payload = buildPayload()

    if (editingId.value) {
      await connectionsStore.update(
        editingId.value,
        payload,
      )
    } else {
      await connectionsStore.create(payload)
    }

    closeForm()
  } catch (error) {
    formError.value =
      error instanceof Error
        ? error.message
        : 'Unable to save database connection.'
  }
}

async function removeConnection(
  connection: DatabaseConnection,
) {
  const confirmed = window.confirm(
    `Delete "${connection.name}"?`,
  )

  if (!confirmed) {
    return
  }

  try {
    await connectionsStore.remove(connection.id)

    if (editingId.value === connection.id) {
      resetForm()
    }
  } catch (error) {
    formError.value =
      error instanceof Error
        ? error.message
        : 'Unable to delete database connection.'
  }
}

async function testConnection(
  connection: DatabaseConnection,
) {
  testingId.value = connection.id

  delete testResults[connection.id]

  try {
    const result =
      await connectionsStore.test(connection.id)

    const details = [
      result.database_name,
      result.database_version,
      result.sqlserver_generation,
      result.sqlserver_provider
        ? `provider: ${result.sqlserver_provider}`
        : null,
      result.sqlserver_driver,
      result.oracle_auth_mode === 'sysdba'
        ? 'SYSDBA'
        : null,
    ]
      .filter(Boolean)
      .join(' · ')

    testResults[connection.id] = {
      success: true,
      message: details
        ? `${result.message} ${details}`
        : result.message,
    }
  } catch (error) {
    testResults[connection.id] = {
      success: false,
      message:
        error instanceof Error
          ? error.message
          : 'Connection test failed.',
    }
  } finally {
    testingId.value = null
  }
}

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

onMounted(() => {
  connectionsStore.load()
  serversStore.load()
})
</script>

<template>
  <div class="settings-connections">
    <section class="panel">
      <div class="panel-header">
        <div>
          <h2>Database connections</h2>
          <p>
            Configure the database targets available to DBAChum.
          </p>
        </div>

        <button type="button" class="primary-button" @click="openAddConnection">
          Add connection
        </button>
      </div>

      <p v-if="connectionsStore.loading" class="empty-state">
        Loading connections...
      </p>

      <p v-else-if="connectionsStore.error" class="login-error">
        {{ connectionsStore.error }}
      </p>

      <div v-else-if="
        connectionsStore.connections.length === 0
      " class="empty-state">
        No database connections have been added yet.
      </div>

      <div v-else class="connection-list">
        <article v-for="connection in connectionsStore.connections" :key="connection.id" class="connection-item">
          <div>
            <div class="connection-title">
              <strong>{{ connection.name }}</strong>

              <span class="status-pill" :class="{
                disabled: !connection.active,
              }">
                {{ connection.active ? 'Enabled' : 'Disabled' }}
              </span>

              <span class="status-pill" :class="{
                disabled: !connection.monitor_enabled,
              }">
                {{ connection.monitor_enabled ? 'Monitored' : 'Not monitored' }}
              </span>
            </div>

            <p>
              {{ engineLabel(connection.engine) }}
              ·
              {{ connection.host }}:{{ connection.port }}
            </p>

            <small>
              {{ connection.username }}
              <template
                v-if="connection.engine === 'oracle' && connection.oracle_auth_mode === 'sysdba'"
              >
                · SYSDBA
              </template>
            </small>
            <p v-if="testResults[connection.id]" class="connection-test-result" :class="{
              success:
                testResults[connection.id]?.success,
              error:
                !testResults[connection.id]?.success,
            }">
              {{ testResults[connection.id]?.message }}
            </p>
          </div>

          <div class="connection-actions">
            <button v-if="canTestConnections" type="button" class="secondary-button"
              @click="testConnection(connection)">
              Test
            </button>
            <button v-if="canManageConnections" type="button" class="secondary-button" @click="editConnection(connection)">
              Edit
            </button>

            <button v-if="canManageConnections" type="button" class="secondary-button" @click="removeConnection(connection)">
              Delete
            </button>
          </div>
        </article>
      </div>
    </section>

    <div v-if="formOpen" class="modal-backdrop" @click.self="closeForm">
      <section class="modal-panel" role="dialog" aria-modal="true" :aria-label="isEditing
        ? 'Edit database connection'
        : 'Add database connection'
        ">
        <div class="modal-header">
          <div>
            <h2>
              {{
                isEditing
                  ? 'Edit connection'
                  : 'Add connection'
              }}
            </h2>

            <p>
              Connection credentials are stored encrypted.
            </p>
          </div>

          <button type="button" class="modal-close" aria-label="Close" @click="closeForm">
            ×
          </button>
        </div>

        <form class="connection-form" @submit.prevent="saveConnection">
          <label>
            Connection name

            <input v-model="form.name" required maxlength="100" placeholder="ERP Production" />
          </label>

          <label>
            Database engine

            <select v-model="form.engine" @change="changeEngine">
              <option value="oracle">Oracle</option>
              <option value="sqlserver">
                SQL Server
              </option>
              <option value="mysql">MySQL</option>
            </select>
          </label>

          <div class="connection-form-row">
            <label>
              Host

              <input v-model="form.host" required placeholder="db01.example.local" />
            </label>

            <label>
              Port

              <input v-model.number="form.port" required type="number" min="1" max="65535" />
            </label>
          </div>

          <template v-if="form.engine === 'oracle'">
            <label>
              Oracle identifier type

              <select v-model="form.oracle_identifier_type">
                <option value="service_name">
                  Service name
                </option>
                <option value="sid">SID</option>
              </select>
            </label>

            <label>
              {{
                form.oracle_identifier_type ===
                  'service_name'
                  ? 'Service name'
                  : 'SID'
              }}

              <input v-model="form.oracle_identifier" required placeholder="ORCLPDB1" />
            </label>

            <label>
              Oracle privilege mode

              <select v-model="form.oracle_auth_mode">
                <option value="normal">Normal</option>
                <option value="sysdba">SYSDBA</option>
              </select>

              <small
                v-if="form.oracle_auth_mode === 'sysdba'"
                class="connection-danger-note"
              >
                SYSDBA grants unrestricted Oracle administrative access.
                Use it only for connections that require privileged DBA operations.
              </small>
            </label>
          </template>

          <label v-else>
            Database
            <span class="optional-label">
              Optional
            </span>

            <input v-model="form.database" placeholder="Database name" />
          </label>

          <template v-if="form.engine === 'sqlserver'">
            <label>
              SQL Server provider

              <select v-model="form.sqlserver_provider">
                <option value="auto">
                  Auto (modern first, legacy fallback)
                </option>
                <option value="mssql_python">
                  Microsoft mssql-python only
                </option>
                <option value="pyodbc">
                  Legacy ODBC / pyodbc
                </option>
              </select>

              <small>
                Use Auto normally. SQL Server 2000 can use the isolated legacy
                ODBC path when the modern provider cannot negotiate with it.
              </small>
            </label>

            <label v-if="form.sqlserver_provider !== 'mssql_python'">
              ODBC driver
              <span class="optional-label">Optional</span>

              <input
                v-model="form.sqlserver_driver"
                placeholder="SQL Server or SQL Server Native Client 10.0"
              />

              <small>
                Leave blank to let DBAChum inspect installed SQL Server ODBC
                drivers. Set this explicitly for a known legacy driver.
              </small>
            </label>

            <label>
              Encryption negotiation

              <select v-model="form.sqlserver_encrypt">
                <option value="auto">Auto (encrypted first)</option>
                <option value="yes">Require encryption</option>
                <option value="no">Disable encryption for legacy server</option>
              </select>

              <small v-if="form.sqlserver_encrypt === 'no'" class="connection-danger-note">
                Use unencrypted transport only for legacy SQL Server endpoints
                on a trusted internal network.
              </small>
            </label>
          </template>
          <label>
            Servers
            <span class="optional-label">
              Optional
            </span>

            <select v-model="form.server_ids" multiple size="4">
              <option v-for="server in serversStore.servers" :key="server.id" :value="server.id">
                {{ server.name }}
                ·
                {{ server.hostname }}
              </option>
            </select>

            <small>
              Database endpoints may represent
              listeners, VIPs or clusters, so
              server relationships are optional.
            </small>
          </label>

          <label>
            Username

            <input v-model="form.username" required autocomplete="off" />
          </label>

          <label>
            Password

            <input v-model="form.password" :required="!isEditing" type="password" autocomplete="new-password"
              :placeholder="isEditing
                ? 'Leave blank to keep current password'
                : 'Database password'
                " />
          </label>

          <label class="connection-checkbox">
            <input v-model="form.active" type="checkbox" />

            Connection enabled
          </label>
          <small>
            Allows DBAChum to use this connection for provisioning, metadata
            discovery and DBA operations.
          </small>

          <label class="connection-checkbox">
            <input v-model="form.monitor_enabled" type="checkbox" />

            Monitor this connection
          </label>
          <small>
            Shows this connection in the Databases workspace and collects
            background monitoring history. Provisioning still works when this
            is unchecked.
          </small>

          <p v-if="formError" class="login-error">
            {{ formError }}
          </p>

          <div class="connection-form-actions">
            <button type="submit" class="primary-button" :disabled="connectionsStore.saving">
              {{
                connectionsStore.saving
                  ? 'Saving...'
                  : isEditing
                    ? 'Save changes'
                    : 'Add connection'
              }}
            </button>

            <button type="button" class="secondary-button" @click="closeForm">
              Cancel
            </button>
          </div>
        </form>
      </section>
    </div>
  </div>
</template>