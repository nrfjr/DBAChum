<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import ScrollableDataTable from '@/components/common/ScrollableDataTable.vue'
import {
  useOracleDbaStore,
  type OracleRoleChangeInput,
  type OracleRoleChangePreview,
  type OracleRoleDetail,
  type OracleRoleListResult,
  type OracleRoleOperation,
  type OracleRoleSummary,
} from '@/stores/oracleDba'

const props = defineProps<{ connectionId: string; active: boolean }>()
const oracleStore = useOracleDbaStore()

const catalog = ref<OracleRoleListResult | null>(null)
const loading = ref(false)
const error = ref<string | null>(null)
const filter = ref('')
const selectedRoleName = ref<string | null>(null)
const detail = ref<OracleRoleDetail | null>(null)
const detailLoading = ref(false)
const detailError = ref<string | null>(null)

const showCreate = ref(false)
const createName = ref('')
const createReference = ref('')
const createPreview = ref<OracleRoleChangePreview | null>(null)
const createLoading = ref(false)
const createError = ref<string | null>(null)

const showAction = ref(false)
const actionOperation = ref<OracleRoleOperation>('grant_to_user')
const actionUsername = ref('')
const actionValue = ref('')
const actionOwner = ref('')
const actionObject = ref('')
const actionPrivilege = ref('')
const actionReference = ref('')
const actionPreview = ref<OracleRoleChangePreview | null>(null)
const actionLoading = ref(false)
const actionError = ref<string | null>(null)

const showDrop = ref(false)
const dropConfirmation = ref('')
const dropReference = ref('')
const dropPreview = ref<Awaited<ReturnType<typeof oracleStore.previewRoleDrop>> | null>(null)
const dropLoading = ref(false)
const dropError = ref<string | null>(null)

const loadedOnce = ref(false)

const filteredRoles = computed(() => {
  const rows = catalog.value?.roles ?? []
  const term = filter.value.trim().toLowerCase()
  if (!term) return rows
  return rows.filter((role) =>
    [
      role.name,
      role.manageable ? 'manageable custom' : 'protected inspect only',
      role.powerful ? 'elevated' : '',
    ].some((value) => value.toLowerCase().includes(term)),
  )
})

const selectedSummary = computed(() =>
  catalog.value?.roles.find((item) => item.name === selectedRoleName.value) ?? null,
)

const actionNeedsUser = computed(() => ['grant_to_user', 'revoke_from_user'].includes(actionOperation.value))
const actionNeedsRole = computed(() => ['grant_child_role', 'revoke_child_role'].includes(actionOperation.value))
const actionNeedsSystemPrivilege = computed(() => ['grant_system_privilege', 'revoke_system_privilege'].includes(actionOperation.value))
const actionNeedsObject = computed(() => ['grant_object_privilege', 'revoke_object_privilege'].includes(actionOperation.value))

const canPreviewAction = computed(() => {
  if (!detail.value?.manageable) return false
  if (actionNeedsUser.value) return Boolean(actionUsername.value.trim())
  if (actionNeedsRole.value) return Boolean(actionValue.value.trim())
  if (actionNeedsSystemPrivilege.value) return Boolean(actionPrivilege.value.trim())
  if (actionNeedsObject.value) {
    return Boolean(actionOwner.value.trim() && actionObject.value.trim() && actionPrivilege.value.trim())
  }
  return false
})

function operationLabel(operation: OracleRoleOperation) {
  const labels: Record<OracleRoleOperation, string> = {
    grant_to_user: 'Grant role to user',
    revoke_from_user: 'Revoke role from user',
    grant_child_role: 'Grant child role',
    revoke_child_role: 'Revoke child role',
    grant_system_privilege: 'Grant system privilege',
    revoke_system_privilege: 'Revoke system privilege',
    grant_object_privilege: 'Grant object privilege',
    revoke_object_privilege: 'Revoke object privilege',
  }
  return labels[operation]
}

function resetActionFields() {
  actionUsername.value = ''
  actionValue.value = ''
  actionOwner.value = ''
  actionObject.value = ''
  actionPrivilege.value = ''
  actionReference.value = ''
  actionPreview.value = null
  actionError.value = null
}

