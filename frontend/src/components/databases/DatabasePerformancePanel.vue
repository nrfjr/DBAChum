<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import ScrollableDataTable from '@/components/common/ScrollableDataTable.vue'
import { useDatabasePerformanceStore, type SqlPlanResponse, type TopSqlItem } from '@/stores/databasePerformance'
import type { DatabaseEngine } from '@/stores/connections'
import { formDialog } from '@/ui/feedback'

const props = defineProps<{ connectionId: string; engine: DatabaseEngine }>()
const store = useDatabasePerformanceStore()
const selected = ref<TopSqlItem | null>(null)
const selectedPlan = ref<SqlPlanResponse | null>(null)

const result = computed(() => store.topSql[props.connectionId])
const loading = computed(() => Boolean(store.loadingTopSql[props.connectionId]))
const loadingPlan = computed(() => Boolean(store.loadingPlan[props.connectionId]))
const error = computed(() => store.errors[props.connectionId])

function formatNumber(value: number | null | undefined) {
  if (value == null) return '—'
  return new Intl.NumberFormat().format(value)
}

function formatSeconds(value: number | null | undefined) {
  if (value == null) return '—'
  if (value < 1) return `${(value * 1000).toFixed(0)} ms`
  return `${value.toFixed(value >= 100 ? 0 : 2)} s`
}

function sqlLabel(item: TopSqlItem) {
  if (item.sql_id) return item.sql_id
  if (item.digest) return item.digest.slice(0, 12)
  if (item.plan_handle) return item.plan_handle.slice(0, 12)
  return item.key.slice(0, 12)
}

async function loadPlan(item: TopSqlItem) {
  selected.value = item
  selectedPlan.value = null
  try {
    if (props.engine === 'oracle') {
      selectedPlan.value = await store.loadPlan(props.connectionId, {
        sql_id: item.sql_id,
        child_number: item.child_number,
      }, item.key)
    } else if (props.engine === 'sqlserver') {
      selectedPlan.value = await store.loadPlan(props.connectionId, {
        plan_handle: item.plan_handle,
      }, item.key)
    } else {
      const result = await formDialog({ title: 'Explain representative SQL', message: 'Paste a representative real SELECT for this normalized digest. DBAChum runs EXPLAIN only.', confirmLabel: 'Explain SQL', fields: [{ name: 'sql', label: 'SELECT statement', type: 'textarea', required: true }] })
      if (!result) return
      selectedPlan.value = await store.loadPlan(props.connectionId, { sql_text: String(result.sql).trim() }, item.key)
    }
  } catch {}
}

async function explainMySqlSql() {
  const result = await formDialog({ title: 'Explain SQL', message: 'Paste a SELECT statement. The query itself will not be executed.', confirmLabel: 'Explain SQL', fields: [{ name: 'sql', label: 'SELECT statement', type: 'textarea', required: true }] })
  if (!result) return
  selected.value = null
  try {
    selectedPlan.value = await store.loadPlan(props.connectionId, { sql_text: String(result.sql).trim() }, 'manual')
  } catch {}
}

onMounted(() => void store.loadTopSql(props.connectionId))
</script>

<template>
  <section class="utility-section">
    <div class="utility-toolbar">
      <div>
        <h2>Current Top SQL</h2>
        <p>{{ result?.source ?? 'Highest-cost cached SQL with engine-native plan inspection and practical tuning hints.' }}</p>
      </div>
      <div class="database-inline-actions">
        <button v-if="engine === 'mysql'" type="button" class="secondary-button" :disabled="loadingPlan" @click="explainMySqlSql">Explain SQL</button>
        <button type="button" class="secondary-button" :disabled="loading" @click="store.loadTopSql(connectionId)">{{ loading ? 'Refreshing...' : 'Refresh Top SQL' }}</button>
      </div>
    </div>

    <p v-if="error" class="login-error">{{ error }}</p>
    <div v-for="warning in result?.warnings ?? []" :key="warning" class="utility-warning">{{ warning }}</div>

    <ScrollableDataTable v-if="result" :empty="result.items.length === 0" empty-message="No Top SQL data returned." max-height="40rem">
      <template #header>
        <tr>
          <th>SQL</th>
          <th>Executions</th>
          <th>Total elapsed</th>
          <th v-if="engine !== 'mysql'">CPU</th>
          <th v-if="engine !== 'mysql'">Logical reads</th>
          <th v-if="engine === 'mysql'">Rows examined</th>
          <th>Diagnostic</th>
          <th>Plan</th>
        </tr>
      </template>
      <tr v-for="item in result.items" :key="item.key">
        <td>
          <strong>{{ sqlLabel(item) }}</strong>
          <div class="utility-sql-text" :title="item.sql_text ?? ''">{{ item.sql_text ?? '—' }}</div>
        </td>
        <td>{{ formatNumber(item.executions) }}</td>
        <td>{{ formatSeconds(item.elapsed_seconds) }}</td>
        <td v-if="engine !== 'mysql'">{{ formatSeconds(item.cpu_seconds) }}</td>
        <td v-if="engine !== 'mysql'">{{ formatNumber(item.logical_reads) }}</td>
        <td v-if="engine === 'mysql'">{{ formatNumber(item.rows_examined) }}</td>
        <td class="utility-sql-text" :title="item.diagnostics.join('\n')">{{ item.diagnostics[0] ?? '—' }}</td>
        <td><button type="button" class="secondary-button" :disabled="loadingPlan" @click="loadPlan(item)">{{ engine === 'mysql' ? 'Explain / Tune' : 'Tune' }}</button></td>
      </tr>
    </ScrollableDataTable>

    <div v-if="selectedPlan" class="modal-backdrop" @click.self="selectedPlan = null">
      <section class="modal-panel backup-detail-modal">
        <header class="modal-header">
          <div><h2>SQL tuning diagnostics</h2><p>{{ selectedPlan.source }}</p></div>
          <button type="button" class="modal-close" aria-label="Close plan" @click="selectedPlan = null">×</button>
        </header>

        <div v-for="warning in selectedPlan.warnings" :key="warning" class="utility-warning">{{ warning }}</div>
        <section class="utility-section">
          <h3>Diagnostics</h3>
          <ul>
            <li v-for="note in [...(selected?.diagnostics ?? []), ...selectedPlan.diagnostics]" :key="note">{{ note }}</li>
          </ul>
        </section>

        <pre v-if="selectedPlan.plan_text" class="utility-code-block">{{ selectedPlan.plan_text }}</pre>

        <ScrollableDataTable v-else :empty="selectedPlan.steps.length === 0" empty-message="No plan steps returned." max-height="32rem">
          <template #header><tr><th>ID</th><th>Operation</th><th>Object</th><th>Cost</th><th>Rows</th><th>Predicates / Extra</th></tr></template>
          <tr v-for="(step, index) in selectedPlan.steps" :key="`${step.id}-${index}`">
            <td>{{ step.id ?? '—' }}</td>
            <td>{{ [step.operation, step.options].filter(Boolean).join(' ') || '—' }}</td>
            <td>{{ [step.object_owner, step.object_name].filter(Boolean).join('.') || '—' }}</td>
            <td>{{ step.cost ?? '—' }}</td>
            <td>{{ step.cardinality ?? '—' }}</td>
            <td class="utility-sql-text" :title="step.access_predicates ?? step.filter_predicates ?? JSON.stringify(step.extra)">{{ step.access_predicates ?? step.filter_predicates ?? JSON.stringify(step.extra) }}</td>
          </tr>
        </ScrollableDataTable>
      </section>
    </div>
  </section>
</template>
