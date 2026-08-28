<script setup lang="ts">
import {
  computed,
  onBeforeUnmount,
  onMounted,
  reactive,
  ref,
  watch,
} from 'vue'

import {
  useOracleDbaStore,
  type OracleDatabaseUser,
  type OracleReferenceUser,
  type OracleCreateUserResult,
  type OracleUserLifecycleState,
  type OracleUserEditPreview,
  type OracleUserAccessInspector,
  type OracleAccessGrantSource,
} from '@/stores/oracleDba'
import OracleBulkProvisionModal from '@/components/databases/oracle/OracleBulkProvisionModal.vue'
import ScrollableDataTable from '@/components/common/ScrollableDataTable.vue'

import {
  useProvisioningStore,
  type ProvisioningExecutionResult,
  type ProvisioningPreviewResult,
  type ProvisioningRunSummary,
  type OracleUserDeprovisionPreview,
  type OracleUserDeprovisionResult,
} from '@/stores/provisioning'

const props = defineProps<{
  connectionId: string
  active?: boolean
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

function formatDeprovisionMatch(values: Record<string, string | null>) {
  return Object.entries(values)
    .map(([key, value]) => `${key}=${value ?? 'NULL'}`)
    .join(', ')
}

type CreateStep = 'identity' | 'access' | 'review' | 'success'

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
const createStep = ref<CreateStep>('identity')
const createError = ref<string | null>(null)
const reference = ref<OracleReferenceUser | null>(null)
const selectedRoles = ref<string[]>([])
const createResult = ref<OracleCreateUserResult | null>(null)
const showPassword = ref(false)
const provisioningPreview = ref<ProvisioningPreviewResult | null>(null)
const provisioningResult = ref<ProvisioningExecutionResult | null>(null)
const previewLoading = ref(false)
const provisioningExecuting = ref(false)
const createForm = reactive<CreateUserForm>(emptyCreateForm())
const createFieldErrors = reactive<Record<string, string>>({})
const usernameChecking = ref(false)
const bulkCreateOpen = ref(false)
const createActionsOpen = ref(false)
const resultPassword = ref('')
const summaryCopyNotice = ref('')

const historyOpen = ref(false)
const historyLoading = ref(false)
const historyError = ref<string | null>(null)
const retryingRunId = ref<string | null>(null)
const retryPasswordRun = ref<ProvisioningRunSummary | null>(null)
const retryPassword = ref('')
const retryShowPassword = ref(false)
const deprovisionLoadingRunId = ref<string | null>(null)
const deprovisionTargetUsername = ref<string | null>(null)
const deprovisionError = ref<string | null>(null)
const deprovisionPreview = ref<OracleUserDeprovisionPreview | null>(null)
const deprovisionExecuting = ref(false)
const deprovisionConfirmation = ref('')
const deprovisionRequestReference = ref('')
const deprovisionResult = ref<OracleUserDeprovisionResult | null>(null)

const actionMenuUsername = ref<string | null>(null)
const actionMenuPosition = ref({ top: 0, left: 0 })
const actionNotice = ref<string | null>(null)

const inspectorTargetUsername = ref<string | null>(null)
const inspectorLoading = ref(false)
const inspectorError = ref<string | null>(null)
const inspector = ref<OracleUserAccessInspector | null>(null)
const inspectorObjectSearch = ref('')

const editTargetUsername = ref<string | null>(null)
const editLoading = ref(false)
const editExecuting = ref(false)
const editError = ref<string | null>(null)
const editState = ref<OracleUserLifecycleState | null>(null)
const editPreview = ref<OracleUserEditPreview | null>(null)
const editRoleSearch = ref('')
const editRequestReference = ref('')
const editSelectedRoles = ref<string[]>([])
const editForm = reactive({
  defaultTablespace: '',
  temporaryTablespace: '',
  profile: '',
  locked: false,
})

const passwordTargetUsername = ref<string | null>(null)
const passwordValue = ref('')
const passwordConfirm = ref('')
const passwordShow = ref(false)
const passwordRequestReference = ref('')
const passwordExecuting = ref(false)
const passwordError = ref<string | null>(null)

type AccountAction = 'lock' | 'unlock' | 'expire_password'
const accountActionTargetUsername = ref<string | null>(null)
const accountAction = ref<AccountAction | null>(null)
const accountActionRequestReference = ref('')
const accountActionExecuting = ref(false)
const accountActionError = ref<string | null>(null)

const provisioningRuns = computed(() =>
  provisioningStore.runsByConnection[props.connectionId] ?? [],
)


function toggleProvisioningHistory() {
  historyOpen.value = !historyOpen.value
}

async function loadProvisioningHistory() {
  historyLoading.value = true
  historyError.value = null
  try {
    await provisioningStore.loadRunsForConnection(props.connectionId)
  } catch (error) {
    historyError.value = error instanceof Error
      ? error.message
      : 'Unable to load provisioning history.'
  } finally {
    historyLoading.value = false
  }
}

async function performRetry(run: ProvisioningRunSummary, password: string | null) {
  retryingRunId.value = run.run_id
  historyError.value = null
  try {
    provisioningResult.value = await provisioningStore.retryRun(
      props.connectionId,
      run.run_id,
      password,
    )
    retryPasswordRun.value = null
    retryPassword.value = ''
    retryShowPassword.value = false
    await oracleStore.loadUsers(props.connectionId)
    await loadProvisioningHistory()
  } catch (error) {
    historyError.value = error instanceof Error
      ? error.message
      : 'Unable to retry the provisioning run.'
  } finally {
    retryingRunId.value = null
  }
}

function retryLabel(run: ProvisioningRunSummary) {
  return run.retry_count > 0 ? `Retry #${run.retry_count + 1}` : 'Retry'
}

async function retryRun(run: ProvisioningRunSummary) {
  // No confirmation dialog: retry either starts immediately or asks only for
  // the non-persisted password when a remaining step actually needs it.
  if (run.password_required) {
    retryPasswordRun.value = run
    retryPassword.value = ''
    retryShowPassword.value = false
    return
  }
  await performRetry(run, null)
}

async function submitRetryPassword() {
  if (!retryPasswordRun.value) return
  if (retryPassword.value.length < 8) {
    historyError.value = 'Provisioning password must contain at least 8 characters.'
    return
  }
  const run = retryPasswordRun.value
  const password = retryPassword.value
  await performRetry(run, password)
  // Drop the password from component state immediately after the request.
  retryPassword.value = ''
}

function cancelRetryPassword() {
  retryPassword.value = ''
  retryPasswordRun.value = null
  retryShowPassword.value = false
}

function closeActionMenu() {
  actionMenuUsername.value = null
}

function toggleActionMenu(user: OracleDatabaseUser, event: Event) {
  event.stopPropagation()

  if (actionMenuUsername.value === user.username) {
    closeActionMenu()
    return
  }

  const button = event.currentTarget as HTMLElement | null
  if (button) {
    const rect = button.getBoundingClientRect()
    const menuWidth = 190
    const menuHeightEstimate = 300
    const gap = 6
    const viewportPadding = 8
    const left = Math.min(
      Math.max(viewportPadding, rect.right - menuWidth),
      Math.max(viewportPadding, window.innerWidth - menuWidth - viewportPadding),
    )
    const belowTop = rect.bottom + gap
    const top = belowTop + menuHeightEstimate <= window.innerHeight
      ? belowTop
      : Math.max(viewportPadding, rect.top - menuHeightEstimate - gap)

    actionMenuPosition.value = { top, left }
  }

  actionMenuUsername.value = user.username
}

function documentClickClosesActionMenu() {
  closeActionMenu()
  createActionsOpen.value = false
}

watch(
  () => props.active,
  (active) => {
    if (active === false) {
      closeActionMenu()
      createActionsOpen.value = false
    }
  },
)

function formatAccessSource(source: OracleAccessGrantSource) {
  if (source.kind === 'direct') return 'Direct'
  if (source.kind === 'public') return 'PUBLIC'
  if (source.via.length) return `via ${source.via.join(' → ')}`
  return source.kind
}

const filteredInspectorObjectPrivileges = computed(() => {
  const value = inspector.value
  if (!value) return []
  const term = inspectorObjectSearch.value.trim().toLowerCase()
  if (!term) return value.object_privileges
  return value.object_privileges.filter((item) =>
    [
      item.owner,
      item.object_name,
      item.column_name,
      item.privilege,
      ...item.sources.flatMap((source) => source.via),
    ]
      .filter(Boolean)
      .some((candidate) => String(candidate).toLowerCase().includes(term)),
  )
})

async function openAccessInspector(user: OracleDatabaseUser) {
  closeActionMenu()
  inspectorTargetUsername.value = user.username
  inspectorLoading.value = true
  inspectorError.value = null
  inspector.value = null
  inspectorObjectSearch.value = ''
  try {
    inspector.value = await oracleStore.loadUserAccessInspector(
      props.connectionId,
      user.username,
    )
  } catch (error) {
    inspectorError.value = error instanceof Error
      ? error.message
      : 'Unable to inspect Oracle access.'
  } finally {
    inspectorLoading.value = false
  }
}

function closeAccessInspector() {
  inspectorTargetUsername.value = null
  inspectorLoading.value = false
  inspectorError.value = null
  inspector.value = null
  inspectorObjectSearch.value = ''
}

function editRoleSelected(roleName: string) {
  return editSelectedRoles.value.includes(roleName)
}

function setEditRoleSelected(roleName: string, checked: boolean) {
  if (checked) {
    if (!editSelectedRoles.value.includes(roleName)) {
      editSelectedRoles.value.push(roleName)
    }
  } else {
    editSelectedRoles.value = editSelectedRoles.value.filter((role) => role !== roleName)
  }
  editPreview.value = null
}

function handleEditRoleToggle(roleName: string, event: Event) {
  const target = event.target as HTMLInputElement
  setEditRoleSelected(roleName, target.checked)
}

const filteredEditRoles = computed(() => {
  const state = editState.value
  if (!state) return []
  const term = editRoleSearch.value.trim().toLowerCase()
  const current = new Set(state.roles.map((role) => role.name))
  return [...state.available_roles]
    .filter((role) => !term || role.name.toLowerCase().includes(term))
    .sort((a, b) => {
      const aCurrent = current.has(a.name) ? 0 : 1
      const bCurrent = current.has(b.name) ? 0 : 1
      if (aCurrent !== bCurrent) return aCurrent - bCurrent
      return a.name.localeCompare(b.name)
    })
})

function editPayload() {
  return {
    roles: [...editSelectedRoles.value],
    default_tablespace: editForm.defaultTablespace.trim() || null,
    temporary_tablespace: editForm.temporaryTablespace.trim() || null,
    profile: editForm.profile.trim() || null,
    locked: editForm.locked,
  }
}

async function openEditUser(user: OracleDatabaseUser) {
  closeActionMenu()
  editTargetUsername.value = user.username
  editLoading.value = true
  editError.value = null
  editPreview.value = null
  editState.value = null
  editRoleSearch.value = ''
  editRequestReference.value = ''
  try {
    const state = await oracleStore.loadUserLifecycleState(props.connectionId, user.username)
    editState.value = state
    editForm.defaultTablespace = state.default_tablespace ?? ''
    editForm.temporaryTablespace = state.temporary_tablespace ?? ''
    editForm.profile = state.profile ?? ''
    editForm.locked = state.locked
    editSelectedRoles.value = state.roles.map((role) => role.name)
  } catch (error) {
    editError.value = error instanceof Error ? error.message : 'Unable to load Oracle user access.'
  } finally {
    editLoading.value = false
  }
}

async function previewEditUser() {
  if (!editTargetUsername.value) return
  editLoading.value = true
  editError.value = null
  try {
    editPreview.value = await oracleStore.previewUserEdit(
      props.connectionId,
      editTargetUsername.value,
      editPayload(),
    )
  } catch (error) {
    editError.value = error instanceof Error ? error.message : 'Unable to preview Oracle user changes.'
  } finally {
    editLoading.value = false
  }
}

async function executeEditUser() {
  if (!editTargetUsername.value || !editPreview.value?.ready_to_execute) return
  editExecuting.value = true
  editError.value = null
  try {
    const result = await oracleStore.editUser(
      props.connectionId,
      editTargetUsername.value,
      {
        ...editPayload(),
        request_reference: editRequestReference.value.trim() || null,
      },
    )
    actionNotice.value = `${result.username} access updated · ${result.changes_applied} change(s).`
    await oracleStore.loadUsers(props.connectionId)
    closeEditUser()
  } catch (error) {
    editError.value = error instanceof Error ? error.message : 'Unable to update Oracle user access.'
  } finally {
    editExecuting.value = false
  }
}

function closeEditUser() {
  editTargetUsername.value = null
  editLoading.value = false
  editExecuting.value = false
  editError.value = null
  editState.value = null
  editPreview.value = null
  editRoleSearch.value = ''
  editRequestReference.value = ''
  editSelectedRoles.value = []
}

function generatedPassword() {
  const letters = 'abcdefghijklmnopqrstuvwxyz'
  const digits = '0123456789'
  const letterPart = Array.from({ length: 3 }, () => randomCharacter(letters)).join('')
  const digitPart = Array.from({ length: 5 }, () => randomCharacter(digits)).join('')
  return `${letterPart}${digitPart}`
}

function openPasswordReset(user: OracleDatabaseUser) {
  closeActionMenu()
  passwordTargetUsername.value = user.username
  passwordValue.value = ''
  passwordConfirm.value = ''
  passwordShow.value = false
  passwordRequestReference.value = ''
  passwordError.value = null
}

function generateResetPassword() {
  const value = generatedPassword()
  passwordValue.value = value
  passwordConfirm.value = value
  passwordShow.value = true
}

async function executePasswordReset() {
  if (!passwordTargetUsername.value) return
  passwordError.value = null
  if (passwordValue.value.length < 8) {
    passwordError.value = 'Password must contain at least 8 characters.'
    return
  }
  if (passwordValue.value !== passwordConfirm.value) {
    passwordError.value = 'Password confirmation does not match.'
    return
  }
  passwordExecuting.value = true
  try {
    const result = await oracleStore.resetUserPassword(
      props.connectionId,
      passwordTargetUsername.value,
      passwordValue.value,
      false,
      passwordRequestReference.value.trim() || null,
    )
    passwordValue.value = ''
    passwordConfirm.value = ''
    actionNotice.value = `${result.username} password reset successfully.`
    await oracleStore.loadUsers(props.connectionId)
    closePasswordReset()
  } catch (error) {
    passwordError.value = error instanceof Error ? error.message : 'Unable to reset Oracle password.'
  } finally {
    passwordExecuting.value = false
    passwordValue.value = ''
    passwordConfirm.value = ''
  }
}

function closePasswordReset() {
  passwordTargetUsername.value = null
  passwordValue.value = ''
  passwordConfirm.value = ''
  passwordShow.value = false
  passwordRequestReference.value = ''
  passwordExecuting.value = false
  passwordError.value = null
}

function openAccountAction(user: OracleDatabaseUser, action: AccountAction) {
  closeActionMenu()
  accountActionTargetUsername.value = user.username
  accountAction.value = action
  accountActionRequestReference.value = ''
  accountActionError.value = null
}

const accountActionLabel = computed(() => {
  if (accountAction.value === 'lock') return 'Lock account'
  if (accountAction.value === 'unlock') return 'Unlock account'
  if (accountAction.value === 'expire_password') return 'Expire password'
  return 'Account action'
})

async function executeAccountAction() {
  if (!accountActionTargetUsername.value || !accountAction.value) return
  accountActionExecuting.value = true
  accountActionError.value = null
  try {
    const result = await oracleStore.runUserAccountAction(
      props.connectionId,
      accountActionTargetUsername.value,
      accountAction.value,
      accountActionRequestReference.value.trim() || null,
    )
    actionNotice.value = `${result.username} · ${accountActionLabel.value} completed.`
    await oracleStore.loadUsers(props.connectionId)
    closeAccountAction()
  } catch (error) {
    accountActionError.value = error instanceof Error ? error.message : 'Unable to update Oracle account state.'
  } finally {
    accountActionExecuting.value = false
  }
}

function closeAccountAction() {
  accountActionTargetUsername.value = null
  accountAction.value = null
  accountActionRequestReference.value = ''
  accountActionExecuting.value = false
  accountActionError.value = null
}

async function previewUserDeprovision(user: OracleDatabaseUser) {
  deprovisionTargetUsername.value = user.username
  deprovisionPreview.value = null
  deprovisionError.value = null
  deprovisionResult.value = null
  deprovisionConfirmation.value = ''
  deprovisionRequestReference.value = ''
  deprovisionLoadingRunId.value = `preview:${user.username}`

  try {
    deprovisionPreview.value = await provisioningStore.previewOracleUserDeprovision(
      props.connectionId,
      user.username,
    )
  } catch (error) {
    deprovisionError.value = error instanceof Error
      ? error.message
      : 'Unable to build the deprovision preview.'
  } finally {
    deprovisionLoadingRunId.value = null
  }
}

const deprovisionConfirmationMatches = computed(() =>
  Boolean(
    deprovisionPreview.value
    && deprovisionConfirmation.value.trim() === deprovisionPreview.value.confirmation_text,
  ),
)

async function executeUserDeprovision() {
  if (!deprovisionPreview.value || !deprovisionConfirmationMatches.value) return

  deprovisionExecuting.value = true
  deprovisionError.value = null
  deprovisionResult.value = null
  try {
    const result = await provisioningStore.executeOracleUserDeprovision(
      props.connectionId,
      deprovisionPreview.value.username,
      deprovisionConfirmation.value.trim(),
      deprovisionRequestReference.value.trim() || null,
    )
    deprovisionResult.value = result

    // Always refresh because a partial run may have removed linked rows even
    // when the final Oracle DROP USER failed.
    await oracleStore.loadUsers(props.connectionId)
    if (historyOpen.value) {
      await loadProvisioningHistory()
    }

    if (result.status === 'succeeded') {
      closeDeprovisionPreview()
    } else {
      // Rebuild the preview so a retry reflects rows already cleaned up.
      deprovisionPreview.value = await provisioningStore.previewOracleUserDeprovision(
        props.connectionId,
        result.username,
      )
      deprovisionConfirmation.value = ''
    }
  } catch (error) {
    deprovisionError.value = error instanceof Error
      ? error.message
      : 'Unable to deprovision the Oracle schema.'
  } finally {
    deprovisionExecuting.value = false
  }
}

function closeDeprovisionPreview() {
  deprovisionTargetUsername.value = null
  deprovisionError.value = null
  deprovisionPreview.value = null
  deprovisionConfirmation.value = ''
  deprovisionRequestReference.value = ''
  deprovisionResult.value = null
  deprovisionExecuting.value = false
}

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
  createStep.value = 'identity'
  createError.value = null
  Object.keys(createFieldErrors).forEach((key) => delete createFieldErrors[key])
  usernameChecking.value = false
  reference.value = null
  selectedRoles.value = []
  createResult.value = null
  provisioningPreview.value = null
  provisioningResult.value = null
  previewLoading.value = false
  provisioningExecuting.value = false
  showPassword.value = false
  resultPassword.value = ''
  summaryCopyNotice.value = ''
}

