<template>
  <div class="tools-terminal-container">
    <!-- Terminal Header with Host Selector and Tabs -->
    <div class="terminal-header">
      <div class="flex items-center space-x-4 flex-1">
        <div class="flex space-x-1">
          <div class="w-3 h-3 bg-red-500 rounded-full"></div>
          <div class="w-3 h-3 bg-yellow-500 rounded-full"></div>
          <div class="w-3 h-3 bg-green-500 rounded-full"></div>
        </div>

        <div class="flex items-center space-x-2 text-sm">
          <i class="fas fa-terminal text-blue-600"></i>
          <span class="font-medium">System Terminal</span>
        </div>

        <!-- Host Selector -->
        <div v-if="enableHostSwitching" class="flex-1 max-w-xs">
          <HostSelector
            v-model="selectedHostId"
            :disabled="isConnected"
            :show-description="false"
            @host-change="handleHostChange"
          />
        </div>
      </div>

      <div class="flex items-center space-x-2">
        <!-- Tab Management -->
        <button
          v-if="enableTabs"
          @click="addNewTab"
          class="terminal-btn"
          title="New Tab"
        >
          <i class="fas fa-plus"></i>
        </button>

        <!-- Connection Toggle -->
        <button
          @click="toggleConnection"
          :class="connectionButtonClass"
          class="terminal-btn"
          title="Toggle Connection"
        >
          <i :class="connectionIconClass"></i>
        </button>

        <!-- Clear Button -->
        <button @click="clearTerminal" class="terminal-btn" title="Clear Terminal">
          <i class="fas fa-trash"></i>
        </button>

        <!-- Connection Status -->
        <div class="flex items-center space-x-1">
          <div
            class="w-2 h-2 rounded-full"
            :class="connectionStatusClass"
          ></div>
          <span class="text-xs text-gray-600">{{ connectionStatusText }}</span>
        </div>
      </div>
    </div>

    <!-- Terminal Tabs -->
    <div v-if="enableTabs && tabs.length > 1" class="terminal-tabs">
      <div
        v-for="tab in tabs"
        :key="tab.id"
        class="terminal-tab"
        :class="{ 'active': tab.isActive }"
        @click="switchTab(tab.id)"
      >
        <i class="fas fa-terminal text-xs mr-1"></i>
        <span class="text-xs">{{ tab.name }}</span>
        <button
          v-if="tabs.length > 1"
          @click.stop="closeTab(tab.id)"
          class="tab-close"
          title="Close Tab"
        >
          <i class="fas fa-times text-xs"></i>
        </button>
      </div>
    </div>

    <!-- Terminal Body with xterm.js -->
    <div class="terminal-body">
      <BaseXTerminal
        v-if="mounted"
        ref="baseTerminalRef"
        :session-id="currentSessionId"
        :auto-connect="false"
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
import { createLogger } from '@/utils/debugUtils'
import BaseXTerminal from '@/components/terminal/BaseXTerminal.vue'

const logger = createLogger('ToolsTerminal')
import HostSelector from '@/components/terminal/HostSelector.vue'
import { useTerminalStore, type HostConfig } from '@/composables/useTerminalStore'
import { useTerminalService } from '@/services/TerminalService'
import type { Terminal } from '@xterm/xterm'

// Props
interface Props {
  defaultHost?: string
  enableHostSwitching?: boolean
  enableTabs?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  defaultHost: 'main',
  enableHostSwitching: true,
  enableTabs: true
})

// Store & Service
const terminalStore = useTerminalStore()
const terminalService = useTerminalService()

// Refs
const baseTerminalRef = ref<InstanceType<typeof BaseXTerminal>>()
const terminal = ref<Terminal>()
const mounted = ref(false)
const isConnected = ref(false)
const selectedHostId = ref(props.defaultHost)

// Current session ID
const currentSessionId = computed(() => {
  const activeTab = tabs.value.find(t => t.isActive)
  return activeTab?.sessionId || `tools_terminal_${Date.now()}`
})

// Tabs management
const tabs = computed(() => terminalStore.terminalTabs)

