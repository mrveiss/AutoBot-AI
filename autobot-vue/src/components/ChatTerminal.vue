<template>
  <div class="chat-terminal-container">
    <!-- Terminal Header with Control State Indicator -->
    <div class="terminal-header" :class="headerClass">
      <div class="flex items-center space-x-3">
        <div class="flex space-x-1">
          <div class="w-3 h-3 bg-red-500 rounded-full"></div>
          <div class="w-3 h-3 bg-yellow-500 rounded-full"></div>
          <div class="w-3 h-3 bg-green-500 rounded-full"></div>
        </div>

        <div class="flex items-center space-x-2 text-sm">
          <i class="fas fa-terminal" :class="iconClass"></i>
          <span class="font-medium">Chat Terminal</span>

          <!-- Control State Badge -->
          <div class="control-state-badge" :class="controlStateClass">
            <i :class="controlStateIcon"></i>
            <span class="text-xs font-semibold">{{ controlStateText }}</span>
          </div>
        </div>

        <div class="text-xs text-gray-500">
          Chat: {{ chatSessionId || 'None' }} | PTY Session: {{ ptySessionId || backendSessionId || 'Not Connected' }}
        </div>
      </div>

      <div class="flex items-center space-x-2">
        <!-- Takeover/Release Button -->
        <button
          v-if="allowUserTakeover"
          @click="toggleControl"
          :class="takeoverButtonClass"
          class="terminal-btn"
          :title="takeoverButtonTitle"
        >
          <i :class="takeoverButtonIcon"></i>
          <span class="text-xs ml-1">{{ takeoverButtonText }}</span>
        </button>

        <!-- Connection Status -->
        <div class="flex items-center space-x-1">
          <div
            class="w-2 h-2 rounded-full"
            :class="connectionStatusClass"
          ></div>
          <span class="text-xs text-gray-600">{{ connectionStatusText }}</span>
        </div>

        <!-- Clear Button -->
        <button @click="clearTerminal" class="terminal-btn" title="Clear Terminal">
          <i class="fas fa-trash"></i>
        </button>
      </div>
    </div>

    <!-- Terminal Body with xterm.js -->
    <div class="terminal-body" :class="terminalBodyClass">
      <BaseXTerminal
        v-if="mounted"
        ref="baseTerminalRef"
        :session-id="sessionId"
        :auto-connect="false"
        :read-only="isAgentControlled"
        theme="dark"
        @ready="handleTerminalReady"
        @data="handleTerminalData"
        @resize="handleTerminalResize"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, shallowRef, computed, onMounted, onUnmounted, watch } from 'vue'
import BaseXTerminal from '@/components/terminal/BaseXTerminal.vue'
import { useTerminalStore } from '@/composables/useTerminalStore'
import { useTerminalService } from '@/services/TerminalService'
import type { Terminal } from '@xterm/xterm'
import appConfig from '@/config/AppConfig.js'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('ChatTerminal')

// Props
interface Props {
  chatSessionId: string | null
  autoConnect?: boolean
  allowUserTakeover?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  autoConnect: true,
  allowUserTakeover: true
})

// Store & Service
const terminalStore = useTerminalStore()
const terminalService = useTerminalService()

// Refs
const baseTerminalRef = ref<InstanceType<typeof BaseXTerminal>>()
// CRITICAL: Use shallowRef for xterm Terminal to prevent Vue's deep reactivity
// from causing "Cannot read properties of undefined (reading 'dimensions')" errors
const terminal = shallowRef<Terminal>()
const mounted = ref(false)
const isConnected = ref(false)

// Session ID for terminal - use ref to maintain stable ID
const sessionId = ref(
  props.chatSessionId
    ? `chat_terminal_${props.chatSessionId}_${Date.now()}`
    : `chat_terminal_${Date.now()}`
)

// Backend session IDs
const backendSessionId = ref<string | null>(null)  // Agent terminal session ID
const ptySessionId = ref<string | null>(null)      // PTY session ID for WebSocket connection

// Terminal scrollback buffer persistence
const SCROLLBACK_KEY = computed(() =>
  props.chatSessionId ? `terminal_scrollback_${props.chatSessionId}` : null
)

// Get session from store
const session = computed(() => {
  return terminalStore.getSession(sessionId.value)
})

// Control state
const controlState = computed(() => {
  return session.value?.controlState || 'user'  // Default to user control mode for chat terminals (agent can take over when needed)
})

const isAgentControlled = computed(() => {
  return controlState.value === 'agent'
})

const isUserControlled = computed(() => {
  return controlState.value === 'user'
})

// Connection status
const connectionStatus = computed(() => {
  return session.value?.status || 'disconnected'
})

