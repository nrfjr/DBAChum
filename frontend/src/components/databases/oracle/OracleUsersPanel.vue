<script setup lang="ts">
import {
  computed,
  onMounted,
  reactive,
  ref,
} from 'vue'

import {
  useOracleDbaStore,
  type OracleDatabaseUser,
  type OracleReferenceUser,
  type OracleCreateUserResult,
} from '@/stores/oracleDba'
import {
  useProvisioningStore,
  type ProvisioningPreviewResult,
} from '@/stores/provisioning'

const props = defineProps<{
  connectionId: string
}>()

const oracleStore = useOracleDbaStore()
const provisioningStore = useProvisioningStore()

const search = ref('')

type AccountFilter =
  | 'all'
  | 'open'
  | 'locked'
  | 'expired'

const filter = ref<AccountFilter>('all')

const users = computed(
  () =>
    oracleStore.users[
      props.connectionId
    ],
)

function matchesFilter(user: OracleDatabaseUser) {
  const status = user.status.toUpperCase()

  switch (filter.value) {
    case 'open':
      return status === 'OPEN'

    case 'locked':
      return status.includes('LOCKED')

    case 'expired':
      return status.includes('EXPIRED')

    default:
      return true
  }
}

const filteredUsers = computed(() => {
  const term = search.value
    .trim()
    .toLowerCase()

  return (users.value?.items ?? [])
    .filter(matchesFilter)
    .filter((user) => {
      if (!term) {
        return true
      }

      return [
        user.username,
        user.status,
        user.default_tablespace,
        user.temporary_tablespace,
        user.profile,
      ]
        .filter(Boolean)
        .some((value) =>
          String(value)
            .toLowerCase()
            .includes(term),
        )
    })
})

function formatDate(value: string | null) {
  if (!value) {
    return '—'
  }

  const parsed = new Date(value)

  if (Number.isNaN(parsed.getTime())) {
    return value
  }

  return parsed.toLocaleString()
}

type CreateStep = 'details' | 'review' | 'success'

interface CreateUserForm {
  username: string
  password: string
  referenceUsername: string
  defaultTablespace: string
  temporaryTablespace: string
  profile: string
  requestReference: string
  requestorName: string
  firstName: string
  middleName: string
  lastName: string
  employeeId: string
  remarks: string
  provisioningProfileId: string
}

function emptyCreateForm(): CreateUserForm {
  return {
    username: '',
    password: '',
    referenceUsername: '',
    defaultTablespace: '',
    temporaryTablespace: '',
    profile: '',
    requestReference: '',
    requestorName: '',
    firstName: '',
    middleName: '',
    lastName: '',
    employeeId: '',
    remarks: '',
    provisioningProfileId: '',
  }
}

const createOpen = ref(false)
const createStep = ref<CreateStep>('details')
const createError = ref<string | null>(null)
const reference = ref<OracleReferenceUser | null>(null)
const selectedRoles = ref<string[]>([])
const createResult = ref<OracleCreateUserResult | null>(null)
const showPassword = ref(false)
const provisioningPreview = ref<ProvisioningPreviewResult | null>(null)
const previewLoading = ref(false)
const createForm = reactive<CreateUserForm>(emptyCreateForm())

const availableProvisioningProfiles = computed(() =>
  provisioningStore.profilesByConnection[props.connectionId] ?? [],
)

const selectedProvisioningProfile = computed(() =>
  availableProvisioningProfiles.value.find(
    (profile) => profile.id === createForm.provisioningProfileId,
  ) ?? null,
)

function resetCreate() {
  Object.assign(createForm, emptyCreateForm())
  createStep.value = 'details'
  createError.value = null
  reference.value = null
  selectedRoles.value = []
  createResult.value = null
  provisioningPreview.value = null
  previewLoading.value = false
  showPassword.value = false
}

function openCreate() {
  resetCreate()
  createOpen.value = true
}

function closeCreate() {
  createOpen.value = false
  resetCreate()
}

