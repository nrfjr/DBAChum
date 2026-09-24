<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import FloatingActionMenu from '@/components/common/FloatingActionMenu.vue'

import { useConnectionsStore } from '@/stores/connections'
import {
  useProvisioningStore,
  type OracleMetadataColumn,
  type OracleMetadataSchema,
  type OracleMetadataSequence,
  type OracleMetadataTable,
  type ProvisioningColumnMapping,
  type ProvisioningFormRequirement,
  type ProvisioningFormRequirementSet,
  type ProvisioningProfile,
  type ProvisioningProfileInput,
  type ProvisioningValueKind,
} from '@/stores/provisioning'
import { confirmDialog, showToast } from '@/ui/feedback'
import {
  useAuthStore,
} from '@/stores/auth'

import {
  hasPermission,
} from '@/core/permissions'

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
const authStore = useAuthStore()

const formOpen = ref(false)
const requirementsOpen = ref(false)
const requirementsSaving = ref(false)
const requirementsError = ref<string | null>(null)
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

const parentOracleConnections = computed(() =>
  oracleConnections.value.filter((connection) => connection.monitor_enabled),
)

const availableLdapProfiles = computed(() =>
  provisioningStore.ldapProfiles.filter((profile) => profile.enabled && profile.configured),
)

const ldapAvailable = computed(() => availableLdapProfiles.value.length > 0)

const sourceOptions = computed(() => provisioningStore.sources)


const requirementFields: Array<{ key: keyof ProvisioningFormRequirementSet; label: string }> = [
  { key: 'middle_name', label: 'Middle name' },
  { key: 'reference_user', label: 'Reference user' },
  { key: 'requestor', label: 'Requestor' },
  { key: 'request_reference', label: 'Request / ticket' },
  { key: 'remarks', label: 'Remarks' },
  { key: 'provisioning_profile', label: 'Provisioning profile' },
]

function defaultRequirementSet(): ProvisioningFormRequirementSet {
  return {
    middle_name: 'optional',
    reference_user: 'optional',
    requestor: 'optional',
    request_reference: 'optional',
    remarks: 'optional',
    provisioning_profile: 'optional',
  }
}

const requirementForm = reactive<{
  single_user: ProvisioningFormRequirementSet
  batch_user: ProvisioningFormRequirementSet
}>({
  single_user: defaultRequirementSet(),
  batch_user: defaultRequirementSet(),
})

function setRequirementForm() {
  const current = provisioningStore.formRequirements
  Object.assign(requirementForm.single_user, current?.single_user ?? defaultRequirementSet())
  Object.assign(requirementForm.batch_user, current?.batch_user ?? defaultRequirementSet())
}

async function openRequirements() {
  requirementsError.value = null
  requirementsOpen.value = true
  try {
    if (!provisioningStore.formRequirements) {
      await provisioningStore.loadFormRequirements()
    }
    setRequirementForm()
  } catch (error) {
    requirementsError.value = error instanceof Error ? error.message : 'Unable to load form requirements.'
  }
}

function closeRequirements() {
  if (requirementsSaving.value) return
  requirementsOpen.value = false
  requirementsError.value = null
}

async function saveRequirements() {
  requirementsSaving.value = true
  requirementsError.value = null
  try {
    await provisioningStore.saveFormRequirements({
      single_user: { ...requirementForm.single_user },
      batch_user: { ...requirementForm.batch_user },
    })
    requirementsOpen.value = false
    showToast({ title: 'Form requirements saved', tone: 'success' })
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Unable to save form requirements.'
    requirementsError.value = message
    showToast({ title: 'Unable to save form requirements', message, tone: 'danger' })
  } finally {
    requirementsSaving.value = false
  }
}

function requirementOptions(): ProvisioningFormRequirement[] {
  return ['required', 'optional']
}

const canManageConnections = computed(
  () =>
    hasPermission(
      authStore.user,
      'connections:manage',
    ),
)

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
    schema_connection_id: parentOracleConnections.value.find(
      (connection) => connection.oracle_auth_mode === 'sysdba',
    )?.id ?? parentOracleConnections.value[0]?.id ?? '',
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
        strict_unique: mapping.strict_unique ?? false,
      })),
      match_columns: [...(step.match_columns ?? [])],
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
    name: `Table upsert ${form.table_steps.length + 1}`,
    connection_id: connectionId,
    owner: '',
    table_name: '',
    mappings: [],
    match_columns: [],
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
    strict_unique: false,
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
  step.match_columns = []
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
  step.match_columns = []
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
  step.match_columns = []
  await loadColumns(index)
}

