<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'

import { useConnectionsStore } from '@/stores/connections'
import {
  useProvisioningStore,
  type OracleMetadataColumn,
  type OracleMetadataSchema,
  type OracleMetadataSequence,
  type OracleMetadataTable,
  type ProvisioningColumnMapping,
  type ProvisioningProfile,
  type ProvisioningProfileInput,
  type ProvisioningValueKind,
} from '@/stores/provisioning'

interface StepMetadata {
  key: number
  schemas: OracleMetadataSchema[]
  tables: OracleMetadataTable[]
  sequences: OracleMetadataSequence[]
  columns: OracleMetadataColumn[]
  loading: boolean
  error: string | null
}

const connectionsStore = useConnectionsStore()
const provisioningStore = useProvisioningStore()

const formOpen = ref(false)
const editingId = ref<string | null>(null)
const formError = ref<string | null>(null)
const stepMetadata = ref<StepMetadata[]>([])
let nextStepKey = 0

const form = reactive<ProvisioningProfileInput>({
  name: '',
  description: null,
  schema_connection_id: '',
  ldap_enabled: false,
  ldap_profile_id: null,
  enabled: true,
  table_steps: [],
})

const oracleConnections = computed(() =>
  connectionsStore.connections.filter((connection) => connection.engine === 'oracle' && connection.active),
)

const availableLdapProfiles = computed(() =>
  provisioningStore.ldapProfiles.filter((profile) => profile.enabled && profile.configured),
)

const ldapAvailable = computed(() => availableLdapProfiles.value.length > 0)

const sourceOptions = computed(() => provisioningStore.sources)

function blankMetadata(): StepMetadata {
  nextStepKey += 1
  return {
    key: nextStepKey,
    schemas: [],
    tables: [],
    sequences: [],
    columns: [],
    loading: false,
    error: null,
  }
}

function resetForm() {
  editingId.value = null
  formError.value = null
  Object.assign(form, {
    name: '',
    description: null,
    schema_connection_id: oracleConnections.value.find(
      (connection) => connection.oracle_auth_mode === 'sysdba',
    )?.id ?? oracleConnections.value[0]?.id ?? '',
    ldap_enabled: false,
    ldap_profile_id: null,
    enabled: true,
    table_steps: [],
  })
  stepMetadata.value = []
}

function ldapEnabledChanged() {
  if (!form.ldap_enabled) {
    form.ldap_profile_id = null
  } else if (!form.ldap_profile_id && availableLdapProfiles.value.length === 1) {
    form.ldap_profile_id = availableLdapProfiles.value[0]?.id ?? null
  }
}

function openAdd() {
  resetForm()
  formOpen.value = true
}

async function openEdit(profile: ProvisioningProfile) {
  editingId.value = profile.id
  formError.value = null
  Object.assign(form, {
    name: profile.name,
    description: profile.description,
    schema_connection_id: profile.schema_connection_id,
    ldap_enabled: profile.ldap_enabled,
    ldap_profile_id: profile.ldap_profile_id,
    enabled: profile.enabled,
    table_steps: profile.table_steps.map((step) => ({
      name: step.name,
      connection_id: step.connection_id,
      owner: step.owner,
      table_name: step.table_name,
      mappings: step.mappings.map((mapping) => ({
        column_name: mapping.column_name,
        value_kind: mapping.value_kind,
        value_key: mapping.value_key,
        custom_value: mapping.custom_value,
      })),
    })),
  })
  stepMetadata.value = profile.table_steps.map(blankMetadata)
  formOpen.value = true

  for (let index = 0; index < form.table_steps.length; index += 1) {
    await refreshStepMetadata(index)
  }
}

function closeForm() {
  formOpen.value = false
  resetForm()
}

function addTableStep() {
  const connectionId = oracleConnections.value[0]?.id ?? ''
  form.table_steps.push({
    name: `Table insert ${form.table_steps.length + 1}`,
    connection_id: connectionId,
    owner: '',
    table_name: '',
    mappings: [],
  })
  stepMetadata.value.push(blankMetadata())
  if (connectionId) void loadSchemas(form.table_steps.length - 1)
}

function removeTableStep(index: number) {
  form.table_steps.splice(index, 1)
  stepMetadata.value.splice(index, 1)
}

