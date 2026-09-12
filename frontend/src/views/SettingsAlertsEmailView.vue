<script setup lang="ts">
import {
  computed,
  onMounted,
  reactive,
  ref,
  watch,
} from 'vue'

import {
  useEmailDeliveryStore,
  type EmailProvider,
  type SmtpSecurity,
} from '@/stores/emailDelivery'

import { useAuthStore } from '@/stores/auth'
import { formatUserDateTime } from '@/core/dateTime'
import { confirmDialog, showToast } from '@/ui/feedback'
import ScrollableDataTable from '@/components/common/ScrollableDataTable.vue'

const emailStore = useEmailDeliveryStore()
const authStore = useAuthStore()

const testError = ref('')
const testRecipient = ref('')
const testRecipientName = ref('')
const selectedDeliveryIds = ref<string[]>([])
const deliveryClearError = ref('')

const form = reactive({
  enabled: false,
  provider: 'brevo' as EmailProvider,
  sender_name: 'DBAChum Alerts',
  sender_email: '',
  reply_to_email: '',
  application_url: '',
  max_retries: 3,
  brevo_api_key: '',
  smtp_host: '',
  smtp_port: 587,
  smtp_security: 'starttls' as SmtpSecurity,
  smtp_username: '',
  smtp_password: '',
})

const providerLabel = computed(() => (
  form.provider === 'brevo' ? 'Brevo API' : 'SMTP'
))

const clearableDeliveries = computed(() =>
  emailStore.deliveries.filter((delivery) =>
    delivery.status === 'sent' || delivery.status === 'failed',
  ),
)

const allClearableSelected = computed(() =>
  clearableDeliveries.value.length > 0
  && clearableDeliveries.value.every((delivery) =>
    selectedDeliveryIds.value.includes(delivery.id),
  ),
)

function applySettings() {
  const settings = emailStore.settings
  if (!settings) {
    return
  }

  form.enabled = settings.enabled
  form.provider = settings.provider
  form.sender_name = settings.sender_name
  form.sender_email = settings.sender_email ?? ''
  form.reply_to_email = settings.reply_to_email ?? ''
  form.application_url = settings.application_url ?? ''
  form.max_retries = settings.max_retries
  form.brevo_api_key = ''
  form.smtp_host = settings.smtp_host ?? ''
  form.smtp_port = settings.smtp_port
  form.smtp_security = settings.smtp_security
  form.smtp_username = settings.smtp_username ?? ''
  form.smtp_password = ''
}

watch(
  () => emailStore.settings,
  () => applySettings(),
)

watch(
  () => emailStore.deliveries.map((delivery) => delivery.id),
  (ids) => {
    selectedDeliveryIds.value = selectedDeliveryIds.value.filter((id) => ids.includes(id))
  },
)

async function saveSettings() {
  testError.value = ''

  try {
    await emailStore.save({
      enabled: form.enabled,
      provider: form.provider,
      sender_name: form.sender_name.trim(),
      sender_email: form.sender_email.trim() || null,
      reply_to_email: form.reply_to_email.trim() || null,
      application_url: form.application_url.trim() || null,
      max_retries: Number(form.max_retries),
      brevo_api_key: form.brevo_api_key.trim() || null,
      smtp_host: form.smtp_host.trim() || null,
      smtp_port: Number(form.smtp_port),
      smtp_security: form.smtp_security,
      smtp_username: form.smtp_username.trim() || null,
      smtp_password: form.smtp_password || null,
    })

    applySettings()
      showToast({ title: 'Email delivery settings saved', tone: 'success' })
  } catch (cause) {
    const message = cause instanceof Error ? cause.message : 'Unable to save email delivery settings.'
    showToast({ title: 'Unable to save email delivery settings', message, tone: 'danger' })
  }
}