function mappingSelection(mapping: ProvisioningColumnMapping): string {
  if (mapping.value_kind === 'form' || mapping.value_kind === 'generated') {
    return `${mapping.value_kind}:${mapping.value_key ?? ''}`
  }
  return mapping.value_kind
}

function mappingCanMatch(mapping: ProvisioningColumnMapping) {
  if (mapping.value_kind === 'custom') return true
  if (mapping.value_kind === 'generated') return mapping.value_key === 'username'
  return mapping.value_kind === 'form' && mapping.value_key === 'employee_id'
}

function mappingCanBeStrict(mapping: ProvisioningColumnMapping) {
  if (mapping.value_kind === 'omit' || mapping.value_kind === 'null' || mapping.value_kind === 'sequence') return false
  return !(mapping.value_kind === 'generated' && mapping.value_key === 'password')
}

function setMappingSource(
  stepIndex: number,
  mapping: ProvisioningColumnMapping,
  value: string,
) {
  if (value.startsWith('form:') || value.startsWith('generated:')) {
    const [kind, key] = value.split(':', 2) as ['form' | 'generated', string]
    mapping.value_kind = kind
    mapping.value_key = key
    mapping.custom_value = null
  } else {
    mapping.value_kind = value as ProvisioningValueKind
    mapping.value_key = null
    mapping.custom_value = null
  }

  if (!mappingCanBeStrict(mapping)) {
    mapping.strict_unique = false
  }

  const step = form.table_steps[stepIndex]
  if (step && !mappingCanMatch(mapping)) {
    step.match_columns = step.match_columns.filter(
      (column) => column !== mapping.column_name,
    )
  }

  if (
    step
    && mapping.value_kind === 'generated'
    && mapping.value_key === 'username'
    && !step.match_columns.includes(mapping.column_name)
  ) {
    step.match_columns.push(mapping.column_name)
  }
}

function matchColumnSelected(stepIndex: number, columnName: string) {
  return form.table_steps[stepIndex]?.match_columns.includes(columnName) ?? false
}

function setMatchColumn(
  stepIndex: number,
  columnName: string,
  checked: boolean,
) {
  const step = form.table_steps[stepIndex]
  if (!step) return

  if (checked) {
    if (!step.match_columns.includes(columnName)) step.match_columns.push(columnName)
  } else {
    step.match_columns = step.match_columns.filter((column) => column !== columnName)
  }
}

function handleMatchColumnToggle(
  stepIndex: number,
  columnName: string,
  event: Event,
) {
  setMatchColumn(
    stepIndex,
    columnName,
    (event.target as HTMLInputElement).checked,
  )
}

function columnInfo(index: number, columnName: string) {
  return stepMetadata.value[index]?.columns.find((column) => column.name === columnName)
}

async function save() {
  formError.value = null

  if (!form.schema_connection_id) {
    formError.value = 'Select an Oracle connection for schema creation.'
    showToast({ title: 'Oracle connection required', message: formError.value, tone: 'warning' })
    return
  }

  if (form.ldap_enabled && !form.ldap_profile_id) {
    formError.value = 'Select an LDAP profile for this provisioning workflow.'
    showToast({ title: 'LDAP profile required', message: formError.value, tone: 'warning' })
    return
  }

  if (form.ldap_enabled && !availableLdapProfiles.value.some((profile) => profile.id === form.ldap_profile_id)) {
    formError.value = 'The selected LDAP profile is unavailable, disabled, or incomplete.'
    showToast({ title: 'LDAP profile unavailable', message: formError.value, tone: 'warning' })
    return
  }

  const stepWithoutMatch = form.table_steps.findIndex((step) => step.match_columns.length === 0)
  if (stepWithoutMatch !== -1) {
    formError.value = `Table step ${stepWithoutMatch + 1} needs at least one upsert match column.`
    showToast({ title: 'Provisioning step incomplete', message: formError.value, tone: 'warning' })
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
          strict_unique: mapping.strict_unique ?? false,
        })),
        match_columns: [...step.match_columns],
      })),
    }

    const updated = Boolean(editingId.value)
    if (editingId.value) {
      await provisioningStore.updateProfile(editingId.value, payload)
    } else {
      await provisioningStore.createProfile(payload)
    }
    closeForm()
    showToast({ title: updated ? 'Provisioning profile updated' : 'Provisioning profile created', message: payload.name, tone: 'success' })
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Unable to save provisioning profile.'
    formError.value = message
    showToast({ title: 'Unable to save provisioning profile', message, tone: 'danger' })
  }
}

