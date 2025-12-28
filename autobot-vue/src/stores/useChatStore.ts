import { ref, computed } from 'vue'
import { defineStore } from 'pinia'
import { generateChatId, generateMessageId } from '@/utils/ChatIdGenerator.js'
import { NetworkConstants } from '@/constants/network'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('useChatStore')

export interface ChatMessage {
  id: string
  content: string
  sender: 'user' | 'assistant' | 'system'
  timestamp: Date
  status?: 'sending' | 'sent' | 'error'
  error?: string // Error message if status is 'error'
  type?: 'thought' | 'planning' | 'debug' | 'utility' | 'sources' | 'json' | 'response' | 'message' | 'command_approval_request' // For filtering
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

  /**
   * Issue #650: Add or update a message with ID-based deduplication.
   * Used for streaming messages where chunks arrive with the same ID.
   *
   * @param message - Message with optional id field
   * @returns The message ID (new or existing)
   */
  function addOrUpdateMessage(message: Partial<ChatMessage> & { content: string; sender: ChatMessage['sender'] }): string {
    if (!currentSession.value) {
      createNewSession()
    }

    // If message has an ID, check if it already exists (streaming update)
    if (message.id) {
      const existingIndex = currentSession.value!.messages.findIndex(m => m.id === message.id)
      if (existingIndex >= 0) {
        // Update existing message (streaming chunk accumulation)
        const existing = currentSession.value!.messages[existingIndex]
        currentSession.value!.messages[existingIndex] = {
          ...existing,
          content: message.content,  // Replace with accumulated content
          type: message.type || existing.type,  // Issue #650: Preserve display type
          metadata: {
            ...existing.metadata,
            ...message.metadata
          }
        }
        currentSession.value!.updatedAt = new Date()
        logger.debug(`[Issue #650] Updated existing message: ${message.id}`)
        return message.id
      }
    }

    // Add new message
    const newMessage: ChatMessage = {
      id: message.id || generateMessageId(),
      timestamp: new Date(),
      content: message.content,
      sender: message.sender,
      type: message.type,
      status: message.status,
      metadata: message.metadata
    }

    currentSession.value!.messages.push(newMessage)
    currentSession.value!.updatedAt = new Date()
    logger.debug(`[Issue #650] Added new message: ${newMessage.id}`)

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

  /**
   * Update metadata for a specific message.
   * Properly triggers Vue reactivity for nested metadata updates.
   *
   * @param messageId - The message ID to update
   * @param metadataUpdates - Partial metadata to merge
   * @returns true if message was found and updated
   */
  function updateMessageMetadata(messageId: string, metadataUpdates: Record<string, any>): boolean {
    if (!currentSession.value) return false

    const messageIndex = currentSession.value.messages.findIndex(m => m.id === messageId)
    if (messageIndex !== -1) {
      const message = currentSession.value.messages[messageIndex]
      // Create new message object to ensure Vue reactivity
      currentSession.value.messages[messageIndex] = {
        ...message,
        metadata: {
          ...message.metadata,
          ...metadataUpdates
        }
      }
      currentSession.value.updatedAt = new Date()
      logger.debug(`[METADATA] Updated message ${messageId} metadata:`, metadataUpdates)
      return true
    }
    logger.warn(`[METADATA] Message not found for metadata update: ${messageId}`)
    return false
  }

  /**
   * Find a message by metadata criteria.
   * Helper for finding messages to update (e.g., approval status).
   *
   * @param criteria - Metadata key-value pairs to match
   * @returns The matching message or undefined
   */
  function findMessageByMetadata(criteria: Record<string, any>): ChatMessage | undefined {
    if (!currentSession.value) return undefined

    return currentSession.value.messages.find(msg => {
      if (!msg.metadata) return false
      return Object.entries(criteria).every(
        ([key, value]) => msg.metadata?.[key] === value
      )
    })
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
    logger.debug(`🗑️ Attempting to delete session: ${sessionId}`)

    const sessionIndex = sessions.value.findIndex(s => s.id === sessionId)
    if (sessionIndex === -1) {
      logger.warn(`⚠️ Session ${sessionId} not found in store`)
      return false // Session doesn't exist
    }

    const session = sessions.value[sessionIndex]
    logger.debug(`📝 Found session to delete: "${session.title}" (${sessionId})`)

    // Store count before deletion for verification
    const beforeCount = sessions.value.length

    // Remove session from array
    sessions.value.splice(sessionIndex, 1)

    // CRITICAL FIX: Reset typing indicator to prevent stuck "AI is typing..." state
    isTyping.value = false

    // Verify deletion occurred
    const afterCount = sessions.value.length
    const deletionSucceeded = afterCount === beforeCount - 1

    if (!deletionSucceeded) {
      logger.error(`❌ Session deletion failed - count before: ${beforeCount}, after: ${afterCount}`)
      return false
    }

    logger.debug(`✅ Session removed from array (${beforeCount} → ${afterCount})`)

    // If deleted session was current, switch to another or clear
    if (currentSessionId.value === sessionId) {
      if (sessions.value.length > 0) {
        logger.debug(`🔄 Switching to first available session: ${sessions.value[0].id}`)
        switchToSession(sessions.value[0].id)
      } else {
        logger.debug(`🔄 No sessions remaining, clearing current session`)
        currentSessionId.value = null
      }
    }

    // Force reactivity trigger to ensure Pinia persistence activates
    // This is critical for ensuring localStorage is updated
    sessions.value = [...sessions.value]

    logger.debug(`✅ Session ${sessionId} successfully deleted from store`)
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
    logger.debug(`🗑️ Clearing all ${sessions.value.length} sessions`)
    sessions.value = []
    currentSessionId.value = null
    isTyping.value = false // Reset typing indicator
    logger.debug(`✅ All sessions cleared`)
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
      logger.debug(`Session ${session.id} already exists, skipping import`)
      return
    }

    sessions.value.push(session)
  }

