<script setup lang="ts">
import { computed, ref } from 'vue'

import {
  useProvisioningStore,
  type BulkProvisionExecutionResult,
  type BulkProvisionImportResult,
  type BulkProvisionPreviewResult,
  type BulkProvisionRequest,
  type BulkProvisionRowInput,
} from '@/stores/provisioning'

const props = defineProps<{ connectionId: string }>()
const emit = defineEmits<{ close: []; completed: [] }>()

const provisioningStore = useProvisioningStore()
type BulkStep = 'import' | 'access' | 'review' | 'result'
const step = ref<BulkStep>('import')
const importResult = ref<BulkProvisionImportResult | null>(null)
const preview = ref<BulkProvisionPreviewResult | null>(null)
const execution = ref<BulkProvisionExecutionResult | null>(null)
const loading = ref(false)
const error = ref<string | null>(null)
const selectedFilename = ref('')
const profileId = ref('')
const useCommonReference = ref(false)
const commonReferenceUser = ref('')
const requestor = ref('')
const requestReference = ref('')
const remarks = ref('')
const showResultPasswords = ref(false)

const profiles = computed(() => provisioningStore.profilesByConnection[props.connectionId] ?? [])
const canContinueImport = computed(() => Boolean(importResult.value && importResult.value.invalid_count === 0))

function close() {
  if (!loading.value) emit('close')
}

function downloadTemplate() {
  const csv = [
    'employee_id,first_name,middle_name,last_name,password,reference_user',
    '12345,Juan,M,Santos,,',
  ].join('\r\n')
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = 'dbachum-bulk-user-template.csv'
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  URL.revokeObjectURL(url)
}

function rowInputRows(): BulkProvisionRowInput[] {
  return (importResult.value?.rows ?? []).map((row) => ({
    row_number: row.row_number,
    password_mode: row.password_mode,
    employee_id: row.employee_id,
    first_name: row.first_name,
    middle_name: row.middle_name,
    last_name: row.last_name,
    reference_user: row.reference_user,
    password: row.password,
  }))
}

function requestPayload(rows = rowInputRows()): BulkProvisionRequest {
  return {
    profile_id: profileId.value || null,
    use_common_reference: useCommonReference.value,
    common_reference_user: useCommonReference.value
      ? commonReferenceUser.value.trim().toUpperCase() || null
      : null,
    requestor: requestor.value.trim() || null,
    request_reference: requestReference.value.trim() || null,
    remarks: remarks.value.trim() || null,
    rows,
  }
}

async function handleFile(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  selectedFilename.value = file.name
  loading.value = true
  error.value = null
  preview.value = null
  execution.value = null
  try {
    importResult.value = await provisioningStore.importBulkFile(props.connectionId, file)
  } catch (caught) {
    importResult.value = null
    error.value = caught instanceof Error ? caught.message : 'Unable to import spreadsheet.'
  } finally {
    loading.value = false
    input.value = ''
  }
}

function goAccess() {
  error.value = null
  if (!canContinueImport.value) {
    error.value = 'Fix the invalid spreadsheet rows before continuing.'
    return
  }
  step.value = 'access'
}

async function buildPreview() {
  error.value = null
  if (useCommonReference.value && !commonReferenceUser.value.trim()) {
    error.value = 'Enter the common reference user or turn the option off.'
    return
  }
  loading.value = true
  try {
    preview.value = await provisioningStore.previewBulk(props.connectionId, requestPayload())
    step.value = 'review'
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : 'Unable to build bulk provisioning preview.'
  } finally {
    loading.value = false
  }
}

async function executeBatch() {
  if (!preview.value?.ready_to_execute) return
  loading.value = true
  error.value = null
  try {
    execution.value = await provisioningStore.executeBulk(props.connectionId, requestPayload())
    step.value = 'result'
    emit('completed')
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : 'Unable to execute bulk provisioning.'
  } finally {
    // Passwords stay only in this open modal and disappear when it is closed.
    loading.value = false
  }
}