async function remove(profile: ProvisioningProfile) {
  const confirmed = await confirmDialog({ title: 'Delete provisioning profile', message: profile.name, confirmLabel: 'Delete profile', destructive: true, tone: 'danger' })
  if (!confirmed) return
  try {
    await provisioningStore.removeProfile(profile.id)
    showToast({ title: 'Provisioning profile deleted', message: profile.name, tone: 'success' })
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Unable to delete provisioning profile.'
    formError.value = message
    showToast({ title: 'Unable to delete provisioning profile', message, tone: 'danger' })
  }
}

function connectionName(id: string) {
  return connectionsStore.connections.find((connection) => connection.id === id)?.name ?? 'Missing connection'
}

onMounted(async () => {
  await Promise.all([
    connectionsStore.load(),
    provisioningStore.loadProfiles(),
    provisioningStore.loadFormRequirements(),
    provisioningStore.loadSources(),
    provisioningStore.loadLdapProfiles(),
  ])
})

</script>

<template>
  <div class="settings-provisioning">
    <section class="panel">
      <div class="panel-header">
        <div title="Define reusable user-creation workflows. Connections only provide access; profiles decide what DBAChum does.">
          <h2>Provisioning profiles</h2>
        </div>

        <div class="provisioning-header-actions">
          <button class="secondary-button" type="button" @click="openRequirements">
            Form requirements
          </button>
          <button class="primary-button" type="button" @click="openAdd">
            Add profile
          </button>
        </div>
      </div>

      <div v-if="parentOracleConnections.length === 0" class="provisioning-warning">
        Add or enable monitoring on an Oracle database connection first. A profile needs a monitored parent so it can appear under that database's Users & Schemas workspace.
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
              Parent DB {{ connectionName(profile.schema_connection_id) }}
              · {{ profile.table_steps.length }} table step{{ profile.table_steps.length === 1 ? '' : 's' }}
              · LDAP {{ profile.ldap_enabled ? (provisioningStore.ldapProfiles.find((ldap) => ldap.id === profile.ldap_profile_id)?.name ?? 'missing profile') : 'off' }}
            </small>
            <ul v-if="profile.issues.length" class="provisioning-issues">
              <li v-for="issue in profile.issues" :key="issue">{{ issue }}</li>
            </ul>
          </div>
          <FloatingActionMenu v-if="canManageConnections" :label="`Actions for ${profile.name}`">
            <button v-if="canManageConnections" type="button" role="menuitem" @click="openEdit(profile)">
              <FontAwesomeIcon icon="pen" />
              Edit
            </button>
            <button v-if="canManageConnections" type="button" role="menuitem" class="danger-menu-item" @click="remove(profile)">
              <FontAwesomeIcon icon="trash-can" />
              Delete
            </button>
          </FloatingActionMenu>
        </article>
      </div>
    </section>

    <div v-if="requirementsOpen" class="modal-backdrop" @click.self="closeRequirements">
      <section
        class="modal-panel provisioning-requirements-modal"
        role="dialog"
        aria-modal="true"
        aria-label="Provisioning form requirements"
      >
        <div class="modal-header">
          <div>
            <h2>Provisioning form requirements</h2>
          </div>
          <button class="modal-close" type="button" aria-label="Close" :disabled="requirementsSaving" @click="closeRequirements">×</button>
        </div>

        <div class="requirements-fixed-note">
          <strong>Always required</strong>
        </div>

        <div class="provisioning-requirements-grid">
          <section class="provisioning-requirement-card">
            <div>
              <h3>Single User Creation</h3>
            </div>
            <label v-for="field in requirementFields" :key="`single-${field.key}`" class="provisioning-requirement-row">
              <span>{{ field.label }}</span>
              <select v-model="requirementForm.single_user[field.key]">
                <option v-for="option in requirementOptions()" :key="option" :value="option">
                  {{ option === 'required' ? 'Required' : 'Optional' }}
                </option>
              </select>
            </label>
          </section>

          <section class="provisioning-requirement-card">
            <div>
              <h3>Batch User Creation</h3>
            </div>
            <label v-for="field in requirementFields" :key="`batch-${field.key}`" class="provisioning-requirement-row">
              <span>{{ field.label }}</span>
              <select v-model="requirementForm.batch_user[field.key]">
                <option v-for="option in requirementOptions()" :key="option" :value="option">
                  {{ option === 'required' ? 'Required' : 'Optional' }}
                </option>
              </select>
            </label>
          </section>
        </div>

        <p v-if="requirementsError" class="login-error">{{ requirementsError }}</p>

        <div class="connection-form-actions provisioning-requirements-actions">
          <button class="secondary-button" type="button" :disabled="requirementsSaving" @click="closeRequirements">Cancel</button>
          <button class="primary-button" type="button" :disabled="requirementsSaving" @click="saveRequirements">
            {{ requirementsSaving ? 'Saving...' : 'Save requirements' }}
          </button>
        </div>
      </section>
    </div>

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
          </div>
          <button class="modal-close" type="button" aria-label="Close" @click="closeForm">×</button>
        </div>

        <form class="connection-form" @submit.prevent="save">
          <label>
            <span class="field-label">Profile name <span class="required-mark" aria-hidden="true">*</span></span>
            <input v-model="form.name" required maxlength="100" placeholder="ORMS User" />
          </label>

          <label>
            Description
            <input v-model="form.description" maxlength="500" placeholder="Creates ORMS database and application access" />
          </label>

          <label>
            <span class="field-label">Parent database connection <span class="required-mark" aria-hidden="true">*</span></span>
            <select v-model="form.schema_connection_id" required>
              <option value="" disabled>Select Oracle connection</option>
              <option v-for="connection in parentOracleConnections" :key="connection.id" :value="connection.id">
                {{ connection.name }} · {{ connection.username }}{{ connection.oracle_auth_mode === 'sysdba' ? ' / SYSDBA' : '' }}
              </option>
            </select>
          </label>

          <label class="connection-checkbox">
            <input v-model="form.enabled" type="checkbox" class="toggle-switch"/>
            Profile enabled
          </label>

          <label class="connection-checkbox">
            <input
              v-model="form.ldap_enabled"
              type="checkbox"
              class="toggle-switch"
              :disabled="!ldapAvailable"
              @change="ldapEnabledChanged"
            />
            Provision LDAP for users created with this profile
          </label>
          <small v-if="!ldapAvailable" class="connection-danger-note">
            LDAP is optional. Add and enable an LDAP profile under Settings → LDAP before this workflow can opt in.
          </small>

          <label v-if="form.ldap_enabled">
            <span class="field-label">LDAP profile <span class="required-mark" aria-hidden="true">*</span></span>
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
          </label>

          <section class="provisioning-step-builder">
            <div class="panel-header">
              <div>
                <h3>Application table steps</h3>
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
                  <button type="button" class="text-button secondary-button" :disabled="index === 0" @click="moveTableStep(index, -1)">↑</button>
                  <button type="button" class="text-button secondary-button" :disabled="index === form.table_steps.length - 1" @click="moveTableStep(index, 1)">↓</button>
                  <button type="button" class="text-button danger secondary-button" @click="removeTableStep(index)">Remove</button>
                </div>
              </div>

              <label>
                <span class="field-label">Step name <span class="required-mark" aria-hidden="true">*</span></span>
                <input v-model="step.name" required maxlength="100" placeholder="Upsert USER_MASTER" />
              </label>

              <label>
                <span class="field-label">Application provisioning connection <span class="required-mark" aria-hidden="true">*</span></span>
                <select v-model="step.connection_id" required @change="connectionChanged(index)">
                  <option value="" disabled>Select Oracle connection</option>
                  <option v-for="connection in oracleConnections" :key="connection.id" :value="connection.id">
                    {{ connection.name }} · {{ connection.username }}
                  </option>
                </select>
              </label>

                <label>
                  <span class="field-label">Schema <span class="required-mark" aria-hidden="true">*</span></span>
                  <select v-model="step.owner" required @focus="loadSchemas(index)" @change="ownerChanged(index)">
                    <option value="" disabled>Select schema</option>
                    <option v-for="schema in stepMetadata[index]?.schemas ?? []" :key="schema.name" :value="schema.name">
                      {{ schema.name }}
                    </option>
                  </select>
                </label>

                <label>
                  <span class="field-label">Table <span class="required-mark" aria-hidden="true">*</span></span>
                  <select v-model="step.table_name" required @change="tableChanged(index)">
                    <option value="" disabled>Select table</option>
                    <option v-for="table in stepMetadata[index]?.tables ?? []" :key="table.name" :value="table.name">
                      {{ table.name }}
                    </option>
                  </select>
                </label>

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
                    <label
                      class="connection-checkbox provisioning-strict-column"
                      :class="{ disabled: !mappingCanBeStrict(mapping) }"
                      title="Block provisioning when another row already uses this resolved value."
                    >
                      <input
                        v-model="mapping.strict_unique"
                        type="checkbox"
                        :disabled="!mappingCanBeStrict(mapping)"
                        class="toggle-switch"
                      />
                      Strict unique
                    </label>
                  </div>

                  <select
                    :value="mappingSelection(mapping)"
                    @change="setMappingSource(index, mapping, ($event.target as HTMLSelectElement).value)"
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

              <section v-if="step.mappings.length" class="provisioning-upsert-match">
                <div>
                  <strong>Upsert match columns</strong>
                </div>

                <div class="provisioning-match-options">
                  <label
                    v-for="mapping in step.mappings"
                    :key="`match-${mapping.column_name}`"
                    class="connection-checkbox"
                    :class="{ disabled: !mappingCanMatch(mapping) }"
                  >
                    <input
                      type="checkbox"
                      :checked="matchColumnSelected(index, mapping.column_name)"
                      :disabled="!mappingCanMatch(mapping)"
                      @change="handleMatchColumnToggle(index, mapping.column_name, $event)"
                      class="toggle-switch"
                    />
                    {{ mapping.column_name }}
                  </label>
                </div>
              </section>
            </article>
          </section>

          <p v-if="formError" class="login-error">{{ formError }}</p>

          <div class="connection-form-actions">
            <button class="primary-button" type="submit" :disabled="provisioningStore.saving || parentOracleConnections.length === 0">
              {{ provisioningStore.saving ? 'Saving...' : editingId ? 'Save profile' : 'Create profile' }}
            </button>
            <button class="secondary-button" type="button" @click="closeForm">Cancel</button>
          </div>
        </form>
      </section>
    </div>
  </div>
    
