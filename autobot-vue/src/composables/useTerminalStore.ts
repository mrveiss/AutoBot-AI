import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import appConfig from '@/config/AppConfig.js'
import type { BackendConfig } from '@/types/app-config'
// FIXED: Import NetworkConstants for default host IPs
import { NetworkConstants } from '@/constants/network'
import { createLogger } from '@/utils/debugUtils'

// Create scoped logger for TerminalStore
const logger = createLogger('TerminalStore')

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

// FIXED: Default fallback hosts (used only if backend config fails) - Use NetworkConstants
const DEFAULT_HOSTS: HostConfig[] = [
  {
    id: 'main',
    name: 'Main (WSL Backend)',
    ip: NetworkConstants.MAIN_MACHINE_IP,
    port: NetworkConstants.BACKEND_PORT,
    description: 'Main backend server on WSL'
  },
  {
    id: 'frontend',
    name: 'VM1 (Frontend)',
    ip: NetworkConstants.FRONTEND_VM_IP,
    port: NetworkConstants.FRONTEND_PORT,
    description: 'Frontend web interface server'
  },
  {
    id: 'npu-worker',
    name: 'VM2 (NPU Worker)',
    ip: NetworkConstants.NPU_WORKER_VM_IP,
    port: NetworkConstants.NPU_WORKER_PORT,
    description: 'Hardware AI acceleration worker'
  },
  {
    id: 'redis',
    name: 'VM3 (Redis)',
    ip: NetworkConstants.REDIS_VM_IP,
    port: NetworkConstants.REDIS_PORT,
    description: 'Redis data layer server'
  },
  {
    id: 'ai-stack',
    name: 'VM4 (AI Stack)',
    ip: NetworkConstants.AI_STACK_VM_IP,
    port: NetworkConstants.AI_STACK_PORT,
    description: 'AI processing stack server'
  },
  {
    id: 'browser',
    name: 'VM5 (Browser)',
    ip: NetworkConstants.BROWSER_VM_IP,
    port: NetworkConstants.BROWSER_SERVICE_PORT,
    description: 'Web automation browser server'
  }
]

// Available hosts configuration - will be loaded from backend
export let AVAILABLE_HOSTS: HostConfig[] = [...DEFAULT_HOSTS]

// Safe getter for hosts - ensures we always have valid hosts
export function getAvailableHosts(): HostConfig[] {
  // CRITICAL: Always ensure we have hosts available
  if (!AVAILABLE_HOSTS || AVAILABLE_HOSTS.length === 0) {
    logger.warn('AVAILABLE_HOSTS was empty, resetting to defaults')
    AVAILABLE_HOSTS = [...DEFAULT_HOSTS]
  }
  return AVAILABLE_HOSTS
}

// Load hosts configuration from backend
async function loadHostsFromBackend(): Promise<void> {
  try {
    const config: BackendConfig = await appConfig.getBackendConfig()

    // Issue #156 Fix: Use typed AppConfig with BackendConfig interface
    // Proper type safety without type assertions
    const hosts = config.hosts || config.config?.hosts

    if (hosts && Array.isArray(hosts) && hosts.length > 0) {
      // Validate that each host has required fields
      const validHosts = hosts.filter((h) => h.id && h.name && h.ip)
      if (validHosts.length > 0) {
        // Backend provided valid host configuration
        AVAILABLE_HOSTS = validHosts
        logger.debug('Loaded hosts from backend:', validHosts.length)
      } else {
        logger.warn('Backend hosts array contained no valid hosts, using defaults')
      }
    } else {
      // Debug level - using defaults is expected when backend doesn't provide hosts
      logger.debug('Backend config does not contain hosts array, using defaults')
    }
  } catch (error) {
    logger.warn('Failed to load hosts from backend, using defaults:', error)
  }
}

// Initialize hosts configuration
loadHostsFromBackend()

export const useTerminalStore = defineStore('terminal', () => {
  // State
  const sessions = ref<Map<string, TerminalSession>>(new Map())
  const activeSessionId = ref<string | null>(null)
  const selectedHost = ref<HostConfig>(getAvailableHosts()[0]) // Default to main host
  const terminalTabs = ref<TerminalTab[]>([])
  const commandHistory = ref<Map<string, string[]>>(new Map()) // host.id -> commands[]
  const agentControlEnabled = ref<boolean>(false)

  // Computed
  const activeSession = computed(() => {
    return activeSessionId.value ? getSession(activeSessionId.value) : null
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
      controlState: 'agent',  // Default to agent control mode
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
    const session = getSession(sessionId)
    if (session) {
      session.status = status
      session.lastActivityAt = new Date()
    }
  }

  const updateControlState = (
    sessionId: string,
    controlState: 'user' | 'agent'
  ): void => {
    const session = getSession(sessionId)
    if (session) {
      session.controlState = controlState
      session.lastActivityAt = new Date()
    }
  }

  const setActiveSession = (sessionId: string | null): void => {
    activeSessionId.value = sessionId
  }

  const removeSession = (sessionId: string): void => {
    // Ensure sessions.value is a Map (handles persistence/hydration issues)
    // Type-safe conversion: When Pinia persists/restores, Map becomes Record<string, TerminalSession>
    if (!(sessions.value instanceof Map)) {
      type SessionEntry = [string, TerminalSession]
      const plainObject: Record<string, TerminalSession> = sessions.value as unknown as Record<string, TerminalSession>
      const entries: SessionEntry[] = Object.entries(plainObject)
      sessions.value = new Map(entries)
    }

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
    const hosts = getAvailableHosts()
    const found = hosts.find(host => host.id === hostId)
    if (!found) {
      logger.warn(`Host not found: ${hostId}, available hosts:`, hosts.map(h => h.id))
    }
    return found
  }

  // Get host by IP
  const getHostByIp = (ip: string): HostConfig | undefined => {
    return getAvailableHosts().find(host => host.ip === ip)
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

  // Ensure sessions is a Map (handles persistence/hydration issues)
  // Type-safe conversion: When Pinia persists/restores, Map becomes Record<string, TerminalSession>
  const ensureSessionsMap = (): Map<string, TerminalSession> => {
    if (!(sessions.value instanceof Map)) {
      type SessionEntry = [string, TerminalSession]
      const plainObject: Record<string, TerminalSession> = sessions.value as unknown as Record<string, TerminalSession>
      const entries: SessionEntry[] = Object.entries(plainObject)
      sessions.value = new Map(entries)
    }
    return sessions.value
  }

  // Get session by ID with Map safety
  const getSession = (sessionId: string): TerminalSession | undefined => {
    return ensureSessionsMap().get(sessionId)
  }

  // Cleanup all sessions
  const cleanup = (): void => {
    ensureSessionsMap().clear()
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
    getSession,
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
    paths: ['selectedHost'] // Only persist selectedHost (Map objects don't serialize to JSON correctly)
  }
})
