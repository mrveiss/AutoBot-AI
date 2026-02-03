<template>
  <div class="terminal-container">
    <!-- Terminal Header (matching browser/desktop style) -->
    <div class="terminal-header bg-gray-100 border-b border-gray-300 p-2 flex items-center justify-between">
      <div class="flex items-center space-x-3">
        <div class="flex space-x-1">
          <div class="w-3 h-3 bg-red-500 rounded-full"></div>
          <div class="w-3 h-3 bg-yellow-500 rounded-full"></div>
          <div class="w-3 h-3 bg-green-500 rounded-full"></div>
        </div>
        <div class="flex items-center space-x-2 text-sm">
          <i class="fas fa-terminal text-green-600"></i>
          <span class="font-medium">{{ props.chatSessionId ? 'Chat Terminal' : 'System Terminal' }}</span>
          <span class="text-xs text-gray-500">{{ props.chatSessionId ? 'Chat Session' : 'Independent Tool' }}</span>
        </div>
      </div>

      <div class="flex items-center space-x-2">
        <!-- Terminal Controls -->
        <div class="flex items-center space-x-1">
          <button @click="toggleConnection" :class="connectionButtonClass" :disabled="isConnecting" class="terminal-btn" :title="connectionButtonText">
            <i :class="connectionIconClass"></i>
          </button>

          <button @click="clearTerminal" class="terminal-btn" title="Clear Terminal">
            <i class="fas fa-trash"></i>
          </button>

          <button @click="copyTerminalOutput" class="terminal-btn" title="Copy Output">
            <i class="fas fa-copy"></i>
          </button>
        </div>
      </div>
    </div>

    <!-- Terminal Body (contained design) -->
    <div class="terminal-body">
      <div class="terminal-status" v-if="statusMessage">
        <i :class="statusIconClass"></i>
        {{ statusMessage }}
      </div>

      <div
        ref="terminalElement"
        class="terminal-output"
        :class="{ 'terminal-connected': isConnected }"
      >
        <div v-for="(line, index) in terminalLines" :key="index" class="terminal-line">
          <span class="line-prefix">{{ line.prefix }}</span>
          <span :class="line.type">{{ line.content }}</span>
        </div>
        <div v-if="isConnected" class="terminal-prompt">
          <span class="prompt">{{ currentPrompt }}</span>
          <input
            ref="commandInput"
            v-model="currentCommand"
            @keydown="handleKeydown"
            @keyup="handleKeyup"
            class="command-input"
            :disabled="!isConnected"
            placeholder="Enter command..."
          />
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, nextTick } from 'vue'
import appConfig from '@/config/AppConfig.js'
import { useWebSocket } from '@/composables/useWebSocket'
import { useSessionActivityLogger } from '@/composables/useSessionActivityLogger'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('Terminal')

// Issue #608: Activity logger for session tracking
const { logTerminalActivity } = useSessionActivityLogger()

// Props
interface Props {
  sessionType?: 'simple' | 'secure' | 'main'
  autoConnect?: boolean
  chatSessionId?: string | null
}

const props = withDefaults(defineProps<Props>(), {
  sessionType: 'simple',
  autoConnect: true,
  chatSessionId: null
})

// State
// CRITICAL: Session ID will be retrieved from backend (for chat) or generated (for system terminal)
const sessionId = ref<string | null>(null)
const sessionInitialized = ref(false)
const statusMessage = ref('')
const wsUrl = ref('')
const terminalLines = ref<Array<{prefix: string, content: string, type: string}>>([])
const currentCommand = ref('')
const currentPrompt = ref('$ ')
const commandHistory = ref<string[]>([])
const historyIndex = ref(-1)

// Refs
const terminalElement = ref<HTMLElement>()
const commandInput = ref<HTMLInputElement>()

// WebSocket composable for terminal connection
const { isConnected, isConnecting, send: wsSend, connect: wsConnect, disconnect: wsDisconnect } = useWebSocket(
  wsUrl,
  {
    autoConnect: false,
    autoReconnect: false, // Terminal handles reconnection explicitly via user action
    parseJSON: true,
    onOpen: () => {
      statusMessage.value = 'Connected to terminal'
      addTerminalLine('system', 'Terminal connected successfully', 'success')

      // Focus input
      nextTick(() => {
        commandInput.value?.focus()
      })

      setTimeout(() => {
        statusMessage.value = ''
      }, 3000)
    },
    onMessage: (data) => {
      try {
        handleTerminalMessage(data)
      } catch (error) {
        // Handle plain text messages
        addTerminalLine('', data, 'output')
      }
    },
    onError: (error) => {
      logger.error('WebSocket error:', error)
      statusMessage.value = 'Connection error'
      addTerminalLine('system', 'Connection error occurred', 'error')
    },
    onClose: (event) => {
      if (event.code !== 1000) {
        statusMessage.value = 'Connection lost'
        addTerminalLine('system', `Connection closed (${event.code})`, 'error')
      } else {
        statusMessage.value = 'Disconnected'
        addTerminalLine('system', 'Terminal disconnected', 'info')
      }
    }
  }
)

