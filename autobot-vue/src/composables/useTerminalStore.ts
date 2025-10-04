import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

// Host configuration interface
export interface HostConfig {
  id: string
  name: string
  ip: string
  port: number
  description: string
}

// Terminal session state interface
export interface TerminalSession {
  id: string
  host: HostConfig
  status: 'disconnected' | 'connecting' | 'connected' | 'ready' | 'error' | 'reconnecting'
  controlState: 'user' | 'agent'
  createdAt: Date
  lastActivityAt: Date
}

// Terminal tab configuration
export interface TerminalTab {
  id: string
  name: string
  sessionId: string
  host: HostConfig
  isActive: boolean
}

// Available hosts configuration
export const AVAILABLE_HOSTS: HostConfig[] = [
  {
    id: 'main',
    name: 'Main (WSL Backend)',
    ip: '172.16.168.20',
    port: 8001,
    description: 'Main backend server on WSL'
  },
  {
    id: 'frontend',
    name: 'VM1 (Frontend)',
    ip: '172.16.168.21',
    port: 8001,
    description: 'Frontend web interface server'
  },
  {
    id: 'npu-worker',
    name: 'VM2 (NPU Worker)',
    ip: '172.16.168.22',
    port: 8001,
    description: 'Hardware AI acceleration worker'
  },
  {
    id: 'redis',
    name: 'VM3 (Redis)',
    ip: '172.16.168.23',
    port: 8001,
    description: 'Redis data layer server'
  },
  {
    id: 'ai-stack',
    name: 'VM4 (AI Stack)',
    ip: '172.16.168.24',
    port: 8001,
    description: 'AI processing stack server'
  },
  {
    id: 'browser',
    name: 'VM5 (Browser)',
    ip: '172.16.168.25',
    port: 8001,
    description: 'Web automation browser server'
  }
]

export const useTerminalStore = defineStore('terminal', () => {
  // State
  const sessions = ref<Map<string, TerminalSession>>(new Map())
  const activeSessionId = ref<string | null>(null)
  const selectedHost = ref<HostConfig>(AVAILABLE_HOSTS[0]) // Default to main host
  const terminalTabs = ref<TerminalTab[]>([])
  const commandHistory = ref<Map<string, string[]>>(new Map()) // host.id -> commands[]
  const agentControlEnabled = ref<boolean>(false)

  // Computed
  const activeSession = computed(() => {
    return activeSessionId.value ? sessions.value.get(activeSessionId.value) : null
  })

  const activeTabs = computed(() => {
    return terminalTabs.value.filter(tab => tab.isActive)
  })

  const connectedSessions = computed(() => {
    return Array.from(sessions.value.values()).filter(
      session => session.status === 'connected' || session.status === 'ready'
    )
  })

  // Actions
  const createSession = (sessionId: string, host: HostConfig): TerminalSession => {
    const session: TerminalSession = {
      id: sessionId,
      host,
      status: 'disconnected',
      controlState: 'user',
      createdAt: new Date(),
      lastActivityAt: new Date()
    }

    sessions.value.set(sessionId, session)
    return session
  }

  const updateSessionStatus = (
    sessionId: string,
    status: TerminalSession['status']
  ): void => {
    const session = sessions.value.get(sessionId)
    if (session) {
      session.status = status
      session.lastActivityAt = new Date()
    }
  }

  const updateControlState = (
    sessionId: string,
    controlState: 'user' | 'agent'
  ): void => {
    const session = sessions.value.get(sessionId)
    if (session) {
      session.controlState = controlState
      session.lastActivityAt = new Date()
    }
  }

  const setActiveSession = (sessionId: string | null): void => {
    activeSessionId.value = sessionId
  }

  const removeSession = (sessionId: string): void => {
    sessions.value.delete(sessionId)
    if (activeSessionId.value === sessionId) {
      activeSessionId.value = null
    }
  }

  const setSelectedHost = (host: HostConfig): void => {
    selectedHost.value = host
  }

  const addCommandToHistory = (hostId: string, command: string): void => {
    if (!commandHistory.value.has(hostId)) {
      commandHistory.value.set(hostId, [])
    }

    const history = commandHistory.value.get(hostId)!
    // Avoid duplicates
    if (history[history.length - 1] !== command) {
      history.push(command)
      // Limit history to last 100 commands
      if (history.length > 100) {
        history.shift()
      }
    }
  }

  const getCommandHistory = (hostId: string): string[] => {
    return commandHistory.value.get(hostId) || []
  }

  const clearCommandHistory = (hostId: string): void => {
    commandHistory.value.delete(hostId)
  }

  // Terminal tabs management
  const addTab = (tab: TerminalTab): void => {
    // Deactivate all tabs
    terminalTabs.value.forEach(t => (t.isActive = false))
    // Add new tab as active
    terminalTabs.value.push({ ...tab, isActive: true })
  }

  const removeTab = (tabId: string): void => {
    const index = terminalTabs.value.findIndex(tab => tab.id === tabId)
    if (index !== -1) {
      terminalTabs.value.splice(index, 1)
      // Activate previous tab if removed tab was active
      if (terminalTabs.value.length > 0 && index > 0) {
        terminalTabs.value[index - 1].isActive = true
      } else if (terminalTabs.value.length > 0) {
        terminalTabs.value[0].isActive = true
      }
    }
  }

  const setActiveTab = (tabId: string): void => {
    terminalTabs.value.forEach(tab => {
      tab.isActive = tab.id === tabId
    })
  }

  const renameTab = (tabId: string, newName: string): void => {
    const tab = terminalTabs.value.find(t => t.id === tabId)
    if (tab) {
      tab.name = newName
    }
  }

  // Get host by ID
  const getHostById = (hostId: string): HostConfig | undefined => {
    return AVAILABLE_HOSTS.find(host => host.id === hostId)
  }

  // Get host by IP
  const getHostByIp = (ip: string): HostConfig | undefined => {
    return AVAILABLE_HOSTS.find(host => host.ip === ip)
  }

  // Agent control management
  const enableAgentControl = (): void => {
    agentControlEnabled.value = true
  }

  const disableAgentControl = (): void => {
    agentControlEnabled.value = false
  }

  const requestUserTakeover = (sessionId: string): void => {
    updateControlState(sessionId, 'user')
    disableAgentControl()
  }

  const requestAgentControl = (sessionId: string): void => {
    updateControlState(sessionId, 'agent')
    enableAgentControl()
  }

  // Cleanup all sessions
  const cleanup = (): void => {
    sessions.value.clear()
    terminalTabs.value = []
    activeSessionId.value = null
  }

  return {
    // State
    sessions,
    activeSessionId,
    selectedHost,
    terminalTabs,
    commandHistory,
    agentControlEnabled,

    // Computed
    activeSession,
    activeTabs,
    connectedSessions,

    // Actions
    createSession,
    updateSessionStatus,
    updateControlState,
    setActiveSession,
    removeSession,
    setSelectedHost,
    addCommandToHistory,
    getCommandHistory,
    clearCommandHistory,
    addTab,
    removeTab,
    setActiveTab,
    renameTab,
    getHostById,
    getHostByIp,
    enableAgentControl,
    disableAgentControl,
    requestUserTakeover,
    requestAgentControl,
    cleanup
  }
}, {
  persist: {
    key: 'autobot-terminal-store',
    storage: localStorage,
    paths: ['selectedHost', 'commandHistory'] // Only persist these fields
  }
})
