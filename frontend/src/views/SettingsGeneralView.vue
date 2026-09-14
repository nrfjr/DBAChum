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
const updateTemporarilyOffline = ref(false)
let updatePollTimer: ReturnType<typeof window.setTimeout> | undefined
const form = reactive({
  installation_name: 'DBAChum',
  default_page_size: 10 as 10 | 25 | 50 | 100,
  default_analytics_months: 12,
})

const logoUrl = computed(() => pendingLogoPreview.value ?? (pendingLogoRemoval.value ? null : store.brandingLogoUrl))
const installationInitial = computed(() => form.installation_name.trim().charAt(0).toUpperCase() || 'D')
const updateInstallState = computed(() => store.updateInstallStatus?.state ?? 'idle')
const updateInstallInProgress = computed(() => ['queued', 'running'].includes(updateInstallState.value))
const canInstallUpdate = computed(() => Boolean(
  store.updateStatus?.update_available
  && store.updateStatus.installable
  && store.updateStatus.latest_version
  && !store.updateInstallLoading
  && !updateInstallInProgress.value,
))

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

  await Promise.all([
    store.checkForUpdates(),
    store.loadUpdateInstallStatus().catch(() => null),
  ])

  if (updateInstallInProgress.value) startUpdatePolling()
}

async function refreshUpdateStatus() {
  await Promise.all([
    store.checkForUpdates(true),
    store.loadUpdateInstallStatus().catch(() => null),
  ])
}

function openLatestRelease() {
  if (!store.updateStatus?.release_url) return
  window.open(store.updateStatus.release_url, '_blank', 'noopener,noreferrer')
}

function stopUpdatePolling() {
  if (updatePollTimer !== undefined) {
    window.clearTimeout(updatePollTimer)
    updatePollTimer = undefined
  }
}

function scheduleUpdatePoll(delayMs = 1800) {
  stopUpdatePolling()
  updatePollTimer = window.setTimeout(() => {
    void pollUpdateStatus()
  }, delayMs)
}

async function pollUpdateStatus() {
  try {
    const status = await store.loadUpdateInstallStatus()
    updateTemporarilyOffline.value = false

    if (['queued', 'running'].includes(status.state)) {
      scheduleUpdatePoll()
      return
    }

    stopUpdatePolling()

    if (status.state === 'succeeded') {
      showToast({
        title: `DBAChum v${status.installed_version ?? status.requested_version ?? ''} installed`,
        message: 'The application restarted successfully. Reloading…',
        tone: 'success',
        durationMs: 6000,
      })
      window.setTimeout(() => window.location.reload(), 1200)
      return
    }

    if (status.state === 'failed_rolled_back') {
      showToast({
        title: 'Update failed — previous version restored',
        message: status.message,
        tone: 'warning',
        durationMs: 8000,
      })
      await store.checkForUpdates(true)
      return
    }

    if (status.state === 'failed') {
      showToast({
        title: 'DBAChum update failed',
        message: status.message,
        tone: 'danger',
        durationMs: 8000,
      })
    }
  } catch {
    if (updateInstallInProgress.value) {
      updateTemporarilyOffline.value = true
      scheduleUpdatePoll(2200)
    } else {
      stopUpdatePolling()
    }
  }
}

function startUpdatePolling() {
  updateTemporarilyOffline.value = false
  scheduleUpdatePoll(600)
}

