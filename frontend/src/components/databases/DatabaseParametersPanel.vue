<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'

import ScrollableDataTable from '@/components/common/ScrollableDataTable.vue'
import { hasPermission } from '@/core/permissions'
import { useAuthStore } from '@/stores/auth'
import { useConnectionsStore } from '@/stores/connections'
import { useDatabaseOperationsStore } from '@/stores/databaseOperations'
import { useDatabaseParametersStore, type DatabaseParameterItem } from '@/stores/databaseParameters'
import type { DatabaseEngine } from '@/stores/connections'
import { formDialog, showToast, type DialogField } from '@/ui/feedback'

const props = defineProps<{ connectionId: string; engine: DatabaseEngine }>()
const authStore = useAuthStore()
const connectionsStore = useConnectionsStore()
const operations = useDatabaseOperationsStore()
const parametersStore = useDatabaseParametersStore()
const search = ref('')
const compareConnectionId = ref('')

const result = computed(() => parametersStore.results[props.connectionId])
const loading = computed(() => Boolean(parametersStore.loading[props.connectionId]))
const error = computed(() => parametersStore.errors[props.connectionId])
const comparisonResult = computed(() => compareConnectionId.value ? parametersStore.results[compareConnectionId.value] : undefined)
const comparisonLoading = computed(() => compareConnectionId.value ? Boolean(parametersStore.loading[compareConnectionId.value]) : false)
const comparisonError = computed(() => compareConnectionId.value ? parametersStore.errors[compareConnectionId.value] : null)
const canOperate = computed(() => hasPermission(authStore.user, 'database:operate'))

const currentConnection = computed(() => connectionsStore.connections.find((item) => item.id === props.connectionId))
const comparisonCandidates = computed(() => connectionsStore.connections
  .filter((item) => item.id !== props.connectionId && item.engine === props.engine && item.active)
  .sort((left, right) => left.name.localeCompare(right.name)))
const comparisonConnection = computed(() => connectionsStore.connections.find((item) => item.id === compareConnectionId.value))

function currentValue(item: DatabaseParameterItem | undefined) {
  if (!item) return '—'
  return item.runtime_value ?? item.display_value ?? item.value ?? '—'
}

function configuredValue(item: DatabaseParameterItem | undefined) {
  if (!item) return '—'
  return item.configured_value ?? item.value ?? '—'
}

function displayValue(item: DatabaseParameterItem | undefined) {
  if (!item) return '—'
  const runtime = currentValue(item)
  if (props.engine === 'sqlserver') {
    const configured = configuredValue(item)
    return runtime === configured ? runtime : `${runtime} (configured ${configured})`
  }
  return runtime
}

function normalizedValue(item: DatabaseParameterItem | undefined) {
  return displayValue(item).trim().toLowerCase()
}

const rows = computed(() => {
  const currentItems = result.value?.items ?? []
  const comparisonItems = comparisonResult.value?.items ?? []
  const comparisonByName = new Map(comparisonItems.map((item) => [item.name.toLowerCase(), item]))
  const currentByName = new Map(currentItems.map((item) => [item.name.toLowerCase(), item]))
  const names = new Set([...currentByName.keys(), ...comparisonByName.keys()])
  const q = search.value.trim().toLowerCase()

  return [...names]
    .sort((left, right) => left.localeCompare(right))
    .map((name) => {
      const current = currentByName.get(name)
      const comparison = comparisonByName.get(name)
      return {
        name: current?.name ?? comparison?.name ?? name,
        current,
        comparison,
        differs: Boolean(compareConnectionId.value) && normalizedValue(current) !== normalizedValue(comparison),
      }
    })
    .filter((row) => {
      if (!q) return true
      return [
        row.name,
        displayValue(row.current),
        displayValue(row.comparison),
        row.current?.description,
        row.comparison?.description,
      ].filter(Boolean).some((value) => String(value).toLowerCase().includes(q))
    })
})

async function loadComparison() {
  if (!compareConnectionId.value) return
  try {
    await parametersStore.load(compareConnectionId.value)
  } catch {}
}

async function refresh() {
  const jobs: Promise<unknown>[] = [parametersStore.load(props.connectionId)]
  if (compareConnectionId.value) jobs.push(parametersStore.load(compareConnectionId.value))
  await Promise.allSettled(jobs)
}

