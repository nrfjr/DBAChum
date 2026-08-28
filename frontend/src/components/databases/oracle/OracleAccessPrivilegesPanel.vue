<script setup lang="ts">
import { computed, ref } from 'vue'
import {
  useOracleDbaStore,
  type OracleAccessGrantSource,
  type OracleAccessLookupResult,
} from '@/stores/oracleDba'

const props = defineProps<{
  connectionId: string
}>()

const oracleStore = useOracleDbaStore()

type LookupKind = 'role' | 'system_privilege' | 'object'

const lookupKind = ref<LookupKind>('role')
const lookupValue = ref('')
const owner = ref('')
const objectName = ref('')
const objectPrivilege = ref('')
const resultFilter = ref('')
const loading = ref(false)
const error = ref<string | null>(null)
const result = ref<OracleAccessLookupResult | null>(null)

const canSearch = computed(() => {
  if (lookupKind.value === 'object') {
    return Boolean(owner.value.trim() && objectName.value.trim())
  }
  return Boolean(lookupValue.value.trim())
})

const filteredMatches = computed(() => {
  if (!result.value) return []
  const term = resultFilter.value.trim().toLowerCase()
  if (!term) return result.value.matches

  return result.value.matches.filter((item) =>
    [
      item.username,
      item.status,
      item.basis,
      item.privilege,
      item.column_name,
      item.source.kind,
      ...item.source.via,
    ]
      .filter(Boolean)
      .some((value) => String(value).toLowerCase().includes(term)),
  )
})

function chooseKind(kind: LookupKind) {
  lookupKind.value = kind
  result.value = null
  error.value = null
  resultFilter.value = ''
}

function formatSource(source: OracleAccessGrantSource) {
  if (source.kind === 'direct') return 'Direct'
  if (source.kind === 'public') return 'PUBLIC'
  if (source.via.length) return `via ${source.via.join(' → ')}`
  return source.kind
}

function kindLabel() {
  if (lookupKind.value === 'role') return 'role'
  if (lookupKind.value === 'system_privilege') return 'system privilege'
  return 'object'
}