function moveTableStep(index: number, offset: number) {
  const destination = index + offset
  if (destination < 0 || destination >= form.table_steps.length) return
  const [step] = form.table_steps.splice(index, 1)
  const [metadata] = stepMetadata.value.splice(index, 1)
  if (!step || !metadata) return
  form.table_steps.splice(destination, 0, step)
  stepMetadata.value.splice(destination, 0, metadata)
}

async function loadSchemas(index: number) {
  const step = form.table_steps[index]
  const meta = stepMetadata.value[index]
  if (!step || !meta || !step.connection_id) return

  meta.loading = true
  meta.error = null
  try {
    meta.schemas = await provisioningStore.schemas(step.connection_id)
  } catch (error) {
    meta.error = error instanceof Error ? error.message : 'Unable to load Oracle schemas.'
  } finally {
    meta.loading = false
  }
}

async function loadTables(index: number) {
  const step = form.table_steps[index]
  const meta = stepMetadata.value[index]
  if (!step || !meta || !step.connection_id || !step.owner) return

  meta.loading = true
  meta.error = null
  try {
    meta.tables = await provisioningStore.tables(step.connection_id, step.owner)
  } catch (error) {
    meta.error = error instanceof Error ? error.message : 'Unable to load Oracle tables.'
  } finally {
    meta.loading = false
  }
}

async function loadSequences(index: number) {
  const step = form.table_steps[index]
  const meta = stepMetadata.value[index]
  if (!step || !meta || !step.connection_id || !step.owner) return

  meta.loading = true
  meta.error = null
  try {
    meta.sequences = await provisioningStore.sequences(step.connection_id, step.owner)
  } catch (error) {
    meta.error = error instanceof Error ? error.message : 'Unable to load Oracle sequences.'
  } finally {
    meta.loading = false
  }
}

function mergeColumnMappings(
  columns: OracleMetadataColumn[],
  existing: ProvisioningColumnMapping[],
): ProvisioningColumnMapping[] {
  const byName = new Map(existing.map((mapping) => [mapping.column_name, mapping]))
  return columns.map((column) => byName.get(column.name) ?? {
    column_name: column.name,
    value_kind: 'omit',
    value_key: null,
    custom_value: null,
  })
}

async function loadColumns(index: number) {
  const step = form.table_steps[index]
  const meta = stepMetadata.value[index]
  if (!step || !meta || !step.connection_id || !step.owner || !step.table_name) return

  meta.loading = true
  meta.error = null
  try {
    meta.columns = await provisioningStore.columns(
      step.connection_id,
      step.owner,
      step.table_name,
    )
    step.mappings = mergeColumnMappings(meta.columns, step.mappings)
  } catch (error) {
    meta.error = error instanceof Error ? error.message : 'Unable to discover Oracle columns.'
  } finally {
    meta.loading = false
  }
}

async function refreshStepMetadata(index: number) {
  const step = form.table_steps[index]
  if (!step) return
  await loadSchemas(index)
  if (step.owner) {
    await loadTables(index)
    await loadSequences(index)
  }
  if (step.owner && step.table_name) await loadColumns(index)
}

async function connectionChanged(index: number) {
  const step = form.table_steps[index]
  const meta = stepMetadata.value[index]
  if (!step || !meta) return
  step.owner = ''
  step.table_name = ''
  step.mappings = []
  meta.schemas = []
  meta.tables = []
  meta.sequences = []
  meta.columns = []
  await loadSchemas(index)
}

async function ownerChanged(index: number) {
  const step = form.table_steps[index]
  const meta = stepMetadata.value[index]
  if (!step || !meta) return
  step.table_name = ''
  step.mappings = []
  meta.tables = []
  meta.sequences = []
  meta.columns = []
  await loadTables(index)
  await loadSequences(index)
}

async function tableChanged(index: number) {
  const step = form.table_steps[index]
  if (!step) return
  step.mappings = []
  await loadColumns(index)
}

function mappingSelection(mapping: ProvisioningColumnMapping): string {
  if (mapping.value_kind === 'form' || mapping.value_kind === 'generated') {
    return `${mapping.value_kind}:${mapping.value_key ?? ''}`
  }
  return mapping.value_kind
}

function setMappingSource(mapping: ProvisioningColumnMapping, value: string) {
  if (value.startsWith('form:') || value.startsWith('generated:')) {
    const [kind, key] = value.split(':', 2) as ['form' | 'generated', string]
    mapping.value_kind = kind
    mapping.value_key = key
    mapping.custom_value = null
    return
  }

  mapping.value_kind = value as ProvisioningValueKind
  mapping.value_key = null
  mapping.custom_value = null
}

