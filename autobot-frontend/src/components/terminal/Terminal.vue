<template>
  <div class="terminal-container">
    <!-- Terminal Header (matching browser/desktop style) -->
    <div class="terminal-header bg-autobot-bg-secondary border-b border-autobot-border p-2 flex items-center justify-between">
      <div class="flex items-center gap-3">
        <div class="flex gap-1">
          <div class="w-3 h-3 bg-red-500 rounded-full"></div>
          <div class="w-3 h-3 bg-yellow-500 rounded-full"></div>
          <div class="w-3 h-3 bg-green-500 rounded-full"></div>
        </div>
        <div class="flex items-center gap-2 text-sm">
          <Icon name="terminal" class="text-green-600" />
          <span class="font-medium">{{ props.chatSessionId ? $t('terminal.terminal.chatTerminal') : $t('terminal.terminal.systemTerminal') }}</span>
          <span class="text-xs text-autobot-text-muted">{{ props.chatSessionId ? $t('terminal.terminal.chatSession') : $t('terminal.terminal.independentTool') }}</span>
        </div>
      </div>

      <div class="flex items-center gap-2">
        <!-- Terminal Controls -->
        <div class="flex items-center gap-1">
          <button @click="toggleConnection" :class="connectionButtonClass" :disabled="isConnecting" class="terminal-btn" :title="connectionButtonText" :aria-label="connectionButtonText">
            <Icon :name="connectionIconClass" />
          </button>

          <button @click="clearTerminal" class="terminal-btn" :title="$t('terminal.terminal.clearTerminal')" :aria-label="$t('terminal.terminal.clearTerminal')">
            <Icon name="trash" />
          </button>

          <button @click="copyTerminalOutput" class="terminal-btn" :title="$t('terminal.terminal.copyOutput')" :aria-label="$t('terminal.terminal.copyOutput')">
            <Icon name="copy" />
          </button>
        </div>
      </div>
    </div>

    <!-- Terminal Body (contained design) -->
    <div class="terminal-body">
      <div class="terminal-status" v-if="statusMessage">
        <Icon :name="statusIconClass" />
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
        <div v-if="isConnected" class="terminal-prompt-wrapper">
          <CompletionSuggestions
            :items="tabCompletion.suggestions.value"
            :selected-index="tabCompletion.selectedIndex.value"
            :visible="tabCompletion.isVisible.value"
            @select="handleCompletionSelect"
          />
          <div class="terminal-prompt">
            <span class="prompt">{{ currentPrompt }}</span>
            <input
              ref="commandInput"
              v-model="currentCommand"
              @keydown="handleKeydown"
              @keyup="handleKeyup"
              class="command-input"
              :disabled="!isConnected"
              :placeholder="t('terminal.terminal.enterCommandPlaceholder')"
            />
          </div>
        </div>
      </div>
      <TerminalStatusBar
        :connection-status="statusBarConnectionStatus"
        :connecting="isConnecting"
        :can-input="isConnected"
        :session-id="sessionId"
        :output-lines-count="terminalLines.length"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import Icon from '@/components/ui/Icon.vue'
import { ref, computed, onMounted, onUnmounted, nextTick } from 'vue'
import { useI18n } from 'vue-i18n'
import appConfig from '@/config/AppConfig.js'
import { useWebSocket } from '@/composables/useWebSocket'
import { useSessionActivityLogger } from '@/composables/useSessionActivityLogger'
import { useTabCompletion } from '@/composables/useTabCompletion'
import CompletionSuggestions from './CompletionSuggestions.vue'
import TerminalStatusBar from './TerminalStatusBar.vue'
import { createLogger } from '@/utils/debugUtils'
import { useTerminalStore } from '@/composables/useTerminalStore'

const { t } = useI18n()

const logger = createLogger('Terminal')

// Terminal store — provides fetchAgentTerminalSessions / createAgentTerminalSession (issue #6080)
const terminalStore = useTerminalStore()

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

// Tab completion (Issue #503)
const tabCompletion = useTabCompletion({ commandHistory })

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
      statusMessage.value = t('terminal.terminal.connectedToTerminal')
      addTerminalLine('system', t('terminal.terminal.terminalConnectedSuccessfully'), 'success')

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
      statusMessage.value = t('terminal.terminal.connectionError')
      addTerminalLine('system', t('terminal.terminal.connectionErrorOccurred'), 'error')
    },
    onClose: (event) => {
      if (event.code !== 1000) {
        statusMessage.value = t('terminal.terminal.connectionLost')
        addTerminalLine('system', t('terminal.terminal.connectionClosed', { code: event.code }), 'error')
      } else {
        statusMessage.value = t('terminal.terminal.disconnected')
        addTerminalLine('system', t('terminal.terminal.terminalDisconnected'), 'info')
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
  if (isConnecting.value) return 'spinner'
  return isConnected.value ? 'plug' : 'power-off'
})