const connectionStatusText = computed(() => {
  const status = connectionStatus.value
  return status.charAt(0).toUpperCase() + status.slice(1)
})

const connectionStatusClass = computed(() => ({
  'bg-green-500': connectionStatus.value === 'connected' || connectionStatus.value === 'ready',
  'bg-yellow-500': connectionStatus.value === 'connecting' || connectionStatus.value === 'reconnecting',
  'bg-red-500': connectionStatus.value === 'disconnected' || connectionStatus.value === 'error'
}))

// Header styling based on control state
const headerClass = computed(() => ({
  'border-cyan-400': isAgentControlled.value,
  'border-green-400': isUserControlled.value
}))

const iconClass = computed(() => ({
  'text-cyan-600': isAgentControlled.value,
  'text-green-600': isUserControlled.value
}))

// Control state badge
const controlStateClass = computed(() => ({
  'bg-cyan-100 text-cyan-800 border-cyan-300': isAgentControlled.value,
  'bg-green-100 text-green-800 border-green-300': isUserControlled.value
}))

const controlStateIcon = computed(() => ({
  'fas fa-robot': isAgentControlled.value,
  'fas fa-user': isUserControlled.value
}))

const controlStateText = computed(() => {
  return isAgentControlled.value ? 'automated' : 'manual'
})

// Terminal body class based on control state
const terminalBodyClass = computed(() => ({
  'border-l-4 border-cyan-500': isAgentControlled.value,
  'border-l-4 border-green-500': isUserControlled.value
}))

// Takeover button
const takeoverButtonClass = computed(() => ({
  'text-green-600 hover:text-green-800 hover:bg-green-100': isAgentControlled.value,
  'text-cyan-600 hover:text-cyan-800 hover:bg-cyan-100': isUserControlled.value
}))

const takeoverButtonIcon = computed(() => ({
  'fas fa-user-shield': isAgentControlled.value,
  'fas fa-robot': isUserControlled.value
}))

const takeoverButtonText = computed(() => {
  return isAgentControlled.value ? 'Take Control' : 'Allow Agent'
})

const takeoverButtonTitle = computed(() => {
  return isAgentControlled.value
    ? 'Interrupt agent and take manual control'
    : 'Allow agent to control terminal'
})

// Terminal scrollback persistence methods
const saveScrollback = (content: string) => {
  if (SCROLLBACK_KEY.value) {
    try {
      const existing = localStorage.getItem(SCROLLBACK_KEY.value) || ''
      const newContent = existing + content
      localStorage.setItem(SCROLLBACK_KEY.value, newContent)
      logger.debug('Saved scrollback:', {
        contentLength: content.length,
        totalLength: newContent.length,
        key: SCROLLBACK_KEY.value
      })
    } catch (error) {
      logger.error('Failed to save scrollback:', error)
    }
  }
}

const loadScrollback = (): string | null => {
  if (SCROLLBACK_KEY.value) {
    try {
      return localStorage.getItem(SCROLLBACK_KEY.value)
    } catch (error) {
      logger.error('Failed to load scrollback:', error)
    }
  }
  return null
}

const clearScrollback = () => {
  if (SCROLLBACK_KEY.value) {
    try {
      localStorage.removeItem(SCROLLBACK_KEY.value)
    } catch (error) {
      logger.error('Failed to clear scrollback:', error)
    }
  }
}

// Methods
const handleTerminalReady = (term: Terminal) => {
  terminal.value = term

  // Restore previous scrollback if exists
  const previousContent = loadScrollback()
  logger.debug('Scrollback restore:', {
    hasContent: !!previousContent,
    contentLength: previousContent?.length || 0,
    firstChars: previousContent?.substring(0, 100) || 'none',
    sessionId: props.chatSessionId
  })

  if (previousContent && previousContent.length > 0) {
    term.write(previousContent)
    term.writeln('\x1b[1;33m--- Session Restored ---\x1b[0m')
  } else {
    // Write initial message only for new sessions
    // FIXED: Removed redundant "Control: X" line (already shown in header badge)
    term.writeln('\x1b[1;36mChat Terminal Initialized\x1b[0m')
    term.writeln(`Session: ${props.chatSessionId || 'None'}`)
    term.writeln('')
  }

  if (props.autoConnect) {
    connectTerminal()
  }
}

const handleTerminalData = (data: string) => {
  // Only allow input in user control mode
  if (!isConnected.value || isAgentControlled.value) {
    logger.warn('Input blocked:', {
      isConnected: isConnected.value,
      isAgentControlled: isAgentControlled.value
    })
    return
  }

  const wsSessionId = ptySessionId.value || backendSessionId.value
  if (!wsSessionId) {
    logger.warn('No WebSocket session ID')
    return
  }

  // Send input directly to PTY - it handles echo
  // This keeps it simple and works for both manual and automated modes
  terminalService.sendInput(wsSessionId, data)
}

