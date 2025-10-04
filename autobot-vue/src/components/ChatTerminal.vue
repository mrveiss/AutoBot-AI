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
          Session: {{ chatSessionId?.slice(-8) || 'None' }}
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
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import BaseXTerminal from '@/components/terminal/BaseXTerminal.vue'
import { useTerminalStore } from '@/composables/useTerminalStore'
import { useTerminalService } from '@/services/TerminalService'
import type { Terminal } from '@xterm/xterm'

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
const terminal = ref<Terminal>()
const mounted = ref(false)
const isConnected = ref(false)

// Session ID for terminal
const sessionId = computed(() => {
  return props.chatSessionId
    ? `chat_terminal_${props.chatSessionId}_${Date.now()}`
    : `chat_terminal_${Date.now()}`
})

// Get session from store
const session = computed(() => {
  return terminalStore.sessions.get(sessionId.value)
})

// Control state
const controlState = computed(() => {
  return session.value?.controlState || 'user'
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
  return isAgentControlled.value ? 'AUTOMATED' : 'MANUAL'
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

// Methods
const handleTerminalReady = (term: Terminal) => {
  terminal.value = term

  // Write initial message
  term.writeln('\x1b[1;36mChat Terminal Initialized\x1b[0m')
  term.writeln(`Session: ${props.chatSessionId?.slice(-8) || 'None'}`)
  term.writeln(`Control: ${controlState.value.toUpperCase()}`)
  term.writeln('')

  if (props.autoConnect) {
    connectTerminal()
  }
}

const handleTerminalData = (data: string) => {
  if (isConnected.value && !isAgentControlled.value) {
    terminalService.sendInput(sessionId.value, data)
  }
}

const handleTerminalResize = (cols: number, rows: number) => {
  if (isConnected.value) {
    terminalService.resize(sessionId.value, rows, cols)
  }
}

const connectTerminal = async () => {
  if (isConnected.value) return

  try {
    // Create session in store
    const host = terminalStore.selectedHost
    terminalStore.createSession(sessionId.value, host)

    // Create backend session
    const backendSessionId = await terminalService.createSession()

    // Connect WebSocket
    await terminalService.connect(backendSessionId, {
      onOutput: (output: any) => {
        if (terminal.value) {
          terminal.value.write(output.content || output.data || '')
        }
      },
      onPromptChange: (prompt: string) => {
        console.log('[ChatTerminal] Prompt changed:', prompt)
      },
      onStatusChange: (status: string) => {
        terminalStore.updateSessionStatus(sessionId.value, status as any)
      },
      onError: (error: string) => {
        if (terminal.value) {
          terminal.value.writeln(`\x1b[1;31mError: ${error}\x1b[0m`)
        }
      }
    })

    isConnected.value = true
    terminalStore.updateSessionStatus(sessionId.value, 'connected')

    if (terminal.value) {
      terminal.value.writeln('\x1b[1;32mConnected to terminal session\x1b[0m')
      terminal.value.focus()
    }
  } catch (error) {
    console.error('[ChatTerminal] Connection failed:', error)
    terminalStore.updateSessionStatus(sessionId.value, 'error')

    if (terminal.value) {
      terminal.value.writeln(`\x1b[1;31mConnection failed: ${error}\x1b[0m`)
    }
  }
}

const disconnectTerminal = () => {
  if (!isConnected.value) return

  terminalService.disconnect(sessionId.value)
  isConnected.value = false
  terminalStore.updateSessionStatus(sessionId.value, 'disconnected')

  if (terminal.value) {
    terminal.value.writeln('\x1b[1;33mDisconnected from terminal session\x1b[0m')
  }
}

const clearTerminal = () => {
  if (baseTerminalRef.value) {
    baseTerminalRef.value.clear()
  }
}

const toggleControl = () => {
  if (isAgentControlled.value) {
    terminalStore.requestUserTakeover(sessionId.value)
    if (terminal.value) {
      terminal.value.writeln('\x1b[1;32m>>> USER CONTROL ACTIVATED <<<\x1b[0m')
      terminal.value.focus()
    }
  } else {
    terminalStore.requestAgentControl(sessionId.value)
    if (terminal.value) {
      terminal.value.writeln('\x1b[1;36m>>> AGENT CONTROL ACTIVATED <<<\x1b[0m')
      terminal.value.blur()
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
