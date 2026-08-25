<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'

import { useProvisioningStore } from '@/stores/provisioning'

const provisioningStore = useProvisioningStore()
const savedMessage = ref<string | null>(null)
const formError = ref<string | null>(null)

const form = reactive({
  enabled: false,
  host: '',
  port: 636,
  use_ssl: true,
  base_dn: '',
  bind_dn: '',
  bind_password: '',
  ldif_template: '',
})

async function load() {
  formError.value = null
  try {
    const ldap = await provisioningStore.loadLdap()
    Object.assign(form, {
      enabled: ldap.enabled,
      host: ldap.host,
      port: ldap.port,
      use_ssl: ldap.use_ssl,
      base_dn: ldap.base_dn,
      bind_dn: ldap.bind_dn,
      bind_password: '',
      ldif_template: ldap.ldif_template,
    })
  } catch (error) {
    formError.value = error instanceof Error
      ? error.message
      : 'Unable to load LDAP settings.'
  }
}

async function save() {
  formError.value = null
  savedMessage.value = null

  try {
    const payload = {
      enabled: form.enabled,
      host: form.host.trim(),
      port: Number(form.port),
      use_ssl: form.use_ssl,
      base_dn: form.base_dn.trim(),
      bind_dn: form.bind_dn.trim(),
      bind_password: form.bind_password || undefined,
      ldif_template: form.ldif_template,
    }
    await provisioningStore.saveLdap(payload)
    form.bind_password = ''
    savedMessage.value = 'LDAP settings saved.'
  } catch (error) {
    formError.value = error instanceof Error
      ? error.message
      : 'Unable to save LDAP settings.'
  }
}

onMounted(load)
</script>

<template>
  <section class="panel settings-ldap">
    <div class="panel-header">
      <div>
        <h2>LDAP</h2>
        <p>
          Configure directory access once. Provisioning profiles can opt in to LDAP individually.
        </p>
      </div>

      <span
        class="status-pill"
        :class="{ disabled: !provisioningStore.ldap?.configured }"
      >
        {{ provisioningStore.ldap?.configured ? 'Configured' : 'Not configured' }}
      </span>
    </div>

    <form class="connection-form" @submit.prevent="save">
      <label class="connection-checkbox">
        <input v-model="form.enabled" type="checkbox" />
        Enable LDAP provisioning
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
        Use TLS / SSL
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
          :placeholder="provisioningStore.ldap?.has_bind_password
            ? 'Leave blank to keep current password'
            : 'LDAP bind password'"
        />
        <small>
          Stored encrypted. Existing passwords are never returned to the browser.
        </small>
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
          Used only to generate the downloadable LDIF after provisioning. Supported placeholders:
          &lt;USERNAME&gt;, &lt;FIRSTNAME&gt;, &lt;MIDDLENAME&gt;, &lt;LASTNAME&gt;,
          &lt;EMPLOYEE ID&gt;, &lt;PASSWORD&gt;, &lt;BASE_DN&gt;.
        </small>
      </label>

      <p v-if="formError" class="login-error">{{ formError }}</p>
      <p v-if="savedMessage" class="connection-test-result success">{{ savedMessage }}</p>

      <div class="connection-form-actions">
        <button class="primary-button" type="submit" :disabled="provisioningStore.saving">
          {{ provisioningStore.saving ? 'Saving...' : 'Save LDAP settings' }}
        </button>
      </div>
    </form>
  </section>
</template>
