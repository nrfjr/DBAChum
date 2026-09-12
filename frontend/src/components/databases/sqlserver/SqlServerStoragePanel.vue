<script setup lang="ts">
import { computed, onMounted } from 'vue'

import ScrollableDataTable from '@/components/common/ScrollableDataTable.vue'
import FloatingActionMenu from '@/components/common/FloatingActionMenu.vue'
import { hasPermission } from '@/core/permissions'
import { useAuthStore } from '@/stores/auth'
import { useDatabaseOperationsStore } from '@/stores/databaseOperations'
import { useSqlServerDbaStore, type SqlServerFile } from '@/stores/sqlServerDba'
import { formDialog, showToast } from '@/ui/feedback'

const props = defineProps<{ connectionId: string }>()
const sqlServerStore = useSqlServerDbaStore()
const operations = useDatabaseOperationsStore()
const authStore = useAuthStore()
const storage = computed(() => sqlServerStore.storage[props.connectionId])
const canOperate = computed(() => hasPermission(authStore.user, 'database:operate'))


function formatBytes(bytes: number | null) {
  if (bytes == null) return '—'
  if (bytes === 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB', 'TB', 'PB']
  const index = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1)
  return `${(bytes / Math.pow(1024, index)).toFixed(1)} ${units[index]}`
}

const freeBytes = computed(() => storage.value?.allocated_bytes != null && storage.value.used_bytes != null ? Math.max(storage.value.allocated_bytes - storage.value.used_bytes, 0) : null)
const usedPercent = computed(() => storage.value?.allocated_bytes && storage.value.used_bytes != null ? Math.round((storage.value.used_bytes / storage.value.allocated_bytes) * 10000) / 100 : null)

async function resizeFile(file: SqlServerFile) {
  const currentMb = Math.round(file.allocated_bytes / 1024 / 1024)
  const result = await formDialog({
    title: 'Resize SQL Server file',
    message: `${file.name} · current size ${formatBytes(file.allocated_bytes)}`,
    confirmLabel: 'Resize file',
    fields: [
      {
        name: 'size_mb',
        label: 'New size',
        type: 'size-gb',
        value: currentMb,
        presetsGb: [10, 20, 30],
        minMb: currentMb,
        hint: 'Shrinking is intentionally blocked here. Use Maintenance only when an explicit shrink is required.',
      },
    ],
  })
  if (!result) return
  try {
    await operations.runStorage(props.connectionId, {
      action: 'resize_file',
      size_mb: Number(result.size_mb),
      logical_name: file.name,
    })
    await sqlServerStore.loadStorage(props.connectionId)
    showToast({ title: 'Database file resized', message: file.name, tone: 'success' })
  } catch (cause) {
    showToast({ title: 'Unable to resize database file', message: cause instanceof Error ? cause.message : operations.error ?? undefined, tone: 'danger' })
  }
}

async function addFile() {
  const result = await formDialog({
    title: 'Add SQL Server database file',
    confirmLabel: 'Add file',
    fields: [
      { name: 'logical_name', label: 'Logical file name', type: 'text', required: true, placeholder: 'AppData02' },
      { name: 'physical_name', label: 'Physical file path', type: 'text', required: true, placeholder: 'D:\\MSSQL\\DATA\\AppData02.ndf' },
      {
        name: 'file_type', label: 'File type', type: 'select', value: 'data',
        options: [
          { label: 'Data file', value: 'data' },
          { label: 'Transaction log', value: 'log' },
        ],
      },
      { name: 'size_mb', label: 'Initial size', type: 'size-gb', value: 10240, presetsGb: [10, 20, 30] },
      {
        name: 'growth_mb', label: 'FILEGROWTH', type: 'select', value: '128',
        options: [
          { label: '128 MB', value: '128' },
          { label: '256 MB', value: '256' },
          { label: '512 MB', value: '512' },
          { label: '1 GB', value: '1024' },
        ],
      },
    ],
  })
  if (!result) return

  try {
    await operations.runStorage(props.connectionId, {
      action: 'add_file',
      size_mb: Number(result.size_mb),
      logical_name: String(result.logical_name).trim(),
      physical_name: String(result.physical_name).trim(),
      file_type: String(result.file_type) as 'data' | 'log',
      growth_mb: Number(result.growth_mb),
    })
    await sqlServerStore.loadStorage(props.connectionId)
    showToast({ title: 'Database file added', message: String(result.logical_name), tone: 'success' })
  } catch (cause) {
    showToast({ title: 'Unable to add database file', message: cause instanceof Error ? cause.message : operations.error ?? undefined, tone: 'danger' })
  }
}