function columnInfo(index: number, columnName: string) {
  return stepMetadata.value[index]?.columns.find((column) => column.name === columnName)
}

async function save() {
  formError.value = null

  if (!form.schema_connection_id) {
    formError.value = 'Select an Oracle connection for schema creation.'
    return
  }

  if (form.ldap_enabled && !form.ldap_profile_id) {
    formError.value = 'Select an LDAP profile for this provisioning workflow.'
    return
  }

  if (form.ldap_enabled && !availableLdapProfiles.value.some((profile) => profile.id === form.ldap_profile_id)) {
    formError.value = 'The selected LDAP profile is unavailable, disabled, or incomplete.'
    return
  }

  try {
    const payload: ProvisioningProfileInput = {
      name: form.name.trim(),
      description: form.description?.trim() || null,
      schema_connection_id: form.schema_connection_id,
      ldap_enabled: form.ldap_enabled,
      ldap_profile_id: form.ldap_enabled ? form.ldap_profile_id : null,
      enabled: form.enabled,
      table_steps: form.table_steps.map((step) => ({
        name: step.name.trim(),
        connection_id: step.connection_id,
        owner: step.owner,
        table_name: step.table_name,
        mappings: step.mappings.map((mapping) => ({
          column_name: mapping.column_name,
          value_kind: mapping.value_kind,
          value_key: mapping.value_key,
          custom_value: mapping.custom_value,
        })),
      })),
    }

    if (editingId.value) {
      await provisioningStore.updateProfile(editingId.value, payload)
    } else {
      await provisioningStore.createProfile(payload)
    }
    closeForm()
  } catch (error) {
    formError.value = error instanceof Error
      ? error.message
      : 'Unable to save provisioning profile.'
  }
}

async function remove(profile: ProvisioningProfile) {
  if (!window.confirm(`Delete provisioning profile "${profile.name}"?`)) return
  try {
    await provisioningStore.removeProfile(profile.id)
  } catch (error) {
    formError.value = error instanceof Error
      ? error.message
      : 'Unable to delete provisioning profile.'
  }
}

function connectionName(id: string) {
  return connectionsStore.connections.find((connection) => connection.id === id)?.name ?? 'Missing connection'
}

onMounted(async () => {
  await Promise.all([
    connectionsStore.load(),
    provisioningStore.loadProfiles(),
    provisioningStore.loadSources(),
    provisioningStore.loadLdapProfiles(),
  ])
})
</script>

