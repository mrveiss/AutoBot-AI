import { useChatStore } from '@/stores/useChatStore'
import { useAppStore } from '@/stores/useAppStore'
import { chatRepository } from '@/models/repositories'
import apiClient from '@/utils/ApiClient'
import type { ChatSession } from '@/stores/useChatStore'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('ChatController')

export class ChatController {
  // FIXED: Lazy initialization - stores only created when accessed, not at module load
  private _chatStore?: ReturnType<typeof useChatStore>
  private _appStore?: ReturnType<typeof useAppStore>
  private retryAttempts = 3
  private retryDelay = 1000

  constructor() {
    // Stores will be initialized lazily when needed
  }

  // Lazy initialization of chatStore
  private get chatStore() {
    if (!this._chatStore) {
      this._chatStore = useChatStore()
    }
    return this._chatStore
  }

  // Lazy initialization of appStore
  private getAppStore(): ReturnType<typeof useAppStore> | null {
    if (!this._appStore) {
      try {
        this._appStore = useAppStore()
      } catch (error) {
        logger.warn('AppStore not available, running without store integration')
        return null
      }
    }
    return this._appStore
  }

  // Enhanced message operations with comprehensive error handling
  async sendMessage(content: string, options?: Record<string, any>): Promise<string> {
    try {
      this.getAppStore()?.setLoading(true, 'Sending message...')
      this.chatStore.setTyping(true)

      // Validate message content
      const validation = this.validateMessage(content)
      if (!validation.valid) {
        throw new Error(validation.error)
      }

      // Add user message to store with sending status
      const userMessageId = this.chatStore.addMessage({
        content,
        sender: 'user',
        status: 'sending'
      })

      // Ensure we have a current session
      if (!this.chatStore.currentSessionId) {
        await this.createNewSession()
      }

      let lastError: Error | null = null

      // Retry mechanism for message sending
      for (let attempt = 1; attempt <= this.retryAttempts; attempt++) {
        try {
          // Send to backend with timeout and retry logic
          const response = await this.sendMessageWithRetry({
            message: content,
            chatId: this.chatStore.currentSessionId!,
            options: options || {}
          }, attempt)

          // Update user message status to sent
          this.chatStore.updateMessage(userMessageId, { status: 'sent' })

          // Invalidate chat list cache since we added a new message
          apiClient.invalidateCache()

          // Handle response based on type
          if (response.type === 'streaming') {
            await this.handleStreamingResponse(response.response!)
          } else {
            this.handleJsonResponse(response.data)
          }

          return userMessageId // Success, exit retry loop

        } catch (error: any) {
          lastError = error
          logger.warn(`Message send attempt ${attempt}/${this.retryAttempts} failed:`, error.message)

          if (attempt < this.retryAttempts) {
            // Wait before retrying
            await new Promise(resolve => setTimeout(resolve, this.retryDelay * attempt))

            // Update user message with retry status
            this.chatStore.updateMessage(userMessageId, {
              status: 'sending',
              metadata: { retrying: true, attempt: attempt + 1 }
            })
          }
        }
      }

      // All retry attempts failed
      this.chatStore.updateMessage(userMessageId, { status: 'error' })

      // Add helpful error message for user
      this.chatStore.addMessage({
        content: `Failed to send message after ${this.retryAttempts} attempts: ${lastError?.message || 'Unknown error'}. Please check your connection and try again.`,
        sender: 'system',
        type: 'utility'
      })

      throw lastError || new Error('Failed to send message')

    } catch (error: any) {
      // Enhanced error handling with user-friendly messages
      const userFriendlyMessage = this.getUfriendlyErrorMessage(error)
      this.getAppStore()?.setGlobalError(userFriendlyMessage)
      throw error
    } finally {
      this.chatStore.setTyping(false)
      this.getAppStore()?.setLoading(false)
    }
  }

  private async sendMessageWithRetry(request: any, attempt: number): Promise<any> {
    try {
      // FIXED: Pass options parameter to preserve attachments and metadata
      return await chatRepository.sendMessage(request.message, request.chatId, request.options)
    } catch (error: any) {
      // Enhanced error context for debugging
      logger.error(`Chat message send attempt ${attempt} failed:`, {
        error: error.message,
        status: error.status,
        chatId: request.chatId,
        messageLength: request.message?.length,
        hasAttachments: request.options?.attachments?.length > 0,
        attempt
      })

      // If it's a 422 validation error, don't retry
      if (error.status === 422) {
        throw new Error(`Invalid message format: ${error.message}. Please check your input and try again.`)
      }

      // If it's a network error, add context
      if (error.name === 'NetworkError' || error.code === 'NETWORK_ERROR') {
        throw new Error(`Network connection failed. Please check your internet connection and try again.`)
      }

      throw error
    }
  }

