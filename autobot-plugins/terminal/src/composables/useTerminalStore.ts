// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { createLogger } from '../utils'

const logger = createLogger('TerminalStore')

export interface HostConfig {
  id: string
  name: string
  ip: string
  port: number
  description: string
}

export interface TerminalSession {
  id: string
  host: HostConfig
  status: 'disconnected' | 'connecting' | 'connected' | 'ready' | 'error' | 'reconnecting'
  controlState: 'user' | 'agent'
  createdAt: Date
  lastActivityAt: Date
}

export interface TerminalTab {
  id: string
  name: string
  sessionId: string
  host: HostConfig
  isActive: boolean
}

const DEFAULT_HOST: HostConfig = { id: 'main', name: 'Main', ip: '127.0.0.1', port: 22, description: 'Default SSH host' }

export const useTerminalStore = defineStore('autobot-terminal', () => {
  const sessions = ref<Map<string, TerminalSession>>(new Map())
  const activeSessionId = ref<string | null>(null)
  const selectedHost = ref<HostConfig>(DEFAULT_HOST)
  const terminalTabs = ref<TerminalTab[]>([])
  const commandHistory = ref<Map<string, string[]>>(new Map())
  const agentControlEnabled = ref(false)

  const activeSession = computed(() => activeSessionId.value ? getSession(activeSessionId.value) : null)
  const activeTabs = computed(() => terminalTabs.value.filter(t => t.isActive))
  const connectedSessions = computed(() =>
    Array.from(sessions.value.values()).filter(s => s.status === 'connected' || s.status === 'ready')
  )

  const ensureMap = () => {
    if (!(sessions.value instanceof Map)) {
      sessions.value = new Map(Object.entries(sessions.value as unknown as Record<string, TerminalSession>))
    }
    return sessions.value
  }

  const ensureCommandHistoryMap = () => {
    if (!(commandHistory.value instanceof Map)) {
      commandHistory.value = new Map(Object.entries(commandHistory.value as unknown as Record<string, string[]>))
    }
    return commandHistory.value
  }

  const getSession = (id: string) => ensureMap().get(id)

  const createSession = (id: string, host: HostConfig): TerminalSession => {
    const s: TerminalSession = { id, host, status: 'disconnected', controlState: 'agent', createdAt: new Date(), lastActivityAt: new Date() }
    sessions.value.set(id, s); return s
  }

  const updateSessionStatus = (id: string, status: TerminalSession['status']) => {
    const s = getSession(id); if (s) { s.status = status; s.lastActivityAt = new Date() }
  }

  const setActiveSession = (id: string | null) => { activeSessionId.value = id }

  const removeSession = (id: string) => {
    ensureMap().delete(id)
    if (activeSessionId.value === id) activeSessionId.value = null
  }

  const setSelectedHost = (host: HostConfig) => { selectedHost.value = host }

  const addCommandToHistory = (hostId: string, command: string) => {
    const hist = ensureCommandHistoryMap()
    if (!hist.has(hostId)) hist.set(hostId, [])
    const h = hist.get(hostId)!
    if (h[h.length - 1] !== command) { h.push(command); if (h.length > 100) h.shift() }
  }

  const getCommandHistory = (hostId: string) => ensureCommandHistoryMap().get(hostId) || []

  const addTab = (tab: TerminalTab) => {
    terminalTabs.value.forEach(t => (t.isActive = false))
    terminalTabs.value.push({ ...tab, isActive: true })
  }

  const removeTab = (id: string) => {
    const i = terminalTabs.value.findIndex(t => t.id === id)
    if (i !== -1) {
      terminalTabs.value.splice(i, 1)
      if (terminalTabs.value.length > 0) terminalTabs.value[Math.max(0, i - 1)].isActive = true
    }
  }

  const setActiveTab = (id: string) => terminalTabs.value.forEach(t => (t.isActive = t.id === id))

  const cleanup = () => { ensureMap().clear(); terminalTabs.value = []; activeSessionId.value = null }

  logger.debug('Terminal store initialized')

  return {
    sessions, activeSessionId, selectedHost, terminalTabs, commandHistory, agentControlEnabled,
    activeSession, activeTabs, connectedSessions,
    getSession, createSession, updateSessionStatus, setActiveSession, removeSession,
    setSelectedHost, addCommandToHistory, getCommandHistory, addTab, removeTab, setActiveTab, cleanup,
  }
})