async function installLatestUpdate() {
  const version = store.updateStatus?.latest_version
  if (!version || !canInstallUpdate.value) return

  const confirmed = await confirmDialog({
    title: `Install DBAChum v${version}?`,
    message: 'DBAChum will back up its MongoDB data, install the verified release, and restart automatically. The previous application version will be restored if the update fails.',
    confirmLabel: 'Install update',
    tone: 'warning',
  })
  if (!confirmed) return

  try {
    await store.installUpdate(version)
    showToast({
      title: `Installing DBAChum v${version}`,
      message: 'The application may be unavailable briefly while it restarts.',
      tone: 'default',
      durationMs: 6000,
    })
    startUpdatePolling()
  } catch (exc) {
    const message = exc instanceof Error ? exc.message : 'Unable to start the DBAChum update.'
    showToast({ title: 'Unable to start update', message, tone: 'danger' })
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
onBeforeUnmount(() => {
  clearLogoPreview()
  stopUpdatePolling()
})
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

      <div class="release-update-card" :class="{ 'release-update-card--busy': updateInstallInProgress }">
        <div class="release-update-copy">
          <template v-if="updateTemporarilyOffline && updateInstallInProgress">
            <strong>DBAChum is restarting…</strong>
            <span>The updater is still running. This page will reconnect automatically.</span>
          </template>
          <template v-else-if="updateInstallState === 'queued'">
            <strong>Preparing DBAChum v{{ store.updateInstallStatus?.requested_version }}…</strong>
            <span>{{ store.updateInstallStatus?.message }}</span>
          </template>
          <template v-else-if="updateInstallState === 'running'">
            <strong>Installing DBAChum v{{ store.updateInstallStatus?.requested_version }}…</strong>
            <span>{{ store.updateInstallStatus?.message }}</span>
          </template>
          <template v-else-if="updateInstallState === 'failed_rolled_back'">
            <strong>Update failed — previous version restored</strong>
            <span>{{ store.updateInstallStatus?.message }}</span>
          </template>
          <template v-else-if="updateInstallState === 'failed'">
            <strong>Last update attempt failed</strong>
            <span>{{ store.updateInstallStatus?.message }}</span>
          </template>
          <strong v-else-if="store.updateLoading">Checking for updates…</strong>
          <template v-else-if="store.updateError">
            <strong>Update check unavailable</strong>
            <span>{{ store.updateError }}</span>
          </template>
          <template v-else-if="store.updateStatus?.update_available">
            <strong>DBAChum v{{ store.updateStatus.latest_version }} is available</strong>
            <span v-if="store.updateStatus.installable">{{ store.updateStatus.release_name }}</span>
            <span v-else>This release is missing one or more required update assets.</span>
          </template>
          <template v-else-if="store.updateStatus">
            <strong>You're up to date</strong>
            <span>Latest stable release: v{{ store.updateStatus.latest_version ?? store.general.app_version }}</span>
          </template>
          <template v-else>
            <strong>Update status not checked</strong>
          </template>
        </div>

        <div class="release-update-actions">
          <button
            v-if="store.updateStatus?.update_available && store.updateStatus.release_url"
            type="button"
            class="secondary-button"
            :disabled="updateInstallInProgress || store.updateInstallLoading"
            @click="openLatestRelease"
          >
            View release notes
          </button>
          <button
            v-if="store.updateStatus?.update_available"
            type="button"
            class="primary-button"
            :disabled="!canInstallUpdate"
            @click="installLatestUpdate"
          >
            {{ store.updateInstallLoading ? 'Starting…' : updateInstallInProgress ? 'Installing…' : 'Install update' }}
          </button>
          <button
            type="button"
            class="secondary-button"
            :disabled="store.updateLoading || updateInstallInProgress || store.updateInstallLoading"
            @click="refreshUpdateStatus"
          >
            {{ store.updateLoading ? 'Checking…' : 'Check again' }}
          </button>
        </div>
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

.release-update-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  margin-top: 1rem;
  padding: 0.9rem 1rem;
  border: 1px solid var(--color-border);
  border-radius: 12px;
  background: var(--color-surface-secondary);
}

.release-update-card--busy {
  border-color: var(--color-primary);
}

.release-update-copy {
  display: grid;
  gap: 0.2rem;
  min-width: 0;
}

.release-update-copy span {
  color: var(--text-muted);
  font-size: 0.82rem;
}

.release-update-actions {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex: 0 0 auto;
}

@media (max-width: 680px) {
  .release-update-card {
    align-items: stretch;
    flex-direction: column;
  }

  .release-update-actions {
    flex-wrap: wrap;
  }
}
</style>