  private getUfriendlyErrorMessage(error: any): string {
    if (error.status === 422) {
      return 'Invalid message format. Please check your input and try again.'
    }
    if (error.status === 404) {
      return 'Chat service not available. Please refresh the page and try again.'
    }
    if (error.status === 500) {
      return 'Server error occurred. Please try again in a moment.'
    }
    if (error.name === 'NetworkError') {
      return 'Network connection failed. Please check your internet connection.'
    }
    if (error.message?.includes('timeout')) {
      return 'Request timed out. Please try again with a shorter message.'
    }

    return `Failed to send message: ${error.message || 'Unknown error'}`
  }

  private async handleStreamingResponse(response: Response): Promise<void> {
    const reader = response.body?.getReader()
    if (!reader) {
      throw new Error('No response stream available')
    }

    // Issue #680: Agent Zero Pattern - Track messages by stable backend ID
    // Backend sends cumulative content with stable message_id - we just replace
    const messageIdMap = new Map<string, string>() // backend_id -> frontend_id
    let fallbackMessageId: string | null = null // For messages without backend ID

    const decoder = new TextDecoder()
    let buffer = ''

    try {
      logger.debug('Starting to read streaming response (Agent Zero pattern)')

      while (true) {
        const { done, value } = await reader.read()

        if (done) {
          logger.debug('Stream completed')
          break
        }

        // Decode chunk and add to buffer
        const chunk = decoder.decode(value, { stream: true })
        buffer += chunk

        // Process complete lines from buffer
        const lines = buffer.split('\n')
        buffer = lines.pop() || '' // Keep incomplete line in buffer

        for (const line of lines) {
          if (!line.trim()) continue

          if (line.startsWith('data: ')) {
            try {
              const jsonStr = line.slice(6).trim()
              if (!jsonStr) continue

              const data = JSON.parse(jsonStr)
              logger.debug('Received stream data:', data.type || 'unknown')

              // Handle control events
              if (data.type === 'start') {
                logger.debug('Stream started:', data.session_id)
                continue
              }
              if (data.type === 'end') {
                logger.debug('Stream ended')
                continue
              }
              if (data.type === 'segment_complete') {
                logger.debug(`Segment complete: ${data.metadata?.completed_type}`)
                // Mark the message as finalized
                const backendId = data.metadata?.message_id
                if (backendId && messageIdMap.has(backendId)) {
                  const frontendId = messageIdMap.get(backendId)!
                  this.chatStore.updateMessage(frontendId, { status: 'sent' })
                }
                continue
              }

              // Handle error events
              if (data.type === 'error') {
                logger.error('Stream error:', data.content)
                const errorMsgId = fallbackMessageId || this.chatStore.addMessage({
                  content: '',
                  sender: 'assistant'
                })
                this.chatStore.updateMessage(errorMsgId, {
                  content: `⚠️ Error: ${data.content || 'Stream error'}`,
                  status: 'error'
                })
                continue
              }

              // Skip messages without content
              if (!data.content && data.type !== 'command_approval_request') {
                continue
              }

              // Agent Zero Pattern: Use backend message_id for stable identity
              const backendMessageId = data.metadata?.message_id || data.id
              let frontendMessageId: string

              if (backendMessageId && messageIdMap.has(backendMessageId)) {
                // Existing message - update it (Agent Zero: always replace)
                frontendMessageId = messageIdMap.get(backendMessageId)!
              } else {
                // New message - create it
                const sender = data.type === 'terminal_output' ? 'system' : 'assistant'
                frontendMessageId = this.chatStore.addMessage({
                  content: '',
                  sender
                })
                if (backendMessageId) {
                  messageIdMap.set(backendMessageId, frontendMessageId)
                }
                fallbackMessageId = frontendMessageId
              }

              // Map backend type to frontend type
              const messageType = this.mapMessageType(data.type, data.metadata?.message_type)

              // Handle special message types
              if (data.type === 'command_approval_request') {
                this.chatStore.setTyping(false)
                // Issue #680: Set pending approval flag to prevent polling race conditions
                this.chatStore.setPendingApproval(true)
                this.chatStore.updateMessage(frontendMessageId, {
                  content: data.content || 'Command approval required',
                  type: 'command_approval_request',
                  metadata: {
                    ...data.metadata,
                    requires_approval: true,
                    approval_status: 'pending'
                  }
                })
                continue
              }

              // Agent Zero Pattern: Backend sends CUMULATIVE content - just replace
              // No local accumulation needed - content is already complete in each update
              this.chatStore.updateMessage(frontendMessageId, {
                content: data.content,
                type: messageType,
                metadata: data.metadata || {}
              })

            } catch (e) {
              logger.warn('Failed to parse stream data:', { line, error: e })
            }
          }
        }
      }

      // Finalize all messages
      for (const frontendId of messageIdMap.values()) {
        const msg = this.chatStore.currentSession?.messages.find(m => m.id === frontendId)
        if (msg && msg.content?.trim()) {
          this.chatStore.updateMessage(frontendId, { status: 'sent' })
        }
      }

      // Clean up empty messages
      for (const frontendId of messageIdMap.values()) {
        const msg = this.chatStore.currentSession?.messages.find(m => m.id === frontendId)
        if (msg && !msg.content?.trim()) {
          this.chatStore.deleteMessage(frontendId)
        }
      }

    } catch (error) {
      logger.error('Streaming response error:', error)
      if (fallbackMessageId) {
        this.chatStore.updateMessage(fallbackMessageId, {
          content: 'Response was interrupted due to an error.',
          status: 'error'
        })
      }
      throw error
    } finally {
      reader.releaseLock()
    }
  }

