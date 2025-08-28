import { ref, computed } from 'vue'
import { defineStore } from 'pinia'

export interface ChatMessage {
  id: string
  content: string
  sender: 'user' | 'assistant' | 'system'
  timestamp: Date
  status?: 'sending' | 'sent' | 'error'
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
  }
}

export interface ChatSession {
  id: string
  title: string
  messages: ChatMessage[]
  createdAt: Date
  updatedAt: Date
  isActive: boolean
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
    const sessionId = `chat-${Date.now()}`
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
      id: `msg-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
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
    importSession
  }
})