async function loadRoles(force = false) {
  if (loadedOnce.value && !force) return
  loading.value = true
  error.value = null
  try {
    catalog.value = await oracleStore.loadRoles(props.connectionId)
    loadedOnce.value = true
    if (selectedRoleName.value && !catalog.value.roles.some((role) => role.name === selectedRoleName.value)) {
      selectedRoleName.value = null
      detail.value = null
    }
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : 'Unable to load Oracle roles.'
  } finally {
    loading.value = false
  }
}

async function selectRole(role: OracleRoleSummary) {
  selectedRoleName.value = role.name
  detailLoading.value = true
  detailError.value = null
  try {
    detail.value = await oracleStore.loadRoleDetail(props.connectionId, role.name)
  } catch (caught) {
    detailError.value = caught instanceof Error ? caught.message : 'Unable to inspect Oracle role.'
    detail.value = null
  } finally {
    detailLoading.value = false
  }
}

async function refreshSelectedRole() {
  if (!selectedRoleName.value) return
  const summary = catalog.value?.roles.find((item) => item.name === selectedRoleName.value)
  if (summary) await selectRole(summary)
  else {
    detailLoading.value = true
    try {
      detail.value = await oracleStore.loadRoleDetail(props.connectionId, selectedRoleName.value)
    } finally {
      detailLoading.value = false
    }
  }
}

function openCreateRole() {
  createName.value = ''
  createReference.value = ''
  createPreview.value = null
  createError.value = null
  showCreate.value = true
}

function closeCreateRole() {
  if (createLoading.value) return
  showCreate.value = false
}

async function previewCreateRole() {
  if (!createName.value.trim() || createLoading.value) return
  createLoading.value = true
  createError.value = null
  createPreview.value = null
  try {
    createPreview.value = await oracleStore.previewRoleCreate(
      props.connectionId,
      createName.value.trim().toUpperCase(),
      createReference.value.trim() || null,
    )
    createName.value = createPreview.value.role_name
  } catch (caught) {
    createError.value = caught instanceof Error ? caught.message : 'Unable to preview role creation.'
  } finally {
    createLoading.value = false
  }
}

async function executeCreateRole() {
  if (!createPreview.value?.ready_to_execute || createLoading.value) return
  createLoading.value = true
  createError.value = null
  try {
    const result = await oracleStore.createRole(
      props.connectionId,
      createPreview.value.role_name,
      createReference.value.trim() || null,
    )
    showCreate.value = false
    await loadRoles(true)
    selectedRoleName.value = result.role.name
    detail.value = result.role
  } catch (caught) {
    createError.value = caught instanceof Error ? caught.message : 'Unable to create Oracle role.'
  } finally {
    createLoading.value = false
  }
}

function openRoleAction(operation: OracleRoleOperation, preset: Partial<OracleRoleChangeInput> = {}) {
  resetActionFields()
  actionOperation.value = operation
  actionUsername.value = preset.username ?? ''
  actionValue.value = preset.value ?? ''
  actionOwner.value = preset.owner ?? ''
  actionObject.value = preset.object_name ?? ''
  actionPrivilege.value = preset.privilege ?? ''
  showAction.value = true
}

function closeRoleAction() {
  if (actionLoading.value) return
  showAction.value = false
}

function actionPayload(): OracleRoleChangeInput {
  return {
    operation: actionOperation.value,
    username: actionNeedsUser.value ? actionUsername.value.trim().toUpperCase() : null,
    value: actionNeedsRole.value ? actionValue.value.trim().toUpperCase() : null,
    owner: actionNeedsObject.value ? actionOwner.value.trim().toUpperCase() : null,
    object_name: actionNeedsObject.value ? actionObject.value.trim().toUpperCase() : null,
    privilege: actionNeedsSystemPrivilege.value || actionNeedsObject.value
      ? actionPrivilege.value.trim().toUpperCase()
      : null,
    request_reference: actionReference.value.trim() || null,
  }
}