  /**
   * Map backend message type to frontend message type.
   * Agent Zero Pattern: Centralized type mapping for consistency.
   */
  private mapMessageType(
    backendType?: string,
    metadataType?: string
  ): 'thought' | 'planning' | 'debug' | 'utility' | 'sources' | 'json' | 'response' | undefined {
    const type = backendType || metadataType
    if (!type) return 'response'

    // Map backend types to frontend types
    if (type === 'thought' || type.includes('thought')) return 'thought'
    if (type.includes('planning')) return 'planning'
    if (type.includes('debug')) return 'debug'
    if (type.includes('utility')) return 'utility'
    if (type.includes('source')) return 'sources'
    if (type.includes('json')) return 'json'
    if (type === 'response' || type === 'llm_response' || type === 'llm_response_chunk') return 'response'

    // Default to response for unknown types
    return 'response'
  }

  private handleJsonResponse(data: any): void {
    // Add workflow messages first (thoughts, planning, debug, utility, sources)
    if (data.workflow_messages && Array.isArray(data.workflow_messages)) {
      data.workflow_messages.forEach((msg: any) => {
        this.chatStore.addMessage({
          content: msg.text || msg.content,
          sender: msg.sender || 'assistant',
          type: msg.type, // This enables filtering
          metadata: msg.metadata || {}
        })
      })
    }

    // FIXED: Support both legacy (data.response) and new (data.content) formats
    // Backend streaming endpoint returns { success: true, data: { content: "...", role: "assistant", ... } }
    // Legacy format was: { response: "..." }
    const responseContent = data.response || data.content

    // Add final response with enhanced metadata
    if (responseContent) {
      this.chatStore.addMessage({
        content: responseContent,
        sender: 'assistant',
        type: 'response', // Mark as final response
        metadata: {
          model: data.model,
          tokens: data.tokens_used,
          duration: data.response_time || data.processing_time,
          message_type: data.message_type,
          knowledge_status: data.knowledge_status,
          sources: data.sources,
          librarian_engaged: data.librarian_engaged,
          mcp_used: data.mcp_used
        }
      })
    }
  }

  // Enhanced session operations with error handling
  async createNewSession(title?: string): Promise<string> {
    try {
      this.getAppStore()?.setLoading(true, 'Creating new chat...')

      // Create session in store first for immediate UI feedback
      const sessionId = this.chatStore.createNewSession(title)

      // Sync with backend with retry logic
      try {
        await chatRepository.createNewChat(title)
        logger.debug('New chat session synced with backend:', sessionId)
      } catch (error) {
        logger.warn('Failed to sync new chat with backend, continuing with local session:', error)
        // Don't throw error here, allow local session to work
      }

      return sessionId

    } catch (error: any) {
      this.getAppStore()?.setGlobalError(`Failed to create chat: ${error.message}`)
      throw error
    } finally {
      this.getAppStore()?.setLoading(false)
    }
  }

