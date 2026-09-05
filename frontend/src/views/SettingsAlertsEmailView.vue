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

const emailStore = useEmailDeliveryStore()
const authStore = useAuthStore()

const savedMessage = ref('')
const testMessage = ref('')
const testError = ref('')
const testRecipient = ref('')
const testRecipientName = ref('')
const selectedDeliveryIds = ref<string[]>([])
const deliveryClearMessage = ref('')
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
  savedMessage.value = ''
  testMessage.value = ''
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
    savedMessage.value = 'Email delivery settings saved.'
  } catch {
    // Store exposes the server-side validation message.
  }
}

async function sendTest() {
  testMessage.value = ''
  testError.value = ''

  const recipient = testRecipient.value.trim()
  if (!recipient) {
    testError.value = 'Enter a recipient email address.'
    return
  }

  try {
    const result = await emailStore.sendTest(
      recipient,
      testRecipientName.value.trim() || null,
    )
    testMessage.value = `Test email accepted by ${result.provider.toUpperCase()} for ${result.recipient_email}.`
  } catch (cause) {
    testError.value = cause instanceof Error
      ? cause.message
      : 'Unable to send test email.'
  }
}

async function retryDelivery(id: string) {
  try {
    await emailStore.retry(id)
  } catch (cause) {
    window.alert(
      cause instanceof Error
        ? cause.message
        : 'Unable to retry delivery.',
    )
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

  if (!window.confirm(
    `Clear ${ids.length} selected terminal delivery record${ids.length === 1 ? '' : 's'}? Pending/retrying mail is never removed by this action.`,
  )) {
    return
  }

  deliveryClearMessage.value = ''
  deliveryClearError.value = ''
  try {
    const result = await emailStore.clearDeliveries(ids, false)
    selectedDeliveryIds.value = []
    deliveryClearMessage.value = `Cleared ${result.deleted_count} delivery record${result.deleted_count === 1 ? '' : 's'}.${result.skipped_count ? ` ${result.skipped_count} pending/nonexistent record(s) were left untouched.` : ''}`
  } catch (cause) {
    deliveryClearError.value = cause instanceof Error
      ? cause.message
      : 'Unable to clear delivery history.'
  }
}

async function clearAllDeliveries() {
  if (!clearableDeliveries.value.length) return

  if (!window.confirm(
    'Clear all sent/failed email delivery history? Queued, retrying and in-flight mail will remain queued.',
  )) {
    return
  }

  deliveryClearMessage.value = ''
  deliveryClearError.value = ''
  try {
    const result = await emailStore.clearDeliveries([], true)
    selectedDeliveryIds.value = []
    deliveryClearMessage.value = `Cleared ${result.deleted_count} terminal delivery record${result.deleted_count === 1 ? '' : 's'}.`
  } catch (cause) {
    deliveryClearError.value = cause instanceof Error
      ? cause.message
      : 'Unable to clear delivery history.'
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
    // Error is shown from store state.
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
          <div>
            <h2>Email delivery</h2>
            <p>
              Configure the installation-wide mail transport. User profiles decide which matching alerts they personally receive.
            </p>
          </div>
        </div>

        <form class="connection-form" @submit.prevent="saveSettings">
          <label class="notification-toggle-row email-master-toggle">
            <span>
              <strong>Enable alert email delivery</strong>
              <small>New active alerts are queued only while this is enabled.</small>
            </span>
            <input v-model="form.enabled" type="checkbox">
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
              DBAChum URL
              <input v-model="form.application_url" type="url" placeholder="https://dbachum.example.com">
              <span class="optional-label">Used for the “Open DBAChum” link in alert mail.</span>
            </label>
          </div>

          <section v-if="form.provider === 'brevo'" class="email-provider-card">
            <div>
              <strong>Brevo API</strong>
              <p>
                DBAChum sends transactional mail through Brevo's HTTPS API. The API key is encrypted at rest and never returned to the browser.
              </p>
            </div>

            <label>
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

          <p class="email-recipient-note">
            Recipient addresses come from DBAChum user profiles and may be any valid email address. DBAChum does not impose a corporate-domain restriction.
          </p>

          <p v-if="emailStore.error" class="login-error">{{ emailStore.error }}</p>
          <p v-if="savedMessage" class="profile-success">{{ savedMessage }}</p>

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
            <p>
              Test {{ providerLabel }} without changing a user's alert subscription. Email delivery may remain globally disabled while you test the provider.
            </p>
          </div>
        </div>

        <form class="connection-form" @submit.prevent="sendTest">
          <div class="connection-form-row email-sender-row">
            <label>
              Recipient email
              <input v-model="testRecipient" type="email" required placeholder="dba@example.com">
            </label>

            <label>
              Recipient name
              <input v-model="testRecipientName" placeholder="Optional">
            </label>
          </div>

          <p v-if="testError" class="login-error">{{ testError }}</p>
          <p v-if="testMessage" class="profile-success">{{ testMessage }}</p>

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
            <p>
              Latest alert/test deliveries. Failed alert mail can be re-queued after the provider problem is fixed.
            </p>
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

        <p class="profile-muted-note">
          Sent/failed rows are history and may be cleared at any time. Queued, retrying and in-flight messages are protected so cleanup cannot cancel delivery. Dates use your profile timezone.
        </p>
        <p v-if="deliveryClearError" class="login-error">{{ deliveryClearError }}</p>
        <p v-if="deliveryClearMessage" class="profile-success">{{ deliveryClearMessage }}</p>

        <div v-if="!emailStore.deliveries.length" class="empty-state">
          No email delivery records yet.
        </div>

        <div v-else class="utility-table-wrap">
          <table class="utility-table email-delivery-table">
            <thead>
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
            </thead>
            <tbody>
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
            </tbody>
          </table>
        </div>
      </section>
    </template>
  </div>
</template>
