<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { Terminal } from '@xterm/xterm'
import { FitAddon } from '@xterm/addon-fit'
import '@xterm/xterm/css/xterm.css'

import { useTerminalSessionsStore } from '@/stores/terminalSessions'
import { useTerminalShortcutsStore, type TerminalShortcut } from '@/stores/terminalShortcuts'

const props = defineProps<{
  sessionId: string
  chipIndex: number
}>()

const sessionsStore = useTerminalSessionsStore()
const shortcutsStore = useTerminalShortcutsStore()

const terminalHost = ref<HTMLElement | null>(null)
const shortcutMenuOpen = ref(false)
const dragLeft = ref<number | null>(null)
const dragTop = ref<number | null>(null)

let terminal: Terminal | null = null
let fitAddon: FitAddon | null = null
let socket: WebSocket | null = null
let resizeObserver: ResizeObserver | null = null
let inputDisposable: { dispose: () => void } | null = null
let reconnectGeneration = 0
let pendingOutput = ''
let pendingOutputTruncated = false

const MAX_PENDING_OUTPUT = 2_000_000

const session = computed(() =>
  sessionsStore.sessions.find((item) => item.client_id === props.sessionId) ?? null,
)

const minimized = computed(() => session.value?.view === 'minimized')
const maximized = computed(() => session.value?.view === 'maximized')
const shortcuts = computed(() =>
  session.value ? (shortcutsStore.serverShortcuts[session.value.server_id] ?? []) : [],
)

const shortcutGroups = computed(() => {
  const groups = new Map<string, TerminalShortcut[]>()
  for (const shortcut of shortcuts.value) {
    const category = shortcut.category || 'General'
    if (!groups.has(category)) groups.set(category, [])
    groups.get(category)!.push(shortcut)
  }
  return [...groups.entries()]
})

const panelStyle = computed(() => {
  if (maximized.value || dragLeft.value == null || dragTop.value == null) return undefined
  return {
    left: `${dragLeft.value}px`,
    top: `${dragTop.value}px`,
    right: 'auto',
    bottom: 'auto',
  }
})

const chipStyle = computed(() => ({
  right: `${16 + props.chipIndex * 222}px`,
}))

function websocketUrl(serverId: string, cols: number, rows: number) {
  const configured = String(import.meta.env.VITE_API_BASE_URL || '/api/v1')
  const url = new URL(configured, window.location.origin)
  url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:'
  url.pathname = `${url.pathname.replace(/\/$/, '')}/terminal/ws/${encodeURIComponent(serverId)}`
  url.search = `?cols=${cols}&rows=${rows}`
  return url.toString()
}

function send(payload: Record<string, unknown>) {
  if (socket?.readyState === WebSocket.OPEN) {
    socket.send(JSON.stringify(payload))
  }
}

function terminalSize() {
  return {
    cols: terminal?.cols || 100,
    rows: terminal?.rows || 30,
  }
}

function writeOutput(data: string) {
  if (!terminal) return
  if (minimized.value) {
    pendingOutput += data
    if (pendingOutput.length > MAX_PENDING_OUTPUT) {
      pendingOutput = pendingOutput.slice(-MAX_PENDING_OUTPUT)
      pendingOutputTruncated = true
    }
    return
  }
  terminal.write(data)
}

function flushPendingOutput() {
  if (!terminal || !pendingOutput) return
  if (pendingOutputTruncated) {
    terminal.writeln('\r\n\x1b[33m[DBAChum: older minimized terminal output was trimmed]\x1b[0m')
  }
  terminal.write(pendingOutput)
  pendingOutput = ''
  pendingOutputTruncated = false
}

