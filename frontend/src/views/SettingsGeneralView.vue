<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'

import AppLegalFooter from '@/components/common/AppLegalFooter.vue'
import { useSystemSettingsStore } from '@/stores/systemSettings'
import { confirmDialog, showToast } from '@/ui/feedback'

const store = useSystemSettingsStore()
const saving = ref(false)
const logoSaving = ref(false)
const error = ref<string | null>(null)
const logoError = ref<string | null>(null)
const logoInput = ref<HTMLInputElement | null>(null)
const pendingLogoFile = ref<File | null>(null)
const pendingLogoPreview = ref<string | null>(null)
const pendingLogoRemoval = ref(false)
const form = reactive({
  installation_name: 'DBAChum',
  default_page_size: 10 as 10 | 25 | 50 | 100,
  default_analytics_months: 12,
})

const logoUrl = computed(() => pendingLogoPreview.value ?? (pendingLogoRemoval.value ? null : store.brandingLogoUrl))
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

function clearLogoPreview() {
  if (pendingLogoPreview.value) URL.revokeObjectURL(pendingLogoPreview.value)
  pendingLogoPreview.value = null
}

function resetPendingLogo() {
  clearLogoPreview()
  pendingLogoFile.value = null
  pendingLogoRemoval.value = false
}

async function save() {
  error.value = null
  logoError.value = null
  if (!form.installation_name.trim()) {
    error.value = 'Installation name is required.'
    showToast({ title: 'Installation name is required', tone: 'warning' })
    return
  }

  saving.value = true
  try {
    await store.saveGeneral({ ...form })

    if (pendingLogoFile.value) {
      logoSaving.value = true
      await store.uploadLogo(pendingLogoFile.value)
    } else if (pendingLogoRemoval.value && store.branding?.has_logo) {
      logoSaving.value = true
      await store.removeLogo()
    }

    resetPendingLogo()
    sync()
    showToast({
      title: 'General settings saved',
      message: 'Installation defaults are now active.',
      tone: 'success',
    })
  } catch (exc) {
    const message = exc instanceof Error ? exc.message : 'Unable to save general settings.'
    error.value = message
    showToast({ title: 'Unable to save general settings', message, tone: 'danger' })
  } finally {
    logoSaving.value = false
    saving.value = false
  }
}

function chooseLogo() {
  logoInput.value?.click()
}

function uploadLogo(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return

  logoError.value = null
  clearLogoPreview()
  pendingLogoFile.value = file
  pendingLogoRemoval.value = false
  pendingLogoPreview.value = URL.createObjectURL(file)
}

async function removeLogo() {
  const confirmed = await confirmDialog({
    title: 'Remove custom application logo?',
    message: 'The logo will be removed when you save changes.',
    confirmLabel: 'Remove logo',
    tone: 'warning',
  })
  if (!confirmed) return

  logoError.value = null
  clearLogoPreview()
  pendingLogoFile.value = null
  pendingLogoRemoval.value = true
}

onMounted(load)
onBeforeUnmount(clearLogoPreview)
</script>

