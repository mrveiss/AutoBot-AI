<template>
  <div class="simple-terminal">
    <div class="terminal-header">
      <h3>Terminal - {{ sessionId.slice(0, 8) }}</h3>
      <div class="terminal-status">
        <span :class="'status-' + connectionStatus">{{ connectionStatusText }}</span>
        <button @click="connect" :disabled="isConnected" class="connect-btn">Connect</button>
        <button @click="disconnect" :disabled="!isConnected" class="disconnect-btn">Disconnect</button>
      </div>
    </div>

    <div class="terminal-output" ref="terminalOutput">
      <div v-for="(line, index) in outputLines" :key="index" class="output-line">
        {{ line }}
      </div>
    </div>

    <div class="terminal-input">
      <span class="prompt">$ </span>
      <input
        v-model="currentInput"
        @keyup.enter="sendCommand"
        :disabled="!isConnected"
        ref="terminalInput"
        class="input-field"
        placeholder="Enter command..."
      />
      <button @click="sendCommand" :disabled="!isConnected" class="send-btn">Send</button>
    </div>

    <div class="terminal-footer">
      <small>Status: {{ connectionStatus }} | Lines: {{ outputLines.length }}</small>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, nextTick } from 'vue'
import { API_CONFIG } from '@/config/environment.js'

// Props
const props = defineProps({
  sessionId: {
    type: String,
    default: () => `terminal_${Date.now()}`
  }
})

// Terminal state
const outputLines = ref([])
const currentInput = ref('')
const connectionStatus = ref('disconnected')
const socket = ref(null)
const terminalOutput = ref(null)
const terminalInput = ref(null)

// Computed
const isConnected = computed(() => connectionStatus.value === 'connected')
const connectionStatusText = computed(() => {
  switch (connectionStatus.value) {
    case 'connected': return 'Connected'
    case 'connecting': return 'Connecting...'
    case 'disconnected': return 'Disconnected'
    case 'error': return 'Error'
    default: return 'Unknown'
  }
})

// WebSocket URL
const getWebSocketUrl = () => {
  const baseWsUrl = API_CONFIG.WS_BASE_URL.replace('/ws', '')
  return `${baseWsUrl}/api/terminal/consolidated/ws/${props.sessionId}`
}

// Methods
const connect = () => {
  if (socket.value) {
    socket.value.close()
  }

  connectionStatus.value = 'connecting'
  addOutputLine('🔌 Connecting to terminal...')
  
  const wsUrl = getWebSocketUrl()
  console.log('Connecting to:', wsUrl)
  
  socket.value = new WebSocket(wsUrl)

  socket.value.onopen = () => {
    connectionStatus.value = 'connected'
    addOutputLine('✅ Connected to terminal')
    // Focus input
    nextTick(() => {
      if (terminalInput.value) {
        terminalInput.value.focus()
      }
    })
  }

  socket.value.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data)
      handleMessage(data)
    } catch (error) {
      // Handle plain text messages
      addOutputLine(event.data)
    }
  }

  socket.value.onerror = (error) => {
    connectionStatus.value = 'error'
    addOutputLine(`❌ WebSocket error: ${error.message || 'Connection failed'}`)
    console.error('WebSocket error:', error)
  }

  socket.value.onclose = (event) => {
    connectionStatus.value = 'disconnected'
    addOutputLine(`🔌 Connection closed (Code: ${event.code})`)
    console.log('WebSocket closed:', event)
  }
}

const disconnect = () => {
  if (socket.value) {
    socket.value.close()
    socket.value = null
  }
  connectionStatus.value = 'disconnected'
  addOutputLine('🔌 Disconnected')
}

const sendCommand = () => {
  if (!currentInput.value.trim() || !isConnected.value) return

  const command = currentInput.value.trim()
  
  // Add command to output
  addOutputLine(`$ ${command}`)
  
  // Send to WebSocket
  const message = {
    type: 'input',
    data: command,
    session_id: props.sessionId
  }

  try {
    socket.value.send(JSON.stringify(message))
    currentInput.value = ''
  } catch (error) {
    addOutputLine(`❌ Failed to send command: ${error.message}`)
  }
}