// Computed
const connectionButtonClass = computed(() => ({
  'connect-btn': !isConnected.value,
  'disconnect-btn': isConnected.value,
  'connecting': isConnecting.value
}))

const connectionIconClass = computed(() => {
  if (isConnecting.value) return 'fas fa-spinner fa-spin'
  return isConnected.value ? 'fas fa-plug' : 'fas fa-power-off'
})

const connectionButtonText = computed(() => {
  if (isConnecting.value) return 'Connecting...'
  return isConnected.value ? 'Disconnect' : 'Connect'
})

const statusIconClass = computed(() => {
  if (isConnecting.value) return 'fas fa-spinner fa-spin text-blue-500'
  if (isConnected.value) return 'fas fa-check-circle text-green-500'
  return 'fas fa-exclamation-circle text-red-500'
})

// Methods
/**
 * Initialize terminal session ID - check for existing or create new
 * CRITICAL: This ensures frontend and backend use the same session
 */
const initializeSession = async (): Promise<string> => {
  if (sessionInitialized.value && sessionId.value) {
    return sessionId.value
  }

  try {
    if (props.chatSessionId) {
      // Chat terminal - check if session already exists

      const sessionsUrl = await appConfig.getApiUrl(
        `/api/agent-terminal/sessions?conversation_id=${props.chatSessionId}`
      )
      const response = await fetch(sessionsUrl)
      if (!response.ok) {
        throw new Error(`Failed to fetch sessions: ${response.status} ${response.statusText}`)
      }
      const data = await response.json()

      if (data.sessions && data.sessions.length > 0) {
        // Use existing session
        const existingSession = data.sessions[0]
        sessionId.value = existingSession.session_id
        addTerminalLine('system', `Connected to existing terminal session ${sessionId.value?.slice(-8) || 'unknown'}`, 'info')
      } else {
        // Create new session via AgentTerminalService

        const createUrl = await appConfig.getApiUrl('/api/agent-terminal/sessions')
        const createResponse = await fetch(createUrl, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            agent_id: `chat_agent_${props.chatSessionId}`,
            agent_role: 'chat_agent',
            conversation_id: props.chatSessionId,
            host: 'main',
            metadata: { created_by: 'frontend_terminal' }
          })
        })

        if (!createResponse.ok) {
          throw new Error(`Failed to create session: ${createResponse.status} ${createResponse.statusText}`)
        }
        const createData = await createResponse.json()
        sessionId.value = createData.session_id
        addTerminalLine('system', `Created new terminal session ${sessionId.value?.slice(-8) || 'unknown'}`, 'success')
      }
    } else {
      // System terminal - generate local ID
      sessionId.value = `system_terminal_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`
      addTerminalLine('system', `System terminal session ${sessionId.value?.slice(-8) || 'unknown'}`, 'info')
    }

    sessionInitialized.value = true
    return sessionId.value as string
  } catch (error) {
    logger.error('Failed to initialize session:', error)
    // Fallback to local generation
    sessionId.value = props.chatSessionId
      ? `chat_terminal_${props.chatSessionId}_${Date.now()}`
      : `system_terminal_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`
    sessionInitialized.value = true
    addTerminalLine('system', `Using fallback session ID (backend unavailable)`, 'warning')
    return sessionId.value
  }
}

const getWebSocketUrl = async () => {
  const wsBaseUrl = await appConfig.getWebSocketUrl()

  switch (props.sessionType) {
    case 'secure':
      return `${wsBaseUrl}/secure/${sessionId.value}`
    case 'main':
      return `${wsBaseUrl}/terminal/${sessionId.value}`
    default:
      return `${wsBaseUrl}/simple/${sessionId.value}`
  }
}

const connectTerminal = async () => {
  if (isConnecting.value || isConnected.value) return

  try {
    statusMessage.value = 'Initializing terminal session...'

    // CRITICAL: Initialize session first to get correct session ID
    await initializeSession()

    statusMessage.value = 'Connecting to terminal...'
    wsUrl.value = await getWebSocketUrl()

    // Connect using WebSocket composable
    wsConnect()

  } catch (error) {
    logger.error('Connection failed:', error)
    statusMessage.value = 'Failed to connect'
    addTerminalLine('system', `Connection failed: ${error}`, 'error')
  }
}