function toggleCreateActions(event: Event) {
  event.stopPropagation()
  createActionsOpen.value = !createActionsOpen.value
}

function openCreate() {
  createActionsOpen.value = false
  resetCreate()
  createOpen.value = true
}

function openBulkCreate() {
  createActionsOpen.value = false
  bulkCreateOpen.value = true
}

async function bulkCompleted() {
  await oracleStore.loadUsers(props.connectionId)
  await loadProvisioningHistory()
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

function setCreateFieldError(field: string, message: string | null) {
  if (message) createFieldErrors[field] = message
  else delete createFieldErrors[field]
}

function validPersonNameInput(value: string, required: boolean) {
  const raw = value.trim()
  if (!raw) return !required
  if (/\d/.test(raw)) return false
  return Boolean(normalizePersonName(raw))
}

function validateIdentityFields() {
  let valid = true
  const employeeId = createForm.employeeId.trim()
  if (!employeeId) {
    setCreateFieldError('employeeId', 'Employee ID is required.')
    valid = false
  } else if (!/^[A-Za-z0-9]+$/.test(employeeId)) {
    setCreateFieldError('employeeId', 'Employee ID must contain letters and numbers only.')
    valid = false
  } else {
    setCreateFieldError('employeeId', null)
  }

  const nameFields: Array<[keyof Pick<CreateUserForm, 'firstName' | 'middleName' | 'lastName'>, string, boolean]> = [
    ['firstName', 'First name', true],
    ['middleName', 'Middle name', false],
    ['lastName', 'Last name', true],
  ]
  for (const [field, label, required] of nameFields) {
    const raw = createForm[field].trim()
    if (!raw && required) {
      setCreateFieldError(field, `${label} is required.`)
      valid = false
    } else if (/\d/.test(raw)) {
      setCreateFieldError(field, `${label} cannot contain numbers.`)
      valid = false
    } else if (raw && !normalizePersonName(raw)) {
      setCreateFieldError(field, `${label} must contain at least one letter.`)
      valid = false
    } else {
      setCreateFieldError(field, null)
    }
  }
  return valid
}

const identityReady = computed(() =>
  Boolean(
    createForm.employeeId.trim()
      && /^[A-Za-z0-9]+$/.test(createForm.employeeId.trim())
      && validPersonNameInput(createForm.firstName, true)
      && validPersonNameInput(createForm.lastName, true)
      && validPersonNameInput(createForm.middleName, false),
  ),
)

function identityInput(field: 'employeeId' | 'firstName' | 'middleName' | 'lastName') {
  setCreateFieldError(field, null)
  createForm.username = ''
  setCreateFieldError('username', null)
  createError.value = null
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
  createForm.password = generatedPassword()
  setCreateFieldError('password', null)
  showPassword.value = true
}

function generateUsername() {
  createError.value = null
  setCreateFieldError('username', null)
  if (!validateIdentityFields()) {
    createForm.username = ''
    return
  }

  const first = cleanUsernamePart(createForm.firstName)
  const middle = cleanUsernamePart(createForm.middleName)
  const last = cleanUsernamePart(createForm.lastName)
  const employeeId = cleanEmployeeIdPart(createForm.employeeId)
  const generated = [first.charAt(0), middle ? middle.charAt(0) : '', last, employeeId].join('')

  if (generated.length > 30) {
    createForm.username = ''
    setCreateFieldError('username', 'Generated username exceeds the 30-character Oracle compatibility limit.')
    return
  }
  createForm.firstName = normalizePersonName(createForm.firstName)
  createForm.middleName = normalizePersonName(createForm.middleName)
  createForm.lastName = normalizePersonName(createForm.lastName)
  createForm.employeeId = cleanEmployeeIdPart(createForm.employeeId)
  createForm.username = generated
}

async function continueIdentity() {
  createError.value = null
  if (!validateIdentityFields()) return
  if (!createForm.username) {
    setCreateFieldError('username', 'Generate the username after entering the required identity fields.')
    return
  }
  usernameChecking.value = true
  try {
    const result = await oracleStore.checkUsernameAvailability(props.connectionId, createForm.username)
    if (!result.available) {
      setCreateFieldError('username', result.message || 'This Oracle username already exists.')
      return
    }
    setCreateFieldError('username', null)
    createStep.value = 'access'
  } catch (error) {
    setCreateFieldError('username', error instanceof Error ? error.message : 'Unable to validate the generated username.')
  } finally {
    usernameChecking.value = false
  }
}

async function inspectReferenceAccess() {
  createError.value = null
  setCreateFieldError('referenceUsername', null)
  const referenceUsername = createForm.referenceUsername.trim().toUpperCase()
  if (!referenceUsername) {
    reference.value = null
    selectedRoles.value = []
    return true
  }

  try {
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
    return true
  } catch (error) {
    setCreateFieldError(
      'referenceUsername',
      error instanceof Error ? error.message : 'Unable to inspect the reference user.',
    )
    reference.value = null
    selectedRoles.value = []
    return false
  }
}

function referenceInput() {
  setCreateFieldError('referenceUsername', null)
  reference.value = null
  selectedRoles.value = []
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
    setCreateFieldError('password', 'Password must contain at least 8 characters.')
    return
  }
  if (createForm.password.includes('"') || [...createForm.password].some((character) => character.charCodeAt(0) < 32)) {
    setCreateFieldError('password', 'Password cannot contain double quotes or control characters.')
    return
  }
  setCreateFieldError('password', null)

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
      if (reference.value?.username !== referenceUsername) {
        const loaded = await inspectReferenceAccess()
        if (!loaded) return
      }
    } else {
      reference.value = null
      selectedRoles.value = []
    }

    if (createForm.provisioningProfileId) {
      previewLoading.value = true
      const builtPreview = await provisioningStore.previewForConnection(
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
      provisioningPreview.value = builtPreview
      createForm.username = builtPreview.username
    }

    createStep.value = 'review'
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Unable to build the user creation review.'
    if (createForm.referenceUsername.trim() && /reference/i.test(message)) {
      setCreateFieldError('referenceUsername', message)
    } else {
      createError.value = message
    }
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

const resultUsername = computed(() =>
  provisioningResult.value?.username ?? createResult.value?.username ?? createForm.username,
)

const resultFullName = computed(() =>
  [createForm.firstName, createForm.middleName, createForm.lastName]
    .map((value) => value.trim())
    .filter(Boolean)
    .join(' '),
)

const requesterSummary = computed(() => [
  `${createForm.employeeId} ${resultFullName.value}`.trim(),
  `Username: ${resultUsername.value.toUpperCase()}`,
  `Password: ${resultPassword.value}`,
].join('\n'))

async function copyRequesterSummary() {
  summaryCopyNotice.value = ''
  const text = requesterSummary.value
  try {
    await navigator.clipboard.writeText(text)
    summaryCopyNotice.value = 'Copied.'
  } catch {
    const textarea = document.createElement('textarea')
    textarea.value = text
    textarea.style.position = 'fixed'
    textarea.style.opacity = '0'
    document.body.appendChild(textarea)
    textarea.select()
    document.execCommand('copy')
    textarea.remove()
    summaryCopyNotice.value = 'Copied.'
  }
}

async function executeProvisioning() {
  if (!createForm.provisioningProfileId || !provisioningPreview.value) {
    return
  }

  createError.value = null
  provisioningExecuting.value = true

  const submittedPassword = createForm.password
  try {
    provisioningResult.value = await provisioningStore.executeForConnection(
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
        roles: [...selectedRoles.value],
        default_tablespace: createForm.defaultTablespace || null,
        temporary_tablespace: createForm.temporaryTablespace || null,
        oracle_profile: createForm.profile || null,
      },
    )

    resultPassword.value = provisioningResult.value.account.password_applied
      ? submittedPassword
      : ''
    // Never keep the submitted password in the editable form after execution.
    createForm.password = ''
    createStep.value = 'success'
    await oracleStore.loadUsers(props.connectionId)
    await loadProvisioningHistory()
  } catch (error) {
    createError.value =
      error instanceof Error
        ? error.message
        : 'Unable to execute provisioning.'
  } finally {
    provisioningExecuting.value = false
  }
}

