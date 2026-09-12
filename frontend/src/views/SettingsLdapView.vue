<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import FloatingActionMenu from '@/components/common/FloatingActionMenu.vue'

import {
  useProvisioningStore,
  type LdapProfile,
  type LdapProfileInput,
  type LdapProfileTestResult,
} from '@/stores/provisioning'
import { confirmDialog, showToast } from '@/ui/feedback'

import {
  useAuthStore,
} from '@/stores/auth'

import {
  hasPermission,
} from '@/core/permissions'

const provisioningStore = useProvisioningStore()
const authStore = useAuthStore()

const formOpen = ref(false)
const editingId = ref<string | null>(null)
const formError = ref<string | null>(null)
const testingId = ref<string | null>(null)
const testResults = ref<Record<string, LdapProfileTestResult>>({})

const form = reactive<LdapProfileInput>({
  name: '',
  description: null,
  enabled: false,
  host: '',
  port: 636,
  use_ssl: true,
  base_dn: '',
  bind_dn: '',
  bind_password: '',
  ldif_template: '',
})

const canManageConnections = computed(
  () =>
    hasPermission(
      authStore.user,
      'connections:manage',
    ),
)

const canTestConnections = computed(
  () =>
    hasPermission(
      authStore.user,
      'connections:test',
    ),
)


function resetForm() {
  editingId.value = null
  formError.value = null
  Object.assign(form, {
    name: '',
    description: null,
    enabled: false,
    host: '',
    port: 636,
    use_ssl: true,
    base_dn: '',
    bind_dn: '',
    bind_password: '',
    ldif_template: '',
  })
}

function openAdd() {
  resetForm()
  formOpen.value = true
}

function openEdit(profile: LdapProfile) {
  editingId.value = profile.id
  formError.value = null
  Object.assign(form, {
    name: profile.name,
    description: profile.description,
    enabled: profile.enabled,
    host: profile.host,
    port: profile.port,
    use_ssl: profile.use_ssl,
    base_dn: profile.base_dn,
    bind_dn: profile.bind_dn,
    bind_password: '',
    ldif_template: profile.ldif_template,
  })
  formOpen.value = true
}

function closeForm() {
  formOpen.value = false
  resetForm()
}

async function testProfile(profile: LdapProfile) {
  testingId.value = profile.id
  delete testResults.value[profile.id]
  try {
    const result = await provisioningStore.testLdapProfile(profile.id)
    testResults.value[profile.id] = result
    showToast({
      title: result.success ? 'LDAP connection test passed' : 'LDAP connection test completed with warnings',
      message: result.message,
      tone: result.success ? 'success' : 'warning',
    })
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Unable to test LDAP profile.'
    testResults.value[profile.id] = {
      success: false,
      connect_ok: false,
      bind_ok: false,
      base_dn_ok: false,
      message,
    }
    showToast({ title: 'LDAP connection test failed', message, tone: 'danger' })
  } finally {
    testingId.value = null
  }
}

async function remove(profile: LdapProfile) {
  const confirmed = await confirmDialog({ title: 'Delete LDAP profile', message: profile.name, confirmLabel: 'Delete profile', destructive: true, tone: 'danger' })
  if (!confirmed) return
  try {
    await provisioningStore.removeLdapProfile(profile.id)
    showToast({ title: 'LDAP profile deleted', message: profile.name, tone: 'success' })
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Unable to delete LDAP profile.'
    showToast({ title: 'Unable to delete LDAP profile', message, tone: 'danger' })
  }
}

async function save() {
  formError.value = null

  try {
    const payload: LdapProfileInput = {
      name: form.name.trim(),
      description: form.description?.trim() || null,
      enabled: form.enabled,
      host: form.host.trim(),
      port: Number(form.port),
      use_ssl: form.use_ssl,
      base_dn: form.base_dn.trim(),
      bind_dn: form.bind_dn.trim(),
      bind_password: form.bind_password || undefined,
      ldif_template: form.ldif_template,
    }

    const updated = Boolean(editingId.value)

    if (editingId.value) {
      await provisioningStore.updateLdapProfile(
        editingId.value,
        payload,
      )
    } else {
      await provisioningStore.createLdapProfile(payload)
    }

    closeForm()

    showToast({
      title: updated
        ? 'LDAP profile updated'
        : 'LDAP profile created',
      message: payload.name,
      tone: 'success',
    })
  } catch (error) {
    const message =
      error instanceof Error
        ? error.message
        : 'Unable to save LDAP profile.'

    formError.value = message

    showToast({
      title: 'Unable to save LDAP profile',
      message,
      tone: 'danger',
    })
  }
}

onMounted(() => {
  provisioningStore.loadLdapProfiles()
})

</script>

