import { defineStore } from 'pinia'

export type TerminalShortcutMode = 'execute' | 'insert'

export interface TerminalShortcut {
  id: string
  name: string
  category: string
  command: string
  mode: TerminalShortcutMode
  server_ids: string[]
  enabled: boolean
  sort_order: number
  scope_label: string
  created_at: string
  updated_at: string
}

export interface TerminalShortcutInput {
  name: string
  category: string
  command: string
  mode: TerminalShortcutMode
  server_ids: string[]
  enabled: boolean
  sort_order: number
}

export interface TerminalSessionAudit {
  session_id: string
  operator_user_id: string
  operator_username: string
  server_id: string
  server_name: string
  target: string
  ssh_username: string
  ssh_profile_id: string
  ssh_profile_name: string
  started_at: string
  ended_at: string | null
  duration_seconds: number | null
  close_reason: string | null
  status: string
  input_bytes: number
  output_bytes: number
  shortcut_actions: Array<{
    shortcut_id: string
    name: string
    mode: TerminalShortcutMode
    used_at: string
  }>
}

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL

async function apiRequest<T>(path: string, options: RequestInit = {}): Promise<T> {
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
    throw new Error(body?.error?.message ?? `Request failed with status ${response.status}`)
  }

  if (response.status === 204) return undefined as T
  return response.json()
}

export const useTerminalShortcutsStore = defineStore('terminalShortcuts', {
  state: () => ({
    shortcuts: [] as TerminalShortcut[],
    serverShortcuts: {} as Record<string, TerminalShortcut[]>,
    audit: [] as TerminalSessionAudit[],
    loading: false,
    saving: false,
    error: null as string | null,
  }),

  actions: {
    async load() {
      this.loading = true
      this.error = null
      try {
        this.shortcuts = await apiRequest<TerminalShortcut[]>('/terminal/shortcuts')
      } catch (error) {
        this.error = error instanceof Error ? error.message : 'Unable to load terminal shortcuts.'
      } finally {
        this.loading = false
      }
    },

    async loadForServer(serverId: string) {
      const shortcuts = await apiRequest<TerminalShortcut[]>(`/terminal/shortcuts/server/${serverId}`)
      this.serverShortcuts[serverId] = shortcuts
      return shortcuts
    },

    async create(data: TerminalShortcutInput) {
      this.saving = true
      try {
        const shortcut = await apiRequest<TerminalShortcut>('/terminal/shortcuts', {
          method: 'POST',
          body: JSON.stringify(data),
        })
        this.shortcuts.push(shortcut)
        this.shortcuts.sort((a, b) =>
          a.category.localeCompare(b.category) || a.sort_order - b.sort_order || a.name.localeCompare(b.name),
        )
        this.serverShortcuts = {}
        return shortcut
      } finally {
        this.saving = false
      }
    },

    async update(id: string, data: TerminalShortcutInput) {
      this.saving = true
      try {
        const shortcut = await apiRequest<TerminalShortcut>(`/terminal/shortcuts/${id}`, {
          method: 'PUT',
          body: JSON.stringify(data),
        })
        const index = this.shortcuts.findIndex((item) => item.id === id)
        if (index !== -1) this.shortcuts[index] = shortcut
        this.shortcuts.sort((a, b) =>
          a.category.localeCompare(b.category) || a.sort_order - b.sort_order || a.name.localeCompare(b.name),
        )
        this.serverShortcuts = {}
        return shortcut
      } finally {
        this.saving = false
      }
    },

    async remove(id: string) {
      await apiRequest<void>(`/terminal/shortcuts/${id}`, { method: 'DELETE' })
      this.shortcuts = this.shortcuts.filter((shortcut) => shortcut.id !== id)
      this.serverShortcuts = {}
    },

    async loadAudit(limit = 50) {
      this.audit = await apiRequest<TerminalSessionAudit[]>(`/terminal/audit?limit=${limit}`)
      return this.audit
    },
  },
})
