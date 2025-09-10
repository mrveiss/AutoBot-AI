import { ref, computed } from 'vue'
import { defineStore } from 'pinia'
import { generateChatId, generateMessageId } from '@/utils/ChatIdGenerator.js'

export interface ChatMessage {
  id: string
  content: string
  sender: 'user' | 'assistant' | 'system'
  timestamp: Date
  status?: 'sending' | 'sent' | 'error'
  type?: 'thought' | 'planning' | 'debug' | 'utility' | 'sources' | 'json' | 'response' | 'message' // For filtering
  attachments?: Array<{
    id: string
    name: string
    type: string
    size: number
    url: string
  }>
  metadata?: {
    model?: string
    tokens?: number
    duration?: number
    [key: string]: any // Allow additional metadata fields
  }
}

export interface ChatSession {
  id: string
  title: string
  messages: ChatMessage[]
  createdAt: Date
  updatedAt: Date
  isActive: boolean
  // Desktop automation context
  desktopSession?: {
    vncUrl?: string
    sessionId?: string
    lastActivity?: Date
    automationContext?: Record<string, any>
  }
}

export interface ChatSettings {
  model: string
  temperature: number
  maxTokens: number
  systemPrompt: string
  autoSave: boolean
  persistHistory: boolean
}

export const useChatStore = defineStore('chat', () => {
  // State
  const sessions = ref<ChatSession[]>([])
  const currentSessionId = ref<string | null>(null)
  const isTyping = ref(false)
  const sidebarCollapsed = ref(false)
  const settings = ref<ChatSettings>({
    model: 'gpt-4',
    temperature: 0.7,
    maxTokens: 2048,
    systemPrompt: '',
    autoSave: true,
    persistHistory: true
  })

  // Computed
  const currentSession = computed(() =>
    sessions.value.find(session => session.id === currentSessionId.value)
  )

  const currentMessages = computed(() =>
    currentSession.value?.messages || []
  )

  const sessionCount = computed(() => sessions.value.length)

  const hasActiveSessions = computed(() => sessionCount.value > 0)

  // Actions
  function createNewSession(title?: string): string {
    const sessionId = generateChatId()
    const newSession: ChatSession = {
      id: sessionId,
      title: title || `Chat ${sessions.value.length + 1}`,
      messages: [],
      createdAt: new Date(),
      updatedAt: new Date(),
      isActive: true
    }

    // Deactivate other sessions
    sessions.value.forEach(session => { session.isActive = false })

    sessions.value.unshift(newSession)
    currentSessionId.value = sessionId

    return sessionId
  }

  function switchToSession(sessionId: string) {
    const session = sessions.value.find(s => s.id === sessionId)
    if (session) {
      // Deactivate other sessions
      sessions.value.forEach(s => { s.isActive = false })
      session.isActive = true
      currentSessionId.value = sessionId
    }
  }

  function addMessage(message: Omit<ChatMessage, 'id' | 'timestamp'>) {
    if (!currentSession.value) {
      createNewSession()
    }

    const newMessage: ChatMessage = {
      id: generateMessageId(),
      timestamp: new Date(),
      ...message
    }

    currentSession.value!.messages.push(newMessage)
    currentSession.value!.updatedAt = new Date()

    return newMessage.id
  }

  function updateMessage(messageId: string, updates: Partial<ChatMessage>) {
    if (!currentSession.value) return

    const messageIndex = currentSession.value.messages.findIndex(m => m.id === messageId)
    if (messageIndex !== -1) {
      currentSession.value.messages[messageIndex] = {
        ...currentSession.value.messages[messageIndex],
        ...updates
      }
      currentSession.value.updatedAt = new Date()
    }
  }

  function deleteMessage(messageId: string) {
    if (!currentSession.value) return

    const messageIndex = currentSession.value.messages.findIndex(m => m.id === messageId)
    if (messageIndex !== -1) {
      currentSession.value.messages.splice(messageIndex, 1)
      currentSession.value.updatedAt = new Date()
    }
  }

  function deleteSession(sessionId: string) {
    const sessionIndex = sessions.value.findIndex(s => s.id === sessionId)
    if (sessionIndex !== -1) {
      sessions.value.splice(sessionIndex, 1)

      // If deleted session was current, switch to another or create new
      if (currentSessionId.value === sessionId) {
        if (sessions.value.length > 0) {
          switchToSession(sessions.value[0].id)
        } else {
          currentSessionId.value = null
        }
      }
    }
  }

  function updateSessionTitle(sessionId: string, title: string) {
    const session = sessions.value.find(s => s.id === sessionId)
    if (session) {
      session.title = title
      session.updatedAt = new Date()
    }
  }

  function clearAllSessions() {
    sessions.value = []
    currentSessionId.value = null
  }

  function updateSettings(newSettings: Partial<ChatSettings>) {
    settings.value = { ...settings.value, ...newSettings }
  }

  function toggleSidebar() {
    sidebarCollapsed.value = !sidebarCollapsed.value
  }

  function setTyping(typing: boolean) {
    isTyping.value = typing
  }

  // Persistence helpers
  function exportSession(sessionId: string): ChatSession | null {
    return sessions.value.find(s => s.id === sessionId) || null
  }

  function importSession(session: ChatSession) {
    // Ensure unique ID
    const existingSession = sessions.value.find(s => s.id === session.id)
    if (existingSession) {
      session.id = `${session.id}-imported-${Date.now()}`
    }

    sessions.value.push(session)
  }

  // Desktop session management
  function createDesktopSession(sessionId: string): string {
    const session = sessions.value.find(s => s.id === sessionId)
    if (!session) return ''

    // Generate unique desktop session ID
    const desktopSessionId = `desktop-${sessionId}-${Date.now()}`
    
    // Initialize desktop session if not exists
    if (!session.desktopSession) {
      session.desktopSession = {
        sessionId: desktopSessionId,
        lastActivity: new Date(),
        automationContext: {}
      }
    }

    return desktopSessionId
  }

  function getDesktopUrl(sessionId: string): string {
    const session = sessions.value.find(s => s.id === sessionId)
    if (!session?.desktopSession) {
      // Create desktop session if it doesn't exist
      createDesktopSession(sessionId)
    }

    // Generate per-chat desktop URL with session context
    const baseUrl = import.meta.env.VITE_DESKTOP_VNC_URL || 'http://172.16.168.20:6080/vnc.html'
    const params = new URLSearchParams({
      autoconnect: 'true',
      password: 'autobot',
      resize: 'remote',
      reconnect: 'true',
      quality: '9',
      compression: '9',
      // Add chat session context for future automation
      chatSession: sessionId,
      desktopSession: session.desktopSession?.sessionId || '',
      // Enable automation tracking
      automationMode: 'true'
    })

    const desktopUrl = `${baseUrl}?${params.toString()}`
    
    // Cache the URL in session
    if (session.desktopSession) {
      session.desktopSession.vncUrl = desktopUrl
      session.desktopSession.lastActivity = new Date()
    }

    return desktopUrl
  }

  function updateDesktopContext(sessionId: string, context: Record<string, any>) {
    const session = sessions.value.find(s => s.id === sessionId)
    if (!session?.desktopSession) {
      createDesktopSession(sessionId)
    }

    if (session.desktopSession) {
      session.desktopSession.automationContext = {
        ...session.desktopSession.automationContext,
        ...context
      }
      session.desktopSession.lastActivity = new Date()
    }
  }

  function getDesktopContext(sessionId: string): Record<string, any> {
    const session = sessions.value.find(s => s.id === sessionId)
    return session?.desktopSession?.automationContext || {}
  }

  return {
    // State
    sessions,
    currentSessionId,
    isTyping,
    sidebarCollapsed,
    settings,

    // Computed
    currentSession,
    currentMessages,
    sessionCount,
    hasActiveSessions,

    // Actions
    createNewSession,
    switchToSession,
    addMessage,
    updateMessage,
    deleteMessage,
    deleteSession,
    updateSessionTitle,
    clearAllSessions,
    updateSettings,
    toggleSidebar,
    setTyping,
    exportSession,
    importSession,
    // Desktop session management
    createDesktopSession,
    getDesktopUrl,
    updateDesktopContext,
    getDesktopContext
  }
}, {
  persist: {
    key: 'autobot-chat-store',
    storage: localStorage,
    // Only persist essential chat data, not sensitive information
    paths: ['sessions', 'currentSessionId', 'settings.autoSave', 'settings.persistHistory', 'sidebarCollapsed'],
    // Exclude sensitive settings like API keys, system prompts, etc.
    serializer: {
      deserialize: (value: string) => {
        try {
          const parsed = JSON.parse(value)
          // Convert timestamp strings back to Date objects
          if (parsed.sessions) {
            parsed.sessions = parsed.sessions.map((session: any) => ({
              ...session,
              createdAt: new Date(session.createdAt),
              updatedAt: new Date(session.updatedAt),
              messages: session.messages.map((msg: any) => ({
                ...msg,
                timestamp: new Date(msg.timestamp)
              })),
              // Handle desktop session dates
              desktopSession: session.desktopSession ? {
                ...session.desktopSession,
                lastActivity: session.desktopSession.lastActivity ? new Date(session.desktopSession.lastActivity) : undefined
              } : undefined
            }))
          }
          return parsed
        } catch {
          return {}
        }
      },
      serialize: JSON.stringify
    }
  }
})