<template>
  <div class="settings-ldap">
    <section class="panel">
      <div class="panel-header">
        <div title="Keep directory connections independent. Provisioning profiles choose the LDAP profile they need.">
          <h2>LDAP profiles</h2>
        </div>

        <button class="primary-button" type="button" @click="openAdd">
          Add LDAP profile
        </button>
      </div>

      <p v-if="provisioningStore.loading" class="empty-state">Loading LDAP profiles
      <p class="loading"></p>
      </p>
      <p v-else-if="provisioningStore.error" class="login-error">{{ provisioningStore.error }}</p>

      <div v-else-if="provisioningStore.ldapProfiles.length === 0" class="empty-state">
        No LDAP profiles yet.
      </div>

      <div v-else class="connection-list">
        <article v-for="profile in provisioningStore.ldapProfiles" :key="profile.id" class="connection-item">
          <div>
            <div class="connection-title">
              <strong>{{ profile.name }}</strong>
              <span class="status-pill" :class="{ disabled: !profile.enabled || !profile.configured }">
                {{ !profile.enabled ? 'Disabled' : profile.configured ? 'Configured' : 'Incomplete' }}
              </span>
            </div>
            <p>{{ profile.description || 'No description' }}</p>
            <small>
              {{ profile.host || 'No host' }}:{{ profile.port }}
              · {{ profile.use_ssl ? 'LDAPS / SSL' : 'LDAP' }}
              · {{ profile.base_dn || 'No Base DN' }}
            </small>
          </div>
          <FloatingActionMenu v-if="canTestConnections || canManageConnections" :label="`Actions for ${profile.name}`">
            <button v-if="canTestConnections" type="button" role="menuitem" @click="testProfile(profile)">
              <FontAwesomeIcon icon="plug" />
              Test connection
            </button>
            <button v-if="canManageConnections" type="button" role="menuitem" @click="openEdit(profile)">
              <FontAwesomeIcon icon="pen" />
              Edit
            </button>
            <button v-if="canManageConnections" type="button" role="menuitem" class="danger-menu-item" @click="remove(profile)">
              <FontAwesomeIcon icon="trash-can" />
              Delete
            </button>
          </FloatingActionMenu>
        </article>
      </div>
    </section>

    <div v-if="formOpen" class="modal-backdrop" @click.self="closeForm">
      <section class="modal-panel" role="dialog" aria-modal="true"
        :aria-label="editingId ? 'Edit LDAP profile' : 'Add LDAP profile'" style="--modal-width: 650px">
        <div class="modal-header">
          <div>
            <h2>{{ editingId ? 'Edit LDAP profile' : 'Add LDAP profile' }}</h2>
          </div>
          <button class="modal-close" type="button" aria-label="Close" @click="closeForm">×</button>
        </div>

        <form class="connection-form" @submit.prevent="save">
          <label>
            <span class="field-label">Profile name <span class="required-mark" aria-hidden="true">*</span></span>
            <input v-model="form.name" required maxlength="100" placeholder="Oracle Retail LDAP" />
          </label>

          <label>
            Description
            <input v-model="form.description" maxlength="500" placeholder="LDAP used by ORMS / OREIM / ORPM" />
          </label>

          <label class="connection-checkbox">
            <input v-model="form.enabled" type="checkbox" class="toggle-switch"/>
            Enable this LDAP profile
          </label>

          <div class="connection-form-row">
            <label>
              <span class="field-label">Host <span v-if="form.enabled" class="required-mark"
                  aria-hidden="true">*</span></span>
              <input v-model="form.host" :required="form.enabled" maxlength="255" placeholder="ldap.example.local" />
            </label>

            <label>
              <span class="field-label">Port <span class="required-mark" aria-hidden="true">*</span></span>
              <input v-model.number="form.port" type="number" min="1" max="65535" required />
            </label>
          </div>

          <label class="connection-checkbox">
            <input v-model="form.use_ssl" type="checkbox" class="toggle-switch"/>
            Use TLS / SSL (LDAPS)
          </label>

          <label>
            <span class="field-label">Base DN <span v-if="form.enabled" class="required-mark"
                aria-hidden="true">*</span></span>
            <input v-model="form.base_dn" :required="form.enabled" maxlength="500" placeholder="dc=example,dc=local" />
          </label>

          <label>
            <span class="field-label">Bind DN <span v-if="form.enabled" class="required-mark"
                aria-hidden="true">*</span></span>
            <input v-model="form.bind_dn" :required="form.enabled" maxlength="500"
              placeholder="cn=dbachum,ou=service,dc=example,dc=local" />
          </label>

          <label>
            Bind password
            <input v-model="form.bind_password" type="password" maxlength="512" autocomplete="new-password"
              placeholder="Leave blank while editing to keep the saved password" />
          </label>

          <label>
            LDIF template
            <textarea v-model="form.ldif_template" rows="10" maxlength="20000" spellcheck="false"
              placeholder="Paste the working LDIF template here"></textarea>
            <small>
              Supported placeholders: &lt;USERNAME&gt;, &lt;FIRSTNAME&gt;, &lt;MIDDLENAME&gt;,
              &lt;LASTNAME&gt;, &lt;EMPLOYEE ID&gt;, &lt;PASSWORD&gt;, &lt;BASE_DN&gt;.
            </small>
          </label>

          <p v-if="formError" class="login-error">{{ formError }}</p>

          <div class="connection-form-actions">
            <button class="primary-button" type="submit" :disabled="provisioningStore.saving">
              {{ provisioningStore.saving ? 'Saving' : editingId ? 'Save LDAP profile' : 'Create LDAP profile' }}
              <p v-if="provisioningStore.saving" class="loading"></p>
            </button>
            <button class="secondary-button" type="button" @click="closeForm">Cancel</button>
          </div>
        </form>
      </section>
    </div>
  </div>
  
</template>