const retryableResults = computed(() => execution.value?.rows.filter((row) => row.status !== 'succeeded') ?? [])

async function retryFailed() {
  const currentExecution = execution.value
  if (!currentExecution || retryableResults.value.length === 0) return
  loading.value = true
  error.value = null
  const importedRows = importResult.value?.rows ?? []
  const importedByRow = new Map<number, (typeof importedRows)[number]>(
    importedRows.map((row) => [row.row_number, row]),
  )
  try {
    for (const result of retryableResults.value) {
      const imported = importedByRow.get(result.row_number)
      if (!imported) continue
      if (result.run_id) {
        try {
          const retried = await provisioningStore.retryRun(
            props.connectionId,
            result.run_id,
            imported.password,
          )
          result.status = retried.status
          result.error = retried.error
          result.audit_id = retried.audit_id
        } catch (caught) {
          result.status = 'failed'
          result.error = caught instanceof Error ? caught.message : 'Retry failed.'
        }
      } else {
        try {
          const rerun = await provisioningStore.executeBulk(
            props.connectionId,
            requestPayload([{
              row_number: imported.row_number,
              password_mode: imported.password_mode,
              employee_id: imported.employee_id,
              first_name: imported.first_name,
              middle_name: imported.middle_name,
              last_name: imported.last_name,
              reference_user: imported.reference_user,
              password: imported.password,
            }]),
          )
          const row = rerun.rows[0]
          if (row) Object.assign(result, row)
        } catch (caught) {
          result.status = 'failed'
          result.error = caught instanceof Error ? caught.message : 'Retry failed.'
        }
      }
    }
    const succeeded = currentExecution.rows.filter((row) => row.status === 'succeeded').length
    const partial = currentExecution.rows.filter((row) => row.status === 'partial').length
    const failed = currentExecution.rows.filter((row) => row.status === 'failed').length
    currentExecution.succeeded_count = succeeded
    currentExecution.partial_count = partial
    currentExecution.failed_count = failed
    currentExecution.status = succeeded === currentExecution.row_count
      ? 'succeeded'
      : failed === currentExecution.row_count
        ? 'failed'
        : 'partial'
    emit('completed')
  } finally {
    loading.value = false
  }
}

function rowError(row: { errors: Record<string, string> }) {
  return Object.values(row.errors).join(' ')
}

function passwordForRow(rowNumber: number) {
  return importResult.value?.rows.find((row) => row.row_number === rowNumber)?.password ?? ''
}