const disconnectTerminal = () => {
  wsDisconnect(1000, 'User disconnected')
  statusMessage.value = 'Disconnected'
}

const toggleConnection = () => {
  if (isConnected.value) {
    disconnectTerminal()
  } else {
    connectTerminal()
  }
}

const sendCommand = (command: string) => {
  if (!isConnected.value) {
    addTerminalLine('system', 'Not connected to terminal', 'error')
    return
  }

  try {
    // Add command to history
    if (command.trim() && commandHistory.value[commandHistory.value.length - 1] !== command) {
      commandHistory.value.push(command)
      if (commandHistory.value.length > 100) {
        commandHistory.value.shift()
      }
    }
    historyIndex.value = -1

    // Display command in terminal
    addTerminalLine(currentPrompt.value, command, 'command')

    // Send command to backend
    const message = {
      type: 'command',
      data: command,
      session_id: sessionId.value
    }

    wsSend(message) // useWebSocket handles JSON.stringify
    currentCommand.value = ''

    // Issue #608: Log terminal activity for session tracking
    if (props.chatSessionId) {
      logTerminalActivity(command, {
        subtype: 'command',
        sessionId: sessionId.value,
        terminalType: props.sessionType
      })
    }

  } catch (error) {
    logger.error('Failed to send command:', error)
    addTerminalLine('system', `Failed to send command: ${error}`, 'error')
  }
}

const handleTerminalMessage = (data: any) => {
  switch (data.type) {
    case 'output':
      addTerminalLine('', data.data, 'output')
      break
    case 'error':
      addTerminalLine('', data.data, 'error')
      break
    case 'prompt':
      currentPrompt.value = data.data || '$ '
      break
    case 'status':
      statusMessage.value = data.message
      break
    default:
      addTerminalLine('', JSON.stringify(data), 'info')
  }
}

const addTerminalLine = (prefix: string, content: string, type: string = 'output') => {
  terminalLines.value.push({
    prefix,
    content,
    type
  })

  // Limit terminal history
  if (terminalLines.value.length > 1000) {
    terminalLines.value.splice(0, 100)
  }

  // Auto-scroll
  nextTick(() => {
    if (terminalElement.value) {
      terminalElement.value.scrollTop = terminalElement.value.scrollHeight
    }
  })
}

const clearTerminal = () => {
  terminalLines.value = []
  addTerminalLine('system', 'Terminal cleared', 'info')
}

const copyTerminalOutput = async () => {
  try {
    const output = terminalLines.value
      .map(line => `${line.prefix}${line.content}`)
      .join('\n')

    await navigator.clipboard.writeText(output)
    addTerminalLine('system', 'Terminal output copied to clipboard', 'info')
  } catch (error) {
    addTerminalLine('system', 'Failed to copy terminal output', 'error')
  }
}

const handleKeydown = (event: KeyboardEvent) => {
  switch (event.key) {
    case 'Enter':
      event.preventDefault()
      if (currentCommand.value.trim()) {
        sendCommand(currentCommand.value.trim())
      }
      break

    case 'ArrowUp':
      event.preventDefault()
      if (commandHistory.value.length > 0) {
        if (historyIndex.value === -1) {
          historyIndex.value = commandHistory.value.length - 1
        } else if (historyIndex.value > 0) {
          historyIndex.value--
        }
        currentCommand.value = commandHistory.value[historyIndex.value] || ''
      }
      break

    case 'ArrowDown':
      event.preventDefault()
      if (historyIndex.value !== -1) {
        if (historyIndex.value < commandHistory.value.length - 1) {
          historyIndex.value++
          currentCommand.value = commandHistory.value[historyIndex.value]
        } else {
          historyIndex.value = -1
          currentCommand.value = ''
        }
      }
      break

    case 'Tab':
      event.preventDefault()
      // TODO: Implement tab completion
      break
  }
}

const handleKeyup = (event: KeyboardEvent) => {
  // Reset history navigation when typing
  if (event.key !== 'ArrowUp' && event.key !== 'ArrowDown') {
    historyIndex.value = -1
  }
}

// Lifecycle
onMounted(async () => {
  if (props.chatSessionId) {
    addTerminalLine('system', `Chat Terminal (Session: ${props.chatSessionId.slice(-8)})`, 'info')
    addTerminalLine('system', `Connection type: ${props.sessionType}`, 'info')
    addTerminalLine('system', `Initializing session...`, 'info')
  } else {
    addTerminalLine('system', `System Terminal (Independent)`, 'info')
    addTerminalLine('system', `Connection type: ${props.sessionType}`, 'info')
  }

  if (props.autoConnect) {
    // connectTerminal will call initializeSession internally
    connectTerminal()
  }
})

onUnmounted(() => {
  disconnectTerminal()
})
</script>

