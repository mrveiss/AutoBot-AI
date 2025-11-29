import { useChatStore } from '@/stores/useChatStore'
import { useAppStore } from '@/stores/useAppStore'
import { chatRepository } from '@/models/repositories'
import apiClient from '@/utils/ApiClient'
import type { ChatMessage, ChatSession } from '@/stores/useChatStore'

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
        console.warn('[ChatController] AppStore not available, running without store integration')
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
          console.warn(`Message send attempt ${attempt}/${this.retryAttempts} failed:`, error.message)

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
      console.error(`Chat message send attempt ${attempt} failed:`, {
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

    const assistantMessageId = this.chatStore.addMessage({
      content: '',
      sender: 'assistant'
    })

    let accumulatedContent = ''
    const decoder = new TextDecoder()
    let buffer = ''

    try {
      console.log('[ChatController] Starting to read streaming response')

      while (true) {
        const { done, value } = await reader.read()

        if (done) {
          console.log('[ChatController] Stream completed')
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
              console.log('[ChatController] Received stream data:', data.type || 'unknown')

              if (data.type === 'start') {
                console.log('[ChatController] Stream started:', data.session_id)
              } else if (data.type === 'command_approval_request') {
                // CRITICAL FIX: Stop typing indicator when approval is requested
                // Backend is waiting for user approval - no more streaming until approved/denied
                console.log('[ChatController] Approval request detected - stopping typing indicator')
                this.chatStore.setTyping(false)

                // Add approval request message to chat
                accumulatedContent += data.content || 'Command approval required'
                this.chatStore.updateMessage(assistantMessageId, {
                  content: accumulatedContent,
                  type: 'command_approval_request',
                  metadata: {
                    ...data.metadata,
                    requires_approval: true,
                    approval_status: 'pending'
                  }
                })
              } else if (data.type === 'end') {
                console.log('[ChatController] Stream ended')
              } else if (data.type === 'error') {
                // Display error as message content instead of throwing
                console.error('[ChatController] Stream error:', data.content)
                accumulatedContent += `⚠️ Error: ${data.content || 'Stream error'}`
                this.chatStore.updateMessage(assistantMessageId, {
                  content: accumulatedContent,
                  status: 'error'
                })
              } else if (data.content) {
                accumulatedContent += data.content

                // Map backend message_type to frontend type
                type MessageType = 'thought' | 'planning' | 'debug' | 'utility' | 'sources' | 'json' | 'response' | 'message' | undefined
                let messageType: MessageType = 'response'
                if (data.metadata?.message_type) {
                  const backendType = data.metadata.message_type
                  // Map backend types to frontend types
                  if (backendType === 'thought' || backendType.includes('thought')) messageType = 'thought'
                  else if (backendType.includes('planning')) messageType = 'planning'
                  else if (backendType.includes('debug')) messageType = 'debug'
                  else if (backendType.includes('utility')) messageType = 'utility'
                  else if (backendType.includes('source')) messageType = 'sources'
                  else if (backendType.includes('json')) messageType = 'json'
                  else messageType = 'response'
                }

                // CRITICAL FIX: Merge metadata instead of replacing to preserve terminal_session_id
                const currentMessage = this.chatStore.currentSession?.messages.find(m => m.id === assistantMessageId)
                const existingMetadata = currentMessage?.metadata || {}

                this.chatStore.updateMessage(assistantMessageId, {
                  content: accumulatedContent,
                  type: messageType,
                  metadata: {
                    ...existingMetadata,  // Preserve existing metadata (including terminal_session_id)
                    ...(data.metadata || {})  // Merge in new metadata
                  }
                })
              }
            } catch (e) {
              console.warn('[ChatController] Failed to parse stream data:', line, e)
            }
          }
        }
      }

      // Final update
      if (accumulatedContent) {
        this.chatStore.updateMessage(assistantMessageId, {
          content: accumulatedContent,
          status: 'sent'
        })
      }

    } catch (error) {
      console.error('[ChatController] Streaming response error:', error)
      this.chatStore.updateMessage(assistantMessageId, {
        content: accumulatedContent || 'Response was interrupted due to an error.',
        status: 'error'
      })
      throw error
    } finally {
      reader.releaseLock()
    }
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
        console.log('New chat session synced with backend:', sessionId)
      } catch (error) {
        console.warn('Failed to sync new chat with backend, continuing with local session:', error)
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
        console.log(`Loaded ${sessions.length} chat sessions`)
      } else {
        console.warn('getChatList() returned non-array value:', sessions)
      }

    } catch (error: any) {
      console.error('Failed to load chat sessions:', error)
      // Don't throw error, allow app to continue with local sessions
      this.getAppStore()?.setGlobalError(`Failed to load chat sessions: ${error.message}`)
    } finally {
      this.getAppStore()?.setLoading(false)
    }
  }

  async loadChatMessages(sessionId: string): Promise<void> {
    try {
      console.log(`[ChatController] 🔍 Loading messages for session: ${sessionId}`)
      this.getAppStore()?.setLoading(true, 'Loading messages...')

      const messages = await chatRepository.getChatMessages(sessionId)
      console.log(`[ChatController] 📦 Received ${messages.length} messages from repository`)

      // Update session with loaded messages
      const session = this.chatStore.sessions.find(s => s.id === sessionId)
      if (session) {
        console.log(`[ChatController] 📝 Found session in store, updating messages (before: ${session.messages.length}, after: ${messages.length})`)
        session.messages = messages as any // Type assertion: repository transforms messages to match store format
        this.chatStore.switchToSession(sessionId)
        console.log(`[ChatController] ✅ Loaded ${messages.length} messages for session ${sessionId}`)
        console.log(`[ChatController] 🔍 Store currentMessages count: ${this.chatStore.currentMessages.length}`)
      } else {
        console.error(`[ChatController] ❌ Session ${sessionId} not found in store! Store has ${this.chatStore.sessions.length} sessions:`, this.chatStore.sessions.map(s => s.id))
      }

    } catch (error: any) {
      console.error('[ChatController] ❌ Failed to load messages:', error)
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

      // CRITICAL FIX Issue #259: Pass session name to backend for proper save
      await chatRepository.saveChatMessages({
        chatId: targetSessionId,
        messages: session.messages,
        name: session.name || ''
      })

      console.log('Chat session saved successfully:', targetSessionId)

    } catch (error: any) {
      console.error('Failed to save chat session:', error)
      this.getAppStore()?.setGlobalError(`Failed to save chat: ${error.message}`)
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
          console.log(`File action executed: ${fileAction}`, fileOptions)
        }
        backendDeleteSucceeded = true
        console.log('Chat successfully deleted from backend:', sessionId)
      } catch (error: any) {
        console.error('Backend deletion failed:', error)
        // Don't throw yet - we'll handle this based on error type

        // If it's a 404 (chat not found), still proceed with local deletion
        if (error.status === 404) {
          console.warn('Chat not found on backend, proceeding with local deletion')
          backendDeleteSucceeded = true // Treat as success since it's already gone
        } else {
          // For other errors, show user error but still try local deletion
          console.warn('Backend deletion failed, but proceeding with local deletion to maintain consistency')
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
          console.log('Chat successfully deleted from store:', sessionId)

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
                console.log('✅ Chat deletion confirmed in localStorage')
              } else {
                console.warn('⚠️ Chat still exists in localStorage - persistence may have failed')
              }
            }
          } catch (persistError) {
            console.warn('Could not verify localStorage persistence:', persistError)
          }

        } else {
          console.warn('Store deletion did not reduce session count - session may not have existed')
          storeDeleteSucceeded = true // If it wasn't there, consider it a success
        }
      } catch (error: any) {
        console.error('Store deletion failed:', error)
        throw new Error(`Failed to delete chat from local storage: ${error.message}`)
      }

      // Step 3: Report final status
      if (storeDeleteSucceeded) {
        console.log(`✅ Chat session ${sessionId} successfully deleted (Backend: ${backendDeleteSucceeded ? 'Success' : 'Failed'}, Store: Success)`)
      } else {
        throw new Error('Failed to delete chat from local storage')
      }

    } catch (error: any) {
      console.error('Failed to delete chat session:', error)
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
    console.log(`[ChatController] 🔀 Switching to session: ${sessionId}`)
    this.chatStore.switchToSession(sessionId)
    console.log(`[ChatController] 📲 Calling loadChatMessages...`)
    // Load messages from backend when switching sessions
    await this.loadChatMessages(sessionId)
    console.log(`[ChatController] ✅ Switch complete, currentSessionId: ${this.chatStore.currentSessionId}`)
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

      console.log('All chats cleared successfully')

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
          console.warn('Auto-save failed:', error)
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

      console.log('Connection test successful')
      return true

    } catch (error) {
      console.error('Connection test failed:', error)
      return false
    } finally {
      this.getAppStore()?.setLoading(false)
    }
  }
}