  async loadChatSessions(): Promise<void> {
    try {
      this.getAppStore()?.setLoading(true, 'Loading chat sessions...')

      const sessions = await chatRepository.getChatList()

      // FIXED: Clear existing sessions before loading to prevent duplicates
      this.chatStore.clearAllSessions()

      // Update store with loaded sessions
      if (Array.isArray(sessions)) {
        sessions.forEach(session => {
          this.chatStore.importSession(session)
        })
        logger.debug(`Loaded ${sessions.length} chat sessions`)
      } else {
        logger.warn('getChatList() returned non-array value:', sessions)
      }

    } catch (error: any) {
      logger.error('Failed to load chat sessions:', error)
      // Don't throw error, allow app to continue with local sessions
      this.getAppStore()?.setGlobalError(`Failed to load chat sessions: ${error.message}`)
    } finally {
      this.getAppStore()?.setLoading(false)
    }
  }

  async loadChatMessages(sessionId: string): Promise<void> {
    try {
      // Issue #680: Skip loading while streaming or pending approval to prevent race conditions
      // During SSE streaming, messages are added in real-time and should not be overwritten
      // by polling which may have stale data from backend
      if (this.chatStore.isTyping) {
        logger.debug(`Skipping message load - streaming in progress (isTyping=true)`)
        return
      }
      if (this.chatStore.hasPendingApproval) {
        logger.debug(`Skipping message load - pending approval (hasPendingApproval=true)`)
        return
      }

      logger.debug(`Loading messages for session: ${sessionId}`)
      this.getAppStore()?.setLoading(true, 'Loading messages...')

      const messages = await chatRepository.getChatMessages(sessionId)
      logger.debug(`Received ${messages.length} messages from repository`)

      // Update session with loaded messages
      const session = this.chatStore.sessions.find(s => s.id === sessionId)
      if (session) {
        // CRITICAL FIX: Only update if message count or last message ID changed
        // This prevents UI flickering during polling when nothing changed
        const lastExisting = session.messages[session.messages.length - 1]
        const lastNew = messages[messages.length - 1]
        const hasChanges = session.messages.length !== messages.length ||
          lastExisting?.id !== lastNew?.id

        if (hasChanges) {
          logger.debug(`Updating messages (${session.messages.length} → ${messages.length})`)
          session.messages = messages as any
        } else {
          logger.debug(`No message changes, skipping update`)
        }

        // Only switch session if not already current
        if (this.chatStore.currentSessionId !== sessionId) {
          this.chatStore.switchToSession(sessionId)
        }
      } else {
        logger.error(`Session ${sessionId} not found in store`)
      }

    } catch (error: any) {
      logger.error('Failed to load messages:', error)
      this.getAppStore()?.setGlobalError(`Failed to load messages: ${error.message}`)
    } finally {
      this.getAppStore()?.setLoading(false)
    }
  }

  async saveChatSession(sessionId?: string): Promise<void> {
    const targetSessionId = sessionId || this.chatStore.currentSessionId
    if (!targetSessionId) return

    try {
      const session = this.chatStore.sessions.find(s => s.id === targetSessionId)
      if (!session) return

      // CRITICAL FIX Issue #259: Pass session title to backend for proper save
      await chatRepository.saveChatMessages({
        chatId: targetSessionId,
        messages: session.messages,
        name: session.title || ''
      })

      logger.debug('Chat session saved successfully:', targetSessionId)

    } catch (error: any) {
      logger.error('Failed to save chat session:', error)
      this.getAppStore()?.setGlobalError(`Failed to save chat: ${error.message}`)
    }
  }

// ============================================================================
  // Session Facts Methods (Issue #547)
  // ============================================================================

  /**
   * Get facts created during a session for pre-deletion preview.
   * Issue #547: Allows users to see and select facts to preserve before deletion.
   */
  async getSessionFacts(sessionId: string) {
    try {
      return await chatRepository.getSessionFacts(sessionId)
    } catch (error: any) {
      logger.error('Failed to get session facts:', error)
      throw error
    }
  }

