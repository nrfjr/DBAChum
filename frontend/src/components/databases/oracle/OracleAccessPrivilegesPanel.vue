<script setup lang="ts">
import { computed, ref } from 'vue'
import ScrollableDataTable from '@/components/common/ScrollableDataTable.vue'
import OracleAccessCompareCategory from '@/components/databases/oracle/OracleAccessCompareCategory.vue'
import OracleRoleManagementPanel from '@/components/databases/oracle/OracleRoleManagementPanel.vue'
import {
  useOracleDbaStore,
  type OracleAccessCompareResult,
  type OracleAccessGrantSource,
  type OracleAccessLookupResult,
} from '@/stores/oracleDba'

const props = defineProps<{
  connectionId: string
}>()

const oracleStore = useOracleDbaStore()

type WorkspaceMode = 'lookup' | 'compare' | 'roles'
type LookupKind = 'role' | 'system_privilege' | 'object'

const workspaceMode = ref<WorkspaceMode>('lookup')

const lookupKind = ref<LookupKind>('role')
const lookupValue = ref('')
const owner = ref('')
const objectName = ref('')
const objectPrivilege = ref('')
const resultFilter = ref('')
const loading = ref(false)
const error = ref<string | null>(null)
const result = ref<OracleAccessLookupResult | null>(null)

const leftUsername = ref('')
const rightUsername = ref('')
const compareFilter = ref('')
const compareLoading = ref(false)
const compareError = ref<string | null>(null)
const compareResult = ref<OracleAccessCompareResult | null>(null)

const canSearch = computed(() => {
  if (lookupKind.value === 'object') {
    return Boolean(owner.value.trim() && objectName.value.trim())
  }
  return Boolean(lookupValue.value.trim())
})

