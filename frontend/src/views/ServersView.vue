<script setup lang="ts">
import {
  computed,
  onMounted,
  reactive,
  ref,
} from 'vue'

import {
  useServersStore,
  type Server,
  type ServerInput,
  type ServerOsFamily,
} from '@/stores/servers'


const serversStore = useServersStore()

const formOpen = ref(false)
const editingId = ref<string | null>(null)
const formError = ref<string | null>(null)


interface ServerForm {
  name: string
  hostname: string
  ip_address: string

  os_family: ServerOsFamily
  os_version: string

  environment: string
  owner: string

  tags: string
  notes: string

  enabled: boolean
}


function emptyForm(): ServerForm {
  return {
    name: '',
    hostname: '',
    ip_address: '',

    os_family: 'linux',
    os_version: '',

    environment: '',
    owner: '',

    tags: '',
    notes: '',

    enabled: true,
  }
}


const form = reactive<ServerForm>(
  emptyForm()
)

const isEditing = computed(
  () => editingId.value !== null
)


function resetForm() {
  Object.assign(
    form,
    emptyForm(),
  )

  editingId.value = null
  formError.value = null
}


function openAddServer() {
  resetForm()
  formOpen.value = true
}


function closeForm() {
  formOpen.value = false
  resetForm()
}


function editServer(server: Server) {
  editingId.value = server.id

  Object.assign(form, {
    name: server.name,
    hostname: server.hostname,
    ip_address:
      server.ip_address ?? '',

    os_family:
      server.os_family,

    os_version:
      server.os_version ?? '',

    environment:
      server.environment ?? '',

    owner:
      server.owner ?? '',

    tags:
      server.tags.join(', '),

    notes:
      server.notes ?? '',

    enabled:
      server.enabled,
  })

  formOpen.value = true
}


function buildPayload(): ServerInput {
  return {
    name: form.name.trim(),
    hostname: form.hostname.trim(),

    ip_address:
      form.ip_address.trim() || null,

    os_family:
      form.os_family,

    os_version:
      form.os_version.trim() || null,

    environment:
      form.environment.trim() || null,

    owner:
      form.owner.trim() || null,

    tags:
      form.tags
        .split(',')
        .map((tag) => tag.trim())
        .filter(Boolean),

    notes:
      form.notes.trim() || null,

    enabled:
      form.enabled,
  }
}


async function saveServer() {
  formError.value = null

  try {
    const payload = buildPayload()

    if (editingId.value) {
      await serversStore.update(
        editingId.value,
        payload,
      )
    } else {
      await serversStore.create(
        payload,
      )
    }

    closeForm()

  } catch (error) {
    formError.value =
      error instanceof Error
        ? error.message
        : 'Unable to save server.'
  }
}


async function removeServer(
  server: Server,
) {
  if (
    !window.confirm(
      `Delete "${server.name}"?`,
    )
  ) {
    return
  }

  await serversStore.remove(
    server.id
  )
}


function osLabel(
  os: ServerOsFamily,
) {
  switch (os) {
    case 'windows':
      return 'Windows'
    case 'linux':
      return 'Linux'
    case 'aix':
      return 'AIX'
    case 'unix':
      return 'Unix'
    case 'other':
      return 'Other'
  }
}


onMounted(() => {
  serversStore.load()
})
</script>