  function syncSessionsWithBackend(backendSessions: ChatSession[]) {
    /**
     * Synchronize store sessions with backend sessions.
     *
     * This is the SOURCE OF TRUTH sync:
     * - Backend sessions are authoritative
     * - Removes sessions that exist in store but not on backend (deleted sessions)
     * - Adds sessions that exist on backend but not in store (new sessions)
     * - Updates existing sessions with backend data
     *
     * This fixes the bug where deleted sessions reappear after page reload.
     */
    logger.debug(`🔄 Syncing sessions: Store has ${sessions.value.length}, Backend has ${backendSessions.length}`)

    const backendIds = new Set(backendSessions.map(s => s.id))
    const storeIds = new Set(sessions.value.map(s => s.id))

    // Find sessions to remove (exist in store but not on backend)
    const sessionsToRemove = sessions.value.filter(s => !backendIds.has(s.id))
    if (sessionsToRemove.length > 0) {
      logger.debug(`🗑️ Removing ${sessionsToRemove.length} stale sessions from store:`, sessionsToRemove.map(s => s.id))
      sessions.value = sessions.value.filter(s => backendIds.has(s.id))
    }

    // Find sessions to add (exist on backend but not in store)
    const sessionsToAdd = backendSessions.filter(s => !storeIds.has(s.id))
    if (sessionsToAdd.length > 0) {
      logger.debug(`➕ Adding ${sessionsToAdd.length} new sessions to store:`, sessionsToAdd.map(s => s.id))
      sessions.value.push(...sessionsToAdd)
    }

    // Update existing sessions with backend data (in case of changes)
    backendSessions.forEach(backendSession => {
      const storeSession = sessions.value.find(s => s.id === backendSession.id)
      if (storeSession) {
        // Update session data (preserve messages if loaded)
        storeSession.title = backendSession.title || storeSession.title
        storeSession.updatedAt = backendSession.updatedAt || storeSession.updatedAt
        storeSession.createdAt = backendSession.createdAt || storeSession.createdAt
        if (!storeSession.messages || storeSession.messages.length === 0) {
          storeSession.messages = backendSession.messages || []
        }
      }
    })

    logger.debug(`✅ Session sync complete: ${sessions.value.length} sessions in store`)
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
    let session = sessions.value.find(s => s.id === sessionId)
    if (!session?.desktopSession) {
      // Create desktop session if it doesn't exist
      createDesktopSession(sessionId)
      // Re-fetch session after creation
      session = sessions.value.find(s => s.id === sessionId)
    }

    // Guard: If session still doesn't exist, return default URL
    if (!session) {
      const baseUrl = import.meta.env.VITE_DESKTOP_VNC_URL || `http://${NetworkConstants.MAIN_MACHINE_IP}:${NetworkConstants.VNC_DESKTOP_PORT}/vnc.html`
      return baseUrl
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
    let session = sessions.value.find(s => s.id === sessionId)
    if (!session?.desktopSession) {
      createDesktopSession(sessionId)
      // Re-fetch session after creation
      session = sessions.value.find(s => s.id === sessionId)
    }

    // Guard: Exit if session doesn't exist
    if (!session) return

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
        logger.debug('📊 Persistence Debug:')
        logger.debug(`  Store sessions: ${sessions.value.length}`)
        logger.debug(`  Persisted sessions: ${parsed.sessions?.length || 0}`)
        logger.debug(`  Store currentSessionId: ${currentSessionId.value}`)
        logger.debug(`  Persisted currentSessionId: ${parsed.currentSessionId}`)

        // Check for specific session IDs
        const storeIds = sessions.value.map(s => s.id)
        const persistedIds = parsed.sessions?.map((s: any) => s.id) || []
        logger.debug(`  Store IDs: [${storeIds.join(', ')}]`)
        logger.debug(`  Persisted IDs: [${persistedIds.join(', ')}]`)

        // Find discrepancies
        const missingFromPersisted = storeIds.filter(id => !persistedIds.includes(id))
        const extraInPersisted = persistedIds.filter((id: string) => !storeIds.includes(id))

        if (missingFromPersisted.length > 0) {
          logger.warn(`⚠️ Sessions in store but not persisted: [${missingFromPersisted.join(', ')}]`)
        }
        if (extraInPersisted.length > 0) {
          logger.warn(`⚠️ Sessions persisted but not in store: [${extraInPersisted.join(', ')}]`)
        }

        if (missingFromPersisted.length === 0 && extraInPersisted.length === 0) {
          logger.debug('✅ Store and persistence are in sync')
        }
      } else {
        logger.debug('📊 No persisted data found in localStorage')
      }
    } catch (error) {
      logger.error('❌ Error checking persistence state:', error)
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
    addOrUpdateMessage,  // Issue #650: ID-based deduplication for streaming
    updateMessage,
    updateMessageMetadata,
    findMessageByMetadata,
    deleteMessage,
    deleteSession,
    updateSessionTitle,
    clearAllSessions,
    updateSettings,
    toggleSidebar,
    setTyping,
    exportSession,
    importSession,
    syncSessionsWithBackend,
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