async function setParameter(item: DatabaseParameterItem) {
  const fields: DialogField[] = [
    {
      name: 'value',
      label: 'New value',
      type: 'text' as const,
      value: currentValue(item) === '—' ? '' : currentValue(item),
      required: true,
    },
  ]

  if (props.engine !== 'sqlserver') {
    fields.push({
      name: 'apply_mode',
      label: 'Apply mode',
      type: 'select' as const,
      value: props.engine === 'mysql' ? 'runtime' : 'both',
      options: [
        { label: 'Runtime only', value: 'runtime' },
        { label: 'Persistent only', value: 'persistent' },
        { label: 'Runtime + persistent', value: 'both' },
      ],
      hint: props.engine === 'mysql' ? 'Persistent changes require a supported MySQL generation.' : 'Oracle persistent changes update the SPFILE when available.',
    })
  }

  const result = await formDialog({
    title: `Change ${item.name}`,
    message: `Current value: ${currentValue(item)}`,
    confirmLabel: 'Apply parameter',
    tone: 'warning',
    fields,
  })
  if (!result) return

  const value = String(result.value ?? '').trim()
  const applyMode = props.engine === 'sqlserver'
    ? 'both'
    : String(result.apply_mode ?? 'runtime') as 'runtime' | 'persistent' | 'both'

  try {
    await operations.runParameter(props.connectionId, {
      action: 'set',
      name: item.name,
      value,
      apply_mode: applyMode,
    })
    await parametersStore.load(props.connectionId)
    showToast({ title: 'Parameter updated', message: `${item.name} = ${value}`, tone: 'success' })
  } catch {}
}

watch(compareConnectionId, () => void loadComparison())

onMounted(async () => {
  if (connectionsStore.connections.length === 0) await connectionsStore.load()
  await parametersStore.load(props.connectionId).catch(() => undefined)
})
</script>

<template>
  <section class="utility-section">
    <div class="utility-toolbar">
      <div>
        <h2>Parameters</h2>
        <p>Inspect and change engine configuration, or compare this database side by side with one other database of the same engine.</p>
      </div>
      <div class="database-inline-actions">
        <label class="parameter-compare-control">
          <span>Compare with</span>
          <select v-model="compareConnectionId" class="utility-select-input">
            <option value="">None</option>
            <option v-for="candidate in comparisonCandidates" :key="candidate.id" :value="candidate.id">
              {{ candidate.name }}
            </option>
          </select>
        </label>
        <input v-model="search" class="utility-search-input" type="search" placeholder="Search parameters" />
        <button type="button" class="secondary-button" :disabled="loading || comparisonLoading" @click="refresh">
          {{ loading || comparisonLoading ? 'Refreshing...' : 'Refresh' }}
        </button>
      </div>
    </div>

    <p v-if="operations.error" class="login-error">{{ operations.error }}</p>
    <p v-if="error" class="login-error">{{ error }}</p>
    <p v-if="comparisonError" class="login-error">Unable to load {{ comparisonConnection?.name ?? 'comparison database' }}: {{ comparisonError }}</p>
    <div v-for="warning in result?.warnings ?? []" :key="`current-${warning}`" class="utility-warning">{{ warning }}</div>
    <div v-for="warning in comparisonResult?.warnings ?? []" :key="`comparison-${warning}`" class="utility-warning">{{ comparisonConnection?.name }}: {{ warning }}</div>

    <ScrollableDataTable
      v-if="result"
      :empty="rows.length === 0"
      empty-message="No matching parameters."
      max-height="42rem"
    >
      <template #header>
        <tr>
          <th>Parameter</th>
          <th>{{ currentConnection?.name ?? 'Current database' }}</th>
          <th v-if="compareConnectionId">{{ comparisonConnection?.name ?? 'Comparison database' }}</th>
          <th>Dynamic</th>
          <th>Description</th>
          <th v-if="canOperate">Actions</th>
        </tr>
      </template>
      <tr v-for="row in rows" :key="row.name" :class="{ 'parameter-comparison-row--different': row.differs }">
        <td><strong>{{ row.name }}</strong></td>
        <td class="utility-sql-text" :title="displayValue(row.current)">{{ displayValue(row.current) }}</td>
        <td v-if="compareConnectionId" class="utility-sql-text" :title="displayValue(row.comparison)">{{ displayValue(row.comparison) }}</td>
        <td>
          <template v-if="row.current && engine === 'oracle'">{{ row.current.system_modifiable ?? '—' }}</template>
          <template v-else-if="row.current?.dynamic != null">{{ row.current.dynamic ? 'Yes' : 'Restart' }}</template>
          <template v-else>Server decides</template>
        </td>
        <td class="utility-sql-text" :title="row.current?.description ?? row.comparison?.description ?? ''">{{ row.current?.description ?? row.comparison?.description ?? '—' }}</td>
        <td v-if="canOperate">
          <button v-if="row.current" type="button" class="secondary-button" :disabled="operations.busy" @click="setParameter(row.current)">Set</button>
        </td>
      </tr>
    </ScrollableDataTable>
  </section>
</template>