async function sendTest() {
  testError.value = ''

  const recipient = testRecipient.value.trim()
  if (!recipient) {
    testError.value = 'Enter a recipient email address.'
    showToast({ title: 'Recipient email required', tone: 'warning' })
    return
  }

  try {
    const result = await emailStore.sendTest(
      recipient,
      testRecipientName.value.trim() || null,
    )
      showToast({
      title: 'Test email accepted',
      message: `${result.provider.toUpperCase()} · ${result.recipient_email}`,
      tone: 'success',
    })
  } catch (cause) {
    const message = cause instanceof Error ? cause.message : 'Unable to send test email.'
    testError.value = message
    showToast({ title: 'Unable to send test email', message, tone: 'danger' })
  }
}

async function retryDelivery(id: string) {
  try {
    await emailStore.retry(id)
  } catch (cause) {
    showToast({ title: 'Unable to retry delivery', message: cause instanceof Error ? cause.message : undefined, tone: 'danger' })
  }
}

function displayDate(value: string | null | undefined) {
  return formatUserDateTime(value, authStore.user?.preferences)
}

function toggleAllClearableDeliveries() {
  selectedDeliveryIds.value = allClearableSelected.value
    ? []
    : clearableDeliveries.value.map((delivery) => delivery.id)
}

async function clearSelectedDeliveries() {
  const ids = [...selectedDeliveryIds.value]
  if (!ids.length) return

  const confirmed = await confirmDialog({
    title: 'Clear delivery history',
    message: `Clear ${ids.length} selected terminal delivery record${ids.length === 1 ? '' : 's'}? Pending and retrying mail will remain queued.`,
    confirmLabel: 'Clear selected',
    destructive: true,
    tone: 'danger',
  })
  if (!confirmed) return

  deliveryClearError.value = ''
  try {
    const result = await emailStore.clearDeliveries(ids, false)
    selectedDeliveryIds.value = []
      showToast({
      title: 'Delivery history cleared',
      message: `${result.deleted_count} record${result.deleted_count === 1 ? '' : 's'} removed${result.skipped_count ? ` · ${result.skipped_count} left untouched` : ''}.`,
      tone: result.skipped_count ? 'warning' : 'success',
    })
  } catch (cause) {
    const message = cause instanceof Error ? cause.message : 'Unable to clear delivery history.'
    deliveryClearError.value = message
    showToast({ title: 'Unable to clear delivery history', message, tone: 'danger' })
  }
}

async function clearAllDeliveries() {
  if (!clearableDeliveries.value.length) return

  const confirmed = await confirmDialog({
    title: 'Clear all delivery history',
    message: 'Clear all sent/failed email delivery history? Queued, retrying and in-flight mail will remain queued.',
    confirmLabel: 'Clear history',
    destructive: true,
    tone: 'danger',
  })
  if (!confirmed) return

  deliveryClearError.value = ''
  try {
    const result = await emailStore.clearDeliveries([], true)
    selectedDeliveryIds.value = []
      showToast({ title: 'Delivery history cleared', message: `${result.deleted_count} record${result.deleted_count === 1 ? '' : 's'} removed.`, tone: 'success' })
  } catch (cause) {
    const message = cause instanceof Error ? cause.message : 'Unable to clear delivery history.'
    deliveryClearError.value = message
    showToast({ title: 'Unable to clear delivery history', message, tone: 'danger' })
  }
}

onMounted(async () => {
  if (authStore.user?.email) {
    testRecipient.value = authStore.user.email
    testRecipientName.value = authStore.user.display_name
  }

  try {
    await emailStore.load()
    applySettings()
  } catch {
  }
})
</script>