function createAnotherUser() {
  const provisioningProfileId = createForm.provisioningProfileId
  Object.assign(createForm, emptyCreateForm())
  createForm.provisioningProfileId = provisioningProfileId
  createStep.value = 'identity'
  createError.value = null
  Object.keys(createFieldErrors).forEach((key) => delete createFieldErrors[key])
  reference.value = null
  selectedRoles.value = []
  createResult.value = null
  provisioningPreview.value = null
  provisioningResult.value = null
  showPassword.value = false
  resultPassword.value = ''
  summaryCopyNotice.value = ''
}

function downloadProvisioningLdif() {
  const ldap = provisioningResult.value?.ldap
  if (!ldap?.content || !ldap.filename) {
    return
  }

  const blob = new Blob([ldap.content], {
    type: 'text/plain;charset=utf-8',
  })
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = ldap.filename
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  URL.revokeObjectURL(url)
}

async function createUser() {
  createError.value = null
  const submittedPassword = createForm.password

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

    resultPassword.value = submittedPassword
    // Do not retain the submitted database password in the editable form.
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
  document.addEventListener('click', documentClickClosesActionMenu)
  window.addEventListener('scroll', closeActionMenu, true)
  oracleStore.loadUsers(
    props.connectionId,
  )
  provisioningStore.loadProfilesForConnection(props.connectionId)
  loadProvisioningHistory()
})