async function previewRoleAction() {
  if (!selectedRoleName.value || !canPreviewAction.value || actionLoading.value) return
  actionLoading.value = true
  actionError.value = null
  actionPreview.value = null
  try {
    actionPreview.value = await oracleStore.previewRoleChange(
      props.connectionId,
      selectedRoleName.value,
      actionPayload(),
    )
  } catch (caught) {
    actionError.value = caught instanceof Error ? caught.message : 'Unable to preview role change.'
  } finally {
    actionLoading.value = false
  }
}

async function executeRoleAction() {
  if (!selectedRoleName.value || !actionPreview.value?.ready_to_execute || actionLoading.value) return
  actionLoading.value = true
  actionError.value = null
  try {
    const result = await oracleStore.changeRole(
      props.connectionId,
      selectedRoleName.value,
      actionPayload(),
    )
    detail.value = result.role
    showAction.value = false
    await loadRoles(true)
  } catch (caught) {
    actionError.value = caught instanceof Error ? caught.message : 'Unable to apply role change.'
  } finally {
    actionLoading.value = false
  }
}

async function openDropRole() {
  if (!detail.value?.manageable || dropLoading.value) return
  showDrop.value = true
  dropConfirmation.value = ''
  dropReference.value = ''
  dropPreview.value = null
  dropError.value = null
  dropLoading.value = true
  try {
    dropPreview.value = await oracleStore.previewRoleDrop(props.connectionId, detail.value.name)
  } catch (caught) {
    dropError.value = caught instanceof Error ? caught.message : 'Unable to preview role deletion.'
  } finally {
    dropLoading.value = false
  }
}

function closeDropRole() {
  if (dropLoading.value) return
  showDrop.value = false
}

async function executeDropRole() {
  if (!detail.value || dropConfirmation.value.trim().toUpperCase() !== detail.value.name || dropLoading.value) return
  dropLoading.value = true
  dropError.value = null
  try {
    await oracleStore.dropRole(
      props.connectionId,
      detail.value.name,
      dropConfirmation.value.trim().toUpperCase(),
      dropReference.value.trim() || null,
    )
    showDrop.value = false
    selectedRoleName.value = null
    detail.value = null
    await loadRoles(true)
  } catch (caught) {
    dropError.value = caught instanceof Error ? caught.message : 'Unable to drop Oracle role.'
  } finally {
    dropLoading.value = false
  }
}

watch(
  () => props.active,
  (active) => {
    if (active) void loadRoles()
  },
  { immediate: true },
)
</script>