async function connect() {
  const current = session.value
  if (!current || !terminal) return

  reconnectGeneration += 1
  const generation = reconnectGeneration

  try {
    socket?.close()
  } catch {
    // no-op
  }

  sessionsStore.markConnecting(current.client_id)
  terminal.writeln('\r\n\x1b[90m[DBAChum: opening SSH session…]\x1b[0m')

  const size = terminalSize()
  const ws = new WebSocket(websocketUrl(current.server_id, size.cols, size.rows))
  socket = ws

  ws.onmessage = (event) => {
    if (generation !== reconnectGeneration) return
    let payload: Record<string, any>
    try {
      payload = JSON.parse(String(event.data))
    } catch {
      return
    }

    if (payload.type === 'ready') {
      sessionsStore.markReady(current.client_id, {
        session_id: String(payload.session_id),
        ssh_username: String(payload.ssh_username),
      })
      writeOutput(`\r\n\x1b[90m[DBAChum: connected to ${payload.target}]\x1b[0m\r\n`)
      nextTick(() => {
        fitAddon?.fit()
        send({ type: 'resize', ...terminalSize() })
        terminal?.focus()
      })
      return
    }

    if (payload.type === 'output') {
      writeOutput(String(payload.data ?? ''))
      return
    }

    if (payload.type === 'error') {
      const message = String(payload.message ?? 'SSH terminal session failed.')
      sessionsStore.markError(current.client_id, message)
      writeOutput(`\r\n\x1b[31m[DBAChum: ${message}]\x1b[0m\r\n`)
      return
    }
  }

  ws.onerror = () => {
    if (generation !== reconnectGeneration) return
    if (session.value?.connection_state === 'connecting') {
      sessionsStore.markError(current.client_id, 'Unable to establish the terminal WebSocket.')
    }
  }

  ws.onclose = () => {
    if (generation !== reconnectGeneration) return
    if (session.value?.connection_state !== 'error') {
      sessionsStore.markDisconnected(current.client_id, 'Disconnected')
    }
  }
}

async function reconnect() {
  shortcutMenuOpen.value = false
  if (socket?.readyState === WebSocket.OPEN) {
    try {
      socket.send(JSON.stringify({ type: 'close' }))
    } catch {
      // no-op
    }
  }
  try {
    socket?.close()
  } catch {
    // no-op
  }
  await new Promise((resolve) => window.setTimeout(resolve, 250))
  await connect()
}

function runShortcut(shortcut: TerminalShortcut) {
  if (session.value?.connection_state !== 'connected') return
  send({ type: 'shortcut', shortcut_id: shortcut.id })
  shortcutMenuOpen.value = false
  terminal?.focus()
}

function clearTerminal() {
  terminal?.clear()
  terminal?.focus()
}

function minimizeTerminal() {
  shortcutMenuOpen.value = false
  sessionsStore.minimize(props.sessionId)
}

function restoreTerminal() {
  sessionsStore.restore(props.sessionId)
}

function toggleMaximize() {
  shortcutMenuOpen.value = false
  sessionsStore.toggleMaximize(props.sessionId)
  dragLeft.value = null
  dragTop.value = null
}

function closeTerminal() {
  reconnectGeneration += 1
  if (socket?.readyState === WebSocket.OPEN) {
    try {
      socket.send(JSON.stringify({ type: 'close' }))
    } catch {
      // no-op
    }
  }
  window.setTimeout(() => {
    try {
      socket?.close()
    } catch {
      // no-op
    }
    sessionsStore.remove(props.sessionId)
  }, 120)
}

function fitTerminal() {
  if (minimized.value) return
  nextTick(() => {
    try {
      fitAddon?.fit()
      send({ type: 'resize', ...terminalSize() })
    } catch {
      // hidden/detached terminal can briefly report zero dimensions while layout changes
    }
  })
}

function startDrag(event: PointerEvent) {
  if (maximized.value || minimized.value) return
  const target = event.target as HTMLElement
  if (target.closest('button, .terminal-shortcut-menu')) return

  const panel = target.closest('.terminal-window') as HTMLElement | null
  if (!panel) return
  const rect = panel.getBoundingClientRect()
  const offsetX = event.clientX - rect.left
  const offsetY = event.clientY - rect.top

  const onMove = (moveEvent: PointerEvent) => {
    const maxLeft = Math.max(window.innerWidth - rect.width, 0)
    const maxTop = Math.max(window.innerHeight - rect.height, 0)
    dragLeft.value = Math.min(Math.max(moveEvent.clientX - offsetX, 0), maxLeft)
    dragTop.value = Math.min(Math.max(moveEvent.clientY - offsetY, 0), maxTop)
  }
  const onUp = () => {
    window.removeEventListener('pointermove', onMove)
    window.removeEventListener('pointerup', onUp)
  }
  window.addEventListener('pointermove', onMove)
  window.addEventListener('pointerup', onUp)
}

watch(
  () => session.value?.view,
  async (view, previous) => {
    if (view && view !== 'minimized' && previous === 'minimized') {
      await nextTick()
      flushPendingOutput()
      fitTerminal()
      terminal?.focus()
    } else if (view && view !== 'minimized') {
      fitTerminal()
    }
  },
)

