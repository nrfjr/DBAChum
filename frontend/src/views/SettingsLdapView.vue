<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'

import {
  useProvisioningStore,
  type LdapProfile,
  type LdapProfileInput,
  type LdapProfileTestResult,
} from '@/stores/provisioning'

const provisioningStore = useProvisioningStore()
const formOpen = ref(false)
const editingId = ref<string | null>(null)
const formError = ref<string | null>(null)
const savedMessage = ref<string | null>(null)
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

function resetForm() {
  editingId.value = null
  formError.value = null
  savedMessage.value = null
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
  savedMessage.value = null
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

async function save() {
  formError.value = null
  savedMessage.value = null
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

    if (editingId.value) {
      await provisioningStore.updateLdapProfile(editingId.value, payload)
    } else {
      await provisioningStore.createLdapProfile(payload)
    }
    closeForm()
  } catch (error) {
    formError.value = error instanceof Error ? error.message : 'Unable to save LDAP profile.'
  }
}

async function testProfile(profile: LdapProfile) {
  testingId.value = profile.id
  delete testResults.value[profile.id]
  try {
    testResults.value[profile.id] = await provisioningStore.testLdapProfile(profile.id)
  } catch (error) {
    testResults.value[profile.id] = {
      success: false,
      connect_ok: false,
      bind_ok: false,
      base_dn_ok: false,
      message: error instanceof Error ? error.message : 'Unable to test LDAP profile.',
    }
  } finally {
    testingId.value = null
  }
}

async function remove(profile: LdapProfile) {
  if (!window.confirm(`Delete LDAP profile "${profile.name}"?`)) return
  try {
    await provisioningStore.removeLdapProfile(profile.id)
  } catch (error) {
    testResults.value[profile.id] = {
      success: false,
      connect_ok: false,
      bind_ok: false,
      base_dn_ok: false,
      message: error instanceof Error ? error.message : 'Unable to delete LDAP profile.',
    }
  }
}

onMounted(() => provisioningStore.loadLdapProfiles())
</script>

<template>
  <div class="settings-ldap">
    <section class="panel">
      <div class="panel-header">
        <div>
          <h2>LDAP profiles</h2>
          <p>
            Keep directory connections independent. Provisioning profiles choose the LDAP profile they need.
          </p>
        </div>

        <button class="primary-button" type="button" @click="openAdd">
          Add LDAP profile
        </button>
      </div>

      <p v-if="provisioningStore.loading" class="empty-state">Loading LDAP profiles...</p>
      <p v-else-if="provisioningStore.error" class="login-error">{{ provisioningStore.error }}</p>

      <div v-else-if="provisioningStore.ldapProfiles.length === 0" class="empty-state">
        No LDAP profiles yet.
      </div>

      <div v-else class="connection-list">
        <article
          v-for="profile in provisioningStore.ldapProfiles"
          :key="profile.id"
          class="connection-item"
        >
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
            <small v-if="profile.migrated_from_legacy" class="connection-danger-note">
              Migrated from your previous global LDAP settings. The old record was kept as a rollback copy.
            </small>

            <p
              v-if="testResults[profile.id]"
              class="connection-test-result"
              :class="{ success: testResults[profile.id]?.success }"
            >
              {{ testResults[profile.id]?.message }}
            </p>
          </div>

          <div class="connection-actions">
            <button
              class="secondary-button"
              type="button"
              :disabled="testingId === profile.id || !profile.configured"
              @click="testProfile(profile)"
            >
              {{ testingId === profile.id ? 'Testing...' : 'Test' }}
            </button>
            <button class="secondary-button" type="button" @click="openEdit(profile)">Edit</button>
            <button v-if="!profile.migrated_from_legacy" class="secondary-button" type="button" @click="remove(profile)">Delete</button>
          </div>
        </article>
      </div>
    </section>

    <div v-if="formOpen" class="modal-backdrop" @click.self="closeForm">
      <section
        class="modal-panel"
        role="dialog"
        aria-modal="true"
        :aria-label="editingId ? 'Edit LDAP profile' : 'Add LDAP profile'"
      >
        <div class="modal-header">
          <div>
            <h2>{{ editingId ? 'Edit LDAP profile' : 'Add LDAP profile' }}</h2>
            <p>Connection, credentials and LDIF template travel together as one reusable profile.</p>
          </div>
          <button class="modal-close" type="button" aria-label="Close" @click="closeForm">×</button>
        </div>

        <form class="connection-form" @submit.prevent="save">
          <label>
            Profile name
            <input v-model="form.name" required maxlength="100" placeholder="Oracle Retail LDAP" />
          </label>

          <label>
            Description
            <input v-model="form.description" maxlength="500" placeholder="LDAP used by ORMS / OREIM / ORPM" />
          </label>

          <label class="connection-checkbox">
            <input v-model="form.enabled" type="checkbox" />
            Enable this LDAP profile
          </label>

          <div class="connection-form-row">
            <label>
              Host
              <input v-model="form.host" :required="form.enabled" placeholder="ldap.example.local" />
            </label>

            <label>
              Port
              <input v-model.number="form.port" type="number" min="1" max="65535" required />
            </label>
          </div>

          <label class="connection-checkbox">
            <input v-model="form.use_ssl" type="checkbox" />
            Use TLS / SSL (LDAPS)
          </label>

          <label>
            Base DN
            <input v-model="form.base_dn" :required="form.enabled" placeholder="dc=example,dc=local" />
          </label>

          <label>
            Bind DN
            <input v-model="form.bind_dn" :required="form.enabled" placeholder="cn=dbachum,ou=service,dc=example,dc=local" />
          </label>

          <label>
            Bind password
            <input
              v-model="form.bind_password"
              type="password"
              autocomplete="new-password"
              placeholder="Leave blank while editing to keep the saved password"
            />
            <small>Stored encrypted. Existing passwords are never returned to the browser.</small>
          </label>

          <label>
            LDIF template
            <textarea
              v-model="form.ldif_template"
              rows="18"
              maxlength="20000"
              spellcheck="false"
              placeholder="Paste the working LDIF template here"
            ></textarea>
            <small>
              Supported placeholders: &lt;USERNAME&gt;, &lt;FIRSTNAME&gt;, &lt;MIDDLENAME&gt;,
              &lt;LASTNAME&gt;, &lt;EMPLOYEE ID&gt;, &lt;PASSWORD&gt;, &lt;BASE_DN&gt;.
            </small>
          </label>

          <p v-if="formError" class="login-error">{{ formError }}</p>
          <p v-if="savedMessage" class="connection-test-result success">{{ savedMessage }}</p>

          <div class="connection-form-actions">
            <button class="primary-button" type="submit" :disabled="provisioningStore.saving">
              {{ provisioningStore.saving ? 'Saving...' : editingId ? 'Save LDAP profile' : 'Create LDAP profile' }}
            </button>
            <button class="secondary-button" type="button" @click="closeForm">Cancel</button>
          </div>
        </form>
      </section>
    </div>
  </div>
</template>