  /**
   * Mark selected facts as preserved before session deletion.
   * Issue #547: Preserved facts will not be deleted with the session.
   */
  async preserveSessionFacts(sessionId: string, factIds: string[], preserve: boolean = true) {
    try {
      return await chatRepository.preserveSessionFacts(sessionId, factIds, preserve)
    } catch (error: any) {
      logger.error('Failed to preserve session facts:', error)
      throw error
    }
  }

  async deleteChatSession(
    sessionId: string,
    fileAction?: 'delete' | 'transfer_kb' | 'transfer_shared',
    fileOptions?: any
  ): Promise<void> {
    try {
      this.getAppStore()?.setLoading(true, 'Deleting chat...')

      // CRITICAL FIX: Enhanced deletion with proper error handling and persistence
      let backendDeleteSucceeded = false
      let storeDeleteSucceeded = false

      // Step 1: Try to delete from backend
      try {
        await chatRepository.deleteChat(sessionId, fileAction, fileOptions)
        if (fileAction) {
          logger.debug(`File action executed: ${fileAction}`, fileOptions)
        }
        backendDeleteSucceeded = true
        logger.debug('Chat successfully deleted from backend:', sessionId)
      } catch (error: any) {
        logger.error('Backend deletion failed:', error)
        // Don't throw yet - we'll handle this based on error type

        // If it's a 404 (chat not found), still proceed with local deletion
        if (error.status === 404) {
          logger.warn('Chat not found on backend, proceeding with local deletion')
          backendDeleteSucceeded = true // Treat as success since it's already gone
        } else {
          // For other errors, show user error but still try local deletion
          logger.warn('Backend deletion failed, but proceeding with local deletion to maintain consistency')
          this.getAppStore()?.setGlobalError(`Backend deletion failed: ${error.message}. Chat removed locally.`)
        }
      }

      // Step 2: Always try to remove from store for consistency
      try {
        // Store current sessions count for verification
        const beforeCount = this.chatStore.sessions.length

        // Delete from store
        this.chatStore.deleteSession(sessionId)

        // Verify deletion occurred
        const afterCount = this.chatStore.sessions.length
        if (afterCount < beforeCount) {
          storeDeleteSucceeded = true
          logger.debug('Chat successfully deleted from store:', sessionId)

          // CRITICAL FIX: Force persistence to ensure localStorage is updated immediately
          // Since Pinia persistence is automatic, we'll add a small delay to ensure it completes
          await new Promise(resolve => setTimeout(resolve, 100))

          // Verify persistence by checking localStorage directly
          try {
            const persistedData = localStorage.getItem('autobot-chat-store')
            if (persistedData) {
              const parsed = JSON.parse(persistedData)
              const persistedSession = parsed.sessions?.find((s: any) => s.id === sessionId)
              if (!persistedSession) {
                logger.debug('Chat deletion confirmed in localStorage')
              } else {
                logger.warn('Chat still exists in localStorage - persistence may have failed')
              }
            }
          } catch (persistError) {
            logger.warn('Could not verify localStorage persistence:', persistError)
          }

        } else {
          logger.warn('Store deletion did not reduce session count - session may not have existed')
          storeDeleteSucceeded = true // If it wasn't there, consider it a success
        }
      } catch (error: any) {
        logger.error('Store deletion failed:', error)
        throw new Error(`Failed to delete chat from local storage: ${error.message}`)
      }

      // Step 3: Report final status
      if (storeDeleteSucceeded) {
        logger.debug(`Chat session ${sessionId} successfully deleted (Backend: ${backendDeleteSucceeded ? 'Success' : 'Failed'}, Store: Success)`)
      } else {
        throw new Error('Failed to delete chat from local storage')
      }

    } catch (error: any) {
      logger.error('Failed to delete chat session:', error)
      this.getAppStore()?.setGlobalError(`Failed to delete chat: ${error.message}`)
      throw error // Re-throw to let caller handle
    } finally {
      this.getAppStore()?.setLoading(false)
    }
  }

  // Settings operations
  updateChatSettings(settings: Partial<any>): void {
    this.chatStore.updateSettings(settings)
  }

  // UI operations
  toggleSidebar(): void {
    this.chatStore.toggleSidebar()
  }

  async switchToSession(sessionId: string): Promise<void> {
    logger.debug(`Switching to session: ${sessionId}`)
    this.chatStore.switchToSession(sessionId)
    logger.debug('Calling loadChatMessages...')
    // Load messages from backend when switching sessions
    await this.loadChatMessages(sessionId)
    logger.debug(`Switch complete, currentSessionId: ${this.chatStore.currentSessionId}`)
  }