<template>
  <div class="email-settings-stack">
    <p v-if="emailStore.loading">Loading email delivery settings...</p>
    <p v-else-if="emailStore.error && !emailStore.settings" class="login-error">
      {{ emailStore.error }}
    </p>

    <template v-else>
      <section class="panel email-settings-panel">
        <div class="panel-header">
          <div title="Configure the installation-wide mail transport. User profiles decide which matching alerts they personally receive.">
            <h2>Email delivery</h2>
          </div>
        </div>

        <form class="connection-form" @submit.prevent="saveSettings">
          <label class="notification-toggle-row email-master-toggle">
            <span>
              <strong>Enable alert email delivery</strong>
            </span>
            <input v-model="form.enabled" type="checkbox" class="toggle-switch" title="New active alerts are queued only while this is enabled.">
          </label>

          <div class="connection-form-row email-provider-row">
            <label>
              Provider
              <select v-model="form.provider">
                <option value="brevo">Brevo API</option>
                <option value="smtp">Generic SMTP</option>
              </select>
            </label>

            <label>
              Retry failures
              <select v-model.number="form.max_retries">
                <option :value="0">No retry</option>
                <option :value="1">1 retry</option>
                <option :value="2">2 retries</option>
                <option :value="3">3 retries</option>
                <option :value="4">4 retries</option>
                <option :value="5">5 retries</option>
              </select>
            </label>
          </div>

          <div class="connection-form-row email-sender-row">
            <label>
              Sender name
              <input v-model="form.sender_name" maxlength="120" placeholder="DBAChum Alerts">
            </label>

            <label>
              Sender email
              <input v-model="form.sender_email" type="email" placeholder="alerts@example.com">
            </label>
          </div>

          <div class="connection-form-row email-sender-row">
            <label>
              Reply-to email
              <input v-model="form.reply_to_email" type="email" placeholder="Optional">
            </label>

            <label>
              Application URL
              <input v-model="form.application_url" type="url" placeholder="https://dbachum.example.com" title="Used for the “Open DBAChum” link in alert mail.">
            </label>
          </div>

          <section v-if="form.provider === 'brevo'" class="email-provider-card">
            <div>
              <strong>Brevo API</strong>
            </div>

            <label title="DBAChum sends transactional mail through Brevo's HTTPS API. The API key is encrypted at rest and never returned to the browser.">
              API key
              <input
                v-model="form.brevo_api_key"
                type="password"
                autocomplete="new-password"
                :placeholder="emailStore.settings?.has_brevo_api_key ? 'Saved — leave blank to keep' : 'xkeysib-…'"
              >
            </label>
          </section>

          <section v-else class="email-provider-card">
            <div>
              <strong>Generic SMTP</strong>
              <p>
                Use a company relay, Microsoft/Google SMTP, or another SMTP service. External-recipient policy is controlled by that SMTP server.
              </p>
            </div>

            <div class="connection-form-row email-smtp-host-row">
              <label>
                SMTP host
                <input v-model="form.smtp_host" placeholder="smtp.example.com">
              </label>

              <label>
                Port
                <input v-model.number="form.smtp_port" type="number" min="1" max="65535">
              </label>
            </div>

            <div class="connection-form-row email-sender-row">
              <label>
                Security
                <select v-model="form.smtp_security">
                  <option value="starttls">STARTTLS</option>
                  <option value="ssl">SSL/TLS</option>
                  <option value="none">None</option>
                </select>
              </label>

              <label>
                Username
                <input v-model="form.smtp_username" autocomplete="username" placeholder="Optional for trusted relays">
              </label>
            </div>

            <label>
              Password
              <input
                v-model="form.smtp_password"
                type="password"
                autocomplete="new-password"
                :placeholder="emailStore.settings?.has_smtp_password ? 'Saved — leave blank to keep' : 'Optional if relay needs no authentication'"
              >
            </label>
          </section>

          <p v-if="emailStore.error" class="login-error">{{ emailStore.error }}</p>

          <div class="connection-form-actions">
            <button type="submit" class="primary-button" :disabled="emailStore.saving">
              {{ emailStore.saving ? 'Saving...' : 'Save email settings' }}
            </button>
          </div>
        </form>
      </section>

      <section class="panel email-settings-panel">
        <div class="panel-header">
          <div>
            <h2>Send a test email</h2>
          </div>
        </div>

        <form class="connection-form" @submit.prevent="sendTest">
          <div class="connection-form-row email-sender-row">
            <label>
              <span class="field-label">Recipient email <span class="required-mark" aria-hidden="true">*</span></span>
              <input v-model="testRecipient" type="email" required placeholder="dba@example.com">
            </label>

            <label>
              Recipient name
              <input v-model="testRecipientName" placeholder="Optional">
            </label>
          </div>

          <p v-if="testError" class="login-error">{{ testError }}</p>

          <div class="connection-form-actions">
            <button type="submit" class="secondary-button" :disabled="emailStore.testing">
              {{ emailStore.testing ? 'Sending...' : 'Send test email' }}
            </button>
          </div>
        </form>
      </section>

      <section class="panel email-settings-panel">
        <div class="panel-header">
          <div>
            <h2>Delivery status</h2>
          </div>

          <div class="table-bulk-actions">
            <button
              type="button"
              class="secondary-button"
              :disabled="emailStore.clearing || selectedDeliveryIds.length === 0"
              @click="clearSelectedDeliveries"
            >
              Clear selected
            </button>
            <button
              type="button"
              class="secondary-button"
              :disabled="emailStore.clearing || clearableDeliveries.length === 0"
              @click="clearAllDeliveries"
            >
              Clear all history
            </button>
            <button type="button" class="secondary-button" :disabled="emailStore.clearing" @click="emailStore.loadDeliveries()">
              Refresh
            </button>
          </div>
        </div>
        <p v-if="deliveryClearError" class="login-error">{{ deliveryClearError }}</p>

        <div v-if="!emailStore.deliveries.length" class="empty-state">
          No email delivery records yet.
        </div>

        <ScrollableDataTable v-else max-height="34rem">
          <template #header>
              <tr>
                <th class="table-selection-cell">
                  <input
                    type="checkbox"
                    :checked="allClearableSelected"
                    :disabled="clearableDeliveries.length === 0"
                    aria-label="Select all clearable delivery history"
                    @change="toggleAllClearableDeliveries"
                  >
                </th>
                <th>When</th>
                <th>Recipient</th>
                <th>Type</th>
                <th>Provider</th>
                <th>Status</th>
                <th>Subject</th>
                <th>Attempts</th>
                <th>Details</th>
              </tr>
          </template>
              <tr v-for="delivery in emailStore.deliveries" :key="delivery.id">
                <td class="table-selection-cell">
                  <input
                    v-if="delivery.status === 'sent' || delivery.status === 'failed'"
                    v-model="selectedDeliveryIds"
                    type="checkbox"
                    :value="delivery.id"
                    :aria-label="`Select ${delivery.subject}`"
                  >
                  <span v-else title="Pending deliveries cannot be cleared">—</span>
                </td>
                <td>{{ displayDate(delivery.sent_at || delivery.created_at) }}</td>
                <td>
                  <strong>{{ delivery.recipient_name || delivery.recipient_email }}</strong>
                  <small v-if="delivery.recipient_name">{{ delivery.recipient_email }}</small>
                </td>
                <td>{{ delivery.kind }}</td>
                <td>{{ delivery.provider }}</td>
                <td>
                  <span class="status-pill" :class="`email-status-${delivery.status}`">
                    {{ delivery.status }}
                  </span>
                </td>
                <td>
                  {{ delivery.subject }}
                  <small v-if="delivery.source_name">{{ delivery.source_name }}</small>
                </td>
                <td>{{ delivery.attempts }} / {{ delivery.max_attempts }}</td>
                <td>
                  <span v-if="delivery.last_error" class="email-delivery-error">
                    {{ delivery.last_error }}
                  </span>
                  <span v-else-if="delivery.provider_message_id" class="email-message-id">
                    {{ delivery.provider_message_id }}
                  </span>
                  <span v-else>—</span>

                  <button
                    v-if="delivery.status === 'failed' && delivery.kind === 'alert'"
                    type="button"
                    class="secondary-button email-retry-button"
                    @click="retryDelivery(delivery.id)"
                  >
                    Retry
                  </button>
                </td>
              </tr>
        </ScrollableDataTable>
      </section>
    </template>
  </div>
</template>