<template>
  <div class="role-management-workspace">
    <section class="role-management-toolbar">
      <div>
        <h3>Oracle roles</h3>
        <p>Create and manage custom roles. Oracle-maintained/protected roles remain inspect-only.</p>
      </div>
      <div class="role-toolbar-actions">
        <button type="button" class="secondary-button" :disabled="loading" @click="loadRoles(true)">
          {{ loading ? 'Refreshing...' : 'Refresh' }}
        </button>
        <button type="button" class="primary-button" @click="openCreateRole">Create role</button>
      </div>
    </section>

    <div v-if="error" class="utility-warning">{{ error }}</div>
    <div v-for="warning in catalog?.warnings ?? []" :key="warning" class="utility-warning">{{ warning }}</div>

    <div class="role-layout">
      <section class="role-list-card">
        <div class="role-filter-row">
          <input v-model="filter" type="search" placeholder="Filter role name or status" />
          <span>{{ filteredRoles.length }} role(s)</span>
        </div>

        <ScrollableDataTable
          :loading="loading && !catalog"
          :empty="!loading && filteredRoles.length === 0"
          empty-message="No Oracle roles match this filter."
          max-height="38rem"
        >
          <template #header>
            <tr>
              <th>Role</th>
              <th>Status</th>
            </tr>
          </template>
          <tr
            v-for="role in filteredRoles"
            :key="role.name"
            class="role-row"
            :class="{ selected: selectedRoleName === role.name }"
            @click="selectRole(role)"
          >
            <td>
              <strong>{{ role.name }}</strong>
              <small v-if="role.powerful">⚠ Elevated</small>
            </td>
            <td>
              <span :class="role.manageable ? 'role-manageable' : 'role-protected'">
                {{ role.manageable ? 'Custom / manageable' : 'Inspect only' }}
              </span>
            </td>
          </tr>
        </ScrollableDataTable>
      </section>

      <section class="role-detail-card">
        <div v-if="!selectedRoleName && !detailLoading" class="role-empty-state">
          <strong>Select a role to inspect it.</strong>
          <span>Members, nested roles, system privileges and object privileges will appear here.</span>
        </div>

        <div v-if="detailLoading" class="role-empty-state">Loading role details...</div>
        <div v-if="detailError" class="utility-warning">{{ detailError }}</div>

        <template v-if="detail && !detailLoading">
          <header class="role-detail-header">
            <div>
              <div class="role-title-line">
                <h3>{{ detail.name }}</h3>
                <span v-if="detail.powerful" class="role-elevated-pill">⚠ Elevated</span>
                <span :class="detail.manageable ? 'role-manageable-pill' : 'role-protected-pill'">
                  {{ detail.manageable ? 'Manageable' : 'Inspect only' }}
                </span>
              </div>
              <p v-if="detail.oracle_maintained">Oracle-maintained role.</p>
              <p v-else-if="detail.protected">Protected by DBAChum's legacy-safe role rules.</p>
              <p v-else>Custom Oracle role eligible for audited DBAChum changes.</p>
            </div>
            <button type="button" class="secondary-button" @click="refreshSelectedRole">Refresh role</button>
          </header>

          <div v-for="warning in detail.warnings" :key="warning" class="utility-warning">{{ warning }}</div>

          <section class="role-summary-grid">
            <div><span>Users</span><strong>{{ detail.members.length }}</strong></div>
            <div><span>Child roles</span><strong>{{ detail.child_roles.length }}</strong></div>
            <div><span>System privileges</span><strong>{{ detail.system_privileges.length }}</strong></div>
            <div><span>Object privileges</span><strong>{{ detail.object_privileges.length }}</strong></div>
          </section>

          <div v-if="detail.manageable" class="role-action-strip">
            <button type="button" class="secondary-button" @click="openRoleAction('grant_to_user')">Grant to user</button>
            <button type="button" class="secondary-button" @click="openRoleAction('grant_child_role')">Add child role</button>
            <button type="button" class="secondary-button" @click="openRoleAction('grant_system_privilege')">Add system privilege</button>
            <button type="button" class="secondary-button" @click="openRoleAction('grant_object_privilege')">Add object privilege</button>
            <button type="button" class="role-drop-button" @click="openDropRole">Drop role</button>
          </div>
          <div v-else class="role-inspect-notice">
            DBAChum will not create, grant, revoke or drop against this protected role.
          </div>

          <details class="role-detail-section" open>
            <summary>Users with this role · {{ detail.members.length }}</summary>
            <ScrollableDataTable :empty="detail.members.length === 0" empty-message="No normal users are directly granted this role." max-height="18rem">
              <template #header><tr><th>User</th><th>Status</th><th>Default</th><th>Admin option</th><th>Flag</th><th v-if="detail.manageable">Action</th></tr></template>
              <tr v-for="member in detail.members" :key="member.username">
                <td><strong>{{ member.username }}</strong></td>
                <td>{{ member.status }}</td>
                <td>{{ member.default_role ? 'YES' : 'NO' }}</td>
                <td>{{ member.admin_option ? 'YES' : 'NO' }}</td>
                <td>{{ member.protected ? 'Protected account' : '—' }}</td>
                <td v-if="detail.manageable"><button v-if="!member.protected" type="button" class="link-action" @click="openRoleAction('revoke_from_user', { username: member.username })">Revoke</button><span v-else>Inspect only</span></td>
              </tr>
            </ScrollableDataTable>
          </details>

          <details v-if="detail.parent_roles.length" class="role-detail-section">
            <summary>Parent roles · {{ detail.parent_roles.length }}</summary>
            <div class="role-chip-list">
              <span v-for="parent in detail.parent_roles" :key="parent.name">{{ parent.name }}<small v-if="parent.admin_option"> · ADMIN</small></span>
            </div>
          </details>

          <details class="role-detail-section" open>
            <summary>Child roles · {{ detail.child_roles.length }}</summary>
            <ScrollableDataTable :empty="detail.child_roles.length === 0" empty-message="No nested roles." max-height="18rem">
              <template #header><tr><th>Role</th><th>Admin option</th><th>Flag</th><th v-if="detail.manageable">Action</th></tr></template>
              <tr v-for="child in detail.child_roles" :key="child.name">
                <td><strong>{{ child.name }}</strong></td>
                <td>{{ child.admin_option ? 'YES' : 'NO' }}</td>
                <td>{{ child.powerful || child.protected ? '⚠ Elevated / protected' : '—' }}</td>
                <td v-if="detail.manageable"><button type="button" class="link-action" @click="openRoleAction('revoke_child_role', { value: child.name })">Revoke</button></td>
              </tr>
            </ScrollableDataTable>
          </details>

          <details class="role-detail-section" open>
            <summary>System privileges · {{ detail.system_privileges.length }}</summary>
            <ScrollableDataTable :empty="detail.system_privileges.length === 0" empty-message="No direct system privileges on this role." max-height="20rem">
              <template #header><tr><th>Privilege</th><th>Admin option</th><th>Flag</th><th v-if="detail.manageable">Action</th></tr></template>
              <tr v-for="privilege in detail.system_privileges" :key="privilege.name">
                <td><strong>{{ privilege.name }}</strong></td>
                <td>{{ privilege.admin_option ? 'YES' : 'NO' }}</td>
                <td>{{ privilege.powerful ? '⚠ Elevated' : '—' }}</td>
                <td v-if="detail.manageable"><button type="button" class="link-action" @click="openRoleAction('revoke_system_privilege', { privilege: privilege.name })">Revoke</button></td>
              </tr>
            </ScrollableDataTable>
          </details>

          <details class="role-detail-section">
            <summary>Object privileges · {{ detail.object_privileges.length }}</summary>
            <ScrollableDataTable :empty="detail.object_privileges.length === 0" empty-message="No direct object privileges on this role." max-height="24rem">
              <template #header><tr><th>Owner</th><th>Object</th><th>Privilege</th><th>Column</th><th>Grantable</th><th v-if="detail.manageable">Action</th></tr></template>
              <tr v-for="item in detail.object_privileges" :key="`${item.owner}.${item.object_name}.${item.column_name || ''}.${item.privilege}`">
                <td>{{ item.owner }}</td>
                <td><strong>{{ item.object_name }}</strong></td>
                <td>{{ item.privilege }}</td>
                <td>{{ item.column_name || '—' }}</td>
                <td>{{ item.grantable ? 'YES' : 'NO' }}</td>
                <td v-if="detail.manageable && !item.column_name"><button type="button" class="link-action" @click="openRoleAction('revoke_object_privilege', { owner: item.owner, object_name: item.object_name, privilege: item.privilege })">Revoke</button></td>
                <td v-else-if="detail.manageable">Review only</td>
              </tr>
            </ScrollableDataTable>
          </details>
        </template>
      </section>
    </div>

    <div v-if="showCreate" class="role-modal-backdrop" @click.self="closeCreateRole">
      <section class="role-modal" role="dialog" aria-modal="true" aria-label="Create Oracle role">
        <header><div><h3>Create Oracle role</h3><p>DBAChum creates a normal role with no password. Preview is required before execution.</p></div><button type="button" @click="closeCreateRole">×</button></header>
        <label>Role name<input v-model="createName" maxlength="30" placeholder="APP_CUSTOM_ROLE" :disabled="Boolean(createPreview)" /></label>
        <label>Request / ticket reference <small>optional</small><input v-model="createReference" maxlength="100" placeholder="REQ-12345" /></label>
        <div v-if="createError" class="utility-warning">{{ createError }}</div>
        <template v-if="createPreview">
          <div v-for="warning in createPreview.warnings" :key="warning" class="utility-warning">{{ warning }}</div>
          <div class="sql-preview"><span>Exact statement</span><code>{{ createPreview.statement }}</code></div>
        </template>
        <footer>
          <button v-if="!createPreview" type="button" class="primary-button" :disabled="!createName.trim() || createLoading" @click="previewCreateRole">{{ createLoading ? 'Previewing...' : 'Preview' }}</button>
          <button v-else type="button" class="primary-button" :disabled="!createPreview.ready_to_execute || createLoading" @click="executeCreateRole">{{ createLoading ? 'Creating...' : 'Create role' }}</button>
          <button v-if="createPreview" type="button" class="secondary-button" :disabled="createLoading" @click="createPreview = null">Back</button>
          <button type="button" class="secondary-button" :disabled="createLoading" @click="closeCreateRole">Cancel</button>
        </footer>
      </section>
    </div>

    <div v-if="showAction && detail" class="role-modal-backdrop" @click.self="closeRoleAction">
      <section class="role-modal" role="dialog" aria-modal="true" :aria-label="`${operationLabel(actionOperation)} for ${detail.name}`">
        <header><div><h3>{{ operationLabel(actionOperation) }}</h3><p>{{ detail.name }} · changes are rebuilt and validated against live Oracle state before execution.</p></div><button type="button" @click="closeRoleAction">×</button></header>

        <label>Action<select v-model="actionOperation" :disabled="Boolean(actionPreview)" @change="resetActionFields">
          <option value="grant_to_user">Grant role to user</option>
          <option value="revoke_from_user">Revoke role from user</option>
          <option value="grant_child_role">Grant child role</option>
          <option value="revoke_child_role">Revoke child role</option>
          <option value="grant_system_privilege">Grant system privilege</option>
          <option value="revoke_system_privilege">Revoke system privilege</option>
          <option value="grant_object_privilege">Grant object privilege</option>
          <option value="revoke_object_privilege">Revoke object privilege</option>
        </select></label>

        <label v-if="actionNeedsUser">Username<input v-model="actionUsername" maxlength="30" placeholder="APPUSER" :disabled="Boolean(actionPreview)" /></label>
        <label v-if="actionNeedsRole">Child role<input v-model="actionValue" list="oracle-role-catalog" maxlength="30" placeholder="APP_READ" :disabled="Boolean(actionPreview)" /></label>
        <template v-if="actionNeedsSystemPrivilege">
          <label>System privilege<input v-model="actionPrivilege" list="oracle-system-privilege-catalog" maxlength="128" placeholder="CREATE SESSION" :disabled="Boolean(actionPreview)" /></label>
        </template>
        <template v-if="actionNeedsObject">
          <div class="role-form-grid">
            <label>Owner<input v-model="actionOwner" maxlength="30" placeholder="APP" :disabled="Boolean(actionPreview)" /></label>
            <label>Object<input v-model="actionObject" maxlength="30" placeholder="ORDERS" :disabled="Boolean(actionPreview)" /></label>
          </div>
          <label>Object privilege<input v-model="actionPrivilege" list="oracle-object-privilege-catalog" maxlength="128" placeholder="SELECT" :disabled="Boolean(actionPreview)" /></label>
        </template>
        <label>Request / ticket reference <small>optional</small><input v-model="actionReference" maxlength="100" placeholder="REQ-12345" /></label>

        <datalist id="oracle-role-catalog"><option v-for="role in catalog?.roles ?? []" :key="role.name" :value="role.name" /></datalist>
        <datalist id="oracle-system-privilege-catalog"><option v-for="item in catalog?.system_privileges_catalog ?? []" :key="item" :value="item" /></datalist>
        <datalist id="oracle-object-privilege-catalog"><option v-for="item in catalog?.object_privileges_catalog ?? []" :key="item" :value="item" /></datalist>

        <div v-if="actionError" class="utility-warning">{{ actionError }}</div>
        <template v-if="actionPreview">
          <div v-for="warning in actionPreview.warnings" :key="warning" class="utility-warning" :class="{ 'role-elevated-warning': actionPreview.powerful }">{{ warning }}</div>
          <div class="sql-preview"><span>Exact statement</span><code>{{ actionPreview.statement }}</code></div>
        </template>

        <footer>
          <button v-if="!actionPreview" type="button" class="primary-button" :disabled="!canPreviewAction || actionLoading" @click="previewRoleAction">{{ actionLoading ? 'Previewing...' : 'Preview' }}</button>
          <button v-else type="button" class="primary-button" :disabled="!actionPreview.ready_to_execute || actionLoading" @click="executeRoleAction">{{ actionLoading ? 'Applying...' : 'Apply change' }}</button>
          <button v-if="actionPreview" type="button" class="secondary-button" :disabled="actionLoading" @click="actionPreview = null">Back</button>
          <button type="button" class="secondary-button" :disabled="actionLoading" @click="closeRoleAction">Cancel</button>
        </footer>
      </section>
    </div>

    <div v-if="showDrop && detail" class="role-modal-backdrop" @click.self="closeDropRole">
      <section class="role-modal role-drop-modal" role="dialog" aria-modal="true" :aria-label="`Drop Oracle role ${detail.name}`">
        <header><div><h3>Drop role · {{ detail.name }}</h3><p>This removes the role and all grants attached to it. Live impact is rebuilt before execution.</p></div><button type="button" @click="closeDropRole">×</button></header>
        <div v-if="dropLoading && !dropPreview" class="role-empty-state">Building live drop preview...</div>
        <div v-if="dropError" class="utility-warning">{{ dropError }}</div>
        <template v-if="dropPreview">
          <section class="role-summary-grid">
            <div><span>Users</span><strong>{{ dropPreview.role.members.length }}</strong></div>
            <div><span>Parent roles</span><strong>{{ dropPreview.role.parent_roles.length }}</strong></div>
            <div><span>Child roles</span><strong>{{ dropPreview.role.child_roles.length }}</strong></div>
            <div><span>Privileges</span><strong>{{ dropPreview.role.system_privileges.length + dropPreview.role.object_privileges.length }}</strong></div>
          </section>
          <div v-for="warning in dropPreview.warnings" :key="warning" class="utility-warning role-elevated-warning">{{ warning }}</div>
          <div class="sql-preview"><span>Exact statement</span><code>{{ dropPreview.statement }}</code></div>
          <label>Type <strong>{{ detail.name }}</strong> to confirm<input v-model="dropConfirmation" maxlength="30" :placeholder="detail.name" /></label>
          <label>Request / ticket reference <small>optional</small><input v-model="dropReference" maxlength="100" placeholder="REQ-12345" /></label>
        </template>
        <footer>
          <button type="button" class="role-drop-button solid" :disabled="!dropPreview || dropConfirmation.trim().toUpperCase() !== detail.name || dropLoading" @click="executeDropRole">{{ dropLoading ? 'Dropping...' : 'Drop role' }}</button>
          <button type="button" class="secondary-button" :disabled="dropLoading" @click="closeDropRole">Cancel</button>
        </footer>
      </section>
    </div>
  </div>
