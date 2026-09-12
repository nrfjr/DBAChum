<script setup lang="ts">
import { computed, ref } from 'vue'

import { hasPermission } from '@/core/permissions'
import { useAuthStore } from '@/stores/auth'
import { useDatabaseOperationsStore, type MaintenanceOperationInput } from '@/stores/databaseOperations'
import type { DatabaseEngine } from '@/stores/connections'
import { confirmDialog, formDialog, showToast } from '@/ui/feedback'

const props = defineProps<{
  connectionId: string
  engine: DatabaseEngine
}>()

const authStore = useAuthStore()
const operations = useDatabaseOperationsStore()
const message = ref<string | null>(null)
const canOperate = computed(() => hasPermission(authStore.user, 'database:operate'))

async function run(body: MaintenanceOperationInput, label: string) {
  if (!canOperate.value) return
  const confirmed = await confirmDialog({
    title: label,
    confirmLabel: 'Run maintenance',
    tone: 'warning',
  })
  if (!confirmed) return

  message.value = null
  try {
    const started = await operations.runMaintenance(props.connectionId, body)
    message.value = `${label} started.`
    showToast({ title: `${label} started`, tone: 'success' })
    if (started.status === 'running') {
      void operations.waitForAction(props.connectionId, started.id).then((finished) => {
        message.value = finished.status === 'succeeded' ? `${label} completed.` : `${label} failed: ${finished.error ?? 'Unknown error'}`
        showToast({
          title: finished.status === 'succeeded' ? `${label} completed` : `${label} failed`,
          message: finished.status === 'succeeded' ? undefined : finished.error ?? 'Unknown error',
          tone: finished.status === 'succeeded' ? 'success' : 'danger',
        })
      }).catch((cause) => {
        const error = cause instanceof Error ? cause.message : 'Unable to follow maintenance operation status.'
        showToast({ title: `${label} status unavailable`, message: error, tone: 'danger' })
      })
    }
  } catch (cause) {
    const error = cause instanceof Error ? cause.message : operations.error ?? 'Unable to start maintenance operation.'
    showToast({ title: `${label} failed to start`, message: error, tone: 'danger' })
  }
}

async function gatherSchemaStats() {
  const result = await formDialog({
    title: 'Gather schema statistics',
    confirmLabel: 'Gather statistics',
    fields: [
      { name: 'schema', label: 'Schema name', type: 'text', placeholder: 'Leave blank to use the connection user' },
    ],
  })
  if (!result) return
  const schema = String(result.schema ?? '').trim() || null
  await run({ action: 'gather_schema_stats', schema_name: schema }, 'Gather schema statistics')
}

async function gatherTableStats() {
  const result = await formDialog({
    title: 'Gather table statistics',
    confirmLabel: 'Gather statistics',
    fields: [
      { name: 'schema', label: 'Schema / owner', type: 'text', placeholder: 'Leave blank to use the connection user' },
      { name: 'table', label: 'Table name', type: 'text', required: true },
    ],
  })
  if (!result) return
  const schema = String(result.schema ?? '').trim() || null
  const table = String(result.table).trim()
  await run({ action: 'gather_table_stats', schema_name: schema, table_name: table }, `Gather statistics for ${table}`)
}

async function sqlServerTableStats() {
  const result = await formDialog({
    title: 'Update SQL Server statistics',
    confirmLabel: 'Continue',
    fields: [{ name: 'table', label: 'Table name', type: 'text' }],
  })
  if (!result) return
  const table = String(result.table ?? '').trim() || null
  await run({ action: 'update_statistics', table_name: table }, table ? `Update statistics for ${table}` : 'Update database statistics')
}

async function shrinkDatabase() {
  const result = await formDialog({
    title: 'Shrink SQL Server database',
    confirmLabel: 'Review shrink',
    tone: 'warning',
    fields: [
      { name: 'target', label: 'Target free space (%)', type: 'number', value: 10, min: 0, max: 99, step: 1, required: true },
    ],
  })
  if (!result) return
  const target = Number(result.target)
  await run({ action: 'shrink_database', target_percent: target }, `Shrink database to ${target}% free space`)
}

