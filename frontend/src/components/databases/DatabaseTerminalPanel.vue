<script setup lang="ts">
import { computed, ref } from 'vue'
import { RouterLink } from 'vue-router'

import { hasPermission } from '@/core/permissions'
import { useAuthStore } from '@/stores/auth'
import type { Server } from '@/stores/servers'
import { useTerminalSessionsStore } from '@/stores/terminalSessions'

const props = defineProps<{
  connectionName: string
  servers: Server[]
}>()

const authStore = useAuthStore()
const terminalStore = useTerminalSessionsStore()
const error = ref<string | null>(null)

const canUseTerminal = computed(() =>
  hasPermission(authStore.user, 'terminal:use'),
)

const canManageConnections = computed(() =>
  hasPermission(authStore.user, 'connections:manage'),
)

function sessionFor(server: Server) {
  return terminalStore.sessions.find(
    (session) => session.server_id === server.id,
  ) ?? null
}

function sshState(server: Server) {
  if (!server.ssh_profile_id) {
    return {
      label: 'SSH profile not assigned',
      ready: false,
      tone: 'muted',
    }
  }

  if (!server.ssh_host_key_fingerprint) {
    return {
      label: 'Host key not trusted',
      ready: false,
      tone: 'warning',
    }
  }

  return {
    label: 'Terminal ready',
    ready: true,
    tone: 'success',
  }
}

function openTerminal(server: Server) {
  error.value = null

  if (!canUseTerminal.value) {
    error.value = 'You do not have permission to open SSH terminals.'
    return
  }

  const state = sshState(server)
  if (!state.ready) {
    error.value = !server.ssh_profile_id
      ? `Assign an SSH access profile to ${server.name} before opening a terminal.`
      : `Test SSH and trust the host key for ${server.name} before opening a terminal.`
    return
  }

  const existing = sessionFor(server)
  if (existing) {
    terminalStore.restore(existing.client_id)
    return
  }

  try {
    terminalStore.open(server)
  } catch (err) {
    error.value = err instanceof Error
      ? err.message
      : 'Unable to open SSH terminal.'
  }
}
</script>

<template>
  <section class="panel database-terminal-panel">
    <div class="panel-header database-terminal-panel__header">
      <div>
        <h2>SSH terminal</h2>
        <p>
          Open an audited shell on a server linked to {{ connectionName }}.
          DBAChum performs SSH authentication on the backend; stored credentials
          are never sent to the browser.
        </p>
      </div>

      <RouterLink
        v-if="canManageConnections"
        class="secondary-button"
        :to="{ name: 'settings-connections', query: { type: 'databases' } }"
      >
        Manage links
      </RouterLink>
    </div>

    <p v-if="error" class="login-error">{{ error }}</p>

    <div v-if="!canUseTerminal" class="database-workspace-empty">
      <strong>Terminal access is not available for your role.</strong>
      <span>Ask an administrator for the terminal:use permission if shell access is required.</span>
    </div>

    <div v-else-if="servers.length === 0" class="database-workspace-empty">
      <strong>No server is linked to this database.</strong>
      <span>
        Link the database connection to a Server / SSH entry before opening a terminal.
      </span>
      <RouterLink
        v-if="canManageConnections"
        class="primary-button"
        :to="{ name: 'settings-connections', query: { type: 'databases' } }"
      >
        Link a server
      </RouterLink>
    </div>

    <div v-else class="database-terminal-grid">
      <article
        v-for="server in servers"
        :key="server.id"
        class="database-terminal-card"
      >
        <div class="database-terminal-card__top">
          <div>
            <RouterLink
              class="database-terminal-card__name"
              :to="{ name: 'server-detail', params: { id: server.id } }"
            >
              {{ server.name }}
            </RouterLink>
            <p>
              {{ server.hostname }}
              <template v-if="server.ip_address"> · {{ server.ip_address }}</template>
            </p>
          </div>

          <span
            class="workspace-status-pill"
            :class="`workspace-status-pill--${sshState(server).tone}`"
          >
            {{ sshState(server).label }}
          </span>
        </div>

        <dl class="database-terminal-meta">
          <div>
            <dt>Operating system</dt>
            <dd>
              {{ server.os_family }}
              <template v-if="server.os_version"> · {{ server.os_version }}</template>
            </dd>
          </div>

          <div>
            <dt>SSH profile</dt>
            <dd>{{ server.ssh_profile_name ?? 'Not assigned' }}</dd>
          </div>

          <div>
            <dt>Session</dt>
            <dd>
              {{ sessionFor(server)?.status_message ?? 'Not open' }}
            </dd>
          </div>
        </dl>

        <div class="database-terminal-card__actions">
          <button
            type="button"
            class="primary-button"
            :disabled="!sshState(server).ready"
            @click="openTerminal(server)"
          >
            {{ sessionFor(server) ? 'Restore terminal' : 'Open terminal' }}
          </button>

          <RouterLink
            class="secondary-button"
            :to="{ name: 'server-detail', params: { id: server.id } }"
          >
            Server workspace
          </RouterLink>
        </div>
      </article>
    </div>

    <div class="database-terminal-notice">
      <strong>Session controls</strong>
      <span>
        Existing DBAChum terminal limits, host-key verification, shortcuts,
        audit history and session cleanup remain in force.
      </span>
    </div>
  </section>
</template>
