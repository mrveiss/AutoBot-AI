<template>
  <div class="xterm-container">
    <!-- Terminal Header -->
    <div class="terminal-header">
      <div class="terminal-title">
        <span class="terminal-icon">⬛</span>
        <span>{{ title }} - {{ sessionId ? sessionId.slice(0, 8) + '...' : 'Loading...' }}</span>
      </div>
      <div class="terminal-controls">
        <div class="connection-status" :class="connectionStatus">
          <div class="status-dot"></div>
          <span>{{ connectionStatusText }}</span>
        </div>
        <button @click="reconnect" :disabled="connecting" class="control-btn">
          🔄 {{ connecting ? 'Connecting...' : 'Reconnect' }}
        </button>
        <button @click="clearTerminal" class="control-btn">
          🗑️ Clear
        </button>
        <button @click="copySelection" class="control-btn">
          📋 Copy
        </button>
      </div>
    </div>

    <!-- XTerm.js Terminal -->
    <div ref="terminalContainer" class="terminal-wrapper"></div>

    <!-- Status Bar -->
    <div class="terminal-status">
      <span>Lines: {{ lineCount }} | Cols: {{ cols }} | Rows: {{ rows }}</span>
      <span v-if="!isConnected" class="warning">⚠️ Not connected</span>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, watch, nextTick, computed } from 'vue'
import { Terminal } from '@xterm/xterm'
import { FitAddon } from '@xterm/addon-fit'
import { WebLinksAddon } from '@xterm/addon-web-links'
// CSS import moved to vite.config.ts to avoid dependency resolution issues
import { useTerminalService } from '@/services/TerminalService.js'

// Props
const props = defineProps({
  sessionId: {
    type: String,
    default: null
  },
  chatContext: {
    type: Boolean,
    default: false
  },
  title: {
    type: String,
    default: 'Terminal'
  }
})

// Terminal service
const {
  sendInput,
  connect: connectToService,
  disconnect,
  createSession,
  isConnected
} = useTerminalService()

// Reactive state
const terminalContainer = ref(null)
const sessionId = ref(props.sessionId)
const connectionStatus = ref('disconnected')
const connecting = ref(false)
const lineCount = ref(0)
const cols = ref(80)
const rows = ref(24)

// XTerm instances
let terminal = null
let fitAddon = null

// Connection status text
const connectionStatusText = computed(() => {
  switch (connectionStatus.value) {
    case 'connected': return 'Connected'
    case 'connecting': return 'Connecting...'
    case 'disconnected': return 'Disconnected'
    case 'error': return 'Error'
    default: return 'Unknown'
  }
})

// Initialize XTerm terminal
const initializeTerminal = async () => {
  if (!terminalContainer.value) return

  try {
    // Create terminal with configuration
    terminal = new Terminal({
    fontFamily: '"Monaco", "Menlo", "Ubuntu Mono", "Consolas", "source-code-pro", monospace',
    fontSize: 14,
    lineHeight: 1.2,
    letterSpacing: 0,
    theme: {
      background: '#000000',
      foreground: '#ffffff',
      cursor: '#ffffff',
      cursorAccent: '#000000',
      selection: '#ffffff40',
      black: '#000000',
      red: '#e06c75',
      green: '#98c379',
      yellow: '#e5c07b',
      blue: '#61afef',
      magenta: '#c678dd',
      cyan: '#56b6c2',
      white: '#ffffff',
      brightBlack: '#5c6370',
      brightRed: '#e06c75',
      brightGreen: '#98c379',
      brightYellow: '#e5c07b',
      brightBlue: '#61afef',
      brightMagenta: '#c678dd',
      brightCyan: '#56b6c2',
      brightWhite: '#ffffff'
    },
    cursorBlink: true,
    cursorStyle: 'block',
    scrollback: 10000,
    tabStopWidth: 8,
    allowTransparency: false
  })

  // Add addons
  fitAddon = new FitAddon()
  const webLinksAddon = new WebLinksAddon()
  
  terminal.loadAddon(fitAddon)
  terminal.loadAddon(webLinksAddon)

  // Open terminal in container
  terminal.open(terminalContainer.value)

  // Fit terminal to container
  fitAddon.fit()
  cols.value = terminal.cols
  rows.value = terminal.rows

  // Handle terminal input
  terminal.onData((data) => {
    if (isConnected(sessionId.value)) {
      sendInput(sessionId.value, data)
    }
  })

  // Handle terminal resize
  terminal.onResize(({ cols: newCols, rows: newRows }) => {
    cols.value = newCols
    rows.value = newRows
    // Send resize to backend if connected
    if (isConnected(sessionId.value)) {
      // Resize PTY on backend (implement in service if needed)
    }
  })

  // Update line count when content changes
  terminal.onRender(() => {
    lineCount.value = terminal.buffer.active.length
  })

  console.log('XTerm terminal initialized')
  
  } catch (error) {
    console.error('Error initializing XTerm terminal:', error)
    // Fallback: show error message
    if (terminalContainer.value) {
      terminalContainer.value.innerHTML = `
        <div style="color: #ff6b6b; padding: 20px; text-align: center;">
          <h3>⚠️ Terminal Initialization Error</h3>
          <p>Failed to load XTerm.js: ${error.message}</p>
          <p>Please check console for details.</p>
        </div>
      `
    }
  }
}

