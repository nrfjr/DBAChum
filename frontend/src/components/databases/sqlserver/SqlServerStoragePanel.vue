<script setup lang="ts">
import { computed, onMounted } from 'vue'

import ScrollableDataTable from '@/components/common/ScrollableDataTable.vue'
import { useSqlServerDbaStore } from '@/stores/sqlServerDba'

const props = defineProps<{
  connectionId: string
}>()

const sqlServerStore = useSqlServerDbaStore()
const storage = computed(() => sqlServerStore.storage[props.connectionId])

function formatBytes(bytes: number | null) {
  if (bytes == null) return '—'
  if (bytes === 0) return '0 B'

  const units = ['B', 'KB', 'MB', 'GB', 'TB', 'PB']
  const index = Math.min(
    Math.floor(Math.log(bytes) / Math.log(1024)),
    units.length - 1,
  )

  return `${(bytes / Math.pow(1024, index)).toFixed(1)} ${units[index]}`
}

const freeBytes = computed(() => {
  if (storage.value?.allocated_bytes == null || storage.value?.used_bytes == null) {
    return null
  }
  return Math.max(storage.value.allocated_bytes - storage.value.used_bytes, 0)
})

const usedPercent = computed(() => {
  if (
    storage.value?.allocated_bytes == null ||
    storage.value.used_bytes == null ||
    storage.value.allocated_bytes <= 0
  ) {
    return null
  }

  return Math.round((storage.value.used_bytes / storage.value.allocated_bytes) * 10000) / 100
})

onMounted(() => {
  void sqlServerStore.loadStorage(props.connectionId)
})
</script>

<template>
  <section>
    <div class="utility-toolbar">
      <div>
        <h2>Storage</h2>
        <p>SQL Server data and transaction-log file allocation.</p>
      </div>

      <button
        type="button"
        class="secondary-button"
        :disabled="sqlServerStore.loadingStorage[connectionId]"
        @click="sqlServerStore.loadStorage(connectionId)"
      >
        {{ sqlServerStore.loadingStorage[connectionId] ? 'Refreshing...' : 'Refresh' }}
      </button>
    </div>

    <p v-if="sqlServerStore.storageError[connectionId]" class="login-error">
      {{ sqlServerStore.storageError[connectionId] }}
    </p>

    <template v-else-if="storage">
      <div
        v-for="warning in storage.warnings"
        :key="warning"
        class="utility-warning"
      >
        {{ warning }}
      </div>

      <div v-if="!storage.available" class="utility-warning">
        SQL Server storage monitoring is unavailable for this connection.
      </div>

      <template v-else>
        <div class="utility-summary">
          <div>
            <span>Database</span>
            <strong>{{ storage.database_name ?? '—' }}</strong>
          </div>
          <div>
            <span>Allocated</span>
            <strong>{{ formatBytes(storage.allocated_bytes) }}</strong>
          </div>
          <div>
            <span>Used</span>
            <strong>{{ formatBytes(storage.used_bytes) }}</strong>
          </div>
          <div>
            <span>Free</span>
            <strong>{{ formatBytes(freeBytes) }}</strong>
          </div>
          <div>
            <span>Used %</span>
            <strong>{{ usedPercent != null ? `${usedPercent}%` : '—' }}</strong>
          </div>
        </div>

        <section class="utility-section">
          <h3>Database files</h3>

          <ScrollableDataTable
            :empty="storage.files.length === 0"
            empty-message="No SQL Server files returned."
            max-height="34rem"
          >
            <template #header>
              <tr>
                <th>Name</th>
                <th>Type</th>
                <th>Allocated</th>
                <th>Used</th>
                <th>Free</th>
                <th>Used %</th>
                <th>Physical path</th>
              </tr>
            </template>

            <tr v-for="file in storage.files" :key="`${file.file_type}-${file.name}`">
              <td>{{ file.name }}</td>
              <td>{{ file.file_type }}</td>
              <td>{{ formatBytes(file.allocated_bytes) }}</td>
              <td>{{ formatBytes(file.used_bytes) }}</td>
              <td>{{ formatBytes(file.free_bytes) }}</td>
              <td>{{ file.used_percent != null ? `${file.used_percent}%` : '—' }}</td>
              <td class="utility-sql-text" :title="file.physical_name ?? ''">
                {{ file.physical_name ?? '—' }}
              </td>
            </tr>
          </ScrollableDataTable>
        </section>
      </template>
    </template>
  </section>
</template>