const handleMessage = (data) => {
  switch (data.type) {
    case 'output':
      addOutputLine(data.content || data.data)
      break
    case 'error':
      addOutputLine(`❌ ${data.content || data.message}`)
      break
    case 'status':
      addOutputLine(`ℹ️ ${data.content || data.message}`)
      break
    case 'prompt':
      // Handle prompt changes if needed
      break
    default:
      addOutputLine(JSON.stringify(data))
  }
}

const addOutputLine = (content) => {
  outputLines.value.push(content)
  
  // Limit output lines
  if (outputLines.value.length > 1000) {
    outputLines.value = outputLines.value.slice(-800)
  }

  // Auto-scroll
  nextTick(() => {
    if (terminalOutput.value) {
      terminalOutput.value.scrollTop = terminalOutput.value.scrollHeight
    }
  })
}

const clearOutput = () => {
  outputLines.value = []
}

// Lifecycle
onMounted(() => {
  addOutputLine(`🖥️ Terminal ready (Session: ${props.sessionId.slice(0, 8)})`)
  addOutputLine('💡 Click "Connect" to start terminal session')
})

onUnmounted(() => {
  disconnect()
})
</script>

<style scoped>
.simple-terminal {
  display: flex;
  flex-direction: column;
  height: 100%;
  max-height: 80vh;
  background: #1a1a1a;
  color: #ffffff;
  font-family: 'Monaco', 'Consolas', 'Ubuntu Mono', monospace;
  border-radius: 8px;
  overflow: hidden;
}

.terminal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1rem;
  background: #2d2d2d;
  border-bottom: 1px solid #444;
}

.terminal-header h3 {
  margin: 0;
  font-size: 1rem;
  color: #fff;
}

.terminal-status {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.status-connected {
  color: #4ade80;
  font-weight: bold;
}

.status-connecting {
  color: #fbbf24;
  font-weight: bold;
}

.status-disconnected {
  color: #f87171;
}

.status-error {
  color: #ef4444;
  font-weight: bold;
}

.connect-btn, .disconnect-btn, .send-btn {
  padding: 0.25rem 0.75rem;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 0.875rem;
  font-weight: 500;
  transition: all 0.2s;
}

.connect-btn {
  background: #10b981;
  color: white;
}

.connect-btn:hover:not(:disabled) {
  background: #059669;
}

.disconnect-btn {
  background: #ef4444;
  color: white;
}

.disconnect-btn:hover:not(:disabled) {
  background: #dc2626;
}

.connect-btn:disabled, .disconnect-btn:disabled, .send-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.terminal-output {
  flex: 1;
  padding: 1rem;
  overflow-y: auto;
  font-size: 0.875rem;
  line-height: 1.4;
  background: #000;
}

.output-line {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-all;
}

.terminal-input {
  display: flex;
  align-items: center;
  padding: 0.75rem 1rem;
  background: #1a1a1a;
  border-top: 1px solid #444;
}

.prompt {
  color: #4ade80;
  margin-right: 0.5rem;
  font-weight: bold;
}

.input-field {
  flex: 1;
  background: none;
  border: none;
  color: #ffffff;
  font-family: inherit;
  font-size: inherit;
  outline: none;
  padding: 0.25rem;
}

.send-btn {
  margin-left: 0.5rem;
  background: #3b82f6;
  color: white;
  padding: 0.25rem 0.75rem;
}

.send-btn:hover:not(:disabled) {
  background: #2563eb;
}

.terminal-footer {
  padding: 0.5rem 1rem;
  background: #2d2d2d;
  border-top: 1px solid #444;
  font-size: 0.75rem;
  color: #888;
}

/* Scrollbar */
.terminal-output::-webkit-scrollbar {
  width: 6px;
}

.terminal-output::-webkit-scrollbar-track {
  background: #1a1a1a;
}

.terminal-output::-webkit-scrollbar-thumb {
  background: #444;
  border-radius: 3px;
}

.terminal-output::-webkit-scrollbar-thumb:hover {
  background: #666;
}
</style>