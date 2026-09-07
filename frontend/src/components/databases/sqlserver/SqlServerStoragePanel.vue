<script setup lang="ts">
import { computed, onMounted } from 'vue'

import ScrollableDataTable from '@/components/common/ScrollableDataTable.vue'
import { hasPermission } from '@/core/permissions'
import { useAuthStore } from '@/stores/auth'
import { useDatabaseOperationsStore } from '@/stores/databaseOperations'
import { useSqlServerDbaStore, type SqlServerFile } from '@/stores/sqlServerDba'

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
  const raw = window.prompt(`Resize logical file ${file.name} to how many MB?`, String(currentMb))
  if (raw == null) return
  const sizeMb = Number.parseInt(raw, 10)
  if (!Number.isFinite(sizeMb) || sizeMb < 1) return window.alert('Enter a valid size in MB.')
  if (!window.confirm(`Resize ${file.name} from ${currentMb} MB to ${sizeMb} MB?`)) return
  try {
    await operations.runStorage(props.connectionId, { action: 'resize_file', size_mb: sizeMb, logical_name: file.name })
    await sqlServerStore.loadStorage(props.connectionId)
  } catch {}
}

async function addFile() {
  const logical = window.prompt('Logical file name:')?.trim()
  if (!logical) return
  const physical = window.prompt('Physical file path:')?.trim()
  if (!physical) return
  const type = window.prompt('File type: data or log', 'data')?.trim().toLowerCase()
  if (type !== 'data' && type !== 'log') return window.alert('File type must be data or log.')
  const rawSize = window.prompt('Initial size in MB:', '1024')
  if (!rawSize) return
  const sizeMb = Number.parseInt(rawSize, 10)
  if (!Number.isFinite(sizeMb) || sizeMb < 1) return window.alert('Enter a valid size in MB.')
  const rawGrowth = window.prompt('FILEGROWTH in MB (optional):', '128')
  const growthMb = rawGrowth?.trim() ? Number.parseInt(rawGrowth, 10) : null
  if (!window.confirm(`Add ${type} file ${logical} (${sizeMb} MB)?`)) return
  try {
    await operations.runStorage(props.connectionId, { action: 'add_file', size_mb: sizeMb, logical_name: logical, physical_name: physical, file_type: type, growth_mb: growthMb })
    await sqlServerStore.loadStorage(props.connectionId)
  } catch {}
}

onMounted(() => void sqlServerStore.loadStorage(props.connectionId))
</script>

<template>
  <section>
    <div class="utility-toolbar">
      <div><h2>Storage</h2><p>SQL Server data and transaction-log file allocation.</p></div>
      <div class="database-inline-actions">
        <button v-if="canOperate" type="button" class="secondary-button" :disabled="operations.busy" @click="addFile">Add file</button>
        <button type="button" class="secondary-button" :disabled="sqlServerStore.loadingStorage[connectionId]" @click="sqlServerStore.loadStorage(connectionId)">{{ sqlServerStore.loadingStorage[connectionId] ? 'Refreshing...' : 'Refresh' }}</button>
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
            <template #header><tr><th>Name</th><th>Type</th><th>Allocated</th><th>Used</th><th>Free</th><th>Used %</th><th>Physical path</th><th v-if="canOperate">Actions</th></tr></template>
            <tr v-for="file in storage.files" :key="`${file.file_type}-${file.name}`">
              <td>{{ file.name }}</td><td>{{ file.file_type }}</td><td>{{ formatBytes(file.allocated_bytes) }}</td><td>{{ formatBytes(file.used_bytes) }}</td><td>{{ formatBytes(file.free_bytes) }}</td><td>{{ file.used_percent != null ? `${file.used_percent}%` : '—' }}</td>
              <td class="utility-sql-text" :title="file.physical_name ?? ''">{{ file.physical_name ?? '—' }}</td><td v-if="canOperate"><button type="button" class="secondary-button" :disabled="operations.busy" @click="resizeFile(file)">Resize</button></td>
            </tr>
          </ScrollableDataTable>
        </section>
      </template>
    </template>
  </section>
</template>
