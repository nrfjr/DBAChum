<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import TerminalSessionPanel from '@/components/terminal/TerminalSessionPanel.vue'
import { hasPermission } from '@/core/permissions'
import { useAuthStore } from '@/stores/auth'
import { useServersStore, type Server } from '@/stores/servers'
import { useTerminalSessionsStore } from '@/stores/terminalSessions'
import { showToast } from '@/ui/feedback'

const authStore = useAuthStore()
const serversStore = useServersStore()
const terminalStore = useTerminalSessionsStore()
const pickerOpen = ref(false)

const canUseTerminal = computed(() =>
  hasPermission(authStore.user, 'terminal:use'),
)

const readyServers = computed(() =>
  serversStore.servers
    .filter((server) =>
      server.enabled
      && Boolean(server.ssh_profile_id)
      && Boolean(server.ssh_host_key_fingerprint)
      && !terminalStore.sessions.some((session) => session.server_id === server.id),
    )
    .sort((a, b) => a.name.localeCompare(b.name)),
)

const canAdd = computed(() =>
  terminalStore.activeCount < terminalStore.maxTerminals,
)

function togglePicker() {
  if (!canAdd.value) return
  pickerOpen.value = !pickerOpen.value
}

function openServer(server: Server) {
  try {
    terminalStore.open(server)
    pickerOpen.value = false
  } catch (cause) {
    showToast({
      title: 'Unable to open SSH terminal',
      message: cause instanceof Error ? cause.message : undefined,
      tone: 'danger',
    })
  }
}

watch(
  canUseTerminal,
  (allowed) => {
    if (allowed && serversStore.servers.length === 0) {
      void serversStore.load()
    }
  },
  { immediate: true },
)

watch(canAdd, (allowed) => {
  if (!allowed) pickerOpen.value = false
})
</script>

<template>
  <div v-if="canUseTerminal" class="terminal-dock" aria-live="polite">
    <div v-if="pickerOpen" class="terminal-dock__picker">
      <button
        v-for="server in readyServers"
        :key="server.id"
        type="button"
        class="terminal-dock__server"
        @click="openServer(server)"
      >
        <strong>{{ server.name }}</strong>
        <small>{{ server.ip_address || server.hostname }}</small>
      </button>
      <div v-if="readyServers.length === 0" class="terminal-dock__empty">
        No additional terminal-ready servers.
      </div>
    </div>

    <button
      v-if="terminalStore.activeCount === 0"
      type="button"
      class="terminal-dock__launcher"
      @click="togglePicker"
    >
      <span>Terminal</span>
      <span>{{ pickerOpen ? '⌃' : '⌄' }}</span>
    </button>

    <div v-else class="terminal-dock__workspace">
      <TerminalSessionPanel
        v-for="(session, index) in terminalStore.sessions"
        :key="session.client_id"
        :session-id="session.client_id"
        :chip-index="index"
      />

      <button
        v-if="canAdd"
        type="button"
        class="terminal-dock__add"
        title="Open another terminal"
        @click="togglePicker"
      >
        +
      </button>
    </div>
  </div>
</template>
