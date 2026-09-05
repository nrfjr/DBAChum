import { defineStore } from 'pinia'

export type EmailProvider = 'brevo' | 'smtp'
export type SmtpSecurity = 'starttls' | 'ssl' | 'none'
export type EmailDeliveryStatus = 'queued' | 'retry' | 'sending' | 'sent' | 'failed'

export interface EmailSettings {
  enabled: boolean
  provider: EmailProvider
  sender_name: string
  sender_email: string | null
  reply_to_email: string | null
  application_url: string | null
  max_retries: number
  has_brevo_api_key: boolean
  smtp_host: string | null
  smtp_port: number
  smtp_security: SmtpSecurity
  smtp_username: string | null
  has_smtp_password: boolean
  updated_at: string | null
  updated_by: string | null
}

export interface EmailSettingsUpdate {
  enabled: boolean
  provider: EmailProvider
  sender_name: string
  sender_email: string | null
  reply_to_email: string | null
  application_url: string | null
  max_retries: number
  brevo_api_key?: string | null
  smtp_host: string | null
  smtp_port: number
  smtp_security: SmtpSecurity
  smtp_username: string | null
  smtp_password?: string | null
}

export interface EmailDeliveryItem {
  id: string
  kind: string
  status: EmailDeliveryStatus
  provider: EmailProvider
  recipient_email: string
  recipient_name: string | null
  subject: string
  alert_key: string | null
  source_name: string | null
  severity: string | null
  attempts: number
  max_attempts: number
  next_attempt_at: string | null
  created_at: string
  updated_at: string
  sent_at: string | null
  last_error: string | null
  provider_message_id: string | null
}

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
  })

  if (!response.ok) {
    const body = await response.json().catch(() => null)
    throw new Error(
      body?.error?.message
        ?? `Request failed with status ${response.status}`,
    )
  }

  return response.json()
}

export const useEmailDeliveryStore = defineStore('emailDelivery', {
  state: () => ({
    settings: null as EmailSettings | null,
    deliveries: [] as EmailDeliveryItem[],
    loading: false,
    saving: false,
    testing: false,
    error: '' as string,
  }),

  actions: {
    async load() {
      this.loading = true
      this.error = ''
      try {
        const [settings, deliveries] = await Promise.all([
          request<EmailSettings>('/notification-delivery/email'),
          request<EmailDeliveryItem[]>('/notification-delivery/email/deliveries?limit=50'),
        ])
        this.settings = settings
        this.deliveries = deliveries
      } catch (error) {
        this.error = error instanceof Error ? error.message : 'Unable to load email settings.'
        throw error
      } finally {
        this.loading = false
      }
    },

    async save(data: EmailSettingsUpdate) {
      this.saving = true
      this.error = ''
      try {
        this.settings = await request<EmailSettings>(
          '/notification-delivery/email',
          {
            method: 'PUT',
            body: JSON.stringify(data),
          },
        )
        return this.settings
      } catch (error) {
        this.error = error instanceof Error ? error.message : 'Unable to save email settings.'
        throw error
      } finally {
        this.saving = false
      }
    },

    async sendTest(recipientEmail: string, recipientName?: string | null) {
      this.testing = true
      this.error = ''
      try {
        const result = await request<{
          sent: boolean
          provider: EmailProvider
          recipient_email: string
          message_id: string | null
        }>(
          '/notification-delivery/email/test',
          {
            method: 'POST',
            body: JSON.stringify({
              recipient_email: recipientEmail,
              recipient_name: recipientName || null,
            }),
          },
        )
        await this.loadDeliveries()
        return result
      } catch (error) {
        this.error = error instanceof Error ? error.message : 'Unable to send test email.'
        await this.loadDeliveries().catch(() => undefined)
        throw error
      } finally {
        this.testing = false
      }
    },

    async loadDeliveries() {
      this.deliveries = await request<EmailDeliveryItem[]>(
        '/notification-delivery/email/deliveries?limit=50',
      )
    },

    async retry(deliveryId: string) {
      await request<EmailDeliveryItem>(
        `/notification-delivery/email/deliveries/${deliveryId}/retry`,
        { method: 'POST' },
      )
      await this.loadDeliveries()
    },
  },
})