const canCompare = computed(() => {
  const left = leftUsername.value.trim().toUpperCase()
  const right = rightUsername.value.trim().toUpperCase()
  return Boolean(left && right && left !== right)
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

function chooseWorkspace(mode: WorkspaceMode) {
  workspaceMode.value = mode
  if (mode === 'lookup') compareError.value = null
  if (mode === 'compare') error.value = null
  if (mode === 'roles') { error.value = null; compareError.value = null }
}

function chooseKind(kind: LookupKind) {
  lookupKind.value = kind
  result.value = null
  error.value = null
  resultFilter.value = ''
}

function formatSource(source: OracleAccessGrantSource) {
  if (source.kind === 'direct') return 'Direct'
  if (source.kind === 'public') return 'PUBLIC'
  if (source.kind === 'password_file') return 'Password file'
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

async function runCompare() {
  if (!canCompare.value || compareLoading.value) return

  compareLoading.value = true
  compareError.value = null
  compareResult.value = null
  compareFilter.value = ''

  const left = leftUsername.value.trim().toUpperCase()
  const right = rightUsername.value.trim().toUpperCase()

  try {
    compareResult.value = await oracleStore.compareUserAccess(
      props.connectionId,
      left,
      right,
    )
    leftUsername.value = compareResult.value.left.username
    rightUsername.value = compareResult.value.right.username
  } catch (caught) {
    compareError.value = caught instanceof Error
      ? caught.message
      : 'Unable to compare Oracle user access.'
  } finally {
    compareLoading.value = false
  }
}
</script>

<template>
  <section class="panel access-privileges-panel">
    <div class="panel-header access-page-header">
      <div>
        <h2>Access &amp; Privileges</h2>
        <p>
          Investigate effective Oracle access and safely manage custom Oracle roles.
        </p>
      </div>
      <span class="access-read-only-pill">{{ workspaceMode === 'roles' ? 'Audited DBA actions' : 'Read only' }}</span>
    </div>

    <div class="access-workspace-tabs" role="tablist" aria-label="Access workspace">
      <button
        type="button"
        :class="{ active: workspaceMode === 'lookup' }"
        @click="chooseWorkspace('lookup')"
      >
        Access lookup
      </button>
      <button
        type="button"
        :class="{ active: workspaceMode === 'compare' }"
        @click="chooseWorkspace('compare')"
      >
        Compare users
      </button>
      <button
        type="button"
        :class="{ active: workspaceMode === 'roles' }"
        @click="chooseWorkspace('roles')"
      >
        Roles
      </button>
    </div>

    <template v-if="workspaceMode === 'lookup'">
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

        <ScrollableDataTable
          :empty="filteredMatches.length === 0"
          :empty-message="result.target_exists ? 'No matching normal Oracle users found.' : 'No result rows.'"
        >
          <template #header>
            <tr>
              <th>User</th>
              <th>Status</th>
              <th>Basis</th>
              <th>Privilege</th>
              <th>Column</th>
              <th>Source</th>
              <th>Flag</th>
            </tr>
          </template>
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
        </ScrollableDataTable>

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
    </template>

    <template v-else-if="workspaceMode === 'compare'">
      <div class="access-search-card compare-search-card">
        <div class="compare-user-inputs">
          <label>
            <span>First user</span>
            <input
              v-model="leftUsername"
              type="text"
              autocomplete="off"
              placeholder="USER_A"
              @keyup.enter="runCompare"
            />
          </label>

          <div class="compare-versus">VS</div>

          <label>
            <span>Second user</span>
            <input
              v-model="rightUsername"
              type="text"
              autocomplete="off"
              placeholder="USER_B"
              @keyup.enter="runCompare"
            />
          </label>
        </div>
        <small>
          Compare effective roles, system privileges, object/column grants and password-file administrative privileges.
        </small>

        <div class="access-search-actions">
          <button
            type="button"
            class="primary-button"
            :disabled="!canCompare || compareLoading"
            @click="runCompare"
          >
            {{ compareLoading ? 'Comparing...' : 'Compare access' }}
          </button>
        </div>
      </div>

      <div v-if="compareError" class="utility-warning access-error">
        {{ compareError }}
      </div>

      <template v-if="compareResult">
        <section class="compare-user-summary">
          <article>
            <strong>{{ compareResult.left.username }}</strong>
            <span>{{ compareResult.left.status }}</span>
            <small>
              Profile {{ compareResult.left.profile || '—' }} ·
              {{ compareResult.left.default_tablespace || '—' }} / {{ compareResult.left.temporary_tablespace || '—' }}
            </small>
          </article>
          <div class="compare-summary-vs">VS</div>
          <article>
            <strong>{{ compareResult.right.username }}</strong>
            <span>{{ compareResult.right.status }}</span>
            <small>
              Profile {{ compareResult.right.profile || '—' }} ·
              {{ compareResult.right.default_tablespace || '—' }} / {{ compareResult.right.temporary_tablespace || '—' }}
            </small>
          </article>
        </section>

        <section class="access-result-summary compare-counts">
          <div>
            <span>Common access</span>
            <strong>{{ compareResult.common_count }}</strong>
          </div>
          <div>
            <span>Only {{ compareResult.left.username }}</span>
            <strong>{{ compareResult.left_only_count }}</strong>
          </div>
          <div>
            <span>Only {{ compareResult.right.username }}</span>
            <strong>{{ compareResult.right_only_count }}</strong>
          </div>
        </section>

        <div class="access-results-toolbar">
          <input
            v-model="compareFilter"
            type="search"
            placeholder="Filter compared access or source path"
          />
          <span>Applies to all categories</span>
        </div>

        <div class="compare-categories">
          <OracleAccessCompareCategory
            title="Roles"
            :category="compareResult.roles"
            :left-username="compareResult.left.username"
            :right-username="compareResult.right.username"
            :filter="compareFilter"
            open
          />
          <OracleAccessCompareCategory
            title="System privileges"
            :category="compareResult.system_privileges"
            :left-username="compareResult.left.username"
            :right-username="compareResult.right.username"
            :filter="compareFilter"
            open
          />
          <OracleAccessCompareCategory
            title="Object & column privileges"
            :category="compareResult.object_privileges"
            :left-username="compareResult.left.username"
            :right-username="compareResult.right.username"
            :filter="compareFilter"
          />
          <OracleAccessCompareCategory
            title="Administrative privileges"
            :category="compareResult.administrative_privileges"
            :left-username="compareResult.left.username"
            :right-username="compareResult.right.username"
            :filter="compareFilter"
          />
        </div>

        <div
          v-for="warning in compareResult.warnings"
          :key="warning"
          class="utility-warning"
        >
          {{ warning }}
        </div>
      </template>

      <div v-else-if="!compareLoading && !compareError" class="access-start-state">
        <strong>Compare two Oracle users.</strong>
        <span>DBAChum will separate common access from grants that only one account receives, including inherited role paths.</span>
      </div>
    </template>

    <div v-show="workspaceMode === 'roles'" class="access-workspace-content">
      <OracleRoleManagementPanel :connection-id="connectionId" :active="workspaceMode === 'roles'" />
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

.access-workspace-tabs,
.access-mode-tabs {
  display: flex;
  flex-wrap: wrap;
  gap: .45rem;
}

.access-workspace-tabs {
  padding-bottom: .75rem;
  border-bottom: 1px solid var(--border);
}

.access-workspace-tabs button,
.access-mode-tabs button {
  border: 1px solid var(--border);
  border-radius: .65rem;
  padding: .55rem .8rem;
  background: var(--surface);
  color: inherit;
  cursor: pointer;
}

.access-workspace-tabs button.active,
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

.access-object-inputs,
.compare-user-inputs {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: .75rem;
}

.compare-user-inputs {
  grid-template-columns: minmax(0, 1fr) auto minmax(0, 1fr);
  align-items: end;
}

.compare-versus,
.compare-summary-vs {
  color: var(--text-muted);
  font-size: .8rem;
  font-weight: 800;
  letter-spacing: .08em;
}

.compare-versus {
  padding: .65rem 0;
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

.compare-counts {
  grid-template-columns: repeat(3, minmax(0, 1fr));
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

.compare-user-summary {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto minmax(0, 1fr);
  gap: .75rem;
  align-items: center;
}

.compare-user-summary article {
  display: grid;
  gap: .2rem;
  padding: .8rem;
  border: 1px solid var(--border);
  border-radius: .75rem;
}

.compare-user-summary article span,
.compare-user-summary article small {
  color: var(--text-muted);
}

.compare-summary-vs {
  text-align: center;
}

.compare-categories {
  display: grid;
  gap: .75rem;
}

.access-start-state {
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
  .access-result-summary,
  .compare-counts,
  .compare-user-inputs,
  .compare-user-summary {
    grid-template-columns: 1fr;
  }

  .compare-versus,
  .compare-summary-vs {
    padding: 0;
    text-align: left;
  }

  .access-results-toolbar {
    align-items: stretch;
    flex-direction: column;
  }
}
</style>