<style scoped>
/* Container styling matching browser/desktop design */
.terminal-container {
  @apply flex flex-col h-full bg-white border-0 border-t border-l border-r border-gray-300 overflow-hidden;
  font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
  min-height: 400px;
  /* Remove shadow and border-radius to prevent overlap with tabs */
  border-top-left-radius: 0;
  border-top-right-radius: 0;
  border-bottom-left-radius: 0.5rem;
  border-bottom-right-radius: 0.5rem;
}

/* Terminal button styling matching browser controls */
.terminal-btn {
  @apply px-2 py-1 text-gray-600 hover:text-gray-800 hover:bg-gray-200 rounded transition-colors duration-200;
}

.terminal-btn:disabled {
  @apply opacity-50 cursor-not-allowed;
}

.terminal-btn.connect-btn {
  @apply text-green-600 hover:text-green-800 hover:bg-green-100;
}

.terminal-btn.disconnect-btn {
  @apply text-red-600 hover:text-red-800 hover:bg-red-100;
}

.terminal-btn.connecting {
  @apply text-blue-600;
}

/* Terminal body with dark theme */
.terminal-body {
  @apply flex-1 flex flex-col bg-gray-900 overflow-hidden;
}

.terminal-status {
  @apply px-4 py-2 bg-gray-800 text-gray-300 text-sm flex items-center gap-2 border-b border-gray-700;
}

.terminal-output {
  @apply flex-1 p-4 bg-gray-900 text-green-400 overflow-y-auto text-sm leading-relaxed min-h-0;
  font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
}

.terminal-connected {
  @apply border-l-4 border-green-500;
}

.terminal-output::-webkit-scrollbar {
  width: 6px;
}

.terminal-output::-webkit-scrollbar-track {
  @apply bg-gray-800;
}

.terminal-output::-webkit-scrollbar-thumb {
  @apply bg-gray-600 rounded;
}

.terminal-output::-webkit-scrollbar-thumb:hover {
  @apply bg-gray-500;
}

.terminal-line {
  margin-bottom: 4px;
  word-wrap: break-word;
}

/* Issue #704: Migrated terminal colors to CSS design tokens */
.line-prefix {
  color: var(--text-tertiary, #6c757d);
  user-select: none;
}

.command {
  color: var(--text-on-primary, #ffffff);
  font-weight: var(--font-medium);
}

.output {
  color: var(--text-primary-light, #e9ecef);
}

.success {
  color: var(--color-success, #28a745);
}

.error {
  color: var(--color-error, #dc3545);
}

.info {
  color: var(--color-info, #17a2b8);
}

.terminal-prompt {
  display: flex;
  align-items: center;
  margin-top: 8px;
  flex-shrink: 0; /* Prevent prompt from shrinking */
}

.prompt {
  color: #6c757d;
  margin-right: 8px;
  user-select: none;
}

.command-input {
  flex: 1;
  background: transparent;
  border: none;
  color: #ffffff;
  font-family: inherit;
  font-size: inherit;
  outline: none;
  padding: 0;
}

/* Additional styling for terminal line types */
.terminal-line {
  @apply mb-1 break-words;
}

.line-prefix {
  @apply text-gray-500 select-none mr-2;
}

.command {
  @apply text-blue-400 font-medium;
}

.output {
  @apply text-green-400;
}

.error {
  @apply text-red-400;
}

.info {
  @apply text-cyan-400;
}

.warning {
  @apply text-yellow-400;
}

.terminal-prompt {
  @apply flex items-center mt-2 pt-2 border-t border-gray-700;
}

.prompt {
  @apply text-green-500 mr-2 select-none font-semibold;
}

.command-input {
  @apply flex-1 bg-transparent border-none text-green-400 outline-none py-1;
  font-family: inherit;
  font-size: inherit;
}

.command-input::placeholder {
  @apply text-gray-500;
}

.command-input:disabled {
  @apply opacity-50;
}

/* Mobile responsive */
@media (max-width: 768px) {
  .working-terminal {
    /* FIXED: Use min-height instead of fixed height for mobile */
    min-height: 300px; /* Minimum viable height on mobile */
  }

  .terminal-header {
    padding: 8px 12px;
  }

  .terminal-header h3 {
    font-size: 12px;
  }

  .terminal-controls button {
    padding: 4px 8px;
    font-size: 11px;
  }

  .terminal-output {
    padding: 12px;
    font-size: 12px;
  }
}

/* ADDED: Ensure terminal works well in flex layouts */
@media (min-width: 769px) {
  .working-terminal {
    /* Ensure terminal adapts to container height on larger screens */
    max-height: 100vh; /* Don't exceed viewport */
  }
}
</style>