function downloadResultsCsv() {
  if (!execution.value) return
  const quote = (value: string) => `"${value.replaceAll('"', '""')}"`
  const lines = [
    ['row', 'username', 'initial_password', 'status', 'run_or_audit', 'error'].join(','),
    ...execution.value.rows.map((row) => [
      String(row.row_number),
      row.username ?? '',
      passwordForRow(row.row_number),
      row.status,
      row.run_id ?? row.audit_id ?? '',
      row.error ?? '',
    ].map(quote).join(',')),
  ]
  const blob = new Blob([lines.join('\r\n')], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = `dbachum-bulk-provision-results-${new Date().toISOString().slice(0, 10)}.csv`
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  URL.revokeObjectURL(url)
}
</script>

<template>
  <div class="modal-backdrop" @click.self="close">
    <section class="modal-panel oracle-bulk-modal" role="dialog" aria-modal="true" aria-label="Bulk create Oracle users">
      <div class="modal-header">
        <div>
          <h2>Bulk create Oracle users</h2>
          <p v-if="step === 'import'">Import employee details first. Nothing is created during import.</p>
          <p v-else-if="step === 'access'">Choose the shared provisioning settings for this batch.</p>
          <p v-else-if="step === 'review'">Review every generated account before execution.</p>
          <p v-else>Batch execution results.</p>
        </div>
        <button type="button" class="modal-close" aria-label="Close" :disabled="loading" @click="close">×</button>
      </div>

      <div class="wizard-steps" aria-label="Bulk provisioning progress">
        <span :class="{ active: step === 'import' }">1 · Import</span>
        <span :class="{ active: step === 'access' }">2 · Access</span>
        <span :class="{ active: step === 'review' }">3 · Preview</span>
        <span :class="{ active: step === 'result' }">4 · Result</span>
      </div>

      <template v-if="step === 'import'">
        <div class="bulk-header-guide">
          <strong>Spreadsheet headers</strong>
          <p>Required: <code>employee_id</code>, <code>first_name</code>, <code>last_name</code></p>
          <p>Optional: <code>middle_name</code>, <code>password</code>, <code>reference_user</code></p>
          <small>Supported: .xlsx and UTF-8 .csv · blank password = DBAChum generates one · reference user is optional.</small>
        </div>

        <div class="bulk-file-row">
          <label class="bulk-file-picker">
            <span>Spreadsheet file</span>
            <input type="file" accept=".xlsx,.csv" :disabled="loading" @change="handleFile" />
            <small v-if="selectedFilename">{{ selectedFilename }}</small>
          </label>
          <button type="button" class="secondary-button" :disabled="loading" @click="downloadTemplate">Download CSV template</button>
        </div>

        <div v-if="loading" class="empty-state">Reading and validating spreadsheet...</div>
        <template v-else-if="importResult">
          <div class="preview-summary-grid">
            <div><span>Rows</span><strong>{{ importResult.row_count }}</strong></div>
            <div><span>Valid</span><strong>{{ importResult.valid_count }}</strong></div>
            <div><span>Invalid</span><strong>{{ importResult.invalid_count }}</strong></div>
          </div>
          <div class="utility-table-wrap bulk-preview-table">
            <table class="utility-table">
              <thead><tr><th>Row</th><th>Employee ID</th><th>First</th><th>Middle</th><th>Last</th><th>Username</th><th>Reference</th><th>Password</th><th>Status</th></tr></thead>
              <tbody>
                <tr v-for="row in importResult.rows" :key="row.row_number" :class="{ 'bulk-row-invalid': !row.valid }">
                  <td>{{ row.row_number }}</td>
                  <td :class="{ 'bulk-cell-invalid': row.errors.employee_id }">{{ row.employee_id || '—' }}</td>
                  <td :class="{ 'bulk-cell-invalid': row.errors.first_name }">{{ row.first_name || '—' }}</td>
                  <td :class="{ 'bulk-cell-invalid': row.errors.middle_name }">{{ row.middle_name || '—' }}</td>
                  <td :class="{ 'bulk-cell-invalid': row.errors.last_name }">{{ row.last_name || '—' }}</td>
                  <td :class="{ 'bulk-cell-invalid': row.errors.username }">{{ row.username || '—' }}</td>
                  <td :class="{ 'bulk-cell-invalid': row.errors.reference_user }">{{ row.reference_user || '—' }}</td>
                  <td :class="{ 'bulk-cell-invalid': row.errors.password }">{{ row.password_mode.toUpperCase() }}</td>
                  <td><span class="provisioning-status" :data-status="row.valid ? 'succeeded' : 'failed'">{{ row.valid ? 'VALID' : 'INVALID' }}</span><small v-if="!row.valid" class="field-error bulk-row-error">{{ rowError(row) }}</small></td>
                </tr>
              </tbody>
            </table>
          </div>
        </template>

        <p v-if="error" class="login-error">{{ error }}</p>
        <div class="connection-form-actions">
          <button type="button" class="primary-button" :disabled="!canContinueImport || loading" @click="goAccess">Next</button>
          <button type="button" class="secondary-button" :disabled="loading" @click="close">Cancel</button>
        </div>
      </template>

      <template v-else-if="step === 'access'">
        <div class="connection-form">
          <label>
            Application provisioning
            <select v-model="profileId">
              <option value="">No provisioning — schema/user only</option>
              <option v-for="profile in profiles" :key="profile.id" :value="profile.id" :disabled="!profile.ready">{{ profile.name }}{{ profile.ready ? '' : ' · Needs attention' }}</option>
            </select>
          </label>

          <label class="bulk-common-reference">
            <span class="checkbox-row"><input v-model="useCommonReference" type="checkbox" /> Use the same reference user for all rows</span>
            <small>When enabled, spreadsheet reference_user values are ignored for this batch.</small>
          </label>
          <label v-if="useCommonReference" :class="{ 'field-invalid': useCommonReference && !commonReferenceUser.trim() }">
            Common reference user
            <input v-model="commonReferenceUser" maxlength="30" autocomplete="off" placeholder="RMSUSER01" />
            <small v-if="useCommonReference && !commonReferenceUser.trim()" class="field-error">Reference user is required while this option is enabled.</small>
          </label>

          <div class="connection-form-row">
            <label>Requestor <span class="optional-label">Optional</span><input v-model="requestor" maxlength="200" /></label>
            <label>Request / ticket <span class="optional-label">Optional</span><input v-model="requestReference" maxlength="100" /></label>
          </div>
          <label>Remarks <span class="optional-label">Optional</span><textarea v-model="remarks" rows="3" maxlength="1000"></textarea></label>
        </div>
        <p v-if="error" class="login-error">{{ error }}</p>
        <div class="connection-form-actions">
          <button type="button" class="primary-button" :disabled="loading" @click="buildPreview">{{ loading ? 'Building preview...' : 'Next' }}</button>
          <button type="button" class="secondary-button" :disabled="loading" @click="step = 'import'">Back</button>
        </div>
      </template>

      <template v-else-if="step === 'review' && preview">
        <div class="preview-summary-grid">
          <div><span>Rows</span><strong>{{ preview.row_count }}</strong></div>
          <div><span>Valid</span><strong>{{ preview.valid_count }}</strong></div>
          <div><span>Blocked</span><strong>{{ preview.invalid_count }}</strong></div>
        </div>
        <div class="utility-table-wrap bulk-preview-table">
          <table class="utility-table">
            <thead><tr><th>Row</th><th>Username</th><th>Name</th><th>Reference</th><th>Roles</th><th>App steps</th><th>LDAP</th><th>Status</th></tr></thead>
            <tbody>
              <tr v-for="row in preview.rows" :key="row.row_number" :class="{ 'bulk-row-invalid': !row.valid }">
                <td>{{ row.row_number }}</td>
                <td><strong>{{ row.username || '—' }}</strong></td>
                <td>{{ [row.first_name, row.middle_name, row.last_name].filter(Boolean).join(' ') }}</td>
                <td>{{ row.reference_user || '—' }}</td>
                <td>{{ row.roles.length }}</td>
                <td>{{ row.provisioning?.table_steps.length ?? 0 }}</td>
                <td>{{ row.provisioning?.ldap.enabled ? 'YES' : '—' }}</td>
                <td><span class="provisioning-status" :data-status="row.valid ? 'succeeded' : 'failed'">{{ row.valid ? 'READY' : 'BLOCKED' }}</span><small v-if="!row.valid" class="field-error bulk-row-error">{{ rowError(row) }}</small></td>
              </tr>
            </tbody>
          </table>
        </div>
        <div class="utility-warning oracle-create-warning">Execution performs the normal single-user provisioning lifecycle for each row. One row failing does not hide later row results.</div>
        <p v-if="error" class="login-error">{{ error }}</p>
        <div class="connection-form-actions">
          <button type="button" class="primary-button" :disabled="loading || !preview.ready_to_execute" @click="executeBatch">{{ loading ? 'Provisioning batch...' : `Provision ${preview.row_count} users` }}</button>
          <button type="button" class="secondary-button" :disabled="loading" @click="step = 'access'">Back</button>
        </div>
      </template>

      <template v-else-if="step === 'result' && execution">
        <div class="preview-summary-grid">
          <div><span>Succeeded</span><strong>{{ execution.succeeded_count }}</strong></div>
          <div><span>Partial</span><strong>{{ execution.partial_count }}</strong></div>
          <div><span>Failed</span><strong>{{ execution.failed_count }}</strong></div>
        </div>
        <div class="bulk-result-password-actions">
          <button type="button" class="secondary-button" @click="showResultPasswords = !showResultPasswords">{{ showResultPasswords ? 'Hide passwords' : 'Show passwords' }}</button>
          <button type="button" class="secondary-button" @click="downloadResultsCsv">Download result CSV</button>
          <small>Passwords exist only in this open bulk session and are not added to DBAChum lifecycle/audit records.</small>
        </div>
        <div class="utility-table-wrap bulk-preview-table">
          <table class="utility-table">
            <thead><tr><th>Row</th><th>Username</th><th>Initial password</th><th>Status</th><th>Run / audit</th><th>Error</th></tr></thead>
            <tbody><tr v-for="row in execution.rows" :key="row.row_number"><td>{{ row.row_number }}</td><td><strong>{{ row.username || '—' }}</strong></td><td><code>{{ showResultPasswords ? passwordForRow(row.row_number) : '••••••••' }}</code></td><td><span class="provisioning-status" :data-status="row.status">{{ row.status.toUpperCase() }}</span></td><td><small>{{ row.run_id || row.audit_id || '—' }}</small></td><td><small :class="{ 'field-error': row.error }">{{ row.error || '—' }}</small></td></tr></tbody>
          </table>
        </div>
        <p v-if="error" class="login-error">{{ error }}</p>
        <div class="connection-form-actions">
          <button v-if="retryableResults.length" type="button" class="primary-button" :disabled="loading" @click="retryFailed">{{ loading ? 'Retrying...' : 'Retry failed / partial' }}</button>
          <button type="button" class="secondary-button" :disabled="loading" @click="close">Done</button>
        </div>
      </template>
    </section>
  </div>
</template>

<style scoped>
.oracle-bulk-modal { width: min(1180px, calc(100vw - 2rem)); max-height: calc(100vh - 2rem); overflow: auto; }
.wizard-steps { display: grid; grid-template-columns: repeat(4, 1fr); gap: .5rem; margin-bottom: 1rem; }
.wizard-steps span { padding: .55rem .7rem; border: 1px solid var(--border-color); border-radius: .6rem; font-size: .82rem; opacity: .65; text-align: center; }
.wizard-steps span.active { opacity: 1; font-weight: 700; border-color: var(--accent); }
.bulk-header-guide { display: grid; gap: .35rem; padding: .9rem; margin-bottom: 1rem; border: 1px solid var(--border-color); border-radius: .7rem; }
.bulk-header-guide p { margin: 0; }
.bulk-file-row { display: flex; align-items: end; gap: .75rem; flex-wrap: wrap; margin-bottom: 1rem; }
.bulk-file-picker { display: grid; gap: .4rem; margin-bottom: 0; min-width: min(520px, 100%); }
.bulk-preview-table { max-height: 430px; overflow: auto; margin-top: 1rem; }
.bulk-row-invalid { background: color-mix(in srgb, var(--color-danger) 7%, transparent); }
.bulk-cell-invalid { outline: 1px solid var(--color-danger); outline-offset: -2px; }
.bulk-row-error { display: block; max-width: 280px; margin-top: .25rem; }
.field-error { color: var(--color-danger); font-size: .75rem; }
.field-invalid input, .field-invalid select, .field-invalid textarea { border-color: var(--color-danger) !important; box-shadow: 0 0 0 1px var(--color-danger); }
.bulk-result-password-actions { display: flex; align-items: center; gap: .6rem; flex-wrap: wrap; margin-top: .8rem; }
.bulk-result-password-actions small { opacity: .72; }
.bulk-common-reference { padding: .75rem; border: 1px solid var(--border-color); border-radius: .65rem; }
@media (max-width: 800px) { .wizard-steps { grid-template-columns: 1fr 1fr; } }
</style>