onBeforeUnmount(() => {
  document.removeEventListener('click', documentClickClosesActionMenu)
  window.removeEventListener('scroll', closeActionMenu, true)
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
        <div class="toolbar-create-dropdown">
          <button
            type="button"
            class="primary-button"
            aria-haspopup="menu"
            :aria-expanded="createActionsOpen"
            @click="toggleCreateActions"
          >
            Create ▾
          </button>
          <div v-if="createActionsOpen" class="toolbar-create-menu" role="menu" @click.stop>
            <button type="button" role="menuitem" @click="openCreate">Create user</button>
            <button type="button" role="menuitem" @click="openBulkCreate">Batch user</button>
          </div>
        </div>

        <button
          type="button"
          class="secondary-button"
          @click="toggleProvisioningHistory"
        >
          {{ historyOpen ? 'Hide provisioning history' : 'Provisioning history' }}
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

        <div v-if="actionNotice" class="preview-callout user-action-notice">
          <div>
            <strong>Oracle user updated</strong>
            <span>{{ actionNotice }}</span>
          </div>
          <button type="button" class="secondary-button compact-button" @click="actionNotice = null">Dismiss</button>
        </div>

        <ScrollableDataTable
          :empty="filteredUsers.length === 0"
          empty-message="No matching database accounts."
          max-height="38rem"
          @scroll="closeActionMenu"
        >
          <template #header>
              <tr>
                <th>Username</th>
                <th>Status</th>
                <th>Default tablespace</th>
                <th>Temporary tablespace</th>
                <th>Profile</th>
                <th>Created</th>
                <th>Expiry</th>
                <th class="user-actions-column">Actions</th>
              </tr>
          </template>
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

                <td class="user-actions-cell">
                  <div class="user-action-menu-wrap" @click.stop>
                    <button
                      type="button"
                      class="user-action-button user-menu-button"
                      :aria-expanded="actionMenuUsername === user.username"
                      :aria-label="`Actions for ${user.username}`"
                      :title="`Actions for ${user.username}`"
                      @click="toggleActionMenu(user, $event)"
                    >
                      <FontAwesomeIcon icon="ellipsis-vertical" />
                    </button>

                    <Teleport to="body">
                      <div
                        v-if="actionMenuUsername === user.username"
                        class="user-action-dropdown"
                        role="menu"
                        :style="{
                          position: 'fixed',
                          top: `${actionMenuPosition.top}px`,
                          left: `${actionMenuPosition.left}px`,
                          right: 'auto',
                          zIndex: 1000,
                        }"
                        @click.stop
                      >
                      <button type="button" role="menuitem" @click="openAccessInspector(user)">
                        Inspect access
                      </button>
                      <button type="button" role="menuitem" @click="openEditUser(user)">
                        Edit access
                      </button>
                      <button type="button" role="menuitem" @click="openPasswordReset(user)">
                        Change password
                      </button>
                      <button
                        type="button"
                        role="menuitem"
                        @click="openAccountAction(user, user.status.toUpperCase().includes('LOCKED') ? 'unlock' : 'lock')"
                      >
                        {{ user.status.toUpperCase().includes('LOCKED') ? 'Unlock account' : 'Lock account' }}
                      </button>
                      <button
                        type="button"
                        role="menuitem"
                        :disabled="user.status.toUpperCase().includes('EXPIRED')"
                        @click="openAccountAction(user, 'expire_password')"
                      >
                        Expire password
                      </button>
                      <div class="user-action-divider"></div>
                      <button
                        type="button"
                        role="menuitem"
                        class="danger-menu-item"
                        :disabled="deprovisionTargetUsername === user.username && deprovisionLoadingRunId !== null"
                        @click="previewUserDeprovision(user); closeActionMenu()"
                      >
                        Deprovision
                      </button>
                      </div>
                    </Teleport>
                  </div>
                </td>
              </tr>

        </ScrollableDataTable>
      </template>
    </template>

    <section v-if="historyOpen" class="provisioning-history-panel">
      <div class="provisioning-history-heading">
        <div>
          <h3>Provisioning history</h3>
          <p>Lifecycle runs created from this parent Oracle database. Passwords are never stored.</p>
        </div>
        <button
          type="button"
          class="secondary-button"
          :disabled="historyLoading"
          @click="loadProvisioningHistory"
        >
          {{ historyLoading ? 'Loading...' : 'Refresh history' }}
        </button>
      </div>

      <p v-if="historyError" class="login-error">{{ historyError }}</p>

      <div v-if="provisioningResult && !createOpen" class="preview-callout provisioning-retry-result">
        <div>
          <strong>Retry result · {{ provisioningResult.username }} · {{ provisioningResult.status.toUpperCase() }}</strong>
          <span v-if="provisioningResult.error">{{ provisioningResult.error }}</span>
          <span v-else>Incomplete lifecycle steps were retried; previously completed steps were skipped.</span>
        </div>
        <button
          v-if="['generated', 'created', 'already_present'].includes(provisioningResult.ldap.action ?? '') && provisioningResult.ldap.content"
          type="button"
          class="secondary-button compact-button"
          @click="downloadProvisioningLdif"
        >
          Download {{ provisioningResult.ldap.filename }}
        </button>
      </div>

      <div v-if="historyLoading && provisioningRuns.length === 0" class="empty-state">
        Loading provisioning history...
      </div>

      <div v-else-if="provisioningRuns.length === 0" class="empty-state">
        No provisioning lifecycle runs have been recorded for this database yet.
      </div>

      <ScrollableDataTable
        v-else
        class="provisioning-history-table"
        :empty="provisioningRuns.length === 0"
        empty-message="No provisioning lifecycle runs have been recorded for this database yet."
        max-height="30rem"
      >
        <template #header>
            <tr>
              <th>User</th>
              <th>Profile</th>
              <th>Status</th>
              <th>Request</th>
              <th>DBA</th>
              <th>Started</th>
              <th>Retry</th>
            </tr>
        </template>
            <tr v-for="run in provisioningRuns" :key="run.run_id">
              <td>
                <strong>{{ run.username }}</strong>
                <small v-if="run.employee_id">ID {{ run.employee_id }}</small>
              </td>
              <td>{{ run.profile_name }}</td>
              <td>
                <span class="provisioning-status" :data-status="run.status">
                  {{ run.status.toUpperCase() }}
                </span>
              </td>
              <td>{{ run.request_reference || '—' }}</td>
              <td>{{ run.operator_username }}</td>
              <td>{{ formatDate(run.started_at) }}</td>
              <td>
                <button
                  v-if="run.retryable"
                  type="button"
                  class="secondary-button compact-button"
                  :disabled="retryingRunId === run.run_id"
                  @click="retryRun(run)"
                >
                  {{ retryingRunId === run.run_id ? 'Retrying...' : retryLabel(run) }}
                </button>
                <span v-else>—</span>
              </td>
            </tr>
      </ScrollableDataTable>

      <div v-if="retryPasswordRun" class="provisioning-retry-password">
        <div>
          <strong>Retry {{ retryPasswordRun.username }}</strong>
          <p>Only the remaining step(s) need the original provisioning password. It will be used in memory for this retry and will not be persisted.</p>
        </div>
        <label>
          <span>Original provisioning password</span>
          <div class="password-input-row">
            <input
              v-model="retryPassword"
              :type="retryShowPassword ? 'text' : 'password'"
              autocomplete="new-password"
              @keyup.enter="submitRetryPassword"
            />
            <button type="button" class="secondary-button" @click="retryShowPassword = !retryShowPassword">
              {{ retryShowPassword ? 'Hide' : 'Show' }}
            </button>
          </div>
        </label>
        <div class="connection-form-actions">
          <button
            type="button"
            class="primary-button"
            :disabled="retryingRunId === retryPasswordRun.run_id"
            @click="submitRetryPassword"
          >
            {{ retryingRunId === retryPasswordRun.run_id ? 'Retrying...' : 'Retry incomplete steps' }}
          </button>
          <button type="button" class="secondary-button" @click="cancelRetryPassword">Cancel</button>
        </div>
      </div>

    </section>

    <div
      v-if="inspectorTargetUsername"
      class="modal-backdrop"
      @click.self="closeAccessInspector"
    >
      <section
        class="modal-panel oracle-user-modal access-inspector-modal"
        role="dialog"
        aria-modal="true"
        :aria-label="`Access inspector for ${inspectorTargetUsername}`"
      >
        <div class="modal-header">
          <div>
            <h2>Access inspector · {{ inspectorTargetUsername }}</h2>
            <p>Read-only view of direct and inherited Oracle access. No grants are changed from this screen.</p>
          </div>
          <button type="button" class="modal-close" aria-label="Close" @click="closeAccessInspector">×</button>
        </div>

        <div v-if="inspectorLoading" class="empty-state">Inspecting Oracle roles and privileges...</div>
        <p v-if="inspectorError" class="login-error">{{ inspectorError }}</p>

        <template v-if="inspector">
          <div class="access-inspector-summary">
            <div><span>Status</span><strong>{{ inspector.status }}</strong></div>
            <div><span>Roles</span><strong>{{ inspector.roles.length }}</strong></div>
            <div><span>System privileges</span><strong>{{ inspector.system_privileges.length }}</strong></div>
            <div><span>Object privileges</span><strong>{{ inspector.object_privileges.length }}</strong></div>
          </div>

          <section class="access-account-summary">
            <div><span>Default tablespace</span><strong>{{ inspector.default_tablespace || '—' }}</strong></div>
            <div><span>Temporary tablespace</span><strong>{{ inspector.temporary_tablespace || '—' }}</strong></div>
            <div><span>Profile</span><strong>{{ inspector.profile || '—' }}</strong></div>
            <div><span>Created</span><strong>{{ formatDate(inspector.created_at) }}</strong></div>
          </section>

          <section v-if="inspector.powerful_findings.length" class="access-powerful-section">
            <div class="user-edit-section-heading">
              <div>
                <h3>Elevated access</h3>
                <p>Explicit flags only — this is not a security score.</p>
              </div>
            </div>
            <div class="access-finding-list">
              <article v-for="finding in inspector.powerful_findings" :key="`${finding.kind}-${finding.name}-${finding.source}`">
                <strong>⚠ {{ finding.name }}</strong>
                <span>{{ finding.source }}</span>
                <small>{{ finding.reason }}</small>
              </article>
            </div>
          </section>

          <details class="access-inspector-section" open>
            <summary>Roles · {{ inspector.roles.length }}</summary>
            <div v-if="inspector.roles.length" class="access-table-wrap">
              <table>
                <thead><tr><th>Role</th><th>Source</th><th>Default</th><th>Admin option</th><th>Flag</th></tr></thead>
                <tbody>
                  <tr v-for="role in inspector.roles" :key="role.name">
                    <td><strong>{{ role.name }}</strong></td>
                    <td>{{ role.sources.map(formatAccessSource).join(', ') }}</td>
                    <td>{{ role.sources.some((source) => source.default_role === true) ? 'YES' : role.sources.some((source) => source.kind === 'direct') ? 'NO' : '—' }}</td>
                    <td>{{ role.sources.some((source) => source.kind === 'direct' && source.admin_option) ? 'YES' : 'NO' }}</td>
                    <td>{{ role.powerful ? '⚠ Elevated' : '—' }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
            <div v-else class="empty-state">No role grants found.</div>
          </details>

          <details class="access-inspector-section">
            <summary>System privileges · {{ inspector.system_privileges.length }}</summary>
            <div v-if="inspector.system_privileges.length" class="access-table-wrap">
              <table>
                <thead><tr><th>Privilege</th><th>Source</th><th>Admin option</th><th>Flag</th></tr></thead>
                <tbody>
                  <tr v-for="privilege in inspector.system_privileges" :key="privilege.name">
                    <td><strong>{{ privilege.name }}</strong></td>
                    <td>{{ privilege.sources.map(formatAccessSource).join(', ') }}</td>
                    <td>{{ privilege.sources.some((source) => source.kind === 'direct' && source.admin_option) ? 'YES' : 'NO' }}</td>
                    <td>{{ privilege.powerful ? '⚠ Elevated' : '—' }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
            <div v-else class="empty-state">No system privileges found.</div>
          </details>

          <details v-if="inspector.administrative_privileges.length" class="access-inspector-section">
            <summary>Password-file administration · {{ inspector.administrative_privileges.length }}</summary>
            <div class="oracle-privilege-list">
              <span v-for="privilege in inspector.administrative_privileges" :key="privilege">⚠ {{ privilege }}</span>
            </div>
          </details>

          <details class="access-inspector-section">
            <summary>Object privileges · {{ inspector.object_privileges.length }}</summary>
            <div class="access-object-toolbar">
              <input v-model="inspectorObjectSearch" type="search" placeholder="Filter owner, object, column, privilege or role" />
              <span>{{ filteredInspectorObjectPrivileges.length }} shown</span>
            </div>
            <div v-if="filteredInspectorObjectPrivileges.length" class="access-table-wrap access-object-table">
              <table>
                <thead><tr><th>Object</th><th>Column</th><th>Privilege</th><th>Source</th><th>Grantable</th></tr></thead>
                <tbody>
                  <tr v-for="item in filteredInspectorObjectPrivileges" :key="`${item.owner}.${item.object_name}.${item.column_name || ''}.${item.privilege}`">
                    <td><strong>{{ item.owner }}.{{ item.object_name }}</strong></td>
                    <td>{{ item.column_name || '—' }}</td>
                    <td>{{ item.privilege }}</td>
                    <td>{{ item.sources.map(formatAccessSource).join(', ') }}</td>
                    <td>{{ item.sources.some((source) => source.kind === 'direct' && source.grantable) ? 'YES' : 'NO' }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
            <div v-else class="empty-state">No matching object privileges.</div>
          </details>

          <div v-for="warning in inspector.warnings" :key="warning" class="utility-warning">{{ warning }}</div>

          <div class="connection-form-actions">
            <button type="button" class="secondary-button" @click="closeAccessInspector">Close</button>
          </div>
        </template>
      </section>
    </div>

    <div
      v-if="editTargetUsername"
      class="modal-backdrop"
      @click.self="closeEditUser"
    >
      <section
        class="modal-panel oracle-user-modal user-edit-modal"
        role="dialog"
        aria-modal="true"
        :aria-label="`Edit access for ${editTargetUsername}`"
      >
        <div class="modal-header">
          <div>
            <h2>Edit {{ editTargetUsername }}</h2>
            <p v-if="!editPreview">Manage Oracle account settings and role grants. Direct system privileges stay review-only.</p>
            <p v-else>Review the exact Oracle changes before applying them.</p>
          </div>
          <button type="button" class="modal-close" aria-label="Close" :disabled="editExecuting" @click="closeEditUser">×</button>
        </div>

        <div v-if="editLoading && !editState" class="empty-state">Loading current Oracle access...</div>
        <p v-if="editError" class="login-error">{{ editError }}</p>

        <template v-if="editState && !editPreview">
          <div class="preview-summary-grid">
            <div><span>Status</span><strong>{{ editState.status }}</strong></div>
            <div><span>Roles</span><strong>{{ editState.roles.length }}</strong></div>
            <div><span>Direct system privileges</span><strong>{{ editState.system_privileges.length }}</strong></div>
          </div>

          <div class="connection-form user-edit-fields">
            <div class="connection-form-row">
              <label>
                Default tablespace
                <input v-model="editForm.defaultTablespace" maxlength="30" @input="editPreview = null" />
              </label>
              <label>
                Temporary tablespace
                <input v-model="editForm.temporaryTablespace" maxlength="30" @input="editPreview = null" />
              </label>
            </div>
            <div class="connection-form-row">
              <label>
                Profile
                <input v-model="editForm.profile" maxlength="30" @input="editPreview = null" />
              </label>
              <label class="user-edit-lock-toggle">
                <span>Account state</span>
                <span class="checkbox-row">
                  <input v-model="editForm.locked" type="checkbox" @change="editPreview = null" />
                  Keep account locked
                </span>
              </label>
            </div>
          </div>

          <section class="user-edit-role-section">
            <div class="user-edit-section-heading">
              <div>
                <h3>Roles</h3>
                <p>Existing roles appear first. New sensitive roles are blocked; existing sensitive roles can be revoked after preview.</p>
              </div>
              <input v-model="editRoleSearch" type="search" placeholder="Find role" />
            </div>

            <div class="user-edit-role-list">
              <label
                v-for="role in filteredEditRoles"
                :key="role.name"
                class="oracle-role-option"
                :class="{ blocked: role.sensitive && !editRoleSelected(role.name) }"
              >
                <input
                  type="checkbox"
                  :checked="editRoleSelected(role.name)"
                  :disabled="role.sensitive && !editRoleSelected(role.name)"
                  @change="handleEditRoleToggle(role.name, $event)"
                />
                <span>
                  <strong>{{ role.name }}</strong>
                  <small>
                    {{ editRoleSelected(role.name) ? 'Granted' : 'Not granted' }}
                    <template v-if="role.sensitive"> · sensitive</template>
                  </small>
                </span>
              </label>
              <div v-if="filteredEditRoles.length === 0" class="empty-state">No matching roles.</div>
            </div>
          </section>

          <details v-if="editState.system_privileges.length" class="user-edit-system-privileges">
            <summary>Direct system privileges · review only</summary>
            <div class="oracle-privilege-list">
              <span v-for="privilege in editState.system_privileges" :key="privilege.name">
                {{ privilege.name }}<template v-if="privilege.admin_option"> · ADMIN OPTION</template>
              </span>
            </div>
          </details>

          <div v-for="warning in editState.warnings" :key="warning" class="utility-warning">{{ warning }}</div>

          <div class="connection-form-actions">
            <button type="button" class="primary-button" :disabled="editLoading" @click="previewEditUser">
              {{ editLoading ? 'Building preview...' : 'Review changes' }}
            </button>
            <button type="button" class="secondary-button" @click="closeEditUser">Cancel</button>
          </div>
        </template>

        <template v-else-if="editState && editPreview">
          <div v-if="editPreview.changes.length" class="user-edit-change-list">
            <article v-for="change in editPreview.changes" :key="`${change.component}-${change.action}-${change.label}`">
              <header>
                <strong>{{ change.label }}</strong>
                <span>{{ change.action.toUpperCase() }}</span>
              </header>
              <p>{{ change.before ?? '—' }} → {{ change.after ?? '—' }}</p>
              <small v-if="change.sensitive">Sensitive role change</small>
            </article>
          </div>
          <div v-else class="empty-state">No changes are pending.</div>

          <div v-for="warning in editPreview.warnings" :key="warning" class="utility-warning">{{ warning }}</div>

          <label class="user-edit-request-reference">
            <span>Request / ticket <small>optional</small></span>
            <input v-model="editRequestReference" maxlength="100" placeholder="Change or ticket reference" />
          </label>

          <div class="connection-form-actions">
            <button
              type="button"
              class="primary-button"
              :disabled="editExecuting || !editPreview.ready_to_execute"
              @click="executeEditUser"
            >
              {{ editExecuting ? 'Applying...' : 'Apply changes' }}
            </button>
            <button type="button" class="secondary-button" :disabled="editExecuting" @click="editPreview = null">Back</button>
          </div>
        </template>
      </section>
    </div>

    <div
      v-if="passwordTargetUsername"
      class="modal-backdrop"
      @click.self="closePasswordReset"
    >
      <section class="modal-panel compact-user-action-modal" role="dialog" aria-modal="true" :aria-label="`Change password for ${passwordTargetUsername}`">
        <div class="modal-header">
          <div>
            <h2>Change password</h2>
            <p>{{ passwordTargetUsername }} · the password is used only for this Oracle ALTER USER operation and is not stored in DBAChum.</p>
          </div>
          <button type="button" class="modal-close" aria-label="Close" :disabled="passwordExecuting" @click="closePasswordReset">×</button>
        </div>

        <div class="connection-form password-reset-form">
          <label>
            New password
            <input v-model="passwordValue" :type="passwordShow ? 'text' : 'password'" minlength="8" maxlength="128" autocomplete="new-password" />
          </label>
          <label>
            Confirm password
            <input v-model="passwordConfirm" :type="passwordShow ? 'text' : 'password'" minlength="8" maxlength="128" autocomplete="new-password" />
          </label>
          <div class="oracle-password-actions">
            <button type="button" class="secondary-button" @click="generateResetPassword">Generate password</button>
            <button type="button" class="secondary-button" @click="passwordShow = !passwordShow">{{ passwordShow ? 'Hide password' : 'Show password' }}</button>
          </div>
          <label>
            Request / ticket <span class="optional-label">Optional</span>
            <input v-model="passwordRequestReference" maxlength="100" placeholder="Change or ticket reference" />
          </label>
        </div>

        <p v-if="passwordError" class="login-error">{{ passwordError }}</p>
        <div class="connection-form-actions">
          <button type="button" class="primary-button" :disabled="passwordExecuting" @click="executePasswordReset">
            {{ passwordExecuting ? 'Changing...' : 'Change password' }}
          </button>
          <button type="button" class="secondary-button" :disabled="passwordExecuting" @click="closePasswordReset">Cancel</button>
        </div>
      </section>
    </div>

    <div
      v-if="accountActionTargetUsername && accountAction"
      class="modal-backdrop"
      @click.self="closeAccountAction"
    >
      <section class="modal-panel compact-user-action-modal" role="dialog" aria-modal="true" :aria-label="`${accountActionLabel} ${accountActionTargetUsername}`">
        <div class="modal-header">
          <div>
            <h2>{{ accountActionLabel }}</h2>
            <p v-if="accountAction === 'expire_password'">{{ accountActionTargetUsername }} will be required to change the password at the next Oracle login.</p>
            <p v-else>{{ accountActionTargetUsername }} will be {{ accountAction === 'lock' ? 'prevented from logging in' : 'allowed to log in again, subject to its password state' }}.</p>
          </div>
          <button type="button" class="modal-close" aria-label="Close" :disabled="accountActionExecuting" @click="closeAccountAction">×</button>
        </div>

        <label class="user-edit-request-reference">
          <span>Request / ticket <small>optional</small></span>
          <input v-model="accountActionRequestReference" maxlength="100" placeholder="Change or ticket reference" />
        </label>
        <p v-if="accountActionError" class="login-error">{{ accountActionError }}</p>
        <div class="connection-form-actions">
          <button type="button" class="primary-button" :disabled="accountActionExecuting" @click="executeAccountAction">
            {{ accountActionExecuting ? 'Applying...' : accountActionLabel }}
          </button>
          <button type="button" class="secondary-button" :disabled="accountActionExecuting" @click="closeAccountAction">Cancel</button>
        </div>
      </section>
    </div>

    <div
      v-if="deprovisionTargetUsername"
      class="modal-backdrop"
      @click.self="closeDeprovisionPreview"
    >
      <section
        class="modal-panel deprovision-preview-modal"
        role="dialog"
        aria-modal="true"
        :aria-label="`Deprovision ${deprovisionTargetUsername}`"
      >
        <div class="modal-header">
          <div>
            <h2>Deprovision {{ deprovisionTargetUsername }}</h2>
            <p>Review the Oracle schema and any linked rows found through enabled provisioning profiles.</p>
          </div>
          <button
            type="button"
            class="modal-close"
            aria-label="Close"
            :disabled="deprovisionExecuting"
            @click="closeDeprovisionPreview"
          >
            ×
          </button>
        </div>

        <div v-if="deprovisionLoadingRunId" class="empty-state">
          Building live deprovision preview...
        </div>

        <div v-else-if="deprovisionError" class="utility-warning oracle-create-warning">
          {{ deprovisionError }}
        </div>

        <template v-if="deprovisionPreview">
          <div v-if="deprovisionResult" class="preview-callout provisioning-retry-result">
            <div>
              <strong>Last execution · {{ deprovisionResult.status.toUpperCase() }}</strong>
              <span v-if="deprovisionResult.error">{{ deprovisionResult.error }}</span>
              <span v-else>{{ deprovisionResult.deleted_provisioning_rows }} linked row(s) and {{ deprovisionResult.deleted_ldap_entries }} LDAP entr{{ deprovisionResult.deleted_ldap_entries === 1 ? 'y' : 'ies' }} removed.</span>
            </div>
          </div>

          <div class="preview-summary-grid">
            <div>
              <span>Owned objects</span>
              <strong>{{ deprovisionPreview.owned_object_count }}</strong>
            </div>
            <div>
              <span>Linked rows</span>
              <strong>{{ deprovisionPreview.linked_row_count }}</strong>
            </div>
            <div>
              <span>LDAP entries</span>
              <strong>{{ deprovisionPreview.linked_ldap_count }}</strong>
            </div>
            <div>
              <span>Execution</span>
              <strong>{{ deprovisionPreview.execution_ready ? 'READY' : 'BLOCKED' }}</strong>
            </div>
          </div>

          <div
            v-if="deprovisionPreview.drop_cascade"
            class="utility-warning oracle-create-warning"
          >
            This schema owns {{ deprovisionPreview.owned_object_count }} object(s). Deprovisioning will execute DROP USER {{ deprovisionPreview.username }} CASCADE and permanently remove those objects.
          </div>

          <div
            v-for="warning in deprovisionPreview.warnings"
            :key="warning"
            class="utility-warning"
          >
            {{ warning }}
          </div>

          <div
            v-for="reason in deprovisionPreview.blocked_reasons"
            :key="reason"
            class="utility-warning oracle-create-warning"
          >
            {{ reason }}
          </div>

          <div class="deprovision-item-list">
            <article
              v-for="item in deprovisionPreview.items"
              :key="`${item.component}-${item.label}`"
              class="deprovision-item"
            >
              <header>
                <strong>{{ item.label }}</strong>
                <span class="provisioning-status" :data-status="item.state">
                  {{ item.state.replace('_', ' ').toUpperCase() }}
                </span>
              </header>
              <p><strong>{{ item.planned_action }}</strong></p>
              <small>{{ item.reason }}</small>
              <small v-if="Object.keys(item.match_values).length" class="deprovision-match-key">
                Match: {{ formatDeprovisionMatch(item.match_values) }}
              </small>
              <small v-if="item.ldap_dn" class="deprovision-match-key">
                DN: {{ item.ldap_dn }}
              </small>
            </article>
          </div>

          <div v-if="deprovisionPreview.execution_ready" class="deprovision-confirmation">
            <div>
              <strong>Permanent deprovision</strong>
              <p>Type <code>{{ deprovisionPreview.confirmation_text }}</code> exactly to enable deletion.</p>
            </div>

            <label>
              <span>Schema confirmation</span>
              <input
                v-model="deprovisionConfirmation"
                type="text"
                autocomplete="off"
                :placeholder="deprovisionPreview.confirmation_text"
                :disabled="deprovisionExecuting"
                @keyup.enter="executeUserDeprovision"
              />
            </label>

            <label>
              <span>Request / ticket <small>optional</small></span>
              <input
                v-model="deprovisionRequestReference"
                type="text"
                maxlength="100"
                placeholder="Change or ticket reference"
                :disabled="deprovisionExecuting"
              />
            </label>
          </div>

          <div class="deprovision-preview-footer">
            <p v-if="deprovisionPreview.lifecycle_run_count">
              {{ deprovisionPreview.lifecycle_run_count }} DBAChum provisioning run(s) found; lifecycle history will be retained.
            </p>
            <p v-else>
              No DBAChum provisioning history is required to delete this schema.
            </p>
            <div class="deprovision-footer-actions">
              <button
                v-if="deprovisionPreview.execution_ready"
                type="button"
                class="primary-button danger-confirm-button"
                :disabled="!deprovisionConfirmationMatches || deprovisionExecuting"
                @click="executeUserDeprovision"
              >
                {{ deprovisionExecuting ? 'Deprovisioning...' : 'Deprovision schema' }}
              </button>
              <button
                type="button"
                class="secondary-button"
                :disabled="deprovisionExecuting"
                @click="closeDeprovisionPreview"
              >
                Close
              </button>
            </div>
          </div>
        </template>
      </section>
    </div>

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
            <p v-if="createStep === 'identity'">
              Enter the identity fields that determine the Oracle username.
            </p>
            <p v-else-if="createStep === 'access'">
              Configure password, reference access and application provisioning.
            </p>
            <p v-else-if="createStep === 'review'">
              Review exactly what DBAChum will change before execution.
            </p>
            <p v-else>Provisioning completed.</p>
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

        <div class="wizard-steps single-create-steps" aria-label="Create user progress">
          <span :class="{ active: createStep === 'identity' }">1 · Identity</span>
          <span :class="{ active: createStep === 'access' }">2 · Access</span>
          <span :class="{ active: createStep === 'review' }">3 · Preview</span>
        </div>

        <form
          v-if="createStep === 'identity'"
          class="connection-form oracle-user-form"
          @submit.prevent="continueIdentity"
        >
          <label :class="{ 'field-invalid': createFieldErrors.employeeId }">
            Employee ID
            <input
              v-model="createForm.employeeId"
              required
              maxlength="100"
              autocomplete="off"
              placeholder="12345"
              @input="identityInput('employeeId')"
            />
            <small v-if="createFieldErrors.employeeId" class="field-error">{{ createFieldErrors.employeeId }}</small>
          </label>

          <div class="connection-form-row">
            <label :class="{ 'field-invalid': createFieldErrors.firstName }">
              First name
              <input
                v-model="createForm.firstName"
                required
                maxlength="100"
                autocomplete="off"
                @input="identityInput('firstName')"
              />
              <small v-if="createFieldErrors.firstName" class="field-error">{{ createFieldErrors.firstName }}</small>
            </label>

            <label :class="{ 'field-invalid': createFieldErrors.lastName }">
              Last name
              <input
                v-model="createForm.lastName"
                required
                maxlength="100"
                autocomplete="off"
                @input="identityInput('lastName')"
              />
              <small v-if="createFieldErrors.lastName" class="field-error">{{ createFieldErrors.lastName }}</small>
            </label>
          </div>

          <label :class="{ 'field-invalid': createFieldErrors.middleName }">
            Middle name <span class="optional-label">Optional</span>
            <input
              v-model="createForm.middleName"
              maxlength="100"
              autocomplete="off"
              @input="identityInput('middleName')"
            />
            <small v-if="createFieldErrors.middleName" class="field-error">{{ createFieldErrors.middleName }}</small>
          </label>

          <div class="username-generation-block" :class="{ 'field-invalid': createFieldErrors.username }">
            <div>
              <strong>Generated username</strong>
              <small>DBAChum uses first initial + optional middle initial + concatenated last name + exact employee ID. Punctuation is removed and the username is always uppercase.</small>
            </div>
            <input
              :value="createForm.username"
              readonly
              autocomplete="off"
              placeholder="Enter identity details, then generate"
            />
            <small v-if="createFieldErrors.username" class="field-error">{{ createFieldErrors.username }}</small>
            <button type="button" class="secondary-button" :disabled="!identityReady" @click="generateUsername">
              {{ createForm.username ? 'Regenerate username' : 'Generate username' }}
            </button>
          </div>

          <p v-if="createError" class="login-error">{{ createError }}</p>
          <div class="connection-form-actions">
            <button type="submit" class="primary-button" :disabled="usernameChecking || !createForm.username">
              {{ usernameChecking ? 'Checking username...' : 'Next' }}
            </button>
            <button type="button" class="secondary-button" @click="closeCreate">Cancel</button>
          </div>
        </form>

        <form
          v-else-if="createStep === 'access'"
          class="connection-form oracle-user-form"
          @submit.prevent="reviewCreate"
        >
          <div class="preview-callout identity-confirmation">
            <div><span>Username</span><strong>{{ createForm.username }}</strong></div>
            <div><span>Employee</span><strong>{{ [createForm.firstName, createForm.middleName, createForm.lastName].filter(Boolean).join(' ') }} · {{ createForm.employeeId }}</strong></div>
          </div>

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
            <small>Only profiles enabled for this parent Oracle database appear here.</small>
          </label>

          <div v-if="selectedProvisioningProfile && !selectedProvisioningProfile.ready" class="utility-warning oracle-create-warning">
            {{ selectedProvisioningProfile.issues.join(' ') }}
          </div>

          <label :class="{ 'field-invalid': createFieldErrors.password }">
            Initial password
            <input
              v-model="createForm.password"
              required
              :type="showPassword ? 'text' : 'password'"
              minlength="8"
              maxlength="128"
              autocomplete="new-password"
              placeholder="At least 8 characters"
              @input="setCreateFieldError('password', null)"
            />
            <small v-if="createFieldErrors.password" class="field-error">{{ createFieldErrors.password }}</small>
            <span class="oracle-password-actions">
              <button type="button" class="secondary-button" @click="generatePassword">Generate password</button>
              <button type="button" class="secondary-button" @click="showPassword = !showPassword">{{ showPassword ? 'Hide password' : 'Show password' }}</button>
            </span>
            <small>Type the requested custom password, or generate the current 3-letter + 5-digit pattern.</small>
          </label>

          <label :class="{ 'field-invalid': createFieldErrors.referenceUsername }">
            Reference user <span class="optional-label">Optional</span>
            <input
              v-model="createForm.referenceUsername"
              maxlength="30"
              autocomplete="off"
              placeholder="Existing user whose roles should be reviewed"
              @input="referenceInput"
            />
            <small v-if="createFieldErrors.referenceUsername" class="field-error">{{ createFieldErrors.referenceUsername }}</small>
            <small>Leave blank when no reference user is needed. Direct system privileges are never copied.</small>
            <button
              v-if="createForm.referenceUsername.trim()"
              type="button"
              class="secondary-button reference-inspect-button"
              :disabled="oracleStore.loadingReference"
              @click="inspectReferenceAccess"
            >
              {{ oracleStore.loadingReference ? 'Inspecting access...' : reference ? 'Reload reference access' : 'Inspect reference access' }}
            </button>
          </label>

          <section v-if="reference" class="oracle-role-review access-role-selection">
            <div>
              <h3>Reference roles</h3>
              <p>Select the roles to copy before moving to Preview. ADMIN OPTION is intentionally not copied.</p>
            </div>
            <div v-if="reference.roles.length === 0" class="empty-state">Reference user has no role grants.</div>
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

          <div v-for="warning in reference?.warnings ?? []" :key="warning" class="utility-warning oracle-create-warning">
            {{ warning }}
          </div>

          <section v-if="reference?.system_privileges.length" class="oracle-system-privileges access-system-privileges">
            <h3>Direct system privileges — review only</h3>
            <p>Visible for comparison only; DBAChum will not grant these automatically.</p>
            <div class="oracle-privilege-list">
              <span v-for="privilege in reference.system_privileges" :key="privilege.name">
                {{ privilege.name }}<template v-if="privilege.admin_option"> · ADMIN OPTION</template>
              </span>
            </div>
          </section>

          <div class="connection-form-row">
            <label>Default tablespace <span class="optional-label">Optional</span><input v-model="createForm.defaultTablespace" maxlength="30" placeholder="Uses reference/default when blank" /></label>
            <label>Temporary tablespace <span class="optional-label">Optional</span><input v-model="createForm.temporaryTablespace" maxlength="30" placeholder="Uses reference/default when blank" /></label>
          </div>
          <label>Profile <span class="optional-label">Optional</span><input v-model="createForm.profile" maxlength="30" placeholder="Uses reference/default when blank" /></label>
          <div class="connection-form-row">
            <label>Requestor <span class="optional-label">Optional</span><input v-model="createForm.requestorName" maxlength="200" placeholder="Requestor full name" /></label>
            <label>Request / ticket reference <span class="optional-label">Optional</span><input v-model="createForm.requestReference" maxlength="100" placeholder="REQ-12345" /></label>
          </div>
          <label>Remarks <span class="optional-label">Optional</span><textarea v-model="createForm.remarks" rows="3" maxlength="1000" placeholder="Reason, access note, or provisioning remarks"></textarea></label>

          <p v-if="createError" class="login-error">{{ createError }}</p>
          <div class="connection-form-actions">
            <button type="submit" class="primary-button" :disabled="oracleStore.loadingReference || previewLoading">
              {{ previewLoading ? 'Building preview...' : oracleStore.loadingReference ? 'Inspecting reference...' : 'Next' }}
            </button>
            <button type="button" class="secondary-button" :disabled="previewLoading" @click="createStep = 'identity'">Back</button>
          </div>
        </form>

        <div
          v-else-if="createStep === 'review'"
          class="oracle-user-review"
        >
          <details class="wizard-review-details">
            <summary>
              <span>Identity &amp; account</span>
              <strong>{{ createForm.username }}</strong>
            </summary>
            <div class="oracle-user-review-summary">
              <div><span>Employee</span><strong>{{ createForm.employeeId }} · {{ [createForm.firstName, createForm.middleName, createForm.lastName].filter(Boolean).join(' ') }}</strong></div>
              <div><span>Provisioning</span><strong>{{ selectedProvisioningProfile?.name ?? 'No provisioning' }}</strong></div>
              <div><span>Reference user</span><strong>{{ reference?.username ?? 'None' }}</strong></div>
              <div><span>Default tablespace</span><strong>{{ createForm.defaultTablespace || 'Database default' }}</strong></div>
              <div><span>Temporary tablespace</span><strong>{{ createForm.temporaryTablespace || 'Database default' }}</strong></div>
              <div><span>Profile</span><strong>{{ createForm.profile || 'Database default' }}</strong></div>
            </div>
          </details>

          <details v-if="reference" class="wizard-review-details role-preview-summary">
            <summary><span>Roles to grant</span><strong>{{ selectedRoles.length }}</strong></summary>
            <section class="oracle-role-review">
            <div>
              <h3>Roles to grant</h3>
              <p>The role selection was made in Access. Go Back if it needs to change.</p>
            </div>
            <div v-if="selectedRoles.length === 0" class="empty-state">No reference roles selected.</div>
            <div v-else class="oracle-privilege-list">
              <span v-for="roleName in selectedRoles" :key="roleName">{{ roleName }}</span>
            </div>
            </section>
          </details>

          <section v-if="provisioningPreview" class="oracle-provisioning-preview">
            <div class="preview-callout">
              <strong>Reviewed execution plan — no changes have been made yet.</strong>
              <span>Click Provision once to execute this parent account and its application provisioning lifecycle.</span>
            </div>

            <details class="wizard-review-details">
              <summary><span>Oracle execution plan</span><strong>{{ provisioningPreview.account_action.toUpperCase() }}</strong></summary>
              <div class="preview-summary-grid">
                <div><span>Oracle account</span><strong>{{ provisioningPreview.account_exists ? 'Existing → ALTER / reconcile' : 'Not found → CREATE' }}</strong></div>
                <div><span>Parent database</span><strong>{{ provisioningPreview.schema_connection_name }}</strong></div>
                <div><span>Requester IP</span><strong>{{ provisioningPreview.requester_ip || 'Unavailable' }}</strong></div>
              </div>
            </details>

            <details class="wizard-review-details">
              <summary><span>Application provisioning</span><strong>{{ provisioningPreview.table_steps.length }} step(s)</strong></summary>
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
            </details>

            <details v-if="provisioningPreview.ldap.enabled" class="wizard-review-details">
              <summary><span>LDAP</span><strong>{{ provisioningPreview.ldap.profile_name }}</strong></summary>
              <section class="preview-section">
              <h3>LDAP</h3>
              <p>
                {{ provisioningPreview.ldap.profile_name }} · directory entry will be added automatically · LDIF validated as
                <strong>{{ provisioningPreview.ldap.filename }}</strong>
              </p>
              </section>
            </details>

            <div v-if="provisioningPreview.warnings.length" class="utility-warning oracle-create-warning">
              <ul>
                <li v-for="warning in provisioningPreview.warnings" :key="warning">{{ warning }}</li>
              </ul>
            </div>
          </section>

          <div class="utility-warning oracle-create-warning">
            <template v-if="provisioningPreview">
              Provision will CREATE or ALTER the Oracle account, reconcile roles, then upsert the configured application rows. Duplicate matches block execution.
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
              :disabled="provisioningExecuting || !provisioningPreview.ready_to_execute"
              @click="executeProvisioning"
            >
              {{ provisioningExecuting ? 'Provisioning...' : `Provision ${createForm.username}` }}
            </button>

            <button
              type="button"
              class="secondary-button"
              :disabled="oracleStore.creatingUser || provisioningExecuting"
              @click="createStep = 'access'"
            >
              Back
            </button>
          </div>
        </div>

        <div
          v-else
          class="oracle-user-success"
        >
          <section v-if="resultPassword" class="requester-result-summary">
            <div>
              <strong>Requester summary</strong>
              <small>Copy this while the result is open. The password is not written to lifecycle audit/history.</small>
            </div>
            <pre>{{ requesterSummary }}</pre>
            <div class="requester-summary-actions">
              <button type="button" class="secondary-button" @click="copyRequesterSummary">Copy summary</button>
              <small v-if="summaryCopyNotice">{{ summaryCopyNotice }}</small>
            </div>
          </section>

          <template v-if="provisioningResult">
            <strong>{{ provisioningResult.username }}</strong>
            <p>
              Provisioning {{ provisioningResult.status === 'succeeded' ? 'completed successfully.' : provisioningResult.status === 'partial' ? 'completed partially.' : 'failed.' }}
            </p>

            <div class="provisioning-result-grid">
              <div>
                <span>Oracle account</span>
                <strong>{{ provisioningResult.account.action.toUpperCase() }}</strong>
              </div>
              <div>
                <span>Roles</span>
                <strong>{{ provisioningResult.roles.length }}</strong>
              </div>
              <div>
                <span>Application steps</span>
                <strong>{{ provisioningResult.table_steps.length }}</strong>
              </div>
            </div>

            <div v-if="provisioningResult.table_steps.length" class="provisioning-result-steps">
              <div v-for="step in provisioningResult.table_steps" :key="`${step.index}-${step.name}`">
                <strong>Step {{ step.index }} · {{ step.name }}</strong>
                <span>{{ step.owner }}.{{ step.table_name }} · {{ step.action.toUpperCase() }}</span>
                <small v-if="Object.keys(step.generated_values).length">Generated: {{ JSON.stringify(step.generated_values) }}</small>
                <small v-if="step.error" class="login-error">{{ step.error }}</small>
              </div>
            </div>

            <div v-if="provisioningResult.ldap.enabled" class="preview-callout">
              <div>
                <strong>LDAP · {{ (provisioningResult.ldap.action ?? 'not_run').replace('_', ' ').toUpperCase() }}</strong>
                <span v-if="provisioningResult.ldap.dn">{{ provisioningResult.ldap.dn }}</span>
                <span v-if="provisioningResult.ldap.error" class="login-error">{{ provisioningResult.ldap.error }}</span>
              </div>
            </div>

            <button
              v-if="['generated', 'created', 'already_present'].includes(provisioningResult.ldap.action ?? '') && provisioningResult.ldap.content"
              type="button"
              class="secondary-button"
              @click="downloadProvisioningLdif"
            >
              Download {{ provisioningResult.ldap.filename }}
            </button>

            <p v-if="provisioningResult.error" class="login-error">
              {{ provisioningResult.error }}
            </p>

            <small>Run ID: {{ provisioningResult.run_id }}</small>
            <small>Audit ID: {{ provisioningResult.audit_id }}</small>
            <small v-if="provisioningResult.requester_ip">Requester IP: {{ provisioningResult.requester_ip }}</small>
          </template>

          <template v-else>
            <strong>{{ createResult?.username }}</strong>
            <p>
              Oracle account created successfully with
              {{ createResult?.roles_applied.length ?? 0 }} role(s).
            </p>
            <small>Audit ID: {{ createResult?.audit_id }}</small>
            <small v-if="createResult?.requester_ip">Requester IP: {{ createResult.requester_ip }}</small>
          </template>

          <div class="connection-form-actions">
            <button
              type="button"
              class="primary-button"
              @click="createAnotherUser"
            >
              Create another user
            </button>
            <button
              type="button"
              class="secondary-button"
              @click="closeCreate"
            >
              Done
            </button>
          </div>
        </div>
      </section>
    </div>

    <OracleBulkProvisionModal
      v-if="bulkCreateOpen"
      :connection-id="connectionId"
      @close="bulkCreateOpen = false"
      @completed="bulkCompleted"
    />
  </section>
</template>


<style scoped>
.toolbar-create-dropdown { position: relative; display: inline-block; }
.toolbar-create-menu { position: absolute; right: 0; top: calc(100% + .35rem); z-index: 15; min-width: 10rem; padding: .35rem; border: 1px solid var(--border-color); border-radius: .65rem; background: var(--color-surface); box-shadow: 0 .7rem 1.8rem rgba(0, 0, 0, .14); }
.toolbar-create-menu button { display: block; width: 100%; border: 0; border-radius: .45rem; padding: .6rem .7rem; text-align: left; color: inherit; background: transparent; cursor: pointer; }
.toolbar-create-menu button:hover { background: var(--color-surface-secondary); }
.wizard-review-details { border: 1px solid var(--border-color); border-radius: .7rem; overflow: hidden; }
.wizard-review-details > summary { display: flex; justify-content: space-between; gap: 1rem; align-items: center; padding: .75rem .85rem; cursor: pointer; list-style: none; }
.wizard-review-details > summary::-webkit-details-marker { display: none; }
.wizard-review-details > summary::after { content: '▾'; opacity: .65; margin-left: auto; }
.wizard-review-details[open] > summary::after { transform: rotate(180deg); }
.wizard-review-details > .oracle-user-review-summary, .wizard-review-details > .preview-summary-grid, .wizard-review-details > .preview-section, .wizard-review-details > .oracle-role-review { padding: 0 .85rem .85rem; }
.requester-result-summary { display: grid; gap: .7rem; padding: .9rem; border: 1px solid var(--border-color); border-radius: .75rem; }
.requester-result-summary > div:first-child { display: grid; gap: .2rem; }
.requester-result-summary pre { margin: 0; padding: .8rem; border-radius: .6rem; background: var(--color-surface-secondary); white-space: pre-wrap; overflow-wrap: anywhere; font: inherit; }
.requester-summary-actions { display: flex; align-items: center; gap: .7rem; }
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

.provisioning-result-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: .75rem; margin: .8rem 0; width: 100%; }
.provisioning-result-grid > div { display: grid; gap: .2rem; padding: .7rem; border: 1px solid var(--border-color); border-radius: .65rem; }
.provisioning-result-grid span { font-size: .78rem; opacity: .7; }
.provisioning-result-steps { display: grid; gap: .5rem; width: 100%; margin: .6rem 0; }
.provisioning-result-steps > div { display: grid; gap: .2rem; padding: .65rem .75rem; border: 1px solid var(--border-color); border-radius: .6rem; }
.provisioning-result-steps span, .provisioning-result-steps small { opacity: .78; }

.wizard-steps { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: .5rem; margin-bottom: 1rem; }
.wizard-steps span { padding: .55rem .7rem; border: 1px solid var(--border-color); border-radius: .6rem; font-size: .82rem; opacity: .62; text-align: center; }
.wizard-steps span.active { opacity: 1; font-weight: 700; border-color: var(--accent); }
.field-invalid input, .field-invalid select, .field-invalid textarea, .username-generation-block.field-invalid input { border-color: var(--color-danger) !important; box-shadow: 0 0 0 1px var(--color-danger); }
.field-error { color: var(--color-danger); font-size: .75rem; }
.username-generation-block { display: grid; gap: .55rem; padding: .85rem; border: 1px solid var(--border-color); border-radius: .7rem; }
.username-generation-block > div { display: grid; gap: .2rem; }
.username-generation-block button { justify-self: start; }
.reference-inspect-button { align-self: start; margin-top: .35rem; }
.access-role-selection, .access-system-privileges { margin-top: .25rem; }
.role-preview-summary .oracle-privilege-list { margin-top: .45rem; }
.identity-confirmation { display: grid; grid-template-columns: 1fr 2fr; gap: .7rem; }
.identity-confirmation > div { display: grid; gap: .15rem; }
.identity-confirmation span { font-size: .78rem; opacity: .7; }
@media (max-width: 700px) { .wizard-steps, .identity-confirmation { grid-template-columns: 1fr; } }

.access-inspector-modal { width: min(100%, 78rem); }
.access-inspector-summary { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: .7rem; }
.access-inspector-summary > div, .access-account-summary > div { display: grid; gap: .2rem; padding: .7rem; border: 1px solid var(--border-color); border-radius: .65rem; }
.access-inspector-summary span, .access-account-summary span { font-size: .78rem; opacity: .7; }
.access-account-summary { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: .7rem; }
.access-powerful-section { display: grid; gap: .65rem; }
.access-finding-list { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: .6rem; }
.access-finding-list article { display: grid; gap: .2rem; padding: .7rem; border: 1px solid var(--color-danger); border-radius: .65rem; }
.access-finding-list article span, .access-finding-list article small { opacity: .78; }
.access-inspector-section { border: 1px solid var(--border-color); border-radius: .7rem; overflow: hidden; }
.access-inspector-section > summary { cursor: pointer; padding: .75rem .85rem; font-weight: 700; background: var(--color-surface-secondary); }
.access-inspector-section > .oracle-privilege-list { padding: .8rem; }
.access-table-wrap { max-height: 24rem; overflow: auto; }
.access-table-wrap table { width: 100%; border-collapse: collapse; }
.access-table-wrap th, .access-table-wrap td { padding: .6rem .75rem; text-align: left; border-bottom: 1px solid var(--border-color); vertical-align: top; }
.access-table-wrap thead th { position: sticky; top: 0; z-index: 1; background: var(--color-surface); }
.access-table-wrap tbody tr:last-child td { border-bottom: 0; }
.access-object-toolbar { display: flex; align-items: center; gap: .7rem; padding: .7rem .8rem; border-top: 1px solid var(--border-color); }
.access-object-toolbar input { min-width: min(32rem, 70vw); }
.access-object-toolbar span { font-size: .8rem; opacity: .72; white-space: nowrap; }
@media (max-width: 800px) {
  .access-inspector-summary, .access-account-summary, .access-finding-list { grid-template-columns: 1fr; }
  .access-object-toolbar { align-items: stretch; flex-direction: column; }
  .access-object-toolbar input { min-width: 0; width: 100%; }
}

</style>
