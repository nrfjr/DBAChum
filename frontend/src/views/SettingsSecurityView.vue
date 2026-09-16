<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'

import { useSystemSettingsStore } from '@/stores/systemSettings'
import { showToast } from '@/ui/feedback'

const store = useSystemSettingsStore()
const saving = ref(false)
const error = ref<string | null>(null)
const form = reactive({
  session_idle_timeout_minutes: 30,
})

function sync() {
  if (!store.security) return
  form.session_idle_timeout_minutes = store.security.session_idle_timeout_minutes
}

async function load() {
  error.value = null
  try {
    await store.loadSecurity()
    sync()
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : 'Unable to load security settings.'
  }
}

async function save() {
  saving.value = true
  error.value = null
  try {
    await store.saveSecurity({
      session_idle_timeout_minutes: Number(form.session_idle_timeout_minutes),
    })
    sync()
    showToast({
      title: 'Security settings saved',
      message: `Sessions now expire after ${form.session_idle_timeout_minutes} minutes of inactivity.`,
      tone: 'success',
    })
  } catch (cause) {
    const message = cause instanceof Error ? cause.message : 'Unable to save security settings.'
    error.value = message
    showToast({ title: 'Unable to save security settings', message, tone: 'danger' })
  } finally {
    saving.value = false
  }
}

onMounted(load)
</script>

<template>
  <section class="panel custom-monitoring-panel">
    <div class="panel-header">
      <div>
        <h3>User sessions</h3>
      </div>
    </div>

    <p v-if="error" class="login-error">{{ error }}</p>

    <div class="settings-form-grid">
      <label>
        <span class="field-label">Idle session timeout</span>
        <input
          v-model.number="form.session_idle_timeout_minutes"
          class="utility-search-input"
          type="number"
          min="5"
          max="1440"
          required
        />
      </label>
    </div>

    <div class="connection-form-actions">
      <button type="button" class="primary-button" :disabled="saving" @click="save">
        {{ saving ? 'Saving…' : 'Save changes' }}
      </button>
    </div>
  </section>
</template>