async function runLookup() {
  if (!canSearch.value || loading.value) return

  loading.value = true
  error.value = null
  result.value = null
  resultFilter.value = ''

  try {
    result.value = await oracleStore.loadAccessLookup(
      props.connectionId,
      {
        kind: lookupKind.value,
        value: lookupKind.value === 'object'
          ? undefined
          : lookupValue.value.trim().toUpperCase(),
        owner: lookupKind.value === 'object'
          ? owner.value.trim().toUpperCase()
          : undefined,
        object_name: lookupKind.value === 'object'
          ? objectName.value.trim().toUpperCase()
          : undefined,
        privilege: lookupKind.value === 'object'
          ? objectPrivilege.value.trim().toUpperCase() || undefined
          : undefined,
      },
    )
  } catch (caught) {
    error.value = caught instanceof Error
      ? caught.message
      : 'Unable to search Oracle access.'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <section class="panel access-privileges-panel">
    <div class="panel-header access-page-header">
      <div>
        <h2>Access &amp; Privileges</h2>
        <p>
          Search effective Oracle access across normal database users. This workspace is read-only.
        </p>
      </div>
      <span class="access-read-only-pill">Read only</span>
    </div>

    <div class="access-mode-tabs" role="tablist" aria-label="Access lookup type">
      <button
        type="button"
        :class="{ active: lookupKind === 'role' }"
        @click="chooseKind('role')"
      >
        Role
      </button>
      <button
        type="button"
        :class="{ active: lookupKind === 'system_privilege' }"
        @click="chooseKind('system_privilege')"
      >
        System privilege
      </button>
      <button
        type="button"
        :class="{ active: lookupKind === 'object' }"
        @click="chooseKind('object')"
      >
        Object access
      </button>
    </div>

    <div class="access-search-card">
      <template v-if="lookupKind === 'role'">
        <label>
          <span>Role name</span>
          <input
            v-model="lookupValue"
            type="text"
            autocomplete="off"
            placeholder="APP_USER"
            @keyup.enter="runLookup"
          />
          <small>Find users who receive the role directly or through another role.</small>
        </label>
      </template>

      <template v-else-if="lookupKind === 'system_privilege'">
        <label>
          <span>System privilege</span>
          <input
            v-model="lookupValue"
            type="text"
            autocomplete="off"
            placeholder="SELECT ANY TABLE"
            @keyup.enter="runLookup"
          />
          <small>Find direct, role-inherited and PUBLIC effective access.</small>
        </label>
      </template>

      <template v-else>
        <div class="access-object-inputs">
          <label>
            <span>Owner</span>
            <input
              v-model="owner"
              type="text"
              autocomplete="off"
              placeholder="APP"
              @keyup.enter="runLookup"
            />
          </label>
          <label>
            <span>Object</span>
            <input
              v-model="objectName"
              type="text"
              autocomplete="off"
              placeholder="ORDERS"
              @keyup.enter="runLookup"
            />
          </label>
          <label>
            <span>Privilege <small>optional</small></span>
            <input
              v-model="objectPrivilege"
              type="text"
              autocomplete="off"
              placeholder="SELECT"
              @keyup.enter="runLookup"
            />
          </label>
        </div>
        <small>
          Includes explicit object/column grants and applicable broad ANY-style privileges.
        </small>
      </template>

      <div class="access-search-actions">
        <button
          type="button"
          class="primary-button"
          :disabled="!canSearch || loading"
          @click="runLookup"
        >
          {{ loading ? 'Searching...' : 'Search access' }}
        </button>
      </div>
    </div>

    <div v-if="error" class="utility-warning access-error">
      {{ error }}
    </div>

    <template v-if="result">
      <section class="access-result-summary">
        <div>
          <span>Target</span>
          <strong>{{ result.target }}</strong>
        </div>
        <div>
          <span>Matching users</span>
          <strong>{{ result.unique_user_count }}</strong>
        </div>
        <div>
          <span>Result rows</span>
          <strong>{{ result.matches.length }}</strong>
        </div>
        <div>
          <span>PUBLIC access</span>
          <strong>{{ result.public_access ? 'YES' : 'NO' }}</strong>
        </div>
      </section>

      <div v-if="!result.target_exists" class="utility-warning">
        The requested {{ kindLabel() }} was not found in the available Oracle catalog data.
      </div>

      <details v-if="result.powerful" class="access-alert-section">
        <summary>⚠ Elevated access target</summary>
        <p>
          {{ result.target }} matches DBAChum's explicit elevated-access rules. This is a warning, not a security score.
        </p>
      </details>

      <div v-if="result.object_type" class="access-object-type">
        <span>Oracle object type</span>
        <strong>{{ result.object_type }}</strong>
      </div>

      <details v-if="result.public_access" class="access-alert-section" open>
        <summary>PUBLIC grants</summary>
        <p>
          This access is granted through PUBLIC and therefore applies to database users generally.
        </p>
        <div class="access-chip-row">
          <span v-for="item in result.public_details" :key="item" class="access-chip">
            {{ item }}
          </span>
        </div>
      </details>

      <div class="access-results-toolbar">
        <input
          v-model="resultFilter"
          type="search"
          placeholder="Filter username, status, privilege or source"
        />
        <span>{{ filteredMatches.length }} shown</span>
      </div>

      <div v-if="filteredMatches.length" class="access-results-table">
        <table>
          <thead>
            <tr>
              <th>User</th>
              <th>Status</th>
              <th>Basis</th>
              <th>Privilege</th>
              <th>Column</th>
              <th>Source</th>
              <th>Flag</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="(item, index) in filteredMatches"
              :key="`${item.username}-${item.basis}-${item.privilege || ''}-${item.column_name || ''}-${index}`"
            >
              <td><strong>{{ item.username }}</strong></td>
              <td>{{ item.status }}</td>
              <td>{{ item.basis }}</td>
              <td>{{ item.privilege || '—' }}</td>
              <td>{{ item.column_name || '—' }}</td>
              <td>{{ formatSource(item.source) }}</td>
              <td>{{ item.powerful ? '⚠ Elevated' : '—' }}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <div v-else-if="result.target_exists" class="empty-state access-empty-result">
        No matching normal Oracle users found.
      </div>

      <div
        v-for="warning in result.warnings"
        :key="warning"
        class="utility-warning"
      >
        {{ warning }}
      </div>
    </template>

    <div v-else-if="!loading && !error" class="access-start-state">
      <strong>Start with an access question.</strong>
      <span>For example: who has DBA, who has SELECT ANY TABLE, or who can SELECT APP.ORDERS?</span>
    </div>
  </section>
</template>

<style scoped>
.access-privileges-panel {
  display: grid;
  gap: 1rem;
}

.access-page-header {
  margin-bottom: 0;
}

.access-read-only-pill {
  display: inline-flex;
  align-items: center;
  padding: .3rem .6rem;
  border: 1px solid var(--border);
  border-radius: 999px;
  color: var(--text-muted);
  font-size: .78rem;
  white-space: nowrap;
}

.access-mode-tabs {
  display: flex;
  flex-wrap: wrap;
  gap: .45rem;
}

.access-mode-tabs button {
  border: 1px solid var(--border);
  border-radius: .65rem;
  padding: .55rem .8rem;
  background: var(--surface);
  color: inherit;
  cursor: pointer;
}

.access-mode-tabs button.active {
  border-color: var(--accent);
  color: var(--accent);
  font-weight: 700;
}

.access-search-card {
  display: grid;
  gap: .8rem;
  padding: 1rem;
  border: 1px solid var(--border);
  border-radius: .8rem;
}

.access-search-card label {
  display: grid;
  gap: .4rem;
}

.access-search-card label > span {
  font-weight: 600;
}

.access-search-card input {
  width: 100%;
}

.access-search-card small {
  color: var(--text-muted);
}

.access-object-inputs {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: .75rem;
}

.access-search-actions {
  display: flex;
  justify-content: flex-end;
}

.access-result-summary {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: .7rem;
}

.access-result-summary > div,
.access-object-type {
  display: grid;
  gap: .2rem;
  padding: .75rem;
  border: 1px solid var(--border);
  border-radius: .7rem;
}

.access-result-summary span,
.access-object-type span {
  color: var(--text-muted);
  font-size: .78rem;
}

.access-alert-section {
  border: 1px solid var(--border);
  border-radius: .75rem;
  overflow: hidden;
}

.access-alert-section > summary {
  padding: .75rem .85rem;
  cursor: pointer;
  font-weight: 700;
}

.access-alert-section > p,
.access-alert-section > .access-chip-row {
  margin: 0;
  padding: 0 .85rem .85rem;
}

.access-chip-row {
  display: flex;
  flex-wrap: wrap;
  gap: .4rem;
}

.access-chip {
  padding: .25rem .5rem;
  border: 1px solid var(--border);
  border-radius: 999px;
  font-size: .78rem;
}

.access-results-toolbar {
  display: flex;
  align-items: center;
  gap: .75rem;
}

.access-results-toolbar input {
  flex: 1;
  min-width: 0;
}

.access-results-toolbar span {
  color: var(--text-muted);
  font-size: .8rem;
  white-space: nowrap;
}

.access-results-table {
  max-height: 34rem;
  overflow: auto;
  border: 1px solid var(--border);
  border-radius: .75rem;
}

.access-results-table table {
  width: 100%;
  border-collapse: collapse;
}

.access-results-table th,
.access-results-table td {
  padding: .65rem .75rem;
  border-bottom: 1px solid var(--border);
  text-align: left;
  vertical-align: top;
}

.access-results-table thead th {
  position: sticky;
  top: 0;
  z-index: 1;
  background: var(--surface);
}

.access-results-table tbody tr:last-child td {
  border-bottom: 0;
}

.access-start-state,
.access-empty-result {
  display: grid;
  gap: .25rem;
  padding: 1.2rem;
  border: 1px dashed var(--border);
  border-radius: .75rem;
  color: var(--text-muted);
}

.access-start-state strong {
  color: inherit;
}

.access-error {
  margin-bottom: 0;
}

@media (max-width: 800px) {
  .access-page-header {
    align-items: flex-start;
  }

  .access-object-inputs,
  .access-result-summary {
    grid-template-columns: 1fr;
  }

  .access-results-toolbar {
    align-items: stretch;
    flex-direction: column;
  }
}
</style>