<template>
  <div class="general-settings-layout">
    <section class="panel custom-monitoring-panel">
      <div class="panel-header">
        <div
          title="Global defaults used across this DBAChum installation. Personal profile preferences still take precedence where applicable.">
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
          <span class="field-label">Default table page size <span class="required-mark"
              aria-hidden="true">*</span></span>
          <select class="utility-select-input" v-model.number="form.default_page_size" required>
            <option :value="10">10</option>
            <option :value="25">25</option>
            <option :value="50">50</option>
            <option :value="100">100</option>
          </select>
        </label>
        <label>
          <span class="field-label">Default Analytics range <span class="required-mark"
              aria-hidden="true">*</span></span>
          <select class="utility-select-input" v-model.number="form.default_analytics_months" required>
            <option :value="6">6 months</option>
            <option :value="12">12 months</option>
            <option :value="24">24 months</option>
            <option :value="36">36 months</option>
            <option :value="60">60 months</option>
          </select>
        </label>
      </div>

      <input ref="logoInput" class="hidden-file-input" type="file" accept="image/png,image/jpeg,image/webp"
        @change="uploadLogo" />

      <div class="branding-setting">
        <div class="branding-setting__body">
          <strong>Application logo</strong>

          <div class="branding-logo-control-row">
            <div class="branding-logo-editor">
              <div class="branding-logo-large" :class="{ 'branding-logo-large--image': logoUrl }">
                <img v-if="logoUrl" :src="logoUrl" alt="Application logo" />

                <span v-else>
                  {{ installationInitial }}
                </span>
              </div>

              <button type="button" class="branding-logo-change" :disabled="saving || logoSaving"
                :aria-label="logoUrl ? 'Change application logo' : 'Add application logo'" @click="chooseLogo">
                {{ logoUrl ? 'Change' : 'Add' }}
              </button>
            </div>

            <div class="branding-logo-controls">
              <input ref="logoInput" class="hidden-file-input" type="file" accept="image/png,image/jpeg,image/webp"
                @change="uploadLogo" />

              <button v-if="logoUrl" type="button" class="secondary-button" :disabled="saving || logoSaving"
                @click="removeLogo">
                Remove
              </button>

              <p v-if="logoError" class="login-error">
                {{ logoError }}
              </p>
            </div>
          </div>
        </div>
      </div>

      <div class="connection-form-actions">
        <button type="button" class="primary-button" :disabled="saving || logoSaving" @click="save">
          {{ saving || logoSaving ? 'Saving…' : 'Save changes' }}
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
        <div><span>API documentation</span><strong>{{ store.general.api_docs_enabled ? 'Enabled' : 'Disabled'
            }}</strong></div>
      </div>
      <div class="settings-runtime-footer">
        <AppLegalFooter />
      </div>
    </section>
  </div>
</template>
<style>
.branding-logo-editor {
  position: relative;
  flex: 0 0 64px;
  width: 64px;
  height: 64px;
  border-radius: 20%;
  overflow: hidden;
}

.branding-logo-change {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: .75rem;
  border: 0;
  border-radius: 20%;
  background: rgb(17 17 21 / 58%);
  color: #fff;
  font: inherit;
  font-size: .75rem;
  font-weight: 650;
  text-align: center;
  cursor: pointer;
  opacity: 0;
  transition: opacity .18s ease;
  backdrop-filter: blur(5px);
}

.branding-logo-editor:hover .branding-logo-change,
.branding-logo-change:focus-visible {
  opacity: 1;
}

.branding-logo-change:disabled {
  cursor: wait;
}

.branding-preference-data {
  display: grid;
  gap: .75rem;
  margin-top: 1.25rem;
  padding-top: 1.25rem;
  border-top: 1px solid var(--border);
}

.branding-preference-data h3,
.branding-preference-data p {
  margin: 0;
}

.branding-preference-data p {
  margin-top: .25rem;
  color: var(--text-muted);
  font-size: .82rem;
}

@media (hover: none) {
  .branding-logo-change {
    opacity: 1;
    background: rgb(17 17 21 / 42%);
  }
}

.branding-identity-heading--editable {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.branding-setting__actions {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  min-width: 0;
}

.branding-logo-actions {
  display: flex;
  align-items: center;
}

.branding-logo-control-row {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  width: 100%;
  margin-top: 0.4rem;
  overflow: visible;
}
.branding-logo-large--image {
  overflow: hidden;
}

.branding-logo-large--image img {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: contain;
  object-position: center;
}

.branding-logo-editor .branding-logo-large {
  width: 64px;
  height: 64px;
  flex: 0 0 64px;
}

.branding-logo-controls {
  position: static;
  display: flex;
  align-items: center;
  gap: 0.5rem;
  width: auto;
  overflow: visible;
}
</style>