// Initialize session
const initializeSession = async () => {
  console.log('🔄 Initializing session...', { 
    chatContext: props.chatContext, 
    propSessionId: props.sessionId 
  })
  
  try {
    if (props.chatContext && props.sessionId) {
      // Use provided chat session ID
      console.log('📋 Using chat session ID:', props.sessionId)
      sessionId.value = props.sessionId
    } else if (props.sessionId) {
      // Use provided standalone session ID
      console.log('📋 Using provided session ID:', props.sessionId)
      sessionId.value = props.sessionId
    } else {
      // Create new terminal session
      console.log('🆕 Creating new terminal session...')
      const newSessionId = await createSession()
      console.log('✅ New session created:', newSessionId)
      sessionId.value = newSessionId
    }
    console.log('🎯 Session initialized:', sessionId.value)
  } catch (error) {
    console.error('❌ Failed to initialize session:', error)
    // Fallback: generate a unique ID for this terminal instance
    const fallbackId = `terminal-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`
    console.warn('🔄 Using fallback session ID:', fallbackId)
    sessionId.value = fallbackId
  }
}

// Connect to terminal service
const connect = async () => {
  console.log('🔌 Connecting to terminal service...')
  
  if (!sessionId.value) {
    console.log('📝 No session ID, initializing...')
    await initializeSession()
  }

  if (!sessionId.value) {
    console.error('❌ No session ID available after initialization')
    return
  }

  console.log('🚀 Connecting with session ID:', sessionId.value)
  connecting.value = true
  connectionStatus.value = 'connecting'

  try {
    await connectToService(sessionId.value, {
      onOutput: handleOutput,
      onStatusChange: handleStatusChange,
      onError: handleError
    })
    console.log('✅ Connected to terminal service')
  } catch (error) {
    console.error('❌ Failed to connect:', error)
    handleError(error.message)
  }
}

// Handle output from terminal service
const handleOutput = (outputData) => {
  if (!terminal) return

  const content = outputData.content || outputData
  if (content) {
    // XTerm handles ANSI sequences automatically!
    terminal.write(content)
  }
}

// Handle status changes
const handleStatusChange = (status) => {
  connectionStatus.value = status
  if (status === 'connected') {
    connecting.value = false
    if (terminal) {
      terminal.focus()
    }
  }
}

// Handle errors
const handleError = (error) => {
  connectionStatus.value = 'error'
  connecting.value = false
  if (terminal) {
    terminal.write(`\r\n\x1b[31mError: ${error}\x1b[0m\r\n`)
  }
}

// Terminal actions
const reconnect = async () => {
  if (isConnected(sessionId.value)) {
    disconnect(sessionId.value)
  }
  await connect()
}

const clearTerminal = () => {
  if (terminal) {
    terminal.clear()
    terminal.write('\x1b[H\x1b[2J') // Clear screen and move cursor to top
  }
}

const copySelection = () => {
  if (terminal && terminal.hasSelection()) {
    const selection = terminal.getSelection()
    navigator.clipboard.writeText(selection)
  }
}

// Handle window resize
const handleResize = () => {
  if (fitAddon) {
    fitAddon.fit()
  }
}

// Lifecycle
onMounted(async () => {
  await initializeSession()
  await nextTick()
  await initializeTerminal()
  await connect()

  // Handle window resize
  window.addEventListener('resize', handleResize)
})

onUnmounted(() => {
  // Clean up
  if (isConnected(sessionId.value)) {
    disconnect(sessionId.value)
  }
  
  if (terminal) {
    terminal.dispose()
  }
  
  window.removeEventListener('resize', handleResize)
})

// Watch for session changes
watch(() => props.sessionId, async (newSessionId) => {
  if (newSessionId && newSessionId !== sessionId.value) {
    sessionId.value = newSessionId
    await reconnect()
  }
})
</script>

<style scoped>
.xterm-container {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: #000;
  color: #fff;
  font-family: 'Monaco', 'Consolas', 'Ubuntu Mono', monospace;
}

.terminal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0.75rem 1rem;
  background: #2d2d2d;
  border-bottom: 1px solid #444;
}

.terminal-title {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-weight: bold;
  font-size: 0.9rem;
}

.terminal-icon {
  font-size: 1rem;
}

.terminal-controls {
  display: flex;
  align-items: center;
  gap: 1rem;
}

.connection-status {
  display: flex;
  align-items: center;
  gap: 0.25rem;
  font-size: 0.8rem;
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #f87171; /* default red */
}

.connected .status-dot {
  background: #4ade80; /* green */
}

.connecting .status-dot {
  background: #fbbf24; /* yellow */
  animation: pulse 1s infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

.control-btn {
  padding: 0.25rem 0.75rem;
  border: 1px solid #555;
  border-radius: 4px;
  background: #444;
  color: #fff;
  cursor: pointer;
  font-size: 0.8rem;
  transition: all 0.2s;
}

.control-btn:hover:not(:disabled) {
  background: #555;
  border-color: #666;
}

.control-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.terminal-wrapper {
  flex: 1;
  padding: 0.5rem;
  overflow: hidden;
}

/* Override XTerm CSS for better integration */
:deep(.xterm) {
  height: 100% !important;
  width: 100% !important;
}

:deep(.xterm-viewport) {
  background-color: transparent !important;
}

:deep(.xterm-screen) {
  background-color: transparent !important;
}

.terminal-status {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0.5rem 1rem;
  background: #2d2d2d;
  border-top: 1px solid #444;
  font-size: 0.75rem;
  color: #888;
}

.warning {
  color: #f59e0b;
  font-weight: bold;
}
</style>