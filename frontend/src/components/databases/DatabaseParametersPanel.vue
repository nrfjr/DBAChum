<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import ScrollableDataTable from '@/components/common/ScrollableDataTable.vue'
import { hasPermission } from '@/core/permissions'
import { useAuthStore } from '@/stores/auth'
import { useDatabaseOperationsStore } from '@/stores/databaseOperations'
import { useDatabaseParametersStore, type DatabaseParameterItem } from '@/stores/databaseParameters'
import type { DatabaseEngine } from '@/stores/connections'

const props = defineProps<{ connectionId: string; engine: DatabaseEngine }>()
const authStore = useAuthStore()
const operations = useDatabaseOperationsStore()
const parametersStore = useDatabaseParametersStore()
const search = ref('')

const result = computed(() => parametersStore.results[props.connectionId])
const loading = computed(() => Boolean(parametersStore.loading[props.connectionId]))
const error = computed(() => parametersStore.errors[props.connectionId])
const canOperate = computed(() => hasPermission(authStore.user, 'database:operate'))
const filtered = computed(() => {
  const q = search.value.trim().toLowerCase()
  if (!q) return result.value?.items ?? []
  return (result.value?.items ?? []).filter((item) =>
    [item.name, item.value, item.display_value, item.description]
      .filter(Boolean)
      .some((value) => String(value).toLowerCase().includes(q)),
  )
})

function currentValue(item: DatabaseParameterItem) {
  return item.runtime_value ?? item.display_value ?? item.value ?? '—'
}

function configuredValue(item: DatabaseParameterItem) {
  return item.configured_value ?? item.value ?? '—'
}

async function setParameter(item: DatabaseParameterItem) {
  const value = window.prompt(`New value for ${item.name}:`, currentValue(item) === '—' ? '' : currentValue(item))
  if (value == null || !value.trim()) return

  let applyMode: 'runtime' | 'persistent' | 'both' = props.engine === 'mysql' ? 'runtime' : 'both'
  if (props.engine !== 'sqlserver') {
    const mode = window.prompt(
      props.engine === 'oracle'
        ? 'Apply mode: runtime, persistent, or both'
        : 'Apply mode: runtime, persistent, or both (persistence requires MySQL 8)',
      applyMode,
    )
    if (mode == null) return
    if (!['runtime', 'persistent', 'both'].includes(mode.trim().toLowerCase())) {
      window.alert('Use runtime, persistent, or both.')
      return
    }
    applyMode = mode.trim().toLowerCase() as typeof applyMode
  }

  const scopeLabel = props.engine === 'sqlserver' ? 'sp_configure + RECONFIGURE' : applyMode
  if (!window.confirm(`Set ${item.name} to ${value} (${scopeLabel})?`)) return
  try {
    await operations.runParameter(props.connectionId, {
      action: 'set',
      name: item.name,
      value,
      apply_mode: applyMode,
    })
    await parametersStore.load(props.connectionId)
  } catch {}
}

onMounted(() => void parametersStore.load(props.connectionId))
</script>

<template>
  <section class="utility-section">
    <div class="utility-toolbar">
      <div>
        <h2>Parameters</h2>
        <p>Engine configuration values. Changes use native Oracle ALTER SYSTEM, SQL Server sp_configure, or MySQL/MariaDB SET.</p>
      </div>
      <div class="database-inline-actions">
        <input v-model="search" class="utility-search-input" type="search" placeholder="Search parameters" />
        <button type="button" class="secondary-button" :disabled="loading" @click="parametersStore.load(connectionId)">
          {{ loading ? 'Refreshing...' : 'Refresh' }}
        </button>
      </div>
    </div>

    <p v-if="operations.error" class="login-error">{{ operations.error }}</p>
    <p v-if="error" class="login-error">{{ error }}</p>
    <div v-for="warning in result?.warnings ?? []" :key="warning" class="utility-warning">{{ warning }}</div>

    <ScrollableDataTable
      v-if="result"
      :empty="filtered.length === 0"
      empty-message="No matching parameters."
      max-height="42rem"
    >
      <template #header>
        <tr>
          <th>Name</th>
          <th>Current</th>
          <th v-if="engine === 'sqlserver'">Configured</th>
          <th>Dynamic</th>
          <th>Description</th>
          <th v-if="canOperate">Actions</th>
        </tr>
      </template>
      <tr v-for="item in filtered" :key="item.name">
        <td><strong>{{ item.name }}</strong></td>
        <td class="utility-sql-text" :title="currentValue(item)">{{ currentValue(item) }}</td>
        <td v-if="engine === 'sqlserver'">{{ configuredValue(item) }}</td>
        <td>
          <template v-if="engine === 'oracle'">{{ item.system_modifiable ?? '—' }}</template>
          <template v-else-if="item.dynamic != null">{{ item.dynamic ? 'Yes' : 'Restart' }}</template>
          <template v-else>Server decides</template>
        </td>
        <td class="utility-sql-text" :title="item.description ?? ''">{{ item.description ?? '—' }}</td>
        <td v-if="canOperate">
          <button type="button" class="secondary-button" :disabled="operations.busy" @click="setParameter(item)">Set</button>
        </td>
      </tr>
    </ScrollableDataTable>
  </section>
</template>