onMounted(() => {
  void sqlServerStore.loadStorage(props.connectionId)
})

</script>

<template>
  <section>
    <div class="utility-toolbar">
      <div title="SQL Server data and transaction-log file allocation."><h2>Storage</h2></div>
      <div class="database-inline-actions">
        <button v-if="canOperate" type="button" class="secondary-button" :disabled="operations.busy" @click="addFile">Add file</button>
        <button type="button" class="secondary-button refresh-button" :disabled="sqlServerStore.loadingStorage[connectionId]" @click="sqlServerStore.loadStorage(connectionId)">{{ sqlServerStore.loadingStorage[connectionId] ? 'Refreshing' : 'Refresh' }}<p v-if="sqlServerStore.loadingStorage[connectionId]" class="loading"></p></button>
      </div>
    </div>

    <p v-if="operations.error" class="login-error">{{ operations.error }}</p>
    <p v-if="sqlServerStore.storageError[connectionId]" class="login-error">{{ sqlServerStore.storageError[connectionId] }}</p>

    <template v-else-if="storage">
      <div v-for="warning in storage.warnings" :key="warning" class="utility-warning">{{ warning }}</div>
      <div v-if="!storage.available" class="utility-warning">SQL Server storage monitoring is unavailable for this connection.</div>
      <template v-else>
        <div class="utility-summary">
          <div><span>Database</span><strong>{{ storage.database_name ?? '—' }}</strong></div><div><span>Allocated</span><strong>{{ formatBytes(storage.allocated_bytes) }}</strong></div><div><span>Used</span><strong>{{ formatBytes(storage.used_bytes) }}</strong></div><div><span>Free</span><strong>{{ formatBytes(freeBytes) }}</strong></div><div><span>Used %</span><strong>{{ usedPercent != null ? `${usedPercent}%` : '—' }}</strong></div>
        </div>
        <section class="utility-section">
          <h3>Database files</h3>
          <ScrollableDataTable :empty="storage.files.length === 0" empty-message="No SQL Server files returned." max-height="34rem">
            <template #header><tr><th>Name</th><th>Type</th><th>Allocated</th><th>Used</th><th>Free</th><th>Used %</th><th>Physical path</th><th v-if="canOperate" class="user-actions-column">Actions</th></tr></template>
            <tr v-for="file in storage.files" :key="`${file.file_type}-${file.name}`">
              <td>{{ file.name }}</td><td>{{ file.file_type }}</td><td>{{ formatBytes(file.allocated_bytes) }}</td><td>{{ formatBytes(file.used_bytes) }}</td><td>{{ formatBytes(file.free_bytes) }}</td><td>{{ file.used_percent != null ? `${file.used_percent}%` : '—' }}</td>
              <td class="utility-sql-text" :title="file.physical_name ?? ''">{{ file.physical_name ?? '—' }}</td>
              <td v-if="canOperate" class="user-actions-cell">
                <FloatingActionMenu :label="`Actions for ${file.name}`" :disabled="operations.busy">
                  <button type="button" role="menuitem" @click="resizeFile(file)">
                    <FontAwesomeIcon icon="expand" />
                    Resize
                  </button>
                </FloatingActionMenu>
              </td>
            </tr>
          </ScrollableDataTable>
        </section>
      </template>
    </template>
  </section>
</template>