  updateSessionTitle(sessionId: string, title: string): void {
    this.chatStore.updateSessionTitle(sessionId, title)
  }

  async resetChat(): Promise<void> {
    try {
      await chatRepository.resetChat()

      if (this.chatStore.currentSessionId) {
        const session = this.chatStore.sessions.find(s => s.id === this.chatStore.currentSessionId)
        if (session) {
          session.messages = []
        }
      }

    } catch (error: any) {
      this.getAppStore()?.setGlobalError(`Failed to reset chat: ${error.message}`)
      throw error
    }
  }

  // Message management
  deleteMessage(messageId: string): void {
    this.chatStore.deleteMessage(messageId)
  }

  editMessage(messageId: string, newContent: string): void {
    this.chatStore.updateMessage(messageId, { content: newContent })
  }

  // Export/Import operations
  exportChatSession(sessionId: string): ChatSession | null {
    return this.chatStore.exportSession(sessionId)
  }

  importChatSession(session: ChatSession): void {
    this.chatStore.importSession(session)
  }

  // Cleanup operations with confirmation
  async clearAllChats(): Promise<void> {
    try {
      this.getAppStore()?.setLoading(true, 'Clearing all chats...')

      // Note: cleanupAllChatData doesn't exist in repository, clearing from store only
      this.chatStore.clearAllSessions()

      logger.debug('All chats cleared successfully')

    } catch (error: any) {
      this.getAppStore()?.setGlobalError(`Failed to clear chats: ${error.message}`)
      throw error
    } finally {
      this.getAppStore()?.setLoading(false)
    }
  }

  async resetCurrentChat(): Promise<void> {
    return this.resetChat()
  }

  // Auto-save functionality with error handling
  enableAutoSave(intervalMs: number = 30000): void {
    setInterval(() => {
      if (this.chatStore.settings.autoSave && this.chatStore.currentSessionId) {
        this.saveChatSession().catch(error => {
          logger.warn('Auto-save failed:', error)
          // Don't show global error for auto-save failures
        })
      }
    }, intervalMs)
  }

  // Enhanced validation helpers
  validateMessage(content: string): { valid: boolean; error?: string } {
    if (!content || typeof content !== 'string') {
      return { valid: false, error: 'Message must be a string' }
    }

    const trimmed = content.trim()
    if (!trimmed) {
      return { valid: false, error: 'Message cannot be empty' }
    }

    if (trimmed.length > 4000) {
      return { valid: false, error: 'Message too long (max 4000 characters)' }
    }

    if (trimmed.length < 1) {
      return { valid: false, error: 'Message must contain at least 1 character' }
    }

    return { valid: true }
  }

  // Enhanced statistics
  getChatStatistics(): {
    totalSessions: number
    totalMessages: number
    averageMessagesPerSession: number
    oldestSession?: Date
    newestSession?: Date
    errorCount: number
    successfulSessions: number
  } {
    const sessions = this.chatStore.sessions
    const totalSessions = sessions.length
    const totalMessages = sessions.reduce((sum, session) => sum + session.messages.length, 0)
    const errorCount = sessions.reduce((sum, session) =>
      sum + session.messages.filter(msg => msg.status === 'error').length, 0)
    const successfulSessions = sessions.filter(session =>
      session.messages.some(msg => msg.sender === 'assistant')).length

    const dates = sessions.map(s => s.createdAt).sort()

    return {
      totalSessions,
      totalMessages,
      averageMessagesPerSession: totalSessions > 0 ? totalMessages / totalSessions : 0,
      oldestSession: dates.length > 0 ? dates[0] : undefined,
      newestSession: dates.length > 0 ? dates[dates.length - 1] : undefined,
      errorCount,
      successfulSessions
    }
  }

  // Connection test method
  async testConnection(): Promise<boolean> {
    try {
      this.getAppStore()?.setLoading(true, 'Testing connection...')

      // Try to create a minimal chat session
      const testResponse = await chatRepository.createNewChat('Connection Test')

      // Clean up the test session if successful
      if (testResponse?.id) {
        try {
          await chatRepository.deleteChat(testResponse.id)
        } catch {
          // Ignore cleanup errors
        }
      }

      logger.debug('Connection test successful')
      return true

    } catch (error) {
      logger.error('Connection test failed:', error)
      return false
    } finally {
      this.getAppStore()?.setLoading(false)
    }
  }
}
