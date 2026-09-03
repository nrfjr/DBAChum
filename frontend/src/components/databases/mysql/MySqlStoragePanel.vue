<script setup lang="ts">
import { computed, onMounted } from 'vue'

import ScrollableDataTable from '@/components/common/ScrollableDataTable.vue'
import { useMySqlDbaStore } from '@/stores/mysqlDba'

const props = defineProps<{ connectionId: string }>()
const mysqlStore = useMySqlDbaStore()
const storage = computed(() => mysqlStore.storage[props.connectionId])

function formatBytes(bytes: number | null) {
  if (bytes == null) return '—'
  if (bytes === 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB', 'TB', 'PB']
  const index = Math.min(
    Math.floor(Math.log(bytes) / Math.log(1024)),
    units.length - 1,
  )
  const value = bytes / Math.pow(1024, index)
  return `${value.toFixed(value >= 100 ? 0 : 1)} ${units[index]}`
}

onMounted(() => {
  void mysqlStore.loadStorage(props.connectionId)
})
</script>

<template>
  <section>
    <div class="utility-toolbar">
      <div>
        <h2>Storage</h2>
        <p>Schema and table allocation reported by INFORMATION_SCHEMA.</p>
      </div>

      <button
        type="button"
        class="secondary-button"
        :disabled="mysqlStore.loadingStorage[connectionId]"
        @click="mysqlStore.loadStorage(connectionId)"
      >
        {{ mysqlStore.loadingStorage[connectionId] ? 'Refreshing...' : 'Refresh' }}
      </button>
    </div>

    <p v-if="mysqlStore.storageError[connectionId]" class="login-error">
      {{ mysqlStore.storageError[connectionId] }}
    </p>

    <template v-else-if="storage">
      <div v-for="warning in storage.warnings" :key="warning" class="utility-warning">
        {{ warning }}
      </div>

      <template v-if="storage.available">
        <div class="utility-summary">
          <div>
            <span>Scope</span>
            <strong>{{ storage.scope === 'database' ? (storage.database_name ?? 'Database') : 'Instance' }}</strong>
          </div>
          <div>
            <span>Schemas</span>
            <strong>{{ storage.schema_count }}</strong>
          </div>
          <div>
            <span>Tables</span>
            <strong>{{ storage.table_count }}</strong>
          </div>
          <div>
            <span>Data</span>
            <strong>{{ formatBytes(storage.data_bytes) }}</strong>
          </div>
          <div>
            <span>Indexes</span>
            <strong>{{ formatBytes(storage.index_bytes) }}</strong>
          </div>
          <div>
            <span>Total</span>
            <strong>{{ formatBytes(storage.total_bytes) }}</strong>
          </div>
        </div>

        <section v-if="storage.schemas.length > 1 || storage.scope === 'instance'" class="utility-section">
          <h3>Schema sizes</h3>
          <ScrollableDataTable
            :empty="storage.schemas.length === 0"
            empty-message="No visible schema allocation returned."
            max-height="20rem"
          >
            <template #header>
              <tr>
                <th>Schema</th>
                <th>Tables</th>
                <th>Data</th>
                <th>Indexes</th>
                <th>Total</th>
              </tr>
            </template>
            <tr v-for="schema in storage.schemas" :key="schema.schema_name">
              <td>{{ schema.schema_name }}</td>
              <td>{{ schema.table_count.toLocaleString() }}</td>
              <td>{{ formatBytes(schema.data_bytes) }}</td>
              <td>{{ formatBytes(schema.index_bytes) }}</td>
              <td>{{ formatBytes(schema.total_bytes) }}</td>
            </tr>
          </ScrollableDataTable>
        </section>

        <section class="utility-section">
          <h3>Largest tables</h3>
          <ScrollableDataTable
            :empty="storage.tables.length === 0"
            empty-message="No visible table allocation returned."
            max-height="34rem"
          >
            <template #header>
              <tr>
                <th v-if="storage.scope === 'instance'">Schema</th>
                <th>Table</th>
                <th>Engine</th>
                <th>Rows (estimate)</th>
                <th>Data</th>
                <th>Indexes</th>
                <th>Total</th>
                <th>Collation</th>
              </tr>
            </template>
            <tr v-for="table in storage.tables" :key="`${table.schema_name}-${table.table_name}`">
              <td v-if="storage.scope === 'instance'">{{ table.schema_name ?? '—' }}</td>
              <td>{{ table.table_name }}</td>
              <td>{{ table.engine ?? '—' }}</td>
              <td>{{ table.rows_estimate?.toLocaleString() ?? '—' }}</td>
              <td>{{ formatBytes(table.data_bytes) }}</td>
              <td>{{ formatBytes(table.index_bytes) }}</td>
              <td>{{ formatBytes(table.total_bytes) }}</td>
              <td>{{ table.collation ?? '—' }}</td>
            </tr>
          </ScrollableDataTable>
        </section>
      </template>
    </template>
  </section>
</template>
