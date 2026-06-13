<template>
  <div class="ssh-terminal" ref="terminalContainer">
    <!-- Connection status bar -->
    <div class="connection-bar" :class="connectionState">
      <span class="status-indicator"></span>
      <span class="status-text">{{ statusText }}</span>
      <button
        v-if="connectionState === 'error' || connectionState === 'disconnected'"
        class="reconnect-btn"
        @click="connect"
      >
        <Icon name="sync-alt" /> Reconnect
      </button>
    </div>

    <!-- XTerm terminal -->
    <div class="terminal-viewport" ref="terminalViewport"></div>
  </div>
</template>

<script setup lang="ts">
import Icon from '@/components/ui/Icon.vue'
import { ref, computed, onMounted, onUnmounted, watch, nextTick } from 'vue'
import { Terminal } from '@xterm/xterm'
import { FitAddon } from '@xterm/addon-fit'
import { WebLinksAddon } from '@xterm/addon-web-links'
import '@xterm/xterm/css/xterm.css'
import { createLogger } from '@/utils/debugUtils'
import { usePollingJob } from '@/composables/usePollingJob'
import { useWebSocket } from '@/composables/useWebSocket'

const logger = createLogger('SSHTerminal')

// Props
const props = defineProps<{
  hostId: string
  chatSessionId?: string | null
}>()

// Emits
const emit = defineEmits<{
  (e: 'connected'): void
  (e: 'disconnected'): void
  (e: 'error', message: string): void
}>()

// Refs
const terminalContainer = ref<HTMLDivElement>()
const terminalViewport = ref<HTMLDivElement>()

// State
const connectionState = ref<'disconnected' | 'connecting' | 'connected' | 'error'>('disconnected')
const errorMessage = ref('')

// Terminal instance
let terminal: Terminal | null = null
let fitAddon: FitAddon | null = null

// Reactive WebSocket URL — updated when hostId changes
const wsUrl = ref('')

const buildWsUrl = () => {
  const params = props.chatSessionId
    ? `?conversation_id=${props.chatSessionId}`
    : ''
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  const host = window.location.host
  return `${protocol}//${host}/api/terminal/ws/ssh/${props.hostId}${params}`
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
    if (typeof data !== 'string') return
    try {
      handleMessage(JSON.parse(data))
    } catch (e) {
      logger.error('Failed to parse SSH message:', e)
    }
  },
  onError: () => {
    connectionState.value = 'error'
    errorMessage.value = 'Connection error'
    emit('error', 'Connection error')
  },
  onClose: (event) => {
    logger.info('SSH WebSocket closed:', { code: event.code, reason: event.reason })
    connectionState.value = 'disconnected'
    emit('disconnected')
  },
})

// Computed
const statusText = computed(() => {
  switch (connectionState.value) {
    case 'connecting':
      return 'Connecting to host...'
    case 'connected':
      return 'Connected'
    case 'error':
      return `Error: ${errorMessage.value}`
    default:
      return 'Disconnected'
  }
})

// Initialize terminal
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

  // Add addons
  fitAddon = new FitAddon()
  terminal.loadAddon(fitAddon)
  terminal.loadAddon(new WebLinksAddon())

  // Render terminal
  terminal.open(terminalViewport.value)

  // Fit to container
  nextTick(() => {
    fitAddon?.fit()
  })

  // Handle user input
  terminal.onData((data) => {
    sendToServer({ type: 'input', text: data })
  })

  // Handle resize
  terminal.onResize(({ cols, rows }) => {
    sendToServer({ type: 'resize', cols, rows })
  })

  logger.info('Terminal initialized')
}

// Connect to SSH WebSocket
const connect = () => {
  if (wsIsConnected.value) {
    logger.debug('Already connected')
    return
  }

  connectionState.value = 'connecting'
  errorMessage.value = ''

  const url = buildWsUrl()
  logger.info(`Connecting to SSH WebSocket: ${url}`)
  wsUrl.value = url
  wsConnect()
}