async function mysqlTable(action: 'analyze_table' | 'optimize_table' | 'check_table', label: string) {
  const result = await formDialog({
    title: `${label} table`,
    confirmLabel: 'Continue',
    fields: [
      { name: 'schema', label: 'Schema / database', type: 'text', required: true },
      { name: 'table', label: 'Table name', type: 'text', required: true },
    ],
  })
  if (!result) return
  const schema = String(result.schema).trim()
  const table = String(result.table).trim()
  await run({ action, schema_name: schema, table_name: table }, `${label} ${schema}.${table}`)
}

</script>

<template>
  <section class="utility-section">
    <div class="utility-toolbar">
      <div title="Occasional engine-native housekeeping. Long-running work continues as an audited operation.">
        <h2>Maintenance</h2>
      </div>
    </div>

    <p v-if="operations.error" class="login-error">{{ operations.error }}</p>

    <div v-if="!canOperate" class="utility-warning">Your role can inspect database information but cannot run maintenance operations.</div>

    <div v-if="engine === 'oracle'" class="maintenance-action-grid">
      <article class="panel maintenance-action-card" title="Refresh optimizer statistics for a schema or a specific table.">
        <h3>Statistics</h3>
        <div class="database-inline-actions">
          <button class="secondary-button" type="button" :disabled="operations.busy || !canOperate" @click="gatherSchemaStats">Gather schema stats</button>
          <button class="secondary-button" type="button" :disabled="operations.busy || !canOperate" @click="gatherTableStats">Gather table stats</button>
        </div>
      </article>
      <article class="panel maintenance-action-card" title="Repair common object-health issues after deployments or structural changes.">
        <h3>Objects</h3>
        <div class="database-inline-actions">
          <button class="secondary-button" type="button" :disabled="operations.busy || !canOperate" @click="run({ action: 'recompile_invalid' }, 'Recompile invalid objects')">Recompile invalids</button>
          <button class="secondary-button" type="button" :disabled="operations.busy || !canOperate" @click="run({ action: 'rebuild_unusable_indexes' }, 'Rebuild unusable indexes')">Rebuild unusable indexes</button>
        </div>
      </article>
      <article class="panel maintenance-action-card" title="Purge the current schema recycle bin when dropped objects no longer need recovery.">
        <h3>Reclaim</h3>
        <button class="secondary-button" type="button" :disabled="operations.busy || !canOperate" @click="run({ action: 'purge_recyclebin' }, 'Purge recycle bin')">Purge recycle bin</button>
      </article>
    </div>

    <div v-else-if="engine === 'sqlserver'" class="maintenance-action-grid">
      <article class="panel maintenance-action-card" title="Run DBCC CHECKDB against the selected database.">
        <h3>Integrity</h3>
        <button class="secondary-button" type="button" :disabled="operations.busy || !canOperate" @click="run({ action: 'check_integrity' }, 'Run DBCC CHECKDB')">Run CHECKDB</button>
      </article>
      <article class="panel maintenance-action-card" title="Update optimizer statistics for the whole database or one table.">
        <h3>Statistics</h3>
        <button class="secondary-button" type="button" :disabled="operations.busy || !canOperate" @click="sqlServerTableStats">Update statistics</button>
      </article>
      <article class="panel maintenance-action-card" title="Explicit database shrink for exceptional reclaim work. Use deliberately; it can introduce fragmentation.">
        <h3>Reclaim</h3>
        <button class="secondary-button" type="button" :disabled="operations.busy || !canOperate" @click="shrinkDatabase">Shrink database</button>
      </article>
    </div>

    <div v-else class="maintenance-action-grid">
      <article class="panel maintenance-action-card" title="Refresh table key distribution and optimizer statistics.">
        <h3>Analyze</h3>
        <button class="secondary-button" type="button" :disabled="operations.busy || !canOperate" @click="mysqlTable('analyze_table', 'Analyze')">Analyze table</button>
      </article>
      <article class="panel maintenance-action-card" title="Run the engine's OPTIMIZE TABLE operation when reclaim/reorganization is appropriate.">
        <h3>Optimize</h3>
        <button class="secondary-button" type="button" :disabled="operations.busy || !canOperate" @click="mysqlTable('optimize_table', 'Optimize')">Optimize table</button>
      </article>
      <article class="panel maintenance-action-card" title="Run CHECK TABLE for a selected table.">
        <h3>Integrity</h3>
        <button class="secondary-button" type="button" :disabled="operations.busy || !canOperate" @click="mysqlTable('check_table', 'Check')">Check table</button>
      </article>
    </div>
  </section>
</template>
