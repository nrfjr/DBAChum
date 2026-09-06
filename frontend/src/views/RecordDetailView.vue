<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { engineLabel } from '@/core/databasePresentation'
import { hasPermission } from '@/core/permissions'
import { useAuthStore } from '@/stores/auth'
import { useRecordsStore, type DbaRecord, type RecordStatus, type RecordType } from '@/stores/records'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()
const recordsStore = useRecordsStore()

const record = ref<DbaRecord | null>(null)
const loading = ref(true)
const error = ref<string | null>(null)
const revealedPassword = ref<string | null>(null)
const secretError = ref<string | null>(null)
const copied = ref<string | null>(null)

const canManage = computed(() => hasPermission(authStore.user, 'records:manage'))

const typeLabels: Record<RecordType, string> = {
  database: 'Database',
  server: 'Server',
  application: 'Application',
  credential: 'Credential / account',
  url: 'URL / web resource',
  other: 'Other',
}

const statusLabels: Record<RecordStatus, string> = {
  active: 'Active',
  standby: 'Standby',
  disabled: 'Disabled',
  retired: 'Retired',
  unknown: 'Unknown',
}

const endpoint = computed(() => {
  if (!record.value) return '—'
  if (record.value.hostname) {
    return `${record.value.hostname}${record.value.port ? `:${record.value.port}` : ''}`
  }
  if (record.value.ip_address) {
    return `${record.value.ip_address}${record.value.port ? `:${record.value.port}` : ''}`
  }
  return '—'
})

function isSafeWebUrl(value: string | null) {
  return Boolean(value && /^https?:\/\//i.test(value))
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: 'medium',
    timeStyle: 'medium',
  }).format(new Date(value))
}

async function copyValue(label: string, value: string | null) {
  if (!value) return
  try {
    await navigator.clipboard.writeText(value)
    copied.value = label
    window.setTimeout(() => {
      if (copied.value === label) copied.value = null
    }, 1600)
  } catch {
    copied.value = null
  }
}

async function revealPassword() {
  if (!record.value || !canManage.value) return
  secretError.value = null
  try {
    revealedPassword.value = await recordsStore.revealPassword(record.value.id)
  } catch (err) {
    secretError.value = err instanceof Error ? err.message : 'Unable to reveal password.'
  }
}

function hidePassword() {
  revealedPassword.value = null
  secretError.value = null
}

function editRecord() {
  if (!record.value) return
  void router.push({ path: '/records', query: { edit: record.value.id } })
}

async function deleteRecord() {
  if (!record.value || !canManage.value) return
  if (!window.confirm(`Delete record "${record.value.name}"? This will not delete linked Connections or Servers.`)) return
  try {
    await recordsStore.remove(record.value.id)
    await router.push('/records')
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Unable to delete record.'
  }
}