// Get current session from store
const session = computed(() => {
  return terminalStore.getSession(currentSessionId.value)
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

const connectionButtonClass = computed(() => ({
  'text-green-600 hover:bg-green-100': !isConnected.value,
  'text-red-600 hover:bg-red-100': isConnected.value
}))

const connectionIconClass = computed(() => {
  if (connectionStatus.value === 'connecting' || connectionStatus.value === 'reconnecting') {
    return 'fas fa-spinner fa-spin'
  }
  return isConnected.value ? 'fas fa-plug' : 'fas fa-power-off'
})

// Methods
const handleTerminalReady = (term: Terminal) => {
  terminal.value = term

  // Write initial message
  const host = terminalStore.getHostById(selectedHostId.value)
  term.writeln('\x1b[1;34mSystem Terminal Initialized\x1b[0m')
  term.writeln(`Host: ${host?.name} (${host?.ip})`)
  term.writeln(`Session: ${currentSessionId.value.slice(-8)}`)
  term.writeln('')

  connectTerminal()
}

const handleTerminalData = (data: string) => {
  if (isConnected.value) {
    terminalService.sendInput(currentSessionId.value, data)
  }
}

const handleTerminalResize = (cols: number, rows: number) => {
  if (isConnected.value) {
    terminalService.resize(currentSessionId.value, rows, cols)
  }
}

const connectTerminal = async () => {
  if (isConnected.value) return

  try {
    // Get host configuration
    const host = terminalStore.getHostById(selectedHostId.value)
    if (!host) {
      throw new Error(`Host not found: ${selectedHostId.value}`)
    }

    // Create session in store
    terminalStore.createSession(currentSessionId.value, host)

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
      },
      onStatusChange: (status: string) => {
        terminalStore.updateSessionStatus(currentSessionId.value, status as any)
      },
      onError: (error: string) => {
        if (terminal.value) {
          terminal.value.writeln(`\x1b[1;31mError: ${error}\x1b[0m`)
        }
      }
    })

    isConnected.value = true
    terminalStore.updateSessionStatus(currentSessionId.value, 'connected')

    if (terminal.value) {
      terminal.value.writeln(`\x1b[1;32mConnected to ${host.name}\x1b[0m`)
      terminal.value.focus()
    }
  } catch (error) {
    logger.error('Connection failed:', error)
    terminalStore.updateSessionStatus(currentSessionId.value, 'error')

    if (terminal.value) {
      terminal.value.writeln(`\x1b[1;31mConnection failed: ${error}\x1b[0m`)
    }
  }
}

const disconnectTerminal = () => {
  if (!isConnected.value) return

  terminalService.disconnect(currentSessionId.value)
  isConnected.value = false
  terminalStore.updateSessionStatus(currentSessionId.value, 'disconnected')

  if (terminal.value) {
    terminal.value.writeln('\x1b[1;33mDisconnected\x1b[0m')
  }
}

const toggleConnection = () => {
  if (isConnected.value) {
    disconnectTerminal()
  } else {
    connectTerminal()
  }
}

const clearTerminal = () => {
  if (baseTerminalRef.value) {
    baseTerminalRef.value.clear()
  }
}

const handleHostChange = (host: HostConfig) => {

  // Disconnect current session
  if (isConnected.value) {
    disconnectTerminal()
  }

  // Update selected host
  selectedHostId.value = host.id

  // Reconnect with new host
  setTimeout(() => {
    connectTerminal()
  }, 100)
}

// Tab management
const addNewTab = () => {
  const tabId = `tab_${Date.now()}`
  const sessionId = `tools_terminal_${tabId}`
  const host = terminalStore.getHostById(selectedHostId.value)!

  terminalStore.addTab({
    id: tabId,
    name: `Terminal ${tabs.value.length + 1}`,
    sessionId,
    host,
    isActive: true
  })
}

const closeTab = (tabId: string) => {
  const tab = tabs.value.find(t => t.id === tabId)
  if (tab) {
    // Disconnect session
    if (isConnected.value && tab.sessionId === currentSessionId.value) {
      disconnectTerminal()
    }
    // Remove from store
    terminalStore.removeTab(tabId)
    terminalStore.removeSession(tab.sessionId)
  }
}

const switchTab = (tabId: string) => {
  // Disconnect current session
  if (isConnected.value) {
    disconnectTerminal()
  }

  // Switch active tab
  terminalStore.setActiveTab(tabId)

  // Reconnect with new tab's session
  setTimeout(() => {
    connectTerminal()
  }, 100)
}

// Initialize first tab if none exist
onMounted(() => {
  mounted.value = true

  if (props.enableTabs && tabs.value.length === 0) {
    addNewTab()
  }
})

// Cleanup
onUnmounted(() => {
  if (isConnected.value) {
    disconnectTerminal()
  }
})
</script>

<style scoped>
.tools-terminal-container {
  @apply flex flex-col h-full bg-white border border-gray-300 overflow-hidden rounded-lg;
  min-height: 500px;
}

.terminal-header {
  @apply bg-gray-100 border-b border-gray-300 p-2 flex items-center justify-between;
}

.terminal-btn {
  @apply px-2 py-1 text-gray-600 hover:text-gray-800 hover:bg-gray-200 rounded transition-colors duration-200;
}

.terminal-tabs {
  @apply flex bg-gray-200 border-b border-gray-300 px-2 gap-1 overflow-x-auto;
}

.terminal-tab {
  @apply flex items-center space-x-1 px-3 py-2 bg-gray-300 text-gray-700 rounded-t cursor-pointer;
  @apply hover:bg-gray-400 transition-colors duration-200;
}

.terminal-tab.active {
  @apply bg-white text-gray-900 border-b-2 border-blue-500;
}

.tab-close {
  @apply ml-2 text-gray-500 hover:text-red-600 transition-colors duration-200;
}

.terminal-body {
  @apply flex-1 bg-gray-900 overflow-hidden;
}
</style>