</template>

<style scoped>
.role-management-workspace { display: grid; gap: 1rem; }
.role-management-toolbar, .role-detail-header { display: flex; align-items: flex-start; justify-content: space-between; gap: 1rem; }
.role-management-toolbar h3, .role-detail-header h3 { margin: 0; }
.role-management-toolbar p, .role-detail-header p { margin: .25rem 0 0; color: var(--text-muted); }
.role-toolbar-actions, .role-action-strip { display: flex; flex-wrap: wrap; gap: .5rem; }
.role-layout { display: grid; grid-template-columns: minmax(19rem, .8fr) minmax(0, 1.6fr); gap: 1rem; align-items: start; }
.role-list-card, .role-detail-card { min-width: 0; border: 1px solid var(--border); border-radius: .85rem; padding: .85rem; background: var(--surface); }
.role-filter-row { display: flex; gap: .75rem; align-items: center; margin-bottom: .75rem; }
.role-filter-row input { flex: 1; }
.role-filter-row span { color: var(--text-muted); font-size: .85rem; white-space: nowrap; }
.role-row { cursor: pointer; }
.role-row:hover td, .role-row.selected td { background: color-mix(in srgb, var(--primary) 8%, var(--surface)); }
.role-row td:first-child { display: grid; gap: .15rem; }
.role-row small { color: var(--color-danger); }
.role-manageable { color: var(--color-success, #2e7d32); }
.role-protected { color: var(--text-muted); }
.role-empty-state { display: grid; gap: .35rem; min-height: 12rem; place-content: center; text-align: center; color: var(--text-muted); }
.role-title-line { display: flex; gap: .5rem; align-items: center; flex-wrap: wrap; }
.role-title-line h3 { font-size: 1.2rem; }
.role-elevated-pill, .role-manageable-pill, .role-protected-pill { border-radius: 999px; padding: .2rem .5rem; font-size: .75rem; border: 1px solid var(--border); }
.role-elevated-pill { border-color: var(--color-danger); color: var(--color-danger); }
.role-manageable-pill { color: var(--color-success, #2e7d32); }
.role-protected-pill { color: var(--text-muted); }
.role-summary-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: .65rem; margin: .9rem 0; }
.role-summary-grid > div { display: grid; gap: .2rem; border: 1px solid var(--border); border-radius: .7rem; padding: .65rem; }
.role-summary-grid span { color: var(--text-muted); font-size: .75rem; }
.role-summary-grid strong { font-size: 1rem; }
.role-action-strip { padding: .75rem 0; border-top: 1px solid var(--border); border-bottom: 1px solid var(--border); }
.role-drop-button { border: 1px solid var(--color-danger); color: var(--color-danger); background: transparent; border-radius: .55rem; padding: .55rem .8rem; cursor: pointer; }
.role-drop-button.solid { background: var(--color-danger); color: white; }
.role-drop-button:disabled { opacity: .5; cursor: not-allowed; }
.role-inspect-notice { padding: .75rem; border: 1px dashed var(--border); border-radius: .65rem; color: var(--text-muted); }
.role-detail-section { margin-top: .85rem; border: 1px solid var(--border); border-radius: .75rem; padding: .7rem; }
.role-detail-section summary { cursor: pointer; font-weight: 700; }
.role-detail-section :deep(.reusable-table-shell) { margin-top: .65rem; }
.role-chip-list { display: flex; flex-wrap: wrap; gap: .45rem; padding-top: .65rem; }
.role-chip-list span { border: 1px solid var(--border); border-radius: 999px; padding: .3rem .55rem; }
.link-action { border: 0; background: transparent; color: var(--primary); cursor: pointer; padding: .15rem; text-decoration: underline; }
.role-modal-backdrop { position: fixed; inset: 0; z-index: 80; display: grid; place-items: center; padding: 1rem; background: rgba(0, 0, 0, .48); }
.role-modal { width: min(44rem, 100%); max-height: calc(100vh - 2rem); overflow: auto; display: grid; gap: .85rem; background: var(--surface); border: 1px solid var(--border); border-radius: 1rem; padding: 1rem; box-shadow: 0 1rem 3rem rgba(0,0,0,.2); }
.role-modal > header { display: flex; justify-content: space-between; gap: 1rem; }
.role-modal > header h3 { margin: 0; }
.role-modal > header p { color: var(--text-muted); margin: .25rem 0 0; }
.role-modal > header > button { border: 0; background: transparent; font-size: 1.5rem; cursor: pointer; color: var(--text); }
.role-modal label { display: grid; gap: .35rem; font-weight: 600; }
.role-modal label small { color: var(--text-muted); font-weight: 400; }
.role-modal input, .role-modal select { width: 100%; }
.role-modal footer { display: flex; flex-wrap: wrap; gap: .55rem; justify-content: flex-end; }
.role-form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: .7rem; }
.sql-preview { display: grid; gap: .35rem; border: 1px solid var(--border); border-radius: .7rem; padding: .7rem; }
.sql-preview span { color: var(--text-muted); font-size: .75rem; }
.sql-preview code { overflow-wrap: anywhere; white-space: pre-wrap; }
.role-elevated-warning { border-color: var(--color-danger); }
@media (max-width: 980px) { .role-layout { grid-template-columns: 1fr; } }
@media (max-width: 680px) { .role-summary-grid { grid-template-columns: repeat(2, 1fr); } .role-form-grid { grid-template-columns: 1fr; } .role-management-toolbar, .role-detail-header { flex-direction: column; } }
</style>
