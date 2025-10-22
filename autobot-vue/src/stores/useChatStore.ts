import { ref, computed } from 'vue'
import { defineStore } from 'pinia'
import { generateChatId, generateMessageId } from '@/utils/ChatIdGenerator.js'
import { NetworkConstants } from '@/constants/network-constants.js'

export interface ChatMessage {
  id: string
  content: string
  sender: 'user' | 'assistant' | 'system'
  timestamp: Date
  status?: 'sending' | 'sent' | 'error'
  error?: string // Error message if status is 'error'
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
    id?: string
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

  function deleteSession(sessionId: string): boolean {
    // CRITICAL FIX: Enhanced session deletion with validation and persistence verification
    console.log(`🗑️ Attempting to delete session: ${sessionId}`)

    const sessionIndex = sessions.value.findIndex(s => s.id === sessionId)
    if (sessionIndex === -1) {
      console.warn(`⚠️ Session ${sessionId} not found in store`)
      return false // Session doesn't exist
    }

    const session = sessions.value[sessionIndex]
    console.log(`📝 Found session to delete: "${session.title}" (${sessionId})`)

    // Store count before deletion for verification
    const beforeCount = sessions.value.length

    // Remove session from array
    sessions.value.splice(sessionIndex, 1)

    // Verify deletion occurred
    const afterCount = sessions.value.length
    const deletionSucceeded = afterCount === beforeCount - 1

    if (!deletionSucceeded) {
      console.error(`❌ Session deletion failed - count before: ${beforeCount}, after: ${afterCount}`)
      return false
    }

    console.log(`✅ Session removed from array (${beforeCount} → ${afterCount})`)

    // If deleted session was current, switch to another or clear
    if (currentSessionId.value === sessionId) {
      if (sessions.value.length > 0) {
        console.log(`🔄 Switching to first available session: ${sessions.value[0].id}`)
        switchToSession(sessions.value[0].id)
      } else {
        console.log(`🔄 No sessions remaining, clearing current session`)
        currentSessionId.value = null
      }
    }

    // Force reactivity trigger to ensure Pinia persistence activates
    // This is critical for ensuring localStorage is updated
    sessions.value = [...sessions.value]

    console.log(`✅ Session ${sessionId} successfully deleted from store`)
    return true
  }

  function updateSessionTitle(sessionId: string, title: string) {
    const session = sessions.value.find(s => s.id === sessionId)
    if (session) {
      session.title = title
      session.updatedAt = new Date()
    }
  }

  function clearAllSessions() {
    console.log(`🗑️ Clearing all ${sessions.value.length} sessions`)
    sessions.value = []
    currentSessionId.value = null
    console.log(`✅ All sessions cleared`)
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
    // Skip if session already exists (prevent duplicate imports)
    const existingSession = sessions.value.find(s => s.id === session.id)
    if (existingSession) {
      console.log(`Session ${session.id} already exists, skipping import`)
      return
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
    const baseUrl = import.meta.env.VITE_DESKTOP_VNC_URL || `http://${NetworkConstants.MAIN_MACHINE_IP}:${NetworkConstants.VNC_DESKTOP_PORT}/vnc.html`
    const params = new URLSearchParams({
      autoconnect: 'true',
      password: import.meta.env.VITE_DESKTOP_VNC_PASSWORD || 'autobot',
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

  // CRITICAL FIX: Debug method to verify persistence state
  function debugPersistenceState(): void {
    try {
      const persistedData = localStorage.getItem('autobot-chat-store')
      if (persistedData) {
        const parsed = JSON.parse(persistedData)
        console.log('📊 Persistence Debug:')
        console.log(`  Store sessions: ${sessions.value.length}`)
        console.log(`  Persisted sessions: ${parsed.sessions?.length || 0}`)
        console.log(`  Store currentSessionId: ${currentSessionId.value}`)
        console.log(`  Persisted currentSessionId: ${parsed.currentSessionId}`)

        // Check for specific session IDs
        const storeIds = sessions.value.map(s => s.id)
        const persistedIds = parsed.sessions?.map((s: any) => s.id) || []
        console.log(`  Store IDs: [${storeIds.join(', ')}]`)
        console.log(`  Persisted IDs: [${persistedIds.join(', ')}]`)

        // Find discrepancies
        const missingFromPersisted = storeIds.filter(id => !persistedIds.includes(id))
        const extraInPersisted = persistedIds.filter((id: string) => !storeIds.includes(id))

        if (missingFromPersisted.length > 0) {
          console.warn(`⚠️ Sessions in store but not persisted: [${missingFromPersisted.join(', ')}]`)
        }
        if (extraInPersisted.length > 0) {
          console.warn(`⚠️ Sessions persisted but not in store: [${extraInPersisted.join(', ')}]`)
        }

        if (missingFromPersisted.length === 0 && extraInPersisted.length === 0) {
          console.log('✅ Store and persistence are in sync')
        }
      } else {
        console.log('📊 No persisted data found in localStorage')
      }
    } catch (error) {
      console.error('❌ Error checking persistence state:', error)
    }
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
    getDesktopContext,
    // Debug method
    debugPersistenceState
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
