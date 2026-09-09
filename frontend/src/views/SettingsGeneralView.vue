<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'

import AppLegalFooter from '@/components/common/AppLegalFooter.vue'
import { useSystemSettingsStore } from '@/stores/systemSettings'
import { confirmDialog, showToast } from '@/ui/feedback'

const store = useSystemSettingsStore()
const saving = ref(false)
const logoSaving = ref(false)
const error = ref<string | null>(null)
const logoError = ref<string | null>(null)
const logoInput = ref<HTMLInputElement | null>(null)
const form = reactive({
  installation_name: 'DBAChum',
  default_page_size: 10 as 10 | 25 | 50 | 100,
  default_analytics_months: 12,
})

const logoUrl = computed(() => store.brandingLogoUrl)
const installationInitial = computed(() => form.installation_name.trim().charAt(0).toUpperCase() || 'D')

function sync() {
  if (!store.general) return
  form.installation_name = store.general.installation_name
  form.default_page_size = store.general.default_page_size
  form.default_analytics_months = store.general.default_analytics_months
}

async function load() {
  error.value = null
  try {
    await Promise.all([store.loadGeneral(), store.loadBranding()])
    sync()
  } catch (exc) {
    error.value = exc instanceof Error ? exc.message : 'Unable to load general settings.'
  }
}

async function save() {
  error.value = null
  if (!form.installation_name.trim()) {
    error.value = 'Installation name is required.'
    return
  }

  saving.value = true
  try {
    await store.saveGeneral({ ...form })
    sync()
    showToast({
      title: 'General settings saved',
      message: 'Installation defaults are now active.',
      tone: 'success',
    })
  } catch (exc) {
    error.value = exc instanceof Error ? exc.message : 'Unable to save general settings.'
  } finally {
    saving.value = false
  }
}

function chooseLogo() {
  logoInput.value?.click()
}

async function uploadLogo(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return

  logoSaving.value = true
  logoError.value = null
  try {
    await store.uploadLogo(file)
    showToast({ title: 'Application logo updated', tone: 'success' })
  } catch (exc) {
    logoError.value = exc instanceof Error ? exc.message : 'Unable to upload the application logo.'
  } finally {
    logoSaving.value = false
  }
}

async function removeLogo() {
  const confirmed = await confirmDialog({
    title: 'Remove custom application logo?',
    message: 'DBAChum will return to the default installation mark.',
    confirmLabel: 'Remove logo',
    tone: 'warning',
  })
  if (!confirmed) return

  logoSaving.value = true
  logoError.value = null
  try {
    await store.removeLogo()
    showToast({ title: 'Custom application logo removed', tone: 'success' })
  } catch (exc) {
    logoError.value = exc instanceof Error ? exc.message : 'Unable to remove the application logo.'
  } finally {
    logoSaving.value = false
  }
}

onMounted(load)
</script>

<template>
  <div class="settings-stack">
    <section class="panel">
      <div class="panel-header">
        <div title="Global defaults used across this DBAChum installation. Personal profile preferences still take precedence where applicable.">
          <h3>Installation defaults</h3>
        </div>
      </div>

      <p v-if="error" class="login-error">{{ error }}</p>

      <div class="settings-form-grid">
        <label>
          <span class="field-label">Installation name <span class="required-mark" aria-hidden="true">*</span></span>
          <input class="utility-search-input" v-model.trim="form.installation_name" required maxlength="80" />
        </label>
        <label>
          <span class="field-label">Default table page size <span class="required-mark" aria-hidden="true">*</span></span>
          <select class="utility-select-input" v-model.number="form.default_page_size" required>
            <option :value="10">10</option>
            <option :value="25">25</option>
            <option :value="50">50</option>
            <option :value="100">100</option>
          </select>
        </label>
        <label>
          <span class="field-label">Default Analytics range <span class="required-mark" aria-hidden="true">*</span></span>
          <select class="utility-select-input" v-model.number="form.default_analytics_months" required>
            <option :value="6">6 months</option>
            <option :value="12">12 months</option>
            <option :value="24">24 months</option>
            <option :value="36">36 months</option>
            <option :value="60">60 months</option>
          </select>
        </label>
      </div>

      <input
        ref="logoInput"
        class="hidden-file-input"
        type="file"
        accept="image/png,image/jpeg,image/webp"
        @change="uploadLogo"
      />

      <div class="branding-setting">
        <div class="branding-setting__preview">
          <img v-if="logoUrl" :src="logoUrl" :alt="`${form.installation_name} logo`" />
          <span v-else>{{ installationInitial }}</span>
        </div>
        <div class="branding-setting__body">
          <strong>Application logo</strong>
          <p>PNG, JPEG or WebP, up to 2 MB. It appears with the installation name on the sign-in page and application shell.</p>
          <p v-if="logoError" class="login-error">{{ logoError }}</p>
          <div class="branding-setting__actions">
            <button type="button" class="secondary-button" :disabled="logoSaving" @click="chooseLogo">
              {{ logoSaving ? 'Updating…' : logoUrl ? 'Change logo' : 'Upload logo' }}
            </button>
            <button v-if="logoUrl" type="button" class="secondary-button" :disabled="logoSaving" @click="removeLogo">
              Remove
            </button>
          </div>
        </div>
      </div>

      <div class="connection-form-actions">
        <button type="button" class="primary-button" :disabled="saving" @click="save">
          {{ saving ? 'Saving…' : 'Save changes' }}
        </button>
      </div>
    </section>

    <section v-if="store.general" class="panel">
      <div class="panel-header">
        <div>
          <h3>Runtime</h3>
          <p>Read-only information about the running DBAChum application.</p>
        </div>
      </div>
      <div class="overview-facts-grid">
        <div><span>Version</span><strong>{{ store.general.app_version }}</strong></div>
        <div><span>Environment</span><strong>{{ store.general.environment }}</strong></div>
        <div><span>API documentation</span><strong>{{ store.general.api_docs_enabled ? 'Enabled' : 'Disabled' }}</strong></div>
      </div>
      <div class="settings-runtime-footer">
        <AppLegalFooter />
      </div>
    </section>
  </div>
</template>
