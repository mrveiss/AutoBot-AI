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
  type?: 'thought' | 'planning' | 'debug' | 'utility' | 'sources' | 'json' | 'response' | 'message' | 'command_approval_request' | 'overseer_plan' | 'overseer_step' | 'terminal_output' | 'terminal_command' // For filtering
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

// Issue #608: User context for session tracking
export interface UserContext {
  id: string
  username: string
  displayName?: string
  role?: 'owner' | 'collaborator' | 'viewer'
}

// Issue #608: Activity tracking within sessions
export interface SessionActivity {
  id: string
  type: 'terminal' | 'file' | 'browser' | 'desktop'
  userId: string
  content: string
  secretsUsed?: string[]
  timestamp: Date
  metadata?: Record<string, unknown>
}

// Issue #608: Session secret reference (not the actual value)
export interface SessionSecret {
  id: string
  name: string
  type: 'api_key' | 'token' | 'password' | 'ssh_key' | 'certificate'
  scope: 'user' | 'session' | 'shared'
  ownerId: string
  usageCount: number
}

export interface ChatSession {
  id: string
  title: string
  messages: ChatMessage[]
  createdAt: Date
  updatedAt: Date
  isActive: boolean
  // Issue #608: User-centric session tracking
  owner?: UserContext
  collaborators?: UserContext[]
  mode?: 'single_user' | 'collaborative'
  // Issue #608: Activity tracking (terminal, file, browser, desktop)
  activities?: SessionActivity[]
  // Issue #608: Session-scoped secrets
  sessionSecrets?: SessionSecret[]
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
  // Issue #691: Track streaming preview text for real-time feedback
  const streamingPreview = ref<string>('')
  // Issue #680: Track pending approval state to prevent polling race conditions
  const hasPendingApproval = ref(false)
  const sidebarCollapsed = ref(false)
  // Issue #671: Track initialization state for loading indicators
  const isInitializing = ref(false)
  const initializationError = ref<string | null>(null)
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

    // Issue #709: Reset typing state when creating new session
    // This prevents stale typing indicator from previous session
    isTyping.value = false
    streamingPreview.value = ''

