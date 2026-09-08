<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'

import { useSystemSettingsStore } from '@/stores/systemSettings'
import { showToast } from '@/ui/feedback'

const store = useSystemSettingsStore()
const saving = ref(false)
const error = ref<string | null>(null)
const form = reactive({ installation_name: 'DBAChum', default_page_size: 10 as 10 | 25 | 50 | 100, default_analytics_months: 12 })

function sync() {
  if (!store.general) return
  form.installation_name = store.general.installation_name
  form.default_page_size = store.general.default_page_size
  form.default_analytics_months = store.general.default_analytics_months
}

async function load() {
  error.value = null
  try { await store.loadGeneral(); sync() } catch (exc) { error.value = exc instanceof Error ? exc.message : 'Unable to load general settings.' }
}

async function save() {
  saving.value = true
  error.value = null
  try {
    await store.saveGeneral({ ...form })
    sync()
    showToast({ title: 'General settings saved', message: 'Installation defaults are now active.', tone: 'success' })
  } catch (exc) { error.value = exc instanceof Error ? exc.message : 'Unable to save general settings.' }
  finally { saving.value = false }
}

onMounted(load)
</script>

<template>
  <div class="settings-stack">
    <section class="panel">
      <div class="panel-header"><div><h3>Installation defaults</h3><p>Global defaults used across this DBAChum installation. Personal profile preferences still take precedence where applicable.</p></div></div>
      <p v-if="error" class="login-error">{{ error }}</p>
      <div class="settings-form-grid">
        <label><span>Installation name</span><input v-model.trim="form.installation_name" maxlength="80" /></label>
        <label><span>Default table page size</span><select v-model.number="form.default_page_size"><option :value="10">10</option><option :value="25">25</option><option :value="50">50</option><option :value="100">100</option></select></label>
        <label><span>Default Analytics range</span><select v-model.number="form.default_analytics_months"><option :value="6">6 months</option><option :value="12">12 months</option><option :value="24">24 months</option><option :value="36">36 months</option><option :value="60">60 months</option></select></label>
      </div>
      <div class="connection-form-actions"><button type="button" class="primary-button" :disabled="saving" @click="save">{{ saving ? 'Saving…' : 'Save changes' }}</button></div>
    </section>

    <section v-if="store.general" class="panel">
      <div class="panel-header"><div><h3>Runtime</h3><p>Read-only information about the running DBAChum application.</p></div></div>
      <div class="overview-facts-grid">
        <div><span>Version</span><strong>{{ store.general.app_version }}</strong></div>
        <div><span>Environment</span><strong>{{ store.general.environment }}</strong></div>
        <div><span>API documentation</span><strong>{{ store.general.api_docs_enabled ? 'Enabled' : 'Disabled' }}</strong></div>
      </div>
    </section>
  </div>
</template>
