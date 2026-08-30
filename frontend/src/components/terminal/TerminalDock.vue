<script setup lang="ts">
import TerminalSessionPanel from '@/components/terminal/TerminalSessionPanel.vue'
import { useTerminalSessionsStore } from '@/stores/terminalSessions'

const terminalStore = useTerminalSessionsStore()
</script>

<template>
  <div class="terminal-dock" aria-live="polite">
    <TerminalSessionPanel
      v-for="(session, index) in terminalStore.sessions"
      :key="session.client_id"
      :session-id="session.client_id"
      :chip-index="index"
    />
  </div>
</template>
