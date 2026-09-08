<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'

import { useSystemSettingsStore } from '@/stores/systemSettings'
import { showToast } from '@/ui/feedback'

const store = useSystemSettingsStore()
const saving = ref(false)
const error = ref<string | null>(null)
const form = reactive({ enabled: true, database_interval_seconds: 30, server_interval_seconds: 60, storage_interval_seconds: 300, analytics_snapshot_interval_seconds: 21600, target_timeout_seconds: 45, concurrency: 5, stale_threshold_seconds: 30 })

const collectorState = computed(() => String(store.monitoring?.collector?.state ?? 'not_started'))
const collectorHeartbeat = computed(() => store.monitoring?.collector?.last_heartbeat_at ? new Date(String(store.monitoring.collector.last_heartbeat_at)).toLocaleString() : '—')

function sync() {
  if (!store.monitoring) return
  Object.assign(form, {
    enabled: store.monitoring.enabled,
    database_interval_seconds: store.monitoring.database_interval_seconds,
    server_interval_seconds: store.monitoring.server_interval_seconds,
    storage_interval_seconds: store.monitoring.storage_interval_seconds,
    analytics_snapshot_interval_seconds: store.monitoring.analytics_snapshot_interval_seconds,
    target_timeout_seconds: store.monitoring.target_timeout_seconds,
    concurrency: store.monitoring.concurrency,
    stale_threshold_seconds: store.monitoring.stale_threshold_seconds,
  })
}
async function load() { error.value = null; try { await store.loadMonitoring(); sync() } catch (exc) { error.value = exc instanceof Error ? exc.message : 'Unable to load monitoring settings.' } }
async function save() {
  saving.value = true; error.value = null
  try { await store.saveMonitoring({ ...form }); sync(); showToast({ title: 'Monitoring settings saved', message: 'The collector reloads these values on its next cycle.', tone: 'success' }) }
  catch (exc) { error.value = exc instanceof Error ? exc.message : 'Unable to save monitoring settings.' }
  finally { saving.value = false }
}
onMounted(load)
</script>

<template>
  <div class="settings-stack">
    <section class="panel">
      <div class="panel-header"><div><h3>Collector status</h3><p>The dedicated background collector owns database/server monitoring and Analytics snapshots.</p></div><button type="button" class="secondary-button" @click="load">Refresh</button></div>
      <div class="overview-facts-grid">
        <div><span>State</span><strong>{{ collectorState }}</strong></div>
        <div><span>Last heartbeat</span><strong>{{ collectorHeartbeat }}</strong></div>
        <div><span>Raw metrics retention</span><strong>{{ store.monitoring?.telemetry_retention_hours ?? 24 }} hours</strong></div>
      </div>
    </section>

    <section class="panel">
      <div class="panel-header"><div><h3>Collection cadence</h3><p>Changes are stored in MongoDB and picked up by the running collector without restarting the web application.</p></div></div>
      <p v-if="error" class="login-error">{{ error }}</p>
      <label class="settings-toggle-row"><input v-model="form.enabled" type="checkbox" /><span><strong>Monitoring enabled</strong><small>Pause collection without stopping the collector process.</small></span></label>
      <div class="settings-form-grid">
        <label><span>Database interval (seconds)</span><input v-model.number="form.database_interval_seconds" type="number" min="10" max="300" /></label>
        <label><span>Server interval (seconds)</span><input v-model.number="form.server_interval_seconds" type="number" min="30" max="600" /></label>
        <label><span>Storage refresh interval (seconds)</span><input v-model.number="form.storage_interval_seconds" type="number" min="60" max="3600" /></label>
        <label><span>Analytics snapshot interval (seconds)</span><input v-model.number="form.analytics_snapshot_interval_seconds" type="number" min="900" max="86400" /></label>
        <label><span>Target timeout (seconds)</span><input v-model.number="form.target_timeout_seconds" type="number" min="10" max="300" /></label>
        <label><span>Collector concurrency</span><input v-model.number="form.concurrency" type="number" min="1" max="20" /></label>
        <label><span>Heartbeat stale threshold (seconds)</span><input v-model.number="form.stale_threshold_seconds" type="number" min="20" max="300" /></label>
      </div>
      <div class="connection-form-actions"><button type="button" class="primary-button" :disabled="saving" @click="save">{{ saving ? 'Saving…' : 'Save monitoring settings' }}</button></div>
    </section>
  </div>
</template>