/** WebSocket message types for SSH terminal communication. */
interface SSHTerminalMessage {
  type: 'input' | 'resize' | 'ping' | 'output' | 'connected' | 'error' | 'terminal_closed' | 'pong';
  content?: string;
  text?: string;
  cols?: number;
  rows?: number;
  host?: { name?: string };
}

// Send message to server
const sendToServer = (message: SSHTerminalMessage) => {
  wsSend(message)
}

// Handle incoming messages
const handleMessage = (message: SSHTerminalMessage) => {
  switch (message.type) {
    case 'output':
      if (terminal && message.content) {
        terminal.write(message.content)
      }
      break

    case 'connected':
      logger.info('SSH session established:', message.host?.name)
      if (terminal && message.content) {
        terminal.write(message.content)
      }
      break

    case 'error':
      logger.error('SSH error:', message.content)
      errorMessage.value = message.content ?? ''
      if (terminal) {
        terminal.write(`\r\n\x1b[31mError: ${message.content}\x1b[0m\r\n`)
      }
      break

    case 'terminal_closed':
      logger.info('SSH session closed:', message.content)
      connectionState.value = 'disconnected'
      if (terminal) {
        terminal.write(`\r\n\x1b[33m${message.content}\x1b[0m\r\n`)
      }
      break

    case 'pong':
      // Heartbeat response
      break

    default:
      logger.debug('Unknown message type:', message.type)
  }
}

// Disconnect
const disconnect = () => {
  wsDisconnect()
}

// Resize handler
const handleResize = () => {
  if (fitAddon) {
    fitAddon.fit()
  }
}

// Heartbeat
const { start: startHeartbeat, stop: stopHeartbeat } = usePollingJob(
  async (_: string) => {
    if (wsIsConnected.value) sendToServer({ type: 'ping' })
  },
  { intervalMs: 30000, maxAttempts: Number.MAX_SAFE_INTEGER }
)

// Watch for host changes
watch(() => props.hostId, (newHostId, oldHostId) => {
  if (newHostId !== oldHostId) {
    disconnect()
    nextTick(() => {
      connect()
    })
  }
})

// Lifecycle
onMounted(() => {
  initTerminal()
  connect()
  startHeartbeat('')
  window.addEventListener('resize', handleResize)
})

onUnmounted(() => {
  stopHeartbeat()
  // useWebSocket handles WebSocket cleanup via its own onUnmounted
  window.removeEventListener('resize', handleResize)
  if (terminal) {
    terminal.dispose()
    terminal = null
  }
})

// Expose methods
defineExpose({
  connect,
  disconnect,
  sendToServer,
})
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
  gap: var(--spacing-2);
  padding: var(--spacing-1-5) var(--spacing-3);
  font-size: var(--text-xs);
  border-bottom: 1px solid #333;
}

.connection-bar.disconnected {
  background: #2d2d2d;
  color: #888;
}

.connection-bar.connecting {
  background: #3d3d00;
  color: #ffc107;
}

.connection-bar.connected {
  background: #1e3d1e;
  color: #4caf50;
}

.connection-bar.error {
  background: #3d1e1e;
  color: #f44336;
}

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

.status-text {
  flex: 1;
}

.reconnect-btn {
  padding: var(--spacing-1) var(--spacing-3);
  background: rgba(255, 255, 255, 0.1);
  border: 1px solid rgba(255, 255, 255, 0.2);
  border-radius: var(--radius-default);
  color: inherit;
  font-size: var(--text-xs);
  cursor: pointer;
  transition: all var(--duration-150);
}

.reconnect-btn:hover {
  background: rgba(255, 255, 255, 0.2);
}

.terminal-viewport {
  flex: 1;
  padding: var(--spacing-1);
  overflow: hidden;
}

/* XTerm container styling */
.terminal-viewport :deep(.xterm) {
  height: 100%;
}

.terminal-viewport :deep(.xterm-viewport) {
  overflow-y: auto !important;
}
</style>
