<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { useSystemSettingsStore } from '@/stores/systemSettings'
import { confirmDialog, showToast } from '@/ui/feedback'

const store = useSystemSettingsStore()
const busy = ref(false)
const error = ref<string | null>(null)
const collectorState = computed(() => String(store.maintenance?.collector?.state ?? 'not_started'))

async function load() { error.value = null; try { await store.loadMaintenance() } catch (exc) { error.value = exc instanceof Error ? exc.message : 'Unable to load system diagnostics.' } }
async function cleanup() {
  const ok = await confirmDialog({ title: 'Run DBAChum cleanup', message: '', confirmLabel: 'Run cleanup' })
  if (!ok) return
  busy.value = true; error.value = null
  try {
    const result = await store.cleanup(); const retained = Object.values(result.retention_deleted).reduce((a, b) => a + b, 0)
    showToast({ title: 'System cleanup complete', message: `${retained} expired history rows · ${result.orphaned_analytics_deleted} orphaned Analytics rows · ${result.stale_terminal_sessions_reconciled} stale terminal sessions`, tone: 'success' })
    await load()
  } catch (exc) {
    const message = exc instanceof Error ? exc.message : 'Cleanup failed.'
    error.value = message
    showToast({ title: 'System cleanup failed', message, tone: 'danger' })
  }
  finally { busy.value = false }
}
async function verifyIndexes() {
  busy.value = true
  error.value = null
  try {
    const result = await store.verifyIndexes()
    showToast({ title: 'Indexes verified', message: result.message, tone: 'success' })
    await load()
  } catch (exc) {
    const message = exc instanceof Error ? exc.message : 'Index verification failed.'
    error.value = message
    showToast({ title: 'Index verification failed', message, tone: 'danger' })
  } finally {
    busy.value = false
  }
}
onMounted(load)
</script>

<template>
  <div class="settings-stack">
    <section class="panel">
      <div class="panel-header"><div title="Maintenance here affects DBAChum's own MongoDB metadata and histories, never the managed database engines."><h3>System diagnostics</h3></div><button type="button" class="secondary-button" :disabled="busy" @click="load">Refresh</button></div>
      <p v-if="error" class="login-error">{{ error }}</p>
      <div class="overview-facts-grid">
        <div><span>MongoDB</span><strong>{{ store.maintenance?.mongodb_ok ? 'Healthy' : 'Unavailable' }}</strong></div>
        <div><span>Collector</span><strong>{{ collectorState }}</strong></div>
        <div><span>Collections</span><strong>{{ store.maintenance?.collection_count ?? '—' }}</strong></div>
        <div><span>Orphaned Analytics</span><strong>{{ store.maintenance?.orphaned_analytics ?? '—' }}</strong></div>
        <div><span>Stale terminal audits</span><strong>{{ store.maintenance?.stale_terminal_sessions ?? '—' }}</strong></div>
      </div>
    </section>

    <section class="panel">
      <div class="panel-header"><div title="Safe application-level housekeeping. Each action is explicit and does not run against Oracle, SQL Server or MySQL targets."><h3>Maintenance actions</h3></div></div>
      <div class="maintenance-action-list">
        <div><span><strong>Retention and orphan cleanup</strong></span><button type="button" class="primary-button" :disabled="busy" @click="cleanup" title="Apply Data retention, remove detached Analytics snapshots and reconcile stale terminal audit rows.">Run cleanup</button></div>
        <div><span><strong>Verify MongoDB indexes</strong></span><button type="button" class="secondary-button" :disabled="busy" @click="verifyIndexes" title="Re-run DBAChum's idempotent index definitions and create any missing application indexes.">Verify indexes</button></div>
      </div>
    </section>
  </div>
</template>