onMounted(async () => {
  loading.value = true
  error.value = null
  try {
    const id = String(route.params.id)
    record.value = recordsStore.byId(id) ?? await recordsStore.loadOne(id)
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Unable to load record.'
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <div v-if="loading" class="empty-state">
    Loading record...
  </div>

  <div v-else-if="error" class="login-error">
    {{ error }}
  </div>

  <template v-else-if="record">
    <section class="page-header record-detail-header">
      <div>
        <RouterLink to="/records" class="text-link">← Back to Records</RouterLink>
        <div class="record-detail-title-row">
          <div>
            <h1>{{ record.name }}</h1>
            <p>
              {{ typeLabels[record.record_type] }}
              <template v-if="record.environment"> · {{ record.environment }}</template>
              <template v-if="record.engine"> · {{ engineLabel(record.engine) }}</template>
            </p>
          </div>
          <span class="record-status-pill" :class="`record-status-pill--${record.status}`">
            {{ statusLabels[record.status] }}
          </span>
        </div>
      </div>

      <div v-if="canManage" class="record-detail-actions">
        <button type="button" class="secondary-button" @click="editRecord">Edit record</button>
        <button type="button" class="danger-button" @click="deleteRecord">Delete</button>
      </div>
    </section>

    <section class="record-detail-grid">
      <article class="detail-card">
        <h2>Identity & ownership</h2>
        <dl class="detail-list record-detail-list">
          <div><dt>Type</dt><dd>{{ typeLabels[record.record_type] }}</dd></div>
          <div><dt>Environment</dt><dd>{{ record.environment ?? '—' }}</dd></div>
          <div><dt>Engine</dt><dd>{{ record.engine ? engineLabel(record.engine) : '—' }}</dd></div>
          <div><dt>Version</dt><dd>{{ record.version ?? '—' }}</dd></div>
          <div><dt>Application</dt><dd>{{ record.application ?? '—' }}</dd></div>
          <div><dt>Owner / team</dt><dd>{{ record.owner ?? '—' }}</dd></div>
        </dl>
      </article>

      <article class="detail-card">
        <h2>Endpoint / resource</h2>
        <dl class="detail-list record-detail-list">
          <div>
            <dt>Endpoint</dt>
            <dd class="record-copy-value">
              <span>{{ endpoint }}</span>
              <button v-if="endpoint !== '—'" type="button" class="record-copy-button" @click="copyValue('endpoint', endpoint)">
                {{ copied === 'endpoint' ? 'Copied' : 'Copy' }}
              </button>
            </dd>
          </div>
          <div><dt>IP address</dt><dd>{{ record.ip_address ?? '—' }}</dd></div>
          <div><dt>Port</dt><dd>{{ record.port ?? '—' }}</dd></div>
          <div>
            <dt>URL</dt>
            <dd>
              <a v-if="record.url && isSafeWebUrl(record.url)" :href="record.url" target="_blank" rel="noopener noreferrer" class="text-link">
                {{ record.url }}
              </a>
              <template v-else-if="record.url">{{ record.url }}</template>
              <template v-else>—</template>
            </dd>
          </div>
        </dl>
      </article>

      <article class="detail-card">
        <h2>DBAChum links</h2>
        <dl class="detail-list record-detail-list">
          <div>
            <dt>Connection</dt>
            <dd>
              <template v-if="record.connection_id">
                <span>{{ record.connection_name ?? 'Linked connection' }}</span>
                <RouterLink
                  v-if="record.record_type === 'database' && record.connection_name"
                  :to="{ name: 'database-detail', params: { id: record.connection_id }, query: record.engine ? { engine: record.engine } : {} }"
                  class="text-link record-detail-link"
                >
                  Open database
                </RouterLink>
              </template>
              <template v-else>—</template>
            </dd>
          </div>
          <div>
            <dt>Server</dt>
            <dd>
              <template v-if="record.server_id">
                <span>{{ record.server_name ?? 'Linked server' }}</span>
                <RouterLink v-if="record.server_name" :to="`/servers/${record.server_id}`" class="text-link record-detail-link">Open server</RouterLink>
              </template>
              <template v-else>—</template>
            </dd>
          </div>
        </dl>
      </article>

      <article class="detail-card">
        <h2>Lookup credential</h2>
        <dl class="detail-list record-detail-list">
          <div>
            <dt>Username</dt>
            <dd class="record-copy-value">
              <span>{{ record.username ?? '—' }}</span>
              <button v-if="record.username" type="button" class="record-copy-button" @click="copyValue('username', record.username)">
                {{ copied === 'username' ? 'Copied' : 'Copy' }}
              </button>
            </dd>
          </div>
          <div>
            <dt>Password</dt>
            <dd>
              <div v-if="record.has_password" class="record-secret-row">
                <code>{{ revealedPassword ?? '••••••••••••' }}</code>
                <button
                  v-if="canManage && !revealedPassword"
                  type="button"
                  class="secondary-button"
                  @click="revealPassword"
                >
                  Reveal
                </button>
                <template v-else-if="canManage && revealedPassword">
                  <button type="button" class="secondary-button" @click="copyValue('password', revealedPassword)">
                    {{ copied === 'password' ? 'Copied' : 'Copy' }}
                  </button>
                  <button type="button" class="secondary-button" @click="hidePassword">Hide</button>
                </template>
              </div>
              <span v-else>—</span>
              <small v-if="record.has_password && !canManage" class="record-detail-muted">Stored; reveal requires record-management permission.</small>
              <small v-if="secretError" class="record-detail-error">{{ secretError }}</small>
            </dd>
          </div>
        </dl>
      </article>

      <article v-if="record.custom_fields.length" class="detail-card record-custom-fields-card">
        <h2>Custom fields</h2>
        <dl class="detail-list record-detail-list">
          <div v-for="field in record.custom_fields" :key="field.key">
            <dt>{{ field.key }}</dt>
            <dd class="record-copy-value">
              <span>{{ field.value || '—' }}</span>
              <button v-if="field.value" type="button" class="record-copy-button" @click="copyValue(`custom:${field.key}`, field.value)">
                {{ copied === `custom:${field.key}` ? 'Copied' : 'Copy' }}
              </button>
            </dd>
          </div>
        </dl>
      </article>

      <article class="detail-card record-notes-card">
        <h2>Notes & tags</h2>
        <p class="record-notes-text">{{ record.notes ?? 'No notes.' }}</p>
        <div v-if="record.tags.length" class="server-tags">
          <span v-for="tag in record.tags" :key="tag">{{ tag }}</span>
        </div>
      </article>

      <article class="detail-card record-audit-card">
        <h2>Record history</h2>
        <dl class="detail-list record-detail-list">
          <div><dt>Created</dt><dd>{{ formatDate(record.created_at) }}</dd></div>
          <div><dt>Created by</dt><dd>{{ record.created_by ?? '—' }}</dd></div>
          <div><dt>Updated</dt><dd>{{ formatDate(record.updated_at) }}</dd></div>
          <div><dt>Updated by</dt><dd>{{ record.updated_by ?? '—' }}</dd></div>
        </dl>
      </article>
    </section>
  </template>
</template>
