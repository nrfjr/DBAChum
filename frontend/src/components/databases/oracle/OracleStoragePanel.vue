<script setup lang="ts">
import { computed, onMounted } from 'vue'

import ScrollableDataTable from '@/components/common/ScrollableDataTable.vue'
import { hasPermission } from '@/core/permissions'
import { useAuthStore } from '@/stores/auth'
import { useDatabaseOperationsStore } from '@/stores/databaseOperations'
import { useOracleDbaStore, type OracleDatafile } from '@/stores/oracleDba'

const props = defineProps<{ connectionId: string }>()
const oracleStore = useOracleDbaStore()
const operations = useDatabaseOperationsStore()
const authStore = useAuthStore()
const storage = computed(() => oracleStore.storage[props.connectionId])
const canOperate = computed(() => hasPermission(authStore.user, 'database:operate'))

function formatBytes(bytes: number | null) {
  if (bytes == null) return '—'
  if (bytes === 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB', 'TB', 'PB']
  const index = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1)
  return `${(bytes / Math.pow(1024, index)).toFixed(1)} ${units[index]}`
}

async function resizeDatafile(file: OracleDatafile) {
  const currentMb = Math.round(file.size_bytes / 1024 / 1024)
  const raw = window.prompt(`Resize datafile ${file.file_id} to how many MB?`, String(currentMb))
  if (raw == null) return
  const sizeMb = Number.parseInt(raw, 10)
  if (!Number.isFinite(sizeMb) || sizeMb < 1) return window.alert('Enter a valid size in MB.')
  if (!window.confirm(`Resize ${file.file_name} from ${currentMb} MB to ${sizeMb} MB?`)) return
  try {
    await operations.runStorage(props.connectionId, { action: 'resize_file', size_mb: sizeMb, file_id: file.file_id })
    await oracleStore.loadStorage(props.connectionId)
  } catch {}
}

async function addDatafile() {
  const tablespace = window.prompt('Tablespace name:')?.trim()
  if (!tablespace) return
  const physicalName = window.prompt('Datafile path (leave blank only if Oracle Managed Files is configured):')?.trim() || null
  const rawSize = window.prompt('Initial size in MB:', '1024')
  if (!rawSize) return
  const sizeMb = Number.parseInt(rawSize, 10)
  if (!Number.isFinite(sizeMb) || sizeMb < 1) return window.alert('Enter a valid size in MB.')
  const rawGrowth = window.prompt('AUTOEXTEND NEXT MB (leave blank for automatic default):', '128')
  const growthMb = rawGrowth?.trim() ? Number.parseInt(rawGrowth, 10) : null
  if (growthMb != null && (!Number.isFinite(growthMb) || growthMb < 1)) return window.alert('Enter a valid growth size.')
  if (!window.confirm(`Add ${sizeMb} MB datafile to tablespace ${tablespace}?`)) return
  try {
    await operations.runStorage(props.connectionId, {
      action: 'add_file', size_mb: sizeMb, tablespace_name: tablespace,
      physical_name: physicalName, autoextend: true, growth_mb: growthMb,
    })
    await oracleStore.loadStorage(props.connectionId)
  } catch {}
}

onMounted(() => void oracleStore.loadStorage(props.connectionId))
</script>

<template>
  <section>
    <div class="utility-toolbar">
      <div><h2>Storage</h2><p>Oracle tablespaces, datafiles, and recovery area usage.</p></div>
      <div class="database-inline-actions">
        <button v-if="canOperate" type="button" class="secondary-button" :disabled="operations.busy" @click="addDatafile">Add datafile</button>
        <button type="button" class="secondary-button" :disabled="oracleStore.loadingStorage" @click="oracleStore.loadStorage(connectionId)">{{ oracleStore.loadingStorage ? 'Refreshing...' : 'Refresh' }}</button>
      </div>
    </div>

    <p v-if="operations.error" class="login-error">{{ operations.error }}</p>
    <p v-if="oracleStore.storageError" class="login-error">{{ oracleStore.storageError }}</p>

    <template v-else-if="storage">
      <div v-for="warning in storage.warnings" :key="warning" class="utility-warning">{{ warning }}</div>

      <section v-if="storage.fra" class="panel utility-section">
        <h3>Fast Recovery Area</h3>
        <div class="utility-summary">
          <div><span>Used</span><strong>{{ formatBytes(storage.fra.used_bytes) }}</strong></div>
          <div><span>Limit</span><strong>{{ formatBytes(storage.fra.limit_bytes) }}</strong></div>
          <div><span>Used %</span><strong>{{ storage.fra.used_percent != null ? `${storage.fra.used_percent}%` : '—' }}</strong></div>
          <div><span>Reclaimable</span><strong>{{ formatBytes(storage.fra.reclaimable_bytes) }}</strong></div>
        </div>
      </section>

      <section class="utility-section">
        <h3>Tablespaces</h3>
        <ScrollableDataTable v-if="storage.tablespaces_available" :empty="storage.tablespaces.length === 0" empty-message="No tablespaces returned." max-height="26rem">
          <template #header><tr><th>Tablespace</th><th>Type</th><th>Status</th><th>Used</th><th>Capacity</th><th>Usage</th></tr></template>
          <tr v-for="tablespace in storage.tablespaces" :key="tablespace.name">
            <td>{{ tablespace.name }}</td><td>{{ tablespace.contents }}</td><td>{{ tablespace.status }}</td><td>{{ formatBytes(tablespace.used_bytes) }}</td><td>{{ formatBytes(tablespace.capacity_bytes) }}</td><td>{{ tablespace.used_percent }}%</td>
          </tr>
        </ScrollableDataTable>
      </section>

      <section class="utility-section">
        <h3>Datafiles</h3>
        <ScrollableDataTable v-if="storage.datafiles_available" :empty="storage.datafiles.length === 0" empty-message="No datafiles returned." max-height="34rem">
          <template #header><tr><th>ID</th><th>Tablespace</th><th>Size</th><th>Autoextend</th><th>Max</th><th>Path</th><th v-if="canOperate">Actions</th></tr></template>
          <tr v-for="file in storage.datafiles" :key="file.file_id">
            <td>{{ file.file_id }}</td><td>{{ file.tablespace_name }}</td><td>{{ formatBytes(file.size_bytes) }}</td><td>{{ file.autoextensible ? 'Yes' : 'No' }}</td><td>{{ formatBytes(file.max_bytes) }}</td>
            <td class="utility-sql-text" :title="file.file_name">{{ file.file_name }}</td>
            <td v-if="canOperate"><button type="button" class="secondary-button" :disabled="operations.busy" @click="resizeDatafile(file)">Resize</button></td>
          </tr>
        </ScrollableDataTable>
      </section>
    </template>
  </section>
</template>