function normalizePersonName(value: string) {
  return value
    .normalize('NFKD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/[^A-Za-z ]/g, '')
    .replace(/\s+/g, ' ')
    .trim()
}

function normalizeNameField(field: 'firstName' | 'middleName' | 'lastName') {
  createForm[field] = normalizePersonName(createForm[field])
}

function cleanUsernamePart(value: string) {
  return normalizePersonName(value)
    .toUpperCase()
    .replace(/[^A-Z]/g, '')
}

function cleanEmployeeIdPart(value: string) {
  return value
    .replace(/[^A-Za-z0-9]/g, '')
    .toUpperCase()
}

function randomIndex(max: number) {
  const values = new Uint32Array(1)
  crypto.getRandomValues(values)
  return (values.at(0) ?? 0) % max
}

function randomCharacter(source: string) {
  return source.charAt(randomIndex(source.length))
}

function generatePassword() {
  const letters = 'abcdefghijklmnopqrstuvwxyz'
  const digits = '0123456789'

  const letterPart = Array.from(
    { length: 3 },
    () => randomCharacter(letters),
  ).join('')

  const digitPart = Array.from(
    { length: 5 },
    () => randomCharacter(digits),
  ).join('')

  createForm.password = `${letterPart}${digitPart}`
  showPassword.value = true
}

function generateUsername() {
  createError.value = null

  const first = cleanUsernamePart(createForm.firstName)
  const middle = cleanUsernamePart(createForm.middleName)
  const last = cleanUsernamePart(createForm.lastName)
  const employeeId = cleanEmployeeIdPart(createForm.employeeId)

  if (!first || !last || !employeeId) {
    createError.value =
      'First name, last name and ID are required to generate a username.'
    return
  }

  const generated = [
    first.charAt(0),
    middle ? middle.charAt(0) : '',
    last,
    employeeId,
  ].join('')

  if (generated.length > 30) {
    createError.value =
      'Generated username exceeds the 30-character Oracle compatibility limit.'
    return
  }

  createForm.username = generated
}

async function reviewCreate() {
  createError.value = null
  provisioningPreview.value = null

  const username = createForm.username
    .trim()
    .toUpperCase()

  if (!/^[A-Z][A-Z0-9_$#]{0,29}$/.test(username)) {
    createError.value =
      'Username must be 1-30 characters and use letters, numbers, _, $, or #.'
    return
  }

  if (createForm.password.length < 8) {
    createError.value =
      'Password must contain at least 8 characters.'
    return
  }

  createForm.firstName = normalizePersonName(createForm.firstName)
  createForm.middleName = normalizePersonName(createForm.middleName)
  createForm.lastName = normalizePersonName(createForm.lastName)
  createForm.employeeId = cleanEmployeeIdPart(createForm.employeeId)
  createForm.username = username

  const referenceUsername = createForm.referenceUsername
    .trim()
    .toUpperCase()

  try {
    if (referenceUsername) {
      const inspected = await oracleStore.loadReferenceUser(
        props.connectionId,
        referenceUsername,
      )

      reference.value = inspected
      createForm.referenceUsername = inspected.username

      selectedRoles.value = inspected.roles
        .filter((role) => !role.sensitive)
        .map((role) => role.name)

      if (!createForm.defaultTablespace) {
        createForm.defaultTablespace = inspected.default_tablespace ?? ''
      }
      if (!createForm.temporaryTablespace) {
        createForm.temporaryTablespace = inspected.temporary_tablespace ?? ''
      }
      if (!createForm.profile) {
        createForm.profile = inspected.profile ?? ''
      }
    } else {
      reference.value = null
      selectedRoles.value = []
    }

    if (createForm.provisioningProfileId) {
      previewLoading.value = true
      provisioningPreview.value = await provisioningStore.previewForConnection(
        props.connectionId,
        createForm.provisioningProfileId,
        {
          username: createForm.username,
          password: createForm.password,
          first_name: createForm.firstName || null,
          middle_name: createForm.middleName || null,
          last_name: createForm.lastName || null,
          employee_id: createForm.employeeId || null,
          reference_user: createForm.referenceUsername || null,
          requestor: createForm.requestorName.trim() || null,
          request_reference: createForm.requestReference.trim() || null,
          remarks: createForm.remarks.trim() || null,
        },
      )
      createForm.username = provisioningPreview.value.username
    }

    createStep.value = 'review'
  } catch (error) {
    createError.value =
      error instanceof Error
        ? error.message
        : 'Unable to build the user creation review.'
  } finally {
    previewLoading.value = false
  }
}

function roleSelected(roleName: string) {
  return selectedRoles.value.includes(roleName)
}

function setRoleSelected(
  roleName: string,
  checked: boolean,
) {
  if (checked) {
    if (!selectedRoles.value.includes(roleName)) {
      selectedRoles.value.push(roleName)
    }
  } else {
    selectedRoles.value = selectedRoles.value.filter(
      (role) => role !== roleName,
    )
  }
}


function handleRoleToggle(
  roleName: string,
  event: Event,
) {
  const target = event.target as HTMLInputElement
  setRoleSelected(roleName, target.checked)
}

async function createUser() {
  createError.value = null

  try {
    createResult.value = await oracleStore.createUser(
      props.connectionId,
      {
        username: createForm.username,
        password: createForm.password,
        reference_username:
          createForm.referenceUsername || null,
        roles: [...selectedRoles.value],
        default_tablespace:
          createForm.defaultTablespace || null,
        temporary_tablespace:
          createForm.temporaryTablespace || null,
        profile: createForm.profile || null,
        request_reference:
          createForm.requestReference.trim() || null,
        requestor_name:
          createForm.requestorName.trim() || null,
        remarks:
          createForm.remarks.trim() || null,
        first_name:
          normalizePersonName(createForm.firstName) || null,
        middle_name:
          normalizePersonName(createForm.middleName) || null,
        last_name:
          normalizePersonName(createForm.lastName) || null,
        employee_id:
          cleanEmployeeIdPart(createForm.employeeId) || null,
        generate_ldif: false,
        ldap_profile_id: null,
      },
    )

    // Do not retain the submitted database password in component state.
    createForm.password = ''
    createStep.value = 'success'

    await oracleStore.loadUsers(
      props.connectionId,
    )
  } catch (error) {
    createError.value =
      error instanceof Error
        ? error.message
        : 'Unable to create Oracle user.'
  }
}

onMounted(() => {
  oracleStore.loadUsers(
    props.connectionId,
  )
  provisioningStore.loadProfilesForConnection(props.connectionId)
})
</script>

<template>
  <section>
    <div class="utility-toolbar">
      <div>
        <h2>Users &amp; Schemas</h2>
        <p>
          Oracle accounts, status and schema defaults.
        </p>
      </div>

      <div class="utility-toolbar-actions">
        <button
          type="button"
          class="primary-button"
          @click="openCreate"
        >
          Create user
        </button>

        <button
          type="button"
          class="secondary-button"
          :disabled="oracleStore.loadingUsers"
          @click="oracleStore.loadUsers(connectionId)"
        >
          {{
            oracleStore.loadingUsers
              ? 'Refreshing...'
              : 'Refresh'
          }}
        </button>
      </div>
    </div>

    <p
      v-if="oracleStore.usersError"
      class="login-error"
    >
      {{ oracleStore.usersError }}
    </p>

    <template v-else-if="users">
      <div
        v-if="!users.available"
        class="utility-warning"
      >
        User inventory is unavailable.

        <div>
          {{ users.warning }}
        </div>

        <div>
          The Oracle connection needs access to DBA_USERS.
          You can grant the required catalog access to the service account,
          or explicitly configure SYSDBA mode in Connection Settings.
        </div>
      </div>

      <template v-else>
        <div class="utility-summary">
          <button
            type="button"
            :class="{ active: filter === 'all' }"
            @click="filter = 'all'"
          >
            <span>Total</span>
            <strong>{{ users.total }}</strong>
          </button>

          <button
            type="button"
            :class="{ active: filter === 'open' }"
            @click="filter = 'open'"
          >
            <span>Open</span>
            <strong>{{ users.open }}</strong>
          </button>

          <button
            type="button"
            :class="{ active: filter === 'locked' }"
            @click="filter = 'locked'"
          >
            <span>Locked</span>
            <strong>{{ users.locked }}</strong>
          </button>

          <button
            type="button"
            :class="{ active: filter === 'expired' }"
            @click="filter = 'expired'"
          >
            <span>Expired</span>
            <strong>{{ users.expired }}</strong>
          </button>
        </div>

        <div class="utility-filter-row">
          <label>
            <span>Find account</span>
            <input
              v-model="search"
              type="search"
              placeholder="Username, status, tablespace or profile"
            />
          </label>

          <span>
            {{ filteredUsers.length }} shown
          </span>
        </div>

        <div class="utility-table-wrap">
          <table class="utility-table">
            <thead>
              <tr>
                <th>Username</th>
                <th>Status</th>
                <th>Default tablespace</th>
                <th>Temporary tablespace</th>
                <th>Profile</th>
                <th>Created</th>
                <th>Expiry</th>
              </tr>
            </thead>

            <tbody>
              <tr
                v-for="user in filteredUsers"
                :key="user.username"
              >
                <td>
                  <strong>{{ user.username }}</strong>
                </td>

                <td>
                  {{ user.status }}
                </td>

                <td>
                  {{ user.default_tablespace ?? '—' }}
                </td>

                <td>
                  {{ user.temporary_tablespace ?? '—' }}
                </td>

                <td>
                  {{ user.profile ?? '—' }}
                </td>

                <td>
                  {{ formatDate(user.created_at) }}
                </td>

                <td>
                  {{ formatDate(user.expiry_date) }}
                </td>
              </tr>

              <tr v-if="filteredUsers.length === 0">
                <td colspan="7">
                  No matching database accounts.
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </template>
    </template>

    <div
      v-if="createOpen"
      class="modal-backdrop"
      @click.self="closeCreate"
    >
      <section
        class="modal-panel oracle-user-modal"
        role="dialog"
        aria-modal="true"
        aria-label="Create Oracle user"
      >
        <div class="modal-header">
          <div>
            <h2>Create Oracle user</h2>
            <p v-if="createStep === 'details'">
              Define the account and optionally inspect a reference user.
            </p>
            <p v-else-if="createStep === 'review'">
              Review exactly what DBAChum will change before execution.
            </p>
            <p v-else>
              Provisioning completed.
            </p>
          </div>

          <button
            type="button"
            class="modal-close"
            aria-label="Close"
            @click="closeCreate"
          >
            ×
          </button>
        </div>

        <form
          v-if="createStep === 'details'"
          class="connection-form oracle-user-form"
          @submit.prevent="reviewCreate"
        >
          <label>
            Application provisioning
            <select v-model="createForm.provisioningProfileId">
              <option value="">No provisioning — schema/user only</option>
              <option
                v-for="profile in availableProvisioningProfiles"
                :key="profile.id"
                :value="profile.id"
                :disabled="!profile.ready"
              >
                {{ profile.name }}{{ profile.ready ? '' : ' · Needs attention' }}
              </option>
            </select>
            <small>Only provisioning profiles whose parent database connection is this database appear here. Each profile may use separate application connections for its table steps.</small>
          </label>

          <div
            v-if="selectedProvisioningProfile && !selectedProvisioningProfile.ready"
            class="utility-warning oracle-create-warning"
          >
            {{ selectedProvisioningProfile.issues.join(' ') }}
          </div>

          <label>
            Username

            <input
              v-model="createForm.username"
              required
              maxlength="30"
              autocomplete="off"
              placeholder="JMSANTOS12345"
            />
          </label>

          <details class="oracle-username-generator">
            <summary>Generate from employee details</summary>

            <div class="connection-form-row">
              <label>
                First name
                <input v-model="createForm.firstName" autocomplete="off" @blur="normalizeNameField('firstName')" />
              </label>

              <label>
                Middle name
                <span class="optional-label">Optional</span>
                <input v-model="createForm.middleName" autocomplete="off" @blur="normalizeNameField('middleName')" />
              </label>
            </div>

            <div class="connection-form-row">
              <label>
                Last name
                <input v-model="createForm.lastName" autocomplete="off" @blur="normalizeNameField('lastName')" />
              </label>

              <label>
                ID
                <input v-model="createForm.employeeId" autocomplete="off" />
              </label>
            </div>

            <button
              type="button"
              class="secondary-button"
              @click="generateUsername"
            >
              Generate username
            </button>
          </details>

          <label>
            Initial password

            <input
              v-model="createForm.password"
              required
              :type="showPassword ? 'text' : 'password'"
              minlength="8"
              maxlength="128"
              autocomplete="new-password"
              placeholder="At least 8 characters"
            />

            <span class="oracle-password-actions">
              <button
                type="button"
                class="secondary-button"
                @click="generatePassword"
              >
                Generate password
              </button>

              <button
                type="button"
                class="secondary-button"
                @click="showPassword = !showPassword"
              >
                {{ showPassword ? 'Hide password' : 'Show password' }}
              </button>
            </span>

            <small>
              Type the requested custom password, or use Generate password for the current 3-letter + 5-digit pattern.
            </small>
          </label>

          <label>
            Reference user
            <span class="optional-label">Optional</span>

            <input
              v-model="createForm.referenceUsername"
              maxlength="30"
              autocomplete="off"
              placeholder="Existing user whose roles should be reviewed"
            />

            <small>
              DBAChum copies only the roles you approve on the review screen.
              Direct system privileges are never copied in this phase.
            </small>
          </label>

          <div class="connection-form-row">
            <label>
              Default tablespace
              <span class="optional-label">Optional</span>
              <input
                v-model="createForm.defaultTablespace"
                maxlength="30"
                placeholder="Uses reference/default when blank"
              />
            </label>

            <label>
              Temporary tablespace
              <span class="optional-label">Optional</span>
              <input
                v-model="createForm.temporaryTablespace"
                maxlength="30"
                placeholder="Uses reference/default when blank"
              />
            </label>
          </div>

          <label>
            Profile
            <span class="optional-label">Optional</span>
            <input
              v-model="createForm.profile"
              maxlength="30"
              placeholder="Uses reference/default when blank"
            />
          </label>

          <div class="connection-form-row">
            <label>
              Requestor
              <span class="optional-label">Optional</span>
              <input
                v-model="createForm.requestorName"
                maxlength="200"
                placeholder="Requestor full name"
              />
            </label>

            <label>
              Request / ticket reference
              <span class="optional-label">Optional</span>
              <input
                v-model="createForm.requestReference"
                maxlength="100"
                placeholder="REQ-12345"
              />
            </label>
          </div>

          <label>
            Remarks
            <span class="optional-label">Optional</span>
            <textarea
              v-model="createForm.remarks"
              rows="3"
              maxlength="1000"
              placeholder="Reason, access note, or provisioning remarks"
            ></textarea>
          </label>

          <p v-if="createError" class="login-error">
            {{ createError }}
          </p>

          <div class="connection-form-actions">
            <button
              type="submit"
              class="primary-button"
              :disabled="oracleStore.loadingReference || previewLoading"
            >
              {{
                previewLoading
                  ? 'Building provisioning preview...'
                  : oracleStore.loadingReference
                    ? 'Inspecting reference...'
                    : 'Review'
              }}
            </button>

            <button
              type="button"
              class="secondary-button"
              @click="closeCreate"
            >
              Cancel
            </button>
          </div>
        </form>

        <div
          v-else-if="createStep === 'review'"
          class="oracle-user-review"
        >
          <div class="oracle-user-review-summary">
            <div>
              <span>New account</span>
              <strong>{{ createForm.username }}</strong>
            </div>

            <div>
              <span>Provisioning</span>
              <strong>{{ selectedProvisioningProfile?.name ?? 'No provisioning' }}</strong>
            </div>

            <div>
              <span>Reference user</span>
              <strong>{{ reference?.username ?? 'None' }}</strong>
            </div>

            <div>
              <span>Default tablespace</span>
              <strong>{{ createForm.defaultTablespace || 'Database default' }}</strong>
            </div>

            <div>
              <span>Temporary tablespace</span>
              <strong>{{ createForm.temporaryTablespace || 'Database default' }}</strong>
            </div>

            <div>
              <span>Profile</span>
              <strong>{{ createForm.profile || 'Database default' }}</strong>
            </div>
          </div>

          <section v-if="reference" class="oracle-role-review">
            <div>
              <h3>Reference roles</h3>
              <p>
                Select the roles to copy. ADMIN OPTION is intentionally not copied.
              </p>
            </div>

            <div
              v-if="reference.roles.length === 0"
              class="empty-state"
            >
              Reference user has no role grants.
            </div>

            <template v-else>
              <label
                v-for="role in reference.roles"
                :key="role.name"
                class="oracle-role-option"
                :class="{ blocked: role.sensitive }"
              >
                <input
                  type="checkbox"
                  :checked="roleSelected(role.name)"
                  :disabled="role.sensitive"
                  @change="handleRoleToggle(role.name, $event)"
                />

                <span>
                  <strong>{{ role.name }}</strong>
                  <small>
                    {{ role.default_role ? 'Default role' : 'Non-default role' }}
                    <template v-if="role.admin_option"> · ADMIN OPTION on reference</template>
                    <template v-if="role.sensitive"> · blocked as sensitive</template>
                  </small>
                </span>
              </label>
            </template>
          </section>

          <div
            v-for="warning in reference?.warnings ?? []"
            :key="warning"
            class="utility-warning oracle-create-warning"
          >
            {{ warning }}
          </div>

          <section
            v-if="reference?.system_privileges.length"
            class="oracle-system-privileges"
          >
            <h3>Direct system privileges — review only</h3>
            <p>
              These are visible so you can compare access, but DBAChum will not grant them automatically.
            </p>

            <div class="oracle-privilege-list">
              <span
                v-for="privilege in reference.system_privileges"
                :key="privilege.name"
              >
                {{ privilege.name }}
                <template v-if="privilege.admin_option"> · ADMIN OPTION</template>
              </span>
            </div>
          </section>

          <section v-if="provisioningPreview" class="oracle-provisioning-preview">
            <div class="preview-callout">
              <strong>Phase 4A preview only — no database, application-table or LDAP changes were made.</strong>
              <span>The selected profile is a child of this database connection. Phase 4B will execute the reviewed lifecycle.</span>
            </div>

            <div class="preview-summary-grid">
              <div>
                <span>Oracle account</span>
                <strong>{{ provisioningPreview.account_exists ? 'Existing → ALTER / reconcile' : 'Not found → CREATE' }}</strong>
              </div>
              <div>
                <span>Parent database</span>
                <strong>{{ provisioningPreview.schema_connection_name }}</strong>
              </div>
              <div>
                <span>Requester IP</span>
                <strong>{{ provisioningPreview.requester_ip || 'Unavailable' }}</strong>
              </div>
            </div>

            <section class="preview-section">
              <h3>Application upsert steps</h3>
              <article
                v-for="step in provisioningPreview.table_steps"
                :key="`${step.index}-${step.name}`"
                class="preview-step"
              >
                <header>
                  <strong>Step {{ step.index }} · {{ step.name }}</strong>
                  <span>{{ step.connection_name }} · {{ step.owner }}.{{ step.table_name }}</span>
                </header>
                <div class="preview-step-plan">
                  <strong>{{ step.planned_action.toUpperCase() }}</strong>
                  <span>Matched {{ step.existing_rows }} row{{ step.existing_rows === 1 ? '' : 's' }} by {{ step.match_columns.join(' + ') }}</span>
                </div>
                <div class="preview-table-wrap">
                  <table>
                    <thead>
                      <tr><th>Column</th><th>Source</th><th>Resolved preview</th></tr>
                    </thead>
                    <tbody>
                      <tr v-for="column in step.columns" :key="column.column_name">
                        <td>{{ column.column_name }}</td>
                        <td>{{ column.source }}</td>
                        <td><code>{{ column.display_value ?? 'NULL / blank' }}</code></td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </article>
              <p v-if="provisioningPreview.table_steps.length === 0" class="empty-state">No application-table steps are configured.</p>
            </section>

            <section class="preview-section">
              <h3>LDAP</h3>
              <p v-if="provisioningPreview.ldap.enabled">
                {{ provisioningPreview.ldap.profile_name }} · template validated · output
                <strong>{{ provisioningPreview.ldap.filename }}</strong>
              </p>
              <p v-else>LDAP is not enabled for this provisioning profile.</p>
            </section>

            <div v-if="provisioningPreview.warnings.length" class="utility-warning oracle-create-warning">
              <ul>
                <li v-for="warning in provisioningPreview.warnings" :key="warning">{{ warning }}</li>
              </ul>
            </div>
          </section>

          <div class="utility-warning oracle-create-warning">
            <template v-if="provisioningPreview">
              Phase 4B will CREATE or ALTER the Oracle account, reconcile roles, then upsert the configured application rows. Duplicate matches block execution.
            </template>
            <template v-else>
              This action creates a real Oracle account and grants the selected roles. The password will not be stored in DBAChum's action history.
            </template>
          </div>

          <p v-if="createError" class="login-error">
            {{ createError }}
          </p>

          <div class="connection-form-actions">
            <button
              v-if="!provisioningPreview"
              type="button"
              class="primary-button"
              :disabled="oracleStore.creatingUser"
              @click="createUser"
            >
              {{
                oracleStore.creatingUser
                  ? 'Creating user...'
                  : `Create ${createForm.username}`
              }}
            </button>

            <button
              v-else
              type="button"
              class="primary-button"
              disabled
              title="Phase 4B will enable profile execution"
            >
              Provision {{ createForm.username }} (Phase 4B)
            </button>

            <button
              type="button"
              class="secondary-button"
              :disabled="oracleStore.creatingUser"
              @click="createStep = 'details'"
            >
              Back
            </button>
          </div>
        </div>

        <div
          v-else
          class="oracle-user-success"
        >
          <strong>{{ createResult?.username }}</strong>
          <p>
            Oracle account created successfully with
            {{ createResult?.roles_applied.length ?? 0 }} role(s).
          </p>
          <small>
            Audit ID: {{ createResult?.audit_id }}
          </small>
          <small v-if="createResult?.requester_ip">
            Requester IP: {{ createResult.requester_ip }}
          </small>

          <div class="connection-form-actions">
            <button
              type="button"
              class="primary-button"
              @click="closeCreate"
            >
              Done
            </button>
          </div>
        </div>
      </section>
    </div>
  </section>
</template>


<style scoped>
.oracle-provisioning-preview { display: grid; gap: 1rem; margin-top: 1rem; }
.preview-callout { display: flex; flex-direction: column; gap: .2rem; padding: .8rem; border: 1px solid var(--border-color); border-radius: .7rem; }
.preview-summary-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: .75rem; }
.preview-summary-grid > div { display: grid; gap: .2rem; padding: .7rem; border: 1px solid var(--border-color); border-radius: .65rem; }
.preview-summary-grid span { font-size: .78rem; opacity: .7; }
.preview-section { display: grid; gap: .7rem; }
.preview-section h3 { margin: 0; }
.preview-step { border: 1px solid var(--border-color); border-radius: .7rem; overflow: hidden; }
.preview-step header { display: flex; justify-content: space-between; gap: 1rem; padding: .7rem .8rem; border-bottom: 1px solid var(--border-color); }
.preview-step header span { opacity: .72; font-size: .84rem; }
.preview-step-plan { display: flex; gap: .8rem; align-items: center; padding: .65rem .8rem; border-bottom: 1px solid var(--border-color); }
.preview-step-plan span { opacity: .75; font-size: .82rem; }
.preview-table-wrap { overflow-x: auto; }
.preview-table-wrap table { width: 100%; border-collapse: collapse; }
.preview-table-wrap th, .preview-table-wrap td { padding: .65rem .8rem; text-align: left; border-bottom: 1px solid var(--border-color); }
.preview-table-wrap tr:last-child td { border-bottom: 0; }
.preview-table-wrap code { white-space: pre-wrap; overflow-wrap: anywhere; }
@media (max-width: 900px) {
  .preview-summary-grid { grid-template-columns: 1fr; }
  .preview-step header { align-items: flex-start; flex-direction: column; }
}
</style>