</template>
<style scoped>
.provisioning-header-actions { display: flex; align-items: center; gap: .6rem; flex-wrap: wrap; }
.provisioning-requirements-modal { width: min(860px, calc(100vw - 2rem)); max-height: calc(100vh - 2rem); overflow-y: auto; }
.requirements-fixed-note { display: grid; gap: .2rem; padding: .8rem .9rem; margin-bottom: 1rem; border: 1px solid var(--border-color); border-radius: .7rem; background: var(--color-surface-secondary); }
.requirements-fixed-note span { opacity: .75; font-size: .82rem; }
.provisioning-requirements-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: .9rem; }
.provisioning-requirement-card { display: grid; gap: .7rem; min-width: 0; padding: .9rem; border: 1px solid var(--border-color); border-radius: .75rem; }
.provisioning-requirement-card h3 { margin: 0; }
.provisioning-requirement-card small { display: block; margin-top: .2rem; opacity: .7; }
.provisioning-requirement-row { display: grid; grid-template-columns: minmax(0, 1fr) 9rem; align-items: center; gap: .75rem; }
.provisioning-requirement-row select { width: 100%; }
.provisioning-requirements-actions { justify-content: flex-end; margin-top: 1rem; }
@media (max-width: 760px) {
  .provisioning-requirements-grid { grid-template-columns: 1fr; }
}
@media (max-width: 520px) {
  .provisioning-requirement-row { grid-template-columns: 1fr; gap: .35rem; }
  .provisioning-requirements-actions { flex-direction: column-reverse; }
  .provisioning-requirements-actions button { width: 100%; }
}
</style>