<template>
  <div class="settings-provisioning">
    <section class="panel">
      <div class="panel-header">
        <div>
          <h2>Provisioning profiles</h2>
          <p>
            Define reusable user-creation workflows. Connections only provide access; profiles decide what DBAChum does.
          </p>
        </div>

        <button class="primary-button" type="button" @click="openAdd">
          Add profile
        </button>
      </div>

      <div v-if="oracleConnections.length === 0" class="provisioning-warning">
        Add an Oracle connection first. A provisioning profile cannot create a database account without one.
      </div>

      <p v-if="provisioningStore.loading" class="empty-state">Loading provisioning profiles...</p>
      <p v-else-if="provisioningStore.error" class="login-error">{{ provisioningStore.error }}</p>

      <div v-else-if="provisioningStore.profiles.length === 0" class="empty-state">
        No provisioning profiles yet.
      </div>

      <div v-else class="connection-list">
        <article v-for="profile in provisioningStore.profiles" :key="profile.id" class="connection-item">
          <div>
            <div class="connection-title">
              <strong>{{ profile.name }}</strong>
              <span class="status-pill" :class="{ disabled: !profile.ready || !profile.enabled }">
                {{ !profile.enabled ? 'Disabled' : profile.ready ? 'Ready' : 'Needs attention' }}
              </span>
            </div>
            <p>{{ profile.description || 'No description' }}</p>
            <small>
              Create via {{ connectionName(profile.schema_connection_id) }}
              · {{ profile.table_steps.length }} table step{{ profile.table_steps.length === 1 ? '' : 's' }}
              · LDAP {{ profile.ldap_enabled ? (provisioningStore.ldapProfiles.find((ldap) => ldap.id === profile.ldap_profile_id)?.name ?? 'missing profile') : 'off' }}
            </small>
            <ul v-if="profile.issues.length" class="provisioning-issues">
              <li v-for="issue in profile.issues" :key="issue">{{ issue }}</li>
            </ul>
          </div>

          <div class="connection-actions">
            <button class="secondary-button" type="button" @click="openEdit(profile)">Edit</button>
            <button class="secondary-button" type="button" @click="remove(profile)">Delete</button>
          </div>
        </article>
      </div>
    </section>

    <div v-if="formOpen" class="modal-backdrop" @click.self="closeForm">
      <section
        class="modal-panel provisioning-modal"
        role="dialog"
        aria-modal="true"
        :aria-label="editingId ? 'Edit provisioning profile' : 'Add provisioning profile'"
      >
        <div class="modal-header">
          <div>
            <h2>{{ editingId ? 'Edit provisioning profile' : 'Add provisioning profile' }}</h2>
            <p>Build the workflow from real Oracle connections, tables and form values.</p>
          </div>
          <button class="modal-close" type="button" aria-label="Close" @click="closeForm">×</button>
        </div>

        <form class="connection-form" @submit.prevent="save">
          <label>
            Profile name
            <input v-model="form.name" required maxlength="100" placeholder="ORMS User" />
          </label>

          <label>
            Description
            <input v-model="form.description" maxlength="500" placeholder="Creates ORMS database and application access" />
          </label>

          <label>
            Schema creation connection
            <select v-model="form.schema_connection_id" required>
              <option value="" disabled>Select Oracle connection</option>
              <option v-for="connection in oracleConnections" :key="connection.id" :value="connection.id">
                {{ connection.name }} · {{ connection.username }}{{ connection.oracle_auth_mode === 'sysdba' ? ' / SYSDBA' : '' }}
              </option>
            </select>
            <small>SYS/SYSDBA is the normal choice, but the profile only requires an Oracle account with the needed privileges.</small>
          </label>

          <label class="connection-checkbox">
            <input v-model="form.enabled" type="checkbox" />
            Profile enabled
          </label>

          <label class="connection-checkbox">
            <input
              v-model="form.ldap_enabled"
              type="checkbox"
              :disabled="!ldapAvailable"
              @change="ldapEnabledChanged"
            />
            Provision LDAP for users created with this profile
          </label>
          <small v-if="!ldapAvailable" class="connection-danger-note">
            LDAP is optional. Add and enable an LDAP profile under Settings → LDAP before this workflow can opt in.
          </small>

          <label v-if="form.ldap_enabled">
            LDAP profile
            <select v-model="form.ldap_profile_id" required>
              <option :value="null" disabled>Select LDAP profile</option>
              <option
                v-for="ldap in availableLdapProfiles"
                :key="ldap.id"
                :value="ldap.id"
              >
                {{ ldap.name }} · {{ ldap.host }}:{{ ldap.port }}
              </option>
            </select>
            <small>The selected profile supplies the LDAP connection, Base DN, credentials, and LDIF template.</small>
          </label>

          <section class="provisioning-step-builder">
            <div class="panel-header">
              <div>
                <h3>Application table steps</h3>
                <p>Each step inserts one row using mappings you define. USER_MASTER is just another table step.</p>
              </div>
              <button type="button" class="secondary-button" @click="addTableStep">Add table step</button>
            </div>

            <div v-if="form.table_steps.length === 0" class="empty-state compact">
              No application tables. This profile will only create the Oracle user and apply reviewed roles.
            </div>

            <article
              v-for="(step, index) in form.table_steps"
              :key="stepMetadata[index]?.key ?? index"
              class="provisioning-step-card"
            >
              <div class="provisioning-step-toolbar">
                <strong>Step {{ index + 1 }}</strong>
                <div>
                  <button type="button" class="text-button" :disabled="index === 0" @click="moveTableStep(index, -1)">↑</button>
                  <button type="button" class="text-button" :disabled="index === form.table_steps.length - 1" @click="moveTableStep(index, 1)">↓</button>
                  <button type="button" class="text-button danger" @click="removeTableStep(index)">Remove</button>
                </div>
              </div>

              <label>
                Step name
                <input v-model="step.name" required placeholder="Insert USER_MASTER" />
              </label>

              <label>
                Oracle connection used for this insert
                <select v-model="step.connection_id" required @change="connectionChanged(index)">
                  <option value="" disabled>Select Oracle connection</option>
                  <option v-for="connection in oracleConnections" :key="connection.id" :value="connection.id">
                    {{ connection.name }} · {{ connection.username }}
                  </option>
                </select>
              </label>

              <div class="connection-form-row">
                <label>
                  Schema
                  <select v-model="step.owner" required @focus="loadSchemas(index)" @change="ownerChanged(index)">
                    <option value="" disabled>Select schema</option>
                    <option v-for="schema in stepMetadata[index]?.schemas ?? []" :key="schema.name" :value="schema.name">
                      {{ schema.name }}
                    </option>
                  </select>
                </label>

                <label>
                  Table
                  <select v-model="step.table_name" required @change="tableChanged(index)">
                    <option value="" disabled>Select table</option>
                    <option v-for="table in stepMetadata[index]?.tables ?? []" :key="table.name" :value="table.name">
                      {{ table.name }}
                    </option>
                  </select>
                </label>
              </div>

              <p v-if="stepMetadata[index]?.loading" class="empty-state compact">Reading Oracle metadata...</p>
              <p v-if="stepMetadata[index]?.error" class="login-error">{{ stepMetadata[index]?.error }}</p>

              <div v-if="step.mappings.length" class="provisioning-mapping-table">
                <div class="provisioning-mapping-head">
                  <span>Column</span>
                  <span>Value source</span>
                  <span>Value</span>
                </div>

                <div
                  v-for="mapping in step.mappings"
                  :key="mapping.column_name"
                  class="provisioning-mapping-row"
                  :data-column="mapping.column_name"
                >
                  <div>
                    <strong>{{ mapping.column_name }}</strong>
                    <small v-if="columnInfo(index, mapping.column_name)">
                      {{ columnInfo(index, mapping.column_name)?.data_type }}
                      · {{ columnInfo(index, mapping.column_name)?.nullable ? 'nullable' : 'required' }}
                      <template v-if="columnInfo(index, mapping.column_name)?.data_default"> · default exists</template>
                    </small>
                  </div>

                  <select
                    :value="mappingSelection(mapping)"
                    @change="setMappingSource(mapping, ($event.target as HTMLSelectElement).value)"
                  >
                    <option value="omit">Database default / omit</option>
                    <option value="null">NULL</option>
                    <option value="custom">Custom value</option>
                    <option value="sequence">Oracle sequence</option>
                    <optgroup label="Provisioning form">
                      <option
                        v-for="source in sourceOptions.filter((item) => item.kind === 'form')"
                        :key="`form:${source.key}`"
                        :value="`form:${source.key}`"
                      >
                        {{ source.label }}
                      </option>
                    </optgroup>
                    <optgroup label="Generated by DBAChum">
                      <option
                        v-for="source in sourceOptions.filter((item) => item.kind === 'generated')"
                        :key="`generated:${source.key}`"
                        :value="`generated:${source.key}`"
                      >
                        {{ source.label }}
                      </option>
                    </optgroup>
                  </select>

                  <input
                    v-if="mapping.value_kind === 'custom'"
                    v-model="mapping.custom_value"
                    placeholder="Custom value"
                  />
                  <select
                    v-else-if="mapping.value_kind === 'sequence'"
                    v-model="mapping.value_key"
                    aria-label="Oracle sequence"
                    required
                  >
                    <option :value="null" disabled>Select sequence</option>
                    <option
                      v-for="sequence in stepMetadata[index]?.sequences ?? []"
                      :key="sequence.name"
                      :value="sequence.name"
                    >
                      {{ sequence.name }}.NEXTVAL
                    </option>
                  </select>
                  <span v-else class="mapping-preview">
                    {{ mapping.value_kind === 'null'
                      ? 'NULL'
                      : mapping.value_kind === 'omit'
                        ? 'Not included in INSERT'
                        : sourceOptions.find((item) => item.key === mapping.value_key)?.label ?? mapping.value_key }}
                  </span>
                </div>
              </div>
            </article>
          </section>

          <p v-if="formError" class="login-error">{{ formError }}</p>

          <div class="connection-form-actions">
            <button class="primary-button" type="submit" :disabled="provisioningStore.saving || oracleConnections.length === 0">
              {{ provisioningStore.saving ? 'Saving...' : editingId ? 'Save profile' : 'Create profile' }}
            </button>
            <button class="secondary-button" type="button" @click="closeForm">Cancel</button>
          </div>
        </form>
      </section>
    </div>
  </div>
</template>