<template>
  <section class="page-header">
    <div>
      <h1>Servers</h1>

      <p>
        Infrastructure hosting monitored
        databases.
      </p>
    </div>

    <button
      type="button"
      class="primary-button"
      @click="openAddServer"
    >
      Add server
    </button>
  </section>

  <p
    v-if="serversStore.loading"
    class="empty-state"
  >
    Loading servers...
  </p>

  <p
    v-else-if="serversStore.error"
    class="login-error"
  >
    {{ serversStore.error }}
  </p>

  <div
    v-else-if="
      serversStore.servers.length === 0
    "
    class="database-empty-state"
  >
    <h2>No servers yet</h2>

    <p>
      Add infrastructure and associate
      database connections with it.
    </p>
  </div>

  <div
    v-else
    class="server-grid"
  >
    <article
      v-for="server in serversStore.servers"
      :key="server.id"
      class="server-card"
    >
      <div class="server-card-header">
        <div>
          <strong>
            {{ server.name }}
          </strong>

          <span>
            {{ osLabel(server.os_family) }}
            <template v-if="server.os_version">
              · {{ server.os_version }}
            </template>
          </span>
        </div>

        <span>
          {{
            server.enabled
              ? 'Enabled'
              : 'Disabled'
          }}
        </span>
      </div>

      <div>
        {{ server.hostname }}

        <template v-if="server.ip_address">
          · {{ server.ip_address }}
        </template>
      </div>

      <div class="server-metadata">
        <span>
          Environment:
          {{ server.environment ?? '—' }}
        </span>

        <span>
          Owner:
          {{ server.owner ?? '—' }}
        </span>

        <span>
          Databases:
          {{ server.database_count }}
        </span>
      </div>

      <div
        v-if="server.tags.length"
        class="server-tags"
      >
        <span
          v-for="tag in server.tags"
          :key="tag"
        >
          {{ tag }}
        </span>
      </div>

      <div class="connection-actions">
        <button
          type="button"
          class="secondary-button"
          @click="editServer(server)"
        >
          Edit
        </button>

        <button
          type="button"
          class="secondary-button"
          @click="removeServer(server)"
        >
          Delete
        </button>
      </div>
    </article>
  </div>

  <div
    v-if="formOpen"
    class="modal-backdrop"
    @click.self="closeForm"
  >
    <section
      class="modal-panel"
      role="dialog"
      aria-modal="true"
    >
      <div class="modal-header">
        <div>
          <h2>
            {{
              isEditing
                ? 'Edit server'
                : 'Add server'
            }}
          </h2>

          <p>
            Infrastructure inventory.
          </p>
        </div>

        <button
          type="button"
          class="modal-close"
          @click="closeForm"
        >
          ×
        </button>
      </div>

      <form
        class="connection-form"
        @submit.prevent="saveServer"
      >
        <label>
          Server name

          <input
            v-model="form.name"
            required
            placeholder="Oracle PROD 01"
          />
        </label>

        <label>
          Hostname

          <input
            v-model="form.hostname"
            required
            placeholder="dbprod01"
          />
        </label>

        <label>
          IP address

          <input
            v-model="form.ip_address"
            placeholder="192.168.1.10"
          />
        </label>

        <label>
          Operating system

          <select
            v-model="form.os_family"
          >
            <option value="windows">
              Windows
            </option>

            <option value="linux">
              Linux
            </option>

            <option value="aix">
              AIX
            </option>

            <option value="unix">
              Unix
            </option>

            <option value="other">
              Other
            </option>
          </select>
        </label>

        <label>
          OS version

          <input
            v-model="form.os_version"
            placeholder="RHEL 9"
          />
        </label>

        <label>
          Environment

          <input
            v-model="form.environment"
            placeholder="Production"
          />
        </label>

        <label>
          Owner / team

          <input
            v-model="form.owner"
            placeholder="Database Administrator"
          />
        </label>

        <label>
          Tags

          <input
            v-model="form.tags"
            placeholder="oracle, production, erp"
          />

          <small>
            Separate tags with commas.
          </small>
        </label>

        <label>
          Notes

          <textarea
            v-model="form.notes"
            rows="4"
          />
        </label>

        <label class="connection-checkbox">
          <input
            v-model="form.enabled"
            type="checkbox"
          />

          Enable this server
        </label>

        <p
          v-if="formError"
          class="login-error"
        >
          {{ formError }}
        </p>

        <div class="connection-form-actions">
          <button
            type="submit"
            class="primary-button"
            :disabled="serversStore.saving"
          >
            {{
              serversStore.saving
                ? 'Saving...'
                : isEditing
                  ? 'Save changes'
                  : 'Add server'
            }}
          </button>

          <button
            type="button"
            class="secondary-button"
            @click="closeForm"
          >
            Cancel
          </button>
        </div>
      </form>
    </section>
  </div>
</template>