<template>
  <div class="ssh-terminal" ref="terminalContainer">
    <div class="connection-bar" :class="connectionState">
      <span class="status-indicator"></span>
      <span class="status-text">{{ statusText }}</span>
      <button
        v-if="connectionState === 'error' || connectionState === 'disconnected'"
        class="reconnect-btn"
        @click="connect"
      >
        ↺ Reconnect
      </button>
    </div>
    <div class="terminal-viewport" ref="terminalViewport"></div>
  </div>
</template>

<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss

import { ref, computed, onMounted, onUnmounted, watch, nextTick } from 'vue'
import { Terminal } from '@xterm/xterm'
import { FitAddon } from '@xterm/addon-fit'
import { WebLinksAddon } from '@xterm/addon-web-links'
import '@xterm/xterm/css/xterm.css'
import { createLogger } from '../utils'
import { usePollingJob } from '../composables/usePollingJob'
import { useWebSocket } from '../composables/useWebSocket'

const logger = createLogger('SshTerminal')

const props = defineProps<{
  hostId: string
  chatSessionId?: string | null
  /** WebSocket base path for SSH connections. Defaults to /api/terminal/ws/ssh/ */
  wsBasePath?: string
}>()

const emit = defineEmits<{
  (e: 'connected'): void
  (e: 'disconnected'): void
  (e: 'error', message: string): void
}>()

const terminalContainer = ref<HTMLDivElement>()
const terminalViewport = ref<HTMLDivElement>()
const connectionState = ref<'disconnected' | 'connecting' | 'connected' | 'error'>('disconnected')
const errorMessage = ref('')

let terminal: Terminal | null = null
let fitAddon: FitAddon | null = null

const wsUrl = ref('')

const buildWsUrl = () => {
  const params = props.chatSessionId ? `?conversation_id=${props.chatSessionId}` : ''
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  const host = window.location.host
  const basePath = props.wsBasePath ?? '/api/terminal/ws/ssh/'
  return `${protocol}//${host}${basePath}${props.hostId}${params}`
}

const { send: wsSend, connect: wsConnect, disconnect: wsDisconnect, isConnected: wsIsConnected } = useWebSocket(wsUrl, {
  autoConnect: false,
  autoReconnect: false,
  parseJSON: false,
  onOpen: () => {
    logger.info('SSH WebSocket connected')
    connectionState.value = 'connected'
    emit('connected')
  },
  onMessage: (data: unknown) => {
    try {
      handleMessage(JSON.parse(data as string))
    } catch (e) {
      logger.error('Failed to parse SSH message:', e)
    }
  },
  onError: () => {
    connectionState.value = 'error'
    errorMessage.value = 'Connection error'
    emit('error', 'Connection error')
  },
  onClose: (event: CloseEvent) => {
    logger.info('SSH WebSocket closed:', { code: event.code, reason: event.reason })
    connectionState.value = 'disconnected'
    emit('disconnected')
  },
})

const statusText = computed(() => {
  switch (connectionState.value) {
    case 'connecting': return 'Connecting to host...'
    case 'connected': return 'Connected'
    case 'error': return `Error: ${errorMessage.value}`
    default: return 'Disconnected'
  }
})

const initTerminal = () => {
  if (!terminalViewport.value || terminal) return

  terminal = new Terminal({
    cursorBlink: true,
    fontSize: 14,
    fontFamily: 'Menlo, Monaco, "Courier New", monospace',
    theme: {
      background: '#1e1e1e',
      foreground: '#d4d4d4',
      cursor: '#aeafad',
      selectionBackground: '#264f78',
      black: '#1e1e1e',
      red: '#f44747',
      green: '#608b4e',
      yellow: '#dcdcaa',
      blue: '#569cd6',
      magenta: '#c586c0',
      cyan: '#4ec9b0',
      white: '#d4d4d4',
      brightBlack: '#808080',
      brightRed: '#f44747',
      brightGreen: '#608b4e',
      brightYellow: '#dcdcaa',
      brightBlue: '#569cd6',
      brightMagenta: '#c586c0',
      brightCyan: '#4ec9b0',
      brightWhite: '#ffffff',
    },
    scrollback: 10000,
    allowProposedApi: true,
  })

  fitAddon = new FitAddon()
  terminal.loadAddon(fitAddon)
  terminal.loadAddon(new WebLinksAddon())
  terminal.open(terminalViewport.value)

  nextTick(() => { fitAddon?.fit() })

  terminal.onData((data: string) => { sendToServer({ type: 'input', text: data }) })
  terminal.onResize(({ cols, rows }: { cols: number; rows: number }) => { sendToServer({ type: 'resize', cols, rows }) })

  logger.info('Terminal initialized')
}

const connect = () => {
  if (wsIsConnected.value) return
  connectionState.value = 'connecting'
  errorMessage.value = ''
  wsUrl.value = buildWsUrl()
  logger.info(`Connecting to SSH WebSocket: ${wsUrl.value}`)
  wsConnect()
}

interface SSHTerminalMessage {
  type: 'input' | 'resize' | 'ping' | 'output' | 'connected' | 'error' | 'terminal_closed' | 'pong'
  content?: string
  text?: string
  cols?: number
  rows?: number
  host?: { name?: string }
}

const sendToServer = (message: SSHTerminalMessage) => { wsSend(message) }

const handleMessage = (message: SSHTerminalMessage) => {
  switch (message.type) {
    case 'output':
      if (terminal && message.content) terminal.write(message.content)
      break
    case 'connected':
      logger.info('SSH session established:', message.host?.name)
      if (terminal && message.content) terminal.write(message.content)
      break
    case 'error':
      logger.error('SSH error:', message.content)
      errorMessage.value = message.content ?? ''
      if (terminal) terminal.write(`\r\n\x1b[31mError: ${message.content}\x1b[0m\r\n`)
      break
    case 'terminal_closed':
      logger.info('SSH session closed:', message.content)
      connectionState.value = 'disconnected'
      if (terminal) terminal.write(`\r\n\x1b[33m${message.content}\x1b[0m\r\n`)
      break
    case 'pong':
      break
    default:
      logger.debug('Unknown message type:', message.type)
  }
}

const disconnect = () => { wsDisconnect() }
const handleResize = () => { if (fitAddon) fitAddon.fit() }

const { start: startHeartbeat, stop: stopHeartbeat } = usePollingJob(
  async (_: string) => { if (wsIsConnected.value) sendToServer({ type: 'ping' }) },
  { intervalMs: 30000, maxAttempts: Number.MAX_SAFE_INTEGER }
)

watch(() => props.hostId, (newId, oldId) => {
  if (newId !== oldId) {
    disconnect()
    nextTick(() => connect())
  }
})

onMounted(() => {
  initTerminal()
  connect()
  startHeartbeat()
  window.addEventListener('resize', handleResize)
})

onUnmounted(() => {
  stopHeartbeat()
  window.removeEventListener('resize', handleResize)
  if (terminal) { terminal.dispose(); terminal = null }
})

defineExpose({ connect, disconnect, sendToServer })
</script>

<style scoped>
.ssh-terminal {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: #1e1e1e;
}

.connection-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 12px;
  font-size: 12px;
  border-bottom: 1px solid #333;
}

.connection-bar.disconnected { background: #2d2d2d; color: #888; }
.connection-bar.connecting { background: #3d3d00; color: #ffc107; }
.connection-bar.connected { background: #1e3d1e; color: #4caf50; }
.connection-bar.error { background: #3d1e1e; color: #f44336; }

.status-indicator {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: currentColor;
}

.connection-bar.connecting .status-indicator {
  animation: pulse 1s ease-in-out infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}

.status-text { flex: 1; }

.reconnect-btn {
  padding: 4px 12px;
  background: rgba(255, 255, 255, 0.1);
  border: 1px solid rgba(255, 255, 255, 0.2);
  border-radius: 4px;
  color: inherit;
  font-size: 12px;
  cursor: pointer;
  transition: background 150ms;
}

.reconnect-btn:hover { background: rgba(255, 255, 255, 0.2); }

.terminal-viewport {
  flex: 1;
  padding: 4px;
  overflow: hidden;
}

.terminal-viewport :deep(.xterm) { height: 100%; }
.terminal-viewport :deep(.xterm-viewport) { overflow-y: auto !important; }
</style>