onMounted(async () => {
  terminal = new Terminal({
    cursorBlink: true,
    convertEol: false,
    scrollback: 5000,
    fontSize: 13,
    fontFamily: 'Consolas, "Cascadia Mono", "Courier New", monospace',
    theme: {
      background: '#0b0f14',
      foreground: '#d7e0ea',
      cursor: '#d7e0ea',
      selectionBackground: '#36546f88',
    },
  })
  fitAddon = new FitAddon()
  terminal.loadAddon(fitAddon)

  if (terminalHost.value) terminal.open(terminalHost.value)
  fitAddon.fit()

  inputDisposable = terminal.onData((data) => {
    if (session.value?.connection_state === 'connected') {
      send({ type: 'input', data })
    }
  })

  resizeObserver = new ResizeObserver(() => fitTerminal())
  if (terminalHost.value) resizeObserver.observe(terminalHost.value)

  if (session.value) {
    shortcutsStore.loadForServer(session.value.server_id).catch(() => undefined)
  }
  await connect()
})

onBeforeUnmount(() => {
  reconnectGeneration += 1
  try {
    if (socket?.readyState === WebSocket.OPEN) socket.send(JSON.stringify({ type: 'close' }))
  } catch {
    // no-op
  }
  try {
    socket?.close()
  } catch {
    // no-op
  }
  inputDisposable?.dispose()
  resizeObserver?.disconnect()
  terminal?.dispose()
})
</script>

<template>
  <div v-if="session" class="terminal-session-root">
    <button
      v-show="minimized"
      type="button"
      class="terminal-chat-chip"
      :style="chipStyle"
      :data-state="session.connection_state"
      @click="restoreTerminal"
    >
      <span class="terminal-status-dot" />
      <span class="terminal-chat-chip__label">{{ session.server_name }}</span>
      <small>{{ session.ssh_username ?? session.ssh_profile_name ?? 'SSH' }}</small>
      <span class="terminal-chat-chip__close" title="Close terminal" @click.stop="closeTerminal">×</span>
    </button>

    <section
      v-show="!minimized"
      class="terminal-window"
      :class="{ 'terminal-window--maximized': maximized }"
      :style="panelStyle"
    >
      <header class="terminal-window__header" @pointerdown="startDrag">
        <div class="terminal-window__identity">
          <span class="terminal-status-dot" :data-state="session.connection_state" />
          <div>
            <strong>{{ session.server_name }}</strong>
            <small>{{ session.ssh_username ?? session.ssh_profile_name ?? 'SSH' }} · {{ session.status_message }}</small>
          </div>
        </div>

        <div class="terminal-window__controls">
          <button type="button" title="Minimize" @click="minimizeTerminal">—</button>
          <button type="button" :title="maximized ? 'Restore size' : 'Maximize'" @click="toggleMaximize">
            {{ maximized ? '❐' : '□' }}
          </button>
          <button type="button" title="Close terminal" @click="closeTerminal">×</button>
        </div>
      </header>

      <div class="terminal-window__toolbar">
        <div class="terminal-shortcut-menu">
          <button type="button" class="terminal-tool-button" @click="shortcutMenuOpen = !shortcutMenuOpen">
            Shortcuts ▾
          </button>
          <div v-if="shortcutMenuOpen" class="terminal-shortcut-popover">
            <template v-if="shortcutGroups.length">
              <div v-for="group in shortcutGroups" :key="group[0]" class="terminal-shortcut-group">
                <strong>{{ group[0] }}</strong>
                <button
                  v-for="shortcut in group[1]"
                  :key="shortcut.id"
                  type="button"
                  :title="shortcut.command"
                  @click="runShortcut(shortcut)"
                >
                  <span>{{ shortcut.name }}</span>
                  <small>{{ shortcut.mode === 'insert' ? 'Insert' : 'Run' }}</small>
                </button>
              </div>
            </template>
            <p v-else>No shortcuts assigned to this server.</p>
          </div>
        </div>
        <button type="button" class="terminal-tool-button" @click="clearTerminal">Clear</button>
        <button type="button" class="terminal-tool-button" @click="reconnect">Reconnect</button>
        <span class="terminal-window__session-count">Terminal {{ chipIndex + 1 }} / {{ sessionsStore.maxTerminals }}</span>
      </div>

      <div ref="terminalHost" class="terminal-window__screen" />
    </section>
  </div>
</template>
