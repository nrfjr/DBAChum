import { defineStore } from 'pinia'

import type { DatabaseEngine } from '@/stores/connections'

export type RecordType =
  | 'database'
  | 'server'
  | 'application'
  | 'credential'
  | 'url'
  | 'other'

export type RecordStatus =
  | 'active'
  | 'standby'
  | 'disabled'
  | 'retired'
  | 'unknown'

export interface RecordCustomField {
  key: string
  value: string
}

export interface DbaRecord {
  id: string
  name: string
  record_type: RecordType
  status: RecordStatus
  engine: DatabaseEngine | null
  hostname: string | null
  ip_address: string | null
  port: number | null
  environment: string | null
  version: string | null
  username: string | null
  application: string | null
  owner: string | null
  url: string | null
  notes: string | null
  tags: string[]
  custom_fields: RecordCustomField[]
  connection_id: string | null
  connection_name: string | null
  server_id: string | null
  server_name: string | null
  has_password: boolean
  created_by: string | null
  updated_by: string | null
  created_at: string
  updated_at: string
}

export interface DbaRecordInput {
  name: string
  record_type: RecordType
  status: RecordStatus
  engine: DatabaseEngine | null
  hostname: string | null
  ip_address: string | null
  port: number | null
  environment: string | null
  version: string | null
  username: string | null
  password?: string
  application: string | null
  owner: string | null
  url: string | null
  notes: string | null
  tags: string[]
  custom_fields: RecordCustomField[]
  connection_id: string | null
  server_id: string | null
}

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL

async function apiRequest<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
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

  if (response.status === 204) {
    return undefined as T
  }

  return response.json()
}

export const useRecordsStore = defineStore('records', {
  state: () => ({
    records: [] as DbaRecord[],
    loading: false,
    saving: false,
    error: null as string | null,
  }),

  getters: {
    byId: (state) => (id: string) =>
      state.records.find((record) => record.id === id),
  },

  actions: {
    async load() {
      this.loading = true
      this.error = null
      try {
        this.records = await apiRequest<DbaRecord[]>('/records')
      } catch (error) {
        this.error = error instanceof Error
          ? error.message
          : 'Unable to load Records.'
      } finally {
        this.loading = false
      }
    },

    async loadOne(id: string) {
      const record = await apiRequest<DbaRecord>(`/records/${id}`)
      const index = this.records.findIndex((item) => item.id === id)
      if (index === -1) this.records.push(record)
      else this.records[index] = record
      return record
    },

    async create(data: DbaRecordInput) {
      this.saving = true
      try {
        const record = await apiRequest<DbaRecord>('/records', {
          method: 'POST',
          body: JSON.stringify(data),
        })
        this.records.push(record)
        this.records.sort((a, b) => a.name.localeCompare(b.name))
        return record
      } finally {
        this.saving = false
      }
    },

    async update(id: string, data: DbaRecordInput) {
      this.saving = true
      try {
        const record = await apiRequest<DbaRecord>(`/records/${id}`, {
          method: 'PUT',
          body: JSON.stringify(data),
        })
        const index = this.records.findIndex((item) => item.id === id)
        if (index !== -1) this.records[index] = record
        this.records.sort((a, b) => a.name.localeCompare(b.name))
        return record
      } finally {
        this.saving = false
      }
    },

    async remove(id: string) {
      await apiRequest<void>(`/records/${id}`, { method: 'DELETE' })
      this.records = this.records.filter((record) => record.id !== id)
    },

    async revealPassword(id: string) {
      const result = await apiRequest<{ password: string }>(
        `/records/${id}/reveal-password`,
        { method: 'POST' },
      )
      return result.password
    },
  },
})
