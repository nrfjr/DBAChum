<script setup lang="ts">
import { computed, ref } from 'vue'

import { hasPermission } from '@/core/permissions'
import { useAuthStore } from '@/stores/auth'
import { useDatabaseOperationsStore, type MaintenanceOperationInput } from '@/stores/databaseOperations'
import type { DatabaseEngine } from '@/stores/connections'

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
  if (!window.confirm(`${label}? This is a database maintenance operation.`)) return
  message.value = null
  try {
    const started = await operations.runMaintenance(props.connectionId, body)
    message.value = `${label} started.`
    if (started.status === 'running') {
      void operations.waitForAction(props.connectionId, started.id).then((finished) => {
        message.value = finished.status === 'succeeded' ? `${label} completed.` : `${label} failed: ${finished.error ?? 'Unknown error'}`
      }).catch(() => {})
    }
  } catch {}
}

function promptValue(label: string, defaultValue = '') {
  const value = window.prompt(label, defaultValue)
  return value?.trim() || null
}

function gatherSchemaStats() {
  const schema = promptValue('Schema name (leave blank to use the connection user):')
  void run({ action: 'gather_schema_stats', schema_name: schema }, 'Gather schema statistics')
}

function gatherTableStats() {
  const schema = promptValue('Schema/owner (leave blank to use the connection user):')
  const table = promptValue('Table name:')
  if (!table) return
  void run({ action: 'gather_table_stats', schema_name: schema, table_name: table }, `Gather statistics for ${table}`)
}

function sqlServerTableStats() {
  const table = promptValue('Table name (leave blank to update statistics for the whole database):')
  void run({ action: 'update_statistics', table_name: table }, table ? `Update statistics for ${table}` : 'Update database statistics')
}

function shrinkDatabase() {
  const raw = promptValue('Target free-space percentage after shrink:', '10')
  if (!raw) return
  const target = Number(raw)
  if (!Number.isInteger(target) || target < 0 || target > 99) {
    window.alert('Enter a whole number from 0 to 99.')
    return
  }
  void run({ action: 'shrink_database', target_percent: target }, `Shrink database to ${target}% free space`)
}

function mysqlTable(action: 'analyze_table' | 'optimize_table' | 'check_table', label: string) {
  const schema = promptValue('Schema/database name:')
  const table = promptValue('Table name:')
  if (!schema || !table) return
  void run({ action, schema_name: schema, table_name: table }, `${label} ${schema}.${table}`)
}
</script>

<template>
  <section class="utility-section">
    <div class="utility-toolbar">
      <div>
        <h2>Maintenance</h2>
        <p>Occasional engine-native housekeeping. Long-running work continues as an audited DBAChum operation.</p>
      </div>
    </div>

    <p v-if="operations.error" class="login-error">{{ operations.error }}</p>
    <p v-if="message" class="database-workspace-message database-workspace-message--info">{{ message }}</p>

    <div v-if="!canOperate" class="utility-warning">Your role can inspect database information but cannot run maintenance operations.</div>

    <div v-if="engine === 'oracle'" class="maintenance-action-grid">
      <article class="panel maintenance-action-card">
        <h3>Statistics</h3>
        <p>Refresh optimizer statistics for a schema or a specific table.</p>
        <div class="database-inline-actions">
          <button class="secondary-button" type="button" :disabled="operations.busy || !canOperate" @click="gatherSchemaStats">Gather schema stats</button>
          <button class="secondary-button" type="button" :disabled="operations.busy || !canOperate" @click="gatherTableStats">Gather table stats</button>
        </div>
      </article>
      <article class="panel maintenance-action-card">
        <h3>Objects</h3>
        <p>Repair common object-health issues after deployments or structural changes.</p>
        <div class="database-inline-actions">
          <button class="secondary-button" type="button" :disabled="operations.busy || !canOperate" @click="run({ action: 'recompile_invalid' }, 'Recompile invalid objects')">Recompile invalids</button>
          <button class="secondary-button" type="button" :disabled="operations.busy || !canOperate" @click="run({ action: 'rebuild_unusable_indexes' }, 'Rebuild unusable indexes')">Rebuild unusable indexes</button>
        </div>
      </article>
      <article class="panel maintenance-action-card">
        <h3>Reclaim</h3>
        <p>Purge the current schema recycle bin when dropped objects no longer need recovery.</p>
        <button class="secondary-button" type="button" :disabled="operations.busy || !canOperate" @click="run({ action: 'purge_recyclebin' }, 'Purge recycle bin')">Purge recycle bin</button>
      </article>
    </div>

    <div v-else-if="engine === 'sqlserver'" class="maintenance-action-grid">
      <article class="panel maintenance-action-card">
        <h3>Integrity</h3>
        <p>Run DBCC CHECKDB against the selected database.</p>
        <button class="secondary-button" type="button" :disabled="operations.busy || !canOperate" @click="run({ action: 'check_integrity' }, 'Run DBCC CHECKDB')">Run CHECKDB</button>
      </article>
      <article class="panel maintenance-action-card">
        <h3>Statistics</h3>
        <p>Update optimizer statistics for the whole database or one table.</p>
        <button class="secondary-button" type="button" :disabled="operations.busy || !canOperate" @click="sqlServerTableStats">Update statistics</button>
      </article>
      <article class="panel maintenance-action-card">
        <h3>Reclaim</h3>
        <p>Explicit database shrink for exceptional reclaim work. Use deliberately; it can introduce fragmentation.</p>
        <button class="secondary-button" type="button" :disabled="operations.busy || !canOperate" @click="shrinkDatabase">Shrink database</button>
      </article>
    </div>

    <div v-else class="maintenance-action-grid">
      <article class="panel maintenance-action-card">
        <h3>Analyze</h3>
        <p>Refresh table key distribution and optimizer statistics.</p>
        <button class="secondary-button" type="button" :disabled="operations.busy || !canOperate" @click="mysqlTable('analyze_table', 'Analyze')">Analyze table</button>
      </article>
      <article class="panel maintenance-action-card">
        <h3>Optimize</h3>
        <p>Run the engine's OPTIMIZE TABLE operation when reclaim/reorganization is appropriate.</p>
        <button class="secondary-button" type="button" :disabled="operations.busy || !canOperate" @click="mysqlTable('optimize_table', 'Optimize')">Optimize table</button>
      </article>
      <article class="panel maintenance-action-card">
        <h3>Integrity</h3>
        <p>Run CHECK TABLE for a selected table.</p>
        <button class="secondary-button" type="button" :disabled="operations.busy || !canOperate" @click="mysqlTable('check_table', 'Check')">Check table</button>
      </article>
    </div>
  </section>
</template>