const handleTerminalResize = (cols: number, rows: number) => {
  // Use PTY session ID for WebSocket operations
  const wsSessionId = ptySessionId.value || backendSessionId.value
  if (isConnected.value && wsSessionId) {
    terminalService.resize(wsSessionId, rows, cols)
  }
}

const connectTerminal = async () => {
  logger.debug('connectTerminal() called', { isConnected: isConnected.value })
  if (isConnected.value) return

  try {
    // Create session in store (defaults to 'agent' mode - user approves commands via dialog)
    const host = terminalStore.selectedHost
    logger.debug('Creating session in store:', { sessionId: sessionId.value, host })
    terminalStore.createSession(sessionId.value, host)

    // CRITICAL: Use Agent Terminal API to ensure approval workflow works
    // Query for existing session first
    let backendSession = null

    if (props.chatSessionId) {

      // REFACTORED: Use AppConfig for dynamic API URL resolution
      const queryUrl = await appConfig.getApiUrl(
        `/api/agent-terminal/sessions?conversation_id=${props.chatSessionId}`
      )
      const queryResponse = await fetch(queryUrl)
      const queryData = await queryResponse.json()

      if (queryData.sessions && queryData.sessions.length > 0) {
        // Use existing session
        const existingSession = queryData.sessions[0]
        backendSession = existingSession.session_id
        const ptySession = existingSession.pty_session_id
        if (terminal.value) {
          terminal.value.writeln(`\x1b[1;36mConnected to existing terminal session ${backendSession}\x1b[0m`)
        }
        // Store PTY session ID for WebSocket connection
        ptySessionId.value = ptySession
      }
    }

    // Create new session if not found
    if (!backendSession) {

      // REFACTORED: Use AppConfig for dynamic API URL resolution
      const createUrl = await appConfig.getApiUrl('/api/agent-terminal/sessions')
      const createResponse = await fetch(
        createUrl,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            agent_id: props.chatSessionId ? `chat_agent_${props.chatSessionId}` : `system_terminal_${Date.now()}`,
            agent_role: 'chat_agent',
            conversation_id: props.chatSessionId || null,
            host: 'main',
            metadata: { created_by: 'chat_terminal_component' }
          })
        }
      )
      const createData = await createResponse.json()
      backendSession = createData.session_id
      const ptySession = createData.pty_session_id
      if (terminal.value) {
        terminal.value.writeln(`\x1b[1;32mCreated new terminal session ${backendSession}\x1b[0m`)
      }
      // Store PTY session ID for WebSocket connection
      ptySessionId.value = ptySession
    }

    backendSessionId.value = backendSession

    // CRITICAL: Use PTY session ID for WebSocket, NOT agent terminal session ID
    const wsSessionId = ptySessionId.value || backendSession

    logger.debug('Session IDs:', {
      frontend: sessionId.value,
      backend: backendSessionId.value,
      pty: ptySessionId.value,
      chatSession: props.chatSessionId,
      websocket: wsSessionId
    })

    // DEBUG: Show WebSocket connection attempt in terminal
    if (terminal.value) {
      terminal.value.writeln(`\x1b[1;33mAttempting WebSocket connection to: ${wsSessionId}\x1b[0m`)
    }

    // Connect WebSocket using PTY session ID
    await terminalService.connect(wsSessionId, {
      onOutput: (output: any) => {
        if (terminal.value) {
          const content = output.content || output.data || ''
          terminal.value.write(content)
          // Save to scrollback buffer
          saveScrollback(content)
        }
      },
      onPromptChange: (_prompt: string) => {
        // Prompt changes are not currently used in chat terminal
      },
      onStatusChange: (status: string) => {
        terminalStore.updateSessionStatus(sessionId.value, status as any)
        // DEBUG: Show status changes in terminal
        if (terminal.value) {
          terminal.value.writeln(`\x1b[1;35mWebSocket Status: ${status}\x1b[0m`)
        }
      },
      onError: (error: string) => {
        if (terminal.value) {
          terminal.value.writeln(`\x1b[1;31mWebSocket Error: ${error}\x1b[0m`)
        }
      }
    })

    isConnected.value = true
    terminalStore.updateSessionStatus(sessionId.value, 'connected')

    // Focus terminal for user input
    if (terminal.value) {
      terminal.value.focus()
    }
  } catch (error) {
    logger.error('Connection failed:', error)
    terminalStore.updateSessionStatus(sessionId.value, 'error')

    if (terminal.value) {
      terminal.value.writeln(`\x1b[1;31mConnection failed: ${error}\x1b[0m`)
    }
  }
}