    return sessionId
  }

  function switchToSession(sessionId: string) {
    const session = sessions.value.find(s => s.id === sessionId)
    if (session) {
      // Deactivate other sessions
      sessions.value.forEach(s => { s.isActive = false })
      session.isActive = true
      currentSessionId.value = sessionId

      // Issue #709: Reset typing state when switching sessions
      // This prevents stale typing indicator from previous session
      isTyping.value = false
      streamingPreview.value = ''
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
   * Issue #656: Enhanced with version-based updates to prevent processing old chunks.
   *
   * Used for streaming messages where chunks arrive with the same ID.
   * The version field (from StreamingMessage) ensures we only process newer updates.
   *
   * @param message - Message with optional id and version fields
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
        const existing = currentSession.value!.messages[existingIndex]

        // Issue #656: Version-based deduplication - skip if we already have this or newer version
        const incomingVersion = message.metadata?.version ?? 0
        const existingVersion = existing.metadata?.version ?? 0

        if (incomingVersion <= existingVersion) {
          // Already processed this version, skip update
          logger.debug(`[Issue #656] Skipping old version: incoming=${incomingVersion}, existing=${existingVersion}`)
          return message.id
        }

        // Update existing message (streaming chunk accumulation)
        currentSession.value!.messages[existingIndex] = {
          ...existing,
          content: message.content,  // Replace with accumulated content
          type: message.type || existing.type,  // Issue #650: Preserve display type
          metadata: {
            ...existing.metadata,
            ...message.metadata,
            version: incomingVersion  // Track version for next comparison
          }
        }
        currentSession.value!.updatedAt = new Date()
        logger.debug(`[Issue #656] Updated message ${message.id} to version ${incomingVersion}`)
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
    logger.debug(`[Issue #656] Added new message: ${newMessage.id}, version: ${message.metadata?.version ?? 0}`)

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
    // Issue #691: Clear streaming preview when typing stops
    if (!typing) {
      streamingPreview.value = ''
    }
  }

  // Issue #691: Set streaming preview text for real-time feedback during LLM generation
  function setStreamingPreview(preview: string) {
    streamingPreview.value = preview
  }

  // Issue #680: Pending approval state management to prevent polling race conditions
  function setPendingApproval(pending: boolean) {
    hasPendingApproval.value = pending
  }

  // Issue #671: Initialization state management for loading feedback
  function setInitializing(value: boolean) {
    isInitializing.value = value
    if (value) {
      // Clear any previous error when starting initialization
      initializationError.value = null
    }
  }

  function setInitializationError(error: string | null) {
    initializationError.value = error
    if (error) {
      // Stop initializing when error occurs
      isInitializing.value = false
    }
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

    // Issue #709: Reset typing state after sync to clear any stale state
    // Issue #820: Only reset if not actively streaming to prevent interrupting active streams
    const isActivelyStreaming = isTyping.value && streamingPreview.value.length > 0
    if (!hasPendingApproval.value && !isActivelyStreaming) {
      isTyping.value = false
      streamingPreview.value = ''
    }

    logger.debug(`✅ Session sync complete: ${sessions.value.length} sessions in store`)
  }

  // Desktop session management
  function createDesktopSession(sessionId: string): string {
    const session = sessions.value.find(s => s.id === sessionId)
    if (!session) return ''

    // Generate unique desktop session ID (#821: add random suffix to prevent collision)
    const desktopSessionId = `desktop-${sessionId}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`

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

  // ==================== ISSUE #608: USER-CENTRIC SESSION TRACKING ====================

  /**
   * Set the owner of a session.
   * Issue #608: User-centric session tracking.
   *
   * @param sessionId - The session to update
   * @param owner - The owner user context
   */
  function setSessionOwner(sessionId: string, owner: UserContext): boolean {
    const session = sessions.value.find(s => s.id === sessionId)
    if (!session) return false

    session.owner = owner
    session.mode = session.collaborators?.length ? 'collaborative' : 'single_user'
    session.updatedAt = new Date()
    logger.debug(`[Issue #608] Set session ${sessionId} owner to ${owner.username}`)
    return true
  }

  /**
   * Add a collaborator to a session.
   * Issue #608: Multi-user collaborative mode support.
   *
   * @param sessionId - The session to update
   * @param collaborator - The collaborator user context
   */
  function addSessionCollaborator(sessionId: string, collaborator: UserContext): boolean {
    const session = sessions.value.find(s => s.id === sessionId)
    if (!session) return false

    if (!session.collaborators) {
      session.collaborators = []
    }

    // Check if already a collaborator
    if (session.collaborators.some(c => c.id === collaborator.id)) {
      logger.debug(`[Issue #608] User ${collaborator.username} is already a collaborator`)
      return false
    }

    session.collaborators.push({ ...collaborator, role: 'collaborator' })
    session.mode = 'collaborative'
    session.updatedAt = new Date()
    logger.debug(`[Issue #608] Added collaborator ${collaborator.username} to session ${sessionId}`)
    return true
  }

  /**
   * Remove a collaborator from a session.
   * Issue #608: Multi-user collaborative mode support.
   *
   * @param sessionId - The session to update
   * @param collaboratorId - The collaborator user ID to remove
   */
  function removeSessionCollaborator(sessionId: string, collaboratorId: string): boolean {
    const session = sessions.value.find(s => s.id === sessionId)
    if (!session || !session.collaborators) return false

    const index = session.collaborators.findIndex(c => c.id === collaboratorId)
    if (index === -1) return false

    session.collaborators.splice(index, 1)

    // Update mode if no more collaborators
    if (session.collaborators.length === 0) {
      session.mode = 'single_user'
    }

    session.updatedAt = new Date()
    logger.debug(`[Issue #608] Removed collaborator ${collaboratorId} from session ${sessionId}`)
    return true
  }

  /**
   * Add an activity to a session.
   * Issue #608: Activity tracking within sessions.
   *
   * @param sessionId - The session to update
   * @param activity - The activity to add (without id and timestamp)
   */
  function addSessionActivity(
    sessionId: string,
    activity: Omit<SessionActivity, 'id' | 'timestamp'>
  ): string | null {
    const session = sessions.value.find(s => s.id === sessionId)
    if (!session) return null

    if (!session.activities) {
      session.activities = []
    }

    const newActivity: SessionActivity = {
      id: generateMessageId(), // Reuse message ID generator
      timestamp: new Date(),
      ...activity
    }

    session.activities.push(newActivity)
    session.updatedAt = new Date()
    logger.debug(`[Issue #608] Added ${activity.type} activity to session ${sessionId}`)
    return newActivity.id
  }

  /**
   * Get activities for a session with optional filtering.
   * Issue #608: Activity tracking within sessions.
   *
   * @param sessionId - The session to query
   * @param filters - Optional filters for activity type and user
   */
  function getSessionActivities(
    sessionId: string,
    filters?: { type?: SessionActivity['type']; userId?: string }
  ): SessionActivity[] {
    const session = sessions.value.find(s => s.id === sessionId)
    if (!session?.activities) return []

    let activities = [...session.activities]

    if (filters?.type) {
      activities = activities.filter(a => a.type === filters.type)
    }

    if (filters?.userId) {
      activities = activities.filter(a => a.userId === filters.userId)
    }

    // Sort by timestamp descending
    return activities.sort((a, b) => b.timestamp.getTime() - a.timestamp.getTime())
  }

  /**
   * Add a session-scoped secret reference.
   * Issue #608: Secret ownership model.
   * Note: This only stores metadata, not the actual secret value.
   *
   * @param sessionId - The session to update
   * @param secret - The secret reference (without usage count)
   */
  function addSessionSecret(
    sessionId: string,
    secret: Omit<SessionSecret, 'usageCount'>
  ): boolean {
    const session = sessions.value.find(s => s.id === sessionId)
    if (!session) return false

    if (!session.sessionSecrets) {
      session.sessionSecrets = []
    }

    // Check if secret already added
    if (session.sessionSecrets.some(s => s.id === secret.id)) {
      logger.debug(`[Issue #608] Secret ${secret.name} already in session`)
      return false
    }

    session.sessionSecrets.push({ ...secret, usageCount: 0 })
    session.updatedAt = new Date()
    logger.debug(`[Issue #608] Added session secret ${secret.name} to session ${sessionId}`)
    return true
  }

  /**
   * Remove a session-scoped secret reference.
   * Issue #608: Secret ownership model.
   *
   * @param sessionId - The session to update
   * @param secretId - The secret ID to remove
   */
  function removeSessionSecret(sessionId: string, secretId: string): boolean {
    const session = sessions.value.find(s => s.id === sessionId)
    if (!session?.sessionSecrets) return false

    const index = session.sessionSecrets.findIndex(s => s.id === secretId)
    if (index === -1) return false

    session.sessionSecrets.splice(index, 1)
    session.updatedAt = new Date()
    logger.debug(`[Issue #608] Removed secret ${secretId} from session ${sessionId}`)
    return true
  }

  /**
   * Increment the usage count for a session secret.
   * Issue #608: Secret usage tracking.
   *
   * @param sessionId - The session containing the secret
   * @param secretId - The secret ID to update
   */
  function incrementSecretUsage(sessionId: string, secretId: string): boolean {
    const session = sessions.value.find(s => s.id === sessionId)
    if (!session?.sessionSecrets) return false

    const secret = session.sessionSecrets.find(s => s.id === secretId)
    if (!secret) return false

    secret.usageCount++
    logger.debug(`[Issue #608] Secret ${secretId} usage count: ${secret.usageCount}`)
    return true
  }

  /**
   * Get the current user context for a session.
   * Issue #608: User-centric session tracking.
   *
   * @param sessionId - The session to query
   * @param userId - The user ID to check
   * @returns The user's role in the session, or null if not a participant
   */
  function getUserSessionRole(sessionId: string, userId: string): UserContext['role'] | null {
    const session = sessions.value.find(s => s.id === sessionId)
    if (!session) return null

    if (session.owner?.id === userId) {
      return 'owner'
    }

    const collaborator = session.collaborators?.find(c => c.id === userId)
    return collaborator?.role || null
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
    streamingPreview,  // Issue #691: Streaming preview text
    hasPendingApproval,  // Issue #680: Pending approval state
    sidebarCollapsed,
    settings,
    // Issue #671: Initialization state for loading indicators
    isInitializing,
    initializationError,

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
    setStreamingPreview,  // Issue #691: Streaming preview text management
    setPendingApproval,  // Issue #680: Pending approval state management
    // Issue #671: Initialization state management
    setInitializing,
    setInitializationError,
    exportSession,
    importSession,
    syncSessionsWithBackend,
    // Desktop session management
    createDesktopSession,
    getDesktopUrl,
    updateDesktopContext,
    getDesktopContext,
    // Issue #608: User-centric session tracking
    setSessionOwner,
    addSessionCollaborator,
    removeSessionCollaborator,
    addSessionActivity,
    getSessionActivities,
    addSessionSecret,
    removeSessionSecret,
    incrementSecretUsage,
    getUserSessionRole,
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
              // Issue #608: Handle activity timestamps
              activities: session.activities?.map((activity: any) => ({
                ...activity,
                timestamp: new Date(activity.timestamp)
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