const connectionButtonText = computed(() => {
  if (isConnecting.value) return t('terminal.terminal.connecting')
  return isConnected.value ? t('terminal.terminal.disconnect') : t('terminal.terminal.connect')
})

const statusIconClass = computed(() => {
  if (isConnecting.value) return 'spinner'
  if (isConnected.value) return 'check-circle'
  return 'exclamation-circle'
})

const statusBarConnectionStatus = computed(() => {
  if (isConnecting.value) return 'connecting'
  if (isConnected.value) return 'connected'
  return 'disconnected'
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
      const sessions = await terminalStore.fetchAgentTerminalSessions(props.chatSessionId)

      if (sessions.length > 0) {
        // Use existing session
        const existingSession = sessions[0] as { session_id: string }
        sessionId.value = existingSession.session_id
        addTerminalLine('system', `Connected to existing terminal session ${sessionId.value?.slice(-8) || 'unknown'}`, 'info')
      } else {
        // Create new session via AgentTerminalService
        sessionId.value = await terminalStore.createAgentTerminalSession({
          agent_id: `chat_agent_${props.chatSessionId}`,
          agent_role: 'chat_agent',
          conversation_id: props.chatSessionId,
          host: 'main',
          metadata: { created_by: 'frontend_terminal' }
        })
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
    statusMessage.value = t('terminal.terminal.initializingSession')

    // CRITICAL: Initialize session first to get correct session ID
    await initializeSession()

    statusMessage.value = t('terminal.terminal.connectingToTerminal')
    wsUrl.value = await getWebSocketUrl()

    // Connect using WebSocket composable
    wsConnect()

  } catch (error) {
    logger.error('Connection failed:', error)
    statusMessage.value = t('terminal.terminal.failedToConnect')
    addTerminalLine('system', `Connection failed: ${error}`, 'error')
  }
}

const disconnectTerminal = () => {
  wsDisconnect(1000, 'User disconnected')
  statusMessage.value = t('terminal.terminal.disconnected')
}

const toggleConnection = () => {
  if (isConnected.value) {
    disconnectTerminal()
  } else {
    connectTerminal()
  }
}

const sendCommand = (command: string) => {
  tabCompletion.dismiss()
  if (!isConnected.value) {
    addTerminalLine('system', t('terminal.terminal.notConnected'), 'error')
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
    // Issue #756: Handle tab completion response
    case 'tab_completion':
      handleTabCompletionResponse(data)
      break
    default:
      addTerminalLine('', JSON.stringify(data), 'info')
  }
}

// Issue #756 / #503: Handle tab completion response from backend
const handleTabCompletionResponse = (
  data: { completions: string[]; prefix: string; error?: string },
) => {
  if (data.error) return
  const completions = data.completions || []
  if (completions.length === 0) return

  if (completions.length === 1) {
    applyCompletion(data.prefix, completions[0])
    tabCompletion.dismiss()
  } else {
    // Feed backend completions into the dropdown
    tabCompletion.suggestions.value = completions.map(
      (c: string) => ({
        value: c,
        type: 'path' as const,
        description: 'From server',
      }),
    )
    tabCompletion.selectedIndex.value = 0
    tabCompletion.isVisible.value = true
  }
}

// Issue #756: Apply a single completion to the current command
const applyCompletion = (
  prefix: string, completion: string,
) => {
  const cmd = currentCommand.value
  const lastSpaceIdx = cmd.lastIndexOf(' ')
  const beforePrefix = lastSpaceIdx >= 0
    ? cmd.slice(0, lastSpaceIdx + 1) : ''
  currentCommand.value = beforePrefix + completion
}

// Issue #503: Handle clicking a suggestion in the dropdown
const handleCompletionSelect = (index: number) => {
  tabCompletion.selectedIndex.value = index
  const accepted = tabCompletion.acceptSelected(
    currentCommand.value,
  )
  if (accepted !== null) {
    currentCommand.value = accepted
  }
  nextTick(() => commandInput.value?.focus())
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
  addTerminalLine('system', t('terminal.terminal.terminalCleared'), 'info')
}

const copyTerminalOutput = async () => {
  try {
    const output = terminalLines.value
      .map(line => `${line.prefix}${line.content}`)
      .join('\n')

    await navigator.clipboard.writeText(output)
    addTerminalLine('system', t('terminal.terminal.outputCopied'), 'info')
  } catch (error) {
    addTerminalLine('system', t('terminal.terminal.copyFailed'), 'error')
  }
}

const handleKeydown = (event: KeyboardEvent) => {
  switch (event.key) {
    case 'Enter':
      if (tabCompletion.isVisible.value) {
        event.preventDefault()
        const accepted = tabCompletion.acceptSelected(
          currentCommand.value,
        )
        if (accepted !== null) currentCommand.value = accepted
        return
      }
      event.preventDefault()
      tabCompletion.dismiss()
      if (currentCommand.value.trim()) {
        sendCommand(currentCommand.value.trim())
      }
      break

    case 'Escape':
      if (tabCompletion.isVisible.value) {
        event.preventDefault()
        tabCompletion.dismiss()
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
        currentCommand.value =
          commandHistory.value[historyIndex.value] || ''
      }
      break

    case 'ArrowDown':
      event.preventDefault()
      if (historyIndex.value !== -1) {
        if (
          historyIndex.value < commandHistory.value.length - 1
        ) {
          historyIndex.value++
          currentCommand.value =
            commandHistory.value[historyIndex.value]
        } else {
          historyIndex.value = -1
          currentCommand.value = ''
        }
      }
      break

    case 'Tab':
      event.preventDefault()
      {
        const el = event.target as HTMLInputElement
        const cursorPos = el?.selectionStart
          ?? currentCommand.value.length
        // Local completion first (Issue #503)
        const result = tabCompletion.complete(
          currentCommand.value, cursorPos,
        )
        if (result !== null) currentCommand.value = result
        // Also send WS request if connected (Issue #756)
        if (isConnected.value) {
          wsSend({
            type: 'tab_completion',
            text: currentCommand.value,
            cursor: cursorPos,
            session_id: sessionId.value,
          })
        }
      }
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
@reference "../../assets/tailwind.css";
/* Container styling matching browser/desktop design */
.terminal-container {
  @apply flex flex-col h-full bg-autobot-bg-card border-0 border-t border-l border-r border-autobot-border overflow-hidden;
  font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
  min-height: 400px;
  /* Remove shadow and border-radius to prevent overlap with tabs */
  border-top-left-radius: 0;
  border-top-right-radius: 0;
  border-bottom-left-radius: var(--radius-lg);
  border-bottom-right-radius: var(--radius-lg);
}

/* Terminal button styling matching browser controls */
.terminal-btn {
  @apply px-2 py-1 text-autobot-text-secondary hover:text-autobot-text-primary hover:bg-autobot-bg-hover rounded transition-colors duration-200;
}

.terminal-btn:disabled {
  @apply opacity-50 cursor-not-allowed;
}

.terminal-btn.connect-btn {
  color: var(--color-success);
  &:hover {
    color: var(--color-success);
    background: var(--color-success-bg);
  }
}

.terminal-btn.disconnect-btn {
  color: var(--color-error);
  &:hover {
    color: var(--color-error);
    background: var(--color-error-bg);
  }
}

.terminal-btn.connecting {
  color: var(--color-info);
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
  margin-bottom: var(--spacing-1);
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

.terminal-prompt-wrapper {
  position: relative;
  flex-shrink: 0;
}

.terminal-prompt {
  display: flex;
  align-items: center;
  margin-top: var(--spacing-2);
  flex-shrink: 0; /* Prevent prompt from shrinking */
}

.prompt {
  color: #6c757d;
  margin-right: var(--spacing-2);
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
  padding: var(--spacing-0);
}

.terminal-input:focus-visible {
  outline: 2px solid var(--color-primary);
  outline-offset: 2px;
}

/* Additional styling for terminal line types */
.terminal-line {
  @apply mb-1 break-words;
}

.line-prefix {
  @apply text-gray-500 select-none mr-2;
}

.command {
  @apply font-medium;
  color: var(--color-info);
}

.output {
  color: var(--color-success);
}

.error {
  color: var(--color-error);
}

.info {
  color: var(--color-info);
}

.warning {
  color: var(--color-warning);
}

.terminal-prompt {
  @apply flex items-center mt-2 pt-2 border-t border-gray-700;
}

.prompt {
  @apply text-green-500 mr-2 select-none font-semibold;
}

.command-input {
  @apply flex-1 bg-transparent border-none text-green-400 outline-hidden py-1;
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
    padding: var(--spacing-2) var(--spacing-3);
  }

  .terminal-header h3 {
    font-size: var(--text-xs);
  }

  .terminal-controls button {
    padding: var(--spacing-1) var(--spacing-2);
    font-size: var(--text-xs);
  }

  .terminal-output {
    padding: var(--spacing-3);
    font-size: var(--text-xs);
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
