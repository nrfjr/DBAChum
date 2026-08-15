<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'

import {
  useConnectionsStore,
  type DatabaseConnection,
  type DatabaseConnectionInput,
  type DatabaseEngine,
} from '@/stores/connections'

const connectionsStore = useConnectionsStore()

const editingId = ref<string | null>(null)
const formError = ref<string | null>(null)

const testingId = ref<string | null>(null)

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
  enabled: boolean
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
    enabled: true,
  }
}

const form = reactive<ConnectionForm>(emptyForm())

const isEditing = computed(() => editingId.value !== null)

function resetForm() {
  Object.assign(form, emptyForm())
  editingId.value = null
  formError.value = null
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
  } else {
    form.oracle_identifier_type = 'service_name'
    form.oracle_identifier = ''
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
    enabled: connection.enabled,
  })
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
    enabled: form.enabled,
  }
}

async function saveConnection() {
  formError.value = null

  if (!isEditing.value && !form.password) {
    formError.value =
      'Password is required for a new connection.'
    return
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

    resetForm()
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
})
</script>

<template>
  <section class="page-header">
    <div>
      <h1>Database Connections</h1>
      <p>
        Manage the database targets monitored by DBAChum.
      </p>
    </div>
  </section>

  <div class="connections-layout">
    <section class="panel">
      <div class="panel-header">
        <div>
          <h2>Connections</h2>
          <p>Configured database targets.</p>
        </div>
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
                disabled: !connection.enabled,
              }">
                {{
                  connection.enabled
                    ? 'Enabled'
                    : 'Disabled'
                }}
              </span>
            </div>

            <p>
              {{ engineLabel(connection.engine) }}
              ·
              {{ connection.host }}:{{ connection.port }}
            </p>

            <small>
              {{ connection.username }}
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
            <button type="button" class="secondary-button" :disabled="testingId === connection.id"
              @click="testConnection(connection)">
              {{
                testingId === connection.id
                  ? 'Testing...'
                  : 'Test'
              }}
            </button>
            <button type="button" class="secondary-button" @click="editConnection(connection)">
              Edit
            </button>

            <button type="button" class="secondary-button" @click="removeConnection(connection)">
              Delete
            </button>
          </div>
        </article>
      </div>
    </section>

    <section class="panel">
      <div class="panel-header">
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
        </template>

        <label v-else>
          Database
          <span class="optional-label">
            Optional
          </span>

          <input v-model="form.database" placeholder="Database name" />
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
          <input v-model="form.enabled" type="checkbox" />

          Monitor this connection
        </label>

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

          <button v-if="isEditing" type="button" class="secondary-button" @click="resetForm">
            Cancel
          </button>
        </div>
      </form>
    </section>
  </div>
</template>