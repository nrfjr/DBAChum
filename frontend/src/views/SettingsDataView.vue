<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'

import ScrollableDataTable from '@/components/common/ScrollableDataTable.vue'
import { useSystemSettingsStore } from '@/stores/systemSettings'
import { showToast } from '@/ui/feedback'

const store = useSystemSettingsStore()
const saving = ref(false)
const error = ref<string | null>(null)
const form = reactive({ analytics_retention_days: 730, action_audit_retention_days: 365, terminal_audit_retention_days: 365, provisioning_history_retention_days: 365 })

function bytes(value: number | null) {
  if (value == null) return '—'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']; let n = value; let i = 0
  while (n >= 1024 && i < units.length - 1) { n /= 1024; i += 1 }
  return `${n.toFixed(i >= 3 ? 1 : n >= 100 ? 0 : 1)} ${units[i]}`
}
function sync() { if (store.data) Object.assign(form, { analytics_retention_days: store.data.analytics_retention_days, action_audit_retention_days: store.data.action_audit_retention_days, terminal_audit_retention_days: store.data.terminal_audit_retention_days, provisioning_history_retention_days: store.data.provisioning_history_retention_days }) }
async function load() { error.value = null; try { await store.loadData(); sync() } catch (exc) { error.value = exc instanceof Error ? exc.message : 'Unable to load data settings.' } }
async function save() { saving.value = true; error.value = null; try { await store.saveData({ ...form }); sync(); showToast({ title: 'Data retention saved', message: 'The collector applies retention cleanup daily; System Maintenance can run it immediately.', tone: 'success' }) } catch (exc) { error.value = exc instanceof Error ? exc.message : 'Unable to save data settings.' } finally { saving.value = false } }
async function exportMetadata() {
  try {
    const data = await store.exportMetadata()
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob); const link = document.createElement('a'); link.href = url; link.download = `dbachum-metadata-${new Date().toISOString().slice(0, 10)}.json`; link.click(); URL.revokeObjectURL(url)
    showToast({ title: 'Metadata exported', message: 'Credentials and encrypted secrets are excluded.', tone: 'success' })
  } catch (exc) { error.value = exc instanceof Error ? exc.message : 'Unable to export metadata.' }
}
onMounted(load)
</script>

<template>
  <div class="settings-stack">
    <section class="panel">
      <div class="panel-header"><div><h3>Retention</h3><p>Raw monitoring remains a short 24-hour feed. Long-term Analytics and operational histories use these retention horizons.</p></div></div>
      <p v-if="error" class="login-error">{{ error }}</p>
      <div class="settings-form-grid">
        <label><span>Analytics snapshots (days)</span><input v-model.number="form.analytics_retention_days" type="number" min="30" max="3650" /></label>
        <label><span>DBA action audit (days)</span><input v-model.number="form.action_audit_retention_days" type="number" min="30" max="3650" /></label>
        <label><span>SSH terminal audit (days)</span><input v-model.number="form.terminal_audit_retention_days" type="number" min="30" max="3650" /></label>
        <label><span>Provisioning history (days)</span><input v-model.number="form.provisioning_history_retention_days" type="number" min="30" max="3650" /></label>
      </div>
      <div class="connection-form-actions"><button type="button" class="primary-button" :disabled="saving" @click="save">{{ saving ? 'Saving…' : 'Save retention' }}</button><button type="button" class="secondary-button" @click="exportMetadata">Export metadata</button><button type="button" class="secondary-button" @click="load">Refresh storage</button></div>
    </section>

    <section class="panel">
      <div class="panel-header"><div><h3>Stored data</h3><p>Approximate MongoDB collection usage. Secrets are never included in metadata exports.</p></div></div>
      <ScrollableDataTable :empty="!(store.data?.collections.length)" empty-message="No DBAChum collections are available yet.">
        <template #header><tr><th>Collection</th><th>Documents</th><th>Logical size</th><th>Storage</th><th>Indexes</th></tr></template>
        <tr v-for="item in store.data?.collections ?? []" :key="item.name"><td><strong>{{ item.name }}</strong></td><td>{{ item.count.toLocaleString() }}</td><td>{{ bytes(item.size_bytes) }}</td><td>{{ bytes(item.storage_bytes) }}</td><td>{{ bytes(item.index_bytes) }}</td></tr>
      </ScrollableDataTable>
    </section>
  </div>
</template>
