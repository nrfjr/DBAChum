import { defineStore } from 'pinia'

import type { Server } from '@/stores/servers'

export type TerminalViewMode = 'minimized' | 'normal' | 'maximized'
export type TerminalConnectionState = 'connecting' | 'connected' | 'disconnected' | 'error'

export interface TerminalSessionUi {
  client_id: string
  backend_session_id: string | null
  server_id: string
  server_name: string
  hostname: string
  ssh_profile_name: string | null
  ssh_username: string | null
  view: TerminalViewMode
  connection_state: TerminalConnectionState
  status_message: string
}

const MAX_TERMINALS = 3

function makeClientId() {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) return crypto.randomUUID()
  return `${Date.now()}-${Math.random().toString(36).slice(2)}`
}

export const useTerminalSessionsStore = defineStore('terminalSessions', {
  state: () => ({
    sessions: [] as TerminalSessionUi[],
  }),

  getters: {
    maxTerminals: () => MAX_TERMINALS,
    activeCount: (state) => state.sessions.length,
  },

  actions: {
    open(server: Server) {
      if (this.sessions.length >= MAX_TERMINALS) {
        throw new Error(`You already have ${MAX_TERMINALS} active terminals. Close one before opening another.`)
      }

      for (const session of this.sessions) session.view = 'minimized'

      const session: TerminalSessionUi = {
        client_id: makeClientId(),
        backend_session_id: null,
        server_id: server.id,
        server_name: server.name,
        hostname: server.ip_address || server.hostname,
        ssh_profile_name: server.ssh_profile_name,
        ssh_username: null,
        view: 'normal',
        connection_state: 'connecting',
        status_message: 'Connecting…',
      }
      this.sessions.push(session)
      return session
    },

    minimize(clientId: string) {
      const session = this.sessions.find((item) => item.client_id === clientId)
      if (session) session.view = 'minimized'
    },

    restore(clientId: string) {
      for (const session of this.sessions) {
        session.view = session.client_id === clientId ? 'normal' : 'minimized'
      }
    },

    toggleMaximize(clientId: string) {
      const selected = this.sessions.find((item) => item.client_id === clientId)
      if (!selected) return
      for (const session of this.sessions) {
        if (session.client_id !== clientId) session.view = 'minimized'
      }
      selected.view = selected.view === 'maximized' ? 'normal' : 'maximized'
    },

    markConnecting(clientId: string) {
      const session = this.sessions.find((item) => item.client_id === clientId)
      if (!session) return
      session.connection_state = 'connecting'
      session.status_message = 'Connecting…'
    },

    markReady(clientId: string, payload: { session_id: string; ssh_username: string }) {
      const session = this.sessions.find((item) => item.client_id === clientId)
      if (!session) return
      session.backend_session_id = payload.session_id
      session.ssh_username = payload.ssh_username
      session.connection_state = 'connected'
      session.status_message = 'Connected'
    },

    markDisconnected(clientId: string, message = 'Disconnected') {
      const session = this.sessions.find((item) => item.client_id === clientId)
      if (!session) return
      session.connection_state = 'disconnected'
      session.status_message = message
    },

    markError(clientId: string, message: string) {
      const session = this.sessions.find((item) => item.client_id === clientId)
      if (!session) return
      session.connection_state = 'error'
      session.status_message = message
    },

    remove(clientId: string) {
      this.sessions = this.sessions.filter((item) => item.client_id !== clientId)
    },

    clear() {
      this.sessions = []
    },
  },
})