const disconnectTerminal = () => {
  if (!isConnected.value) return

  // Use PTY session ID for WebSocket operations
  const wsSessionId = ptySessionId.value || backendSessionId.value
  if (wsSessionId) {
    terminalService.disconnect(wsSessionId)
  }
  isConnected.value = false
  backendSessionId.value = null
  ptySessionId.value = null
  terminalStore.updateSessionStatus(sessionId.value, 'disconnected')

  if (terminal.value) {
    terminal.value.writeln('\x1b[1;33mDisconnected from terminal session\x1b[0m')
  }
}

const clearTerminal = () => {
  if (baseTerminalRef.value) {
    baseTerminalRef.value.clear()
  }
  // Also clear scrollback storage
  clearScrollback()
}

const toggleControl = async () => {
  if (!backendSessionId.value) {
    logger.error('No backend session ID for control toggle')
    return
  }

  try {
    if (isAgentControlled.value) {
      // User taking control from agent - call interrupt API
      const interruptUrl = await appConfig.getApiUrl(`/api/agent-terminal/sessions/${backendSessionId.value}/interrupt`)
      const response = await fetch(interruptUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          user_id: 'chat_user',
          reason: 'User manual takeover from chat terminal'
        })
      })

      if (response.ok) {
        terminalStore.requestUserTakeover(sessionId.value)
        if (terminal.value) {
          terminal.value.writeln('\x1b[1;32m>>> USER CONTROL ACTIVATED <<<\x1b[0m')
          terminal.value.focus()
        }
      } else {
        logger.error('Failed to interrupt agent session:', await response.text())
        if (terminal.value) {
          terminal.value.writeln('\x1b[1;31m>>> Failed to take control <<<\x1b[0m')
        }
      }
    } else {
      // Agent resuming control - call resume API
      const resumeUrl = await appConfig.getApiUrl(`/api/agent-terminal/sessions/${backendSessionId.value}/resume`)
      const response = await fetch(resumeUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' }
      })

      if (response.ok) {
        terminalStore.requestAgentControl(sessionId.value)
        if (terminal.value) {
          terminal.value.writeln('\x1b[1;36m>>> AGENT CONTROL ACTIVATED <<<\x1b[0m')
          terminal.value.blur()
        }
      } else {
        logger.error('Failed to resume agent session:', await response.text())
        if (terminal.value) {
          terminal.value.writeln('\x1b[1;31m>>> Failed to activate agent control <<<\x1b[0m')
        }
      }
    }
  } catch (error) {
    logger.error('Error toggling control:', error)
    if (terminal.value) {
      terminal.value.writeln('\x1b[1;31m>>> Control toggle failed <<<\x1b[0m')
    }
  }
}

// Watch for chat session changes
watch(() => props.chatSessionId, (newSessionId, oldSessionId) => {
  if (newSessionId !== oldSessionId) {
    // Disconnect old session
    if (isConnected.value) {
      disconnectTerminal()
    }

    // Generate new stable session ID
    sessionId.value = newSessionId
      ? `chat_terminal_${newSessionId}_${Date.now()}`
      : `chat_terminal_${Date.now()}`

    // Clear backend session IDs
    backendSessionId.value = null
    ptySessionId.value = null

    // Connect to new session if autoConnect
    if (newSessionId && props.autoConnect) {
      setTimeout(() => {
        connectTerminal()
      }, 100)
    }
  }
})

// Lifecycle
onMounted(() => {
  mounted.value = true
})

onUnmounted(() => {
  if (isConnected.value) {
    disconnectTerminal()
  }
  terminalStore.removeSession(sessionId.value)
})
</script>

<style scoped>
.chat-terminal-container {
  @apply flex flex-col h-full bg-white border border-gray-300 overflow-hidden rounded-lg;
  min-height: 400px;
}

.terminal-header {
  @apply bg-gray-100 border-b-2 p-2 flex items-center justify-between;
  transition: border-color 0.3s ease;
}

.control-state-badge {
  @apply px-2 py-1 rounded-md border flex items-center space-x-1;
  transition: all 0.3s ease;
}

.terminal-btn {
  @apply px-2 py-1 text-gray-600 hover:text-gray-800 hover:bg-gray-200 rounded transition-colors duration-200;
}

.terminal-btn:disabled {
  @apply opacity-50 cursor-not-allowed;
}

.terminal-body {
  @apply flex-1 bg-gray-900 overflow-hidden;
  transition: border-color 0.3s ease;
}
</style>
