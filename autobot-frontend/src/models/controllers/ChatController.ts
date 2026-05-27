import { useChatStore } from '@/stores/useChatStore'
import { useAppStore } from '@/stores/useAppStore'
import { chatRepository } from '@/models/repositories'
import apiClient from '@/utils/ApiClient'
import type { ChatSession } from '@/stores/useChatStore'
import { createLogger } from '@/utils/debugUtils'
import { extractErrorMessage } from '@/utils/errorExtract'
import type { ChatMessage, ChatMessageDisplayType } from '@/types/api'
import { requestQueue } from '@/composables/useRequestQueue'

const logger = createLogger('ChatController')

/** Shape of a buffered (non-streaming) JSON response from the chat backend */
interface ChatJsonResponseData {
  response?: string
  content?: string
  model?: string
  tokens_used?: number
  response_time?: number
  processing_time?: number
  message_type?: string
  knowledge_status?: string
  sources?: unknown
  librarian_engaged?: boolean
  mcp_used?: boolean
  workflow_messages?: Array<{
    text?: string
    content?: string
    sender?: string
    type?: string
    metadata?: Record<string, unknown>
  }>
}

/** Shape of a message-send request passed internally */
interface SendMessageRequest {
  message: string
  chatId: string
  options: Record<string, unknown>
}

export class ChatController {
  // FIXED: Lazy initialization - stores only created when accessed, not at module load
  private _chatStore?: ReturnType<typeof useChatStore>
  private _appStore?: ReturnType<typeof useAppStore>
  private retryAttempts = 3
  private retryDelay = 1000

  // Issue #1312: Streaming update throttle state
  private _pendingStreamUpdate: {
    messageId: string
    content: string
    type: ChatMessageDisplayType | string | undefined
    metadata: Record<string, unknown>
  } | null = null
  private _streamFlushTimer: ReturnType<typeof setTimeout> | null = null
  private _previewThrottleTimer: ReturnType<typeof setTimeout> | null = null
  private static readonly STREAM_FLUSH_INTERVAL_MS = 80
  private static readonly PREVIEW_THROTTLE_MS = 200

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
      } catch {
        logger.warn('AppStore not available, running without store integration')
        return null
      }
    }
    return this._appStore
  }

  // Enhanced message operations with comprehensive error handling
  async sendMessage(content: string, options?: Record<string, unknown>): Promise<string> {
    try {
      // #6693: don't toggle the global appStore.isLoading flag here. App.vue
      // wraps the entire <router-view> in a UnifiedLoadingView bound to it,
      // so flipping it on a per-message send blanks the chat history for the
      // duration of the request. chatStore.setTyping is the per-message UX.
      this.chatStore.setTyping(true)

      // Validate message content
      const validation = this.validateMessage(content)
      if (!validation.valid) {
        throw new Error(validation.error)
      }

      // #6746: ensure session exists BEFORE addMessage. addMessage no longer
      // creates a session as a side effect (that was a major churn source —
      // see #6745). Order: session-first, then attach message.
      if (!this.chatStore.currentSessionId) {
        await this.createNewSession()
      }

      const userMessageId = this.chatStore.addMessage({
        content,
        sender: 'user',
        status: 'sending'
      })
      if (!userMessageId) {
        throw new Error('Failed to add user message — no current session')
      }

      let lastError: Error | null = null

      // Retry mechanism for message sending
      for (let attempt = 1; attempt <= this.retryAttempts; attempt++) {
        try {
          // Send to backend with timeout and retry logic
          // Issue #6313: Route through requestQueue for concurrency backpressure
          const chatId = this.chatStore.currentSessionId!
          const response = await requestQueue.enqueue({
            fn: () => this.sendMessageWithRetry({
              message: content,
              chatId,
              options: options || {}
            }, attempt),
            priority: 'high',
            dedupeKey: `chat-send-${chatId}-${attempt}`,
          })

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

        } catch (error: unknown) {
          lastError = error instanceof Error ? error : new Error(extractErrorMessage(error, 'Unknown error'))
          logger.warn(`Message send attempt ${attempt}/${this.retryAttempts} failed:`, lastError.message)

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

    } catch (error: unknown) {
      // Enhanced error handling with user-friendly messages
      const userFriendlyMessage = this.getUserFriendlyErrorMessage(error)
      this.getAppStore()?.setGlobalError(userFriendlyMessage)
      throw error
    } finally {
      this.chatStore.setTyping(false)
    }
  }

  private async sendMessageWithRetry(
    request: SendMessageRequest,
    attempt: number
  ): Promise<{ type: string; response?: Response; data?: ChatJsonResponseData }> {
    try {
      // FIXED: Pass options parameter to preserve attachments and metadata
      return await chatRepository.sendMessage(request.message, request.chatId, request.options)
    } catch (error: unknown) {
      const errMsg = extractErrorMessage(error, 'Unknown error')
      const errStatus = (error as { status?: number }).status
      // Enhanced error context for debugging
      logger.error(`Chat message send attempt ${attempt} failed:`, {
        error: errMsg,
        status: errStatus,
        chatId: request.chatId,
        messageLength: request.message?.length,
        hasAttachments: Array.isArray((request.options as Record<string, unknown>)?.attachments),
        attempt
      })

      // If it's a 422 validation error, don't retry
      if (errStatus === 422) {
        throw new Error(`Invalid message format: ${errMsg}. Please check your input and try again.`)
      }

      // If it's a network error, add context
      const errName = (error as { name?: string }).name
      const errCode = (error as { code?: string }).code
      if (errName === 'NetworkError' || errCode === 'NETWORK_ERROR') {
        throw new Error(`Network connection failed. Please check your internet connection and try again.`)
      }

      throw error
    }
  }

  private getUserFriendlyErrorMessage(error: unknown): string {
    const status = (error as { status?: number }).status
    const name = (error as { name?: string }).name
    const message = extractErrorMessage(error, 'Unknown error')

    if (status === 422) {
      return 'Invalid message format. Please check your input and try again.'
    }
    if (status === 404) {
      return 'Chat service not available. Please refresh the page and try again.'
    }
    if (status === 500) {
      return 'Server error occurred. Please try again in a moment.'
    }
    if (name === 'NetworkError') {
      return 'Network connection failed. Please check your internet connection.'
    }
    if (message.includes('timeout')) {
      return 'Request timed out. Please try again with a shorter message.'
    }

    return `Failed to send message: ${message}`
  }

  /**
   * Issue #1312: Flush pending streaming update to the store.
   * Batches rapid chunk updates into a single store mutation per flush interval.
   */
  private flushStreamUpdate(): void {
    if (!this._pendingStreamUpdate) return
    const { messageId, content, type, metadata } = this._pendingStreamUpdate
    this._pendingStreamUpdate = null
    this.chatStore.updateMessage(messageId, { content, type, metadata: metadata as ChatMessage["metadata"] })
  }

  /**
   * Issue #1312: Schedule a throttled streaming update.
   * Instead of mutating the store on every chunk, we buffer the latest state
   * and flush at ~12fps (80ms) which is perceptually smooth for text.
   */
  private scheduleStreamUpdate(
    messageId: string,
    content: string,
    type: ChatMessageDisplayType | string | undefined,
    metadata: Record<string, unknown>
  ): void {
    this._pendingStreamUpdate = { messageId, content, type, metadata }
    if (!this._streamFlushTimer) {
      this._streamFlushTimer = setTimeout(() => {
        this._streamFlushTimer = null
        this.flushStreamUpdate()
      }, ChatController.STREAM_FLUSH_INTERVAL_MS)
    }
  }

  /**
   * Issue #1312: Throttled preview extraction.
   * Runs at most every 200ms instead of per-chunk.
   */
  private schedulePreviewUpdate(content: string, messageType?: string): void {
    if (this._previewThrottleTimer) return // Already scheduled
    this._previewThrottleTimer = setTimeout(() => {
      this._previewThrottleTimer = null
      const preview = this.extractStreamingPreview(content, messageType)
      if (preview) {
        this.chatStore.setStreamingPreview(preview)
      }
    }, ChatController.PREVIEW_THROTTLE_MS)
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

        const chunk = decoder.decode(value, { stream: true })
        buffer += chunk

        const lines = buffer.split('\n')
        buffer = lines.pop() || ''

        for (const line of lines) {
          if (!line.trim()) continue
          if (line.startsWith('data: ')) {
            fallbackMessageId = this._processStreamLine(line, messageIdMap, fallbackMessageId)
          }
        }
      }

      this._finalizeStreamMessages(messageIdMap, fallbackMessageId)

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

  private _processStreamLine(
    line: string,
    messageIdMap: Map<string, string>,
    fallbackMessageId: string | null
  ): string | null {
    try {
      const jsonStr = line.slice(6).trim()
      if (!jsonStr) return fallbackMessageId

      const data = JSON.parse(jsonStr)
      logger.debug('Received stream data:', data.type || 'unknown')

      if (data.type === 'start') {
        logger.debug('Stream started:', data.session_id)
        return fallbackMessageId
      }
      if (data.type === 'end') {
        logger.debug('Stream ended')
        return fallbackMessageId
      }
      if (data.type === 'segment_complete') {
        logger.debug(`Segment complete: ${data.metadata?.completed_type}`)
        const backendId = data.metadata?.message_id
        if (backendId && messageIdMap.has(backendId)) {
          this.chatStore.updateMessage(messageIdMap.get(backendId)!, { status: 'sent' })
        }
        return fallbackMessageId
      }

      if (data.type === 'error') {
        logger.error('Stream error:', data.content)
        const errorMsgId = fallbackMessageId || this.chatStore.addMessage({
          content: '',
          sender: 'assistant'
        })
        if (!errorMsgId) return fallbackMessageId
        this.chatStore.updateMessage(errorMsgId, {
          content: `Error: ${data.content || data.message || 'Unknown error'}`,
          status: 'error'
        })
        return fallbackMessageId
      }

      if (!data.content && data.type !== 'command_approval_request') {
        return fallbackMessageId
      }

      // Map backend type to frontend type (must be before addMessage to set type immediately,
      // preventing the 80ms throttle window where the message appears as 'response' then
      // disappears when the real type is applied — issue #1364)
      const messageType = this.mapMessageType(data.type, data.metadata?.message_type)

      // Agent Zero Pattern: Use backend message_id for stable identity
      const backendMessageId = data.metadata?.message_id || data.id
      let frontendMessageId: string

      if (backendMessageId && messageIdMap.has(backendMessageId)) {
        frontendMessageId = messageIdMap.get(backendMessageId)!
      } else if (!backendMessageId && fallbackMessageId) {
        // No backend ID but we already have a fallback — reuse it
        // Prevents duplicate messages when chunks lack message_id
        frontendMessageId = fallbackMessageId as string
      } else {
        // New message - create it with type set immediately to prevent filter flicker (#1364)
        const sender = data.type === 'terminal_output' ? 'system' : 'assistant'
        frontendMessageId = this.chatStore.addMessage({
          content: '',
          sender,
          type: messageType
        }) as string
        if (backendMessageId) {
          messageIdMap.set(backendMessageId, frontendMessageId)
        }
        fallbackMessageId = frontendMessageId
      }

      if (data.type === 'command_approval_request') {
        this.chatStore.setTyping(false)
        // Issue #680: Set pending approval flag to prevent polling race conditions
        this.chatStore.setPendingApproval(true)
        this.chatStore.updateMessage(frontendMessageId, {
          content: data.content || 'Command approval required',
          type: 'command_approval_request',
          metadata: {
            ...data.metadata,
            requires_approval: true
            // Note: approval_status is NOT set here - it's only set after user action
            // This allows the template to show approval buttons when !approval_status
          }
        })
        return fallbackMessageId
      }

      // Agent Zero Pattern: Backend sends CUMULATIVE content - just replace
      // Issue #1312: Throttle store updates to ~12fps instead of per-chunk
      // This reduces 200+ re-renders to ~20 per streaming response
      this.scheduleStreamUpdate(frontendMessageId, data.content, messageType, data.metadata || {})

      // Issue #1312: Throttle preview extraction to max every 200ms
      if (data.content && this.chatStore.isTyping) {
        this.schedulePreviewUpdate(data.content, messageType)
      }

    } catch (e) {
      logger.warn('Failed to parse stream data:', { line, error: e })
    }

    return fallbackMessageId
  }

  private _finalizeStreamMessages(
    messageIdMap: Map<string, string>,
    fallbackMessageId: string | null
  ): void {
    // Issue #1312: Flush any remaining buffered update before finalization
    if (this._streamFlushTimer) {
      clearTimeout(this._streamFlushTimer)
      this._streamFlushTimer = null
    }
    this.flushStreamUpdate()
    if (this._previewThrottleTimer) {
      clearTimeout(this._previewThrottleTimer)
      this._previewThrottleTimer = null
    }

    // Issue #1302: Finalize all messages and clean up truly empty ones
    // Check displayable content (after stripping internal tags) not raw content
    // to prevent deleting messages that have visible text between tags
    const allIds = [...messageIdMap.values()]
    if (fallbackMessageId && !allIds.includes(fallbackMessageId)) {
      allIds.push(fallbackMessageId)
    }

    for (const frontendId of allIds) {
      const msg = this.chatStore.currentSession?.messages.find(m => m.id === frontendId)
      if (!msg) continue

      const displayContent = (msg.content || '')
        .replace(/\[\/?(THOUGHT|PLANNING|DEBUG|SOURCES)\]?/gi, '')
        .replace(/\[\/?(?:THO(?:UGH?T?)?|PLA(?:NN?I?N?G?)?|DEB(?:UG?)?|SOU(?:RC?E?S?)?)\]?/gi, '')
        .trim()

      if (displayContent) {
        if (msg.status !== 'error') {
          this.chatStore.updateMessage(frontendId, { status: 'sent' })
        }
      } else {
        this.chatStore.deleteMessage(frontendId)
      }
    }
  }

  /**
   * Issue #691: Extract a meaningful preview from streaming content.
   * Used to display real LLM content in the typing indicator instead of placeholder text.
   *
   * @param content - The full streaming content so far
   * @param messageType - The type of message (thought, planning, response, etc.)
   * @returns A short preview string (max 80 chars) or empty string if no preview available
   */
  private extractStreamingPreview(content: string, messageType?: string): string {
    if (!content || content.length < 3) return ''

    // Strip internal tags that shouldn't be shown to users
    // Handles complete tags and partial/truncated tags from streaming (e.g. [/THO)
    const preview = content
      .replace(/\[\/?(THOUGHT|PLANNING|DEBUG|SOURCES)\]?/gi, '')
      .replace(/\[\/?(?:THO(?:UGH?T?)?|PLA(?:NN?I?N?G?)?|DEB(?:UG?)?|SOU(?:RC?E?S?)?)\]?$/gi, '')
      .replace(/<tool_call[^>]*>.*?<\/tool_call>/gs, '')
      .replace(/<TOOL_CALL[^>]*>.*?<\/TOOL_CALL>/gs, '')
      .trim()

    if (!preview) return ''

    // Get the last meaningful portion (most recent thinking)
    // Take the last sentence or last 80 characters
    // Issue #691: Filter empty sentences to avoid blank preview when content ends with punctuation
    const sentences = preview.split(/[.!?]\s+/)
    const lastSentence = sentences.filter(s => s.trim()).pop() || preview

    // Create a concise preview
    let result = lastSentence.trim()
    if (result.length > 80) {
      // Find a good breaking point (word boundary)
      result = result.substring(0, 77)
      const lastSpace = result.lastIndexOf(' ')
      if (lastSpace > 50) {
        result = result.substring(0, lastSpace)
      }
      result += '...'
    }

    // Add type-specific prefix for context
    if (messageType === 'thought') {
      return `Thinking: ${result}`
    } else if (messageType === 'planning') {
      return `Planning: ${result}`
    }

    return result
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

  private handleJsonResponse(data: ChatJsonResponseData | undefined): void {
    if (!data) return
    // Add workflow messages first (thoughts, planning, debug, utility, sources)
    if (data.workflow_messages && Array.isArray(data.workflow_messages)) {
      data.workflow_messages.forEach((msg) => {
        this.chatStore.addMessage({
          content: msg.text || msg.content || '',
          sender: (msg.sender as 'user' | 'assistant' | 'system') || 'assistant',
          type: msg.type, // This enables filtering
          metadata: (msg.metadata || {}) as ChatMessage["metadata"]
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
        } as ChatMessage["metadata"]
      })
    }
  }

  // Enhanced session operations with error handling
  async createNewSession(title?: string): Promise<string> {
    // MVA-164: Client-mint UUID before any API call (server-round-trip-first pattern)
    // Generate UUID upfront
    const sessionId = crypto.randomUUID()

    // Call backend immediately with the client-minted UUID
    try {
      await chatRepository.createNewChat(title, undefined, sessionId)
      logger.debug('New chat session created on backend:', sessionId)
    } catch (error) {
      // Backend create failed - don't create local session if backend fails
      logger.error('Failed to create chat session on backend:', error)
      this.getAppStore()?.setGlobalError(`Failed to create chat: ${extractErrorMessage(error, 'Unknown error')}`)
      throw error
    }

    // Backend succeeded - now create the local session with the same UUID
    const localSessionId = this.chatStore.createNewSession(title, sessionId)
    if (localSessionId !== sessionId) {
      // This shouldn't happen since we're passing the sessionId to createNewSession
      logger.warn(`Session ID mismatch: generated ${sessionId}, store created ${localSessionId}`)
    }

    return sessionId
  }

  async loadChatSessions(): Promise<void> {
    try {

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

    } catch (error: unknown) {
      logger.error('Failed to load chat sessions:', error)
      // Don't throw error, allow app to continue with local sessions
      this.getAppStore()?.setGlobalError(`Failed to load chat sessions: ${extractErrorMessage(error, 'Unknown error')}`)
    } finally {
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

      const messages = await chatRepository.getChatMessages(sessionId)
      logger.debug(`Received ${messages.length} messages from repository`)

      // Update session with loaded messages
      const session = this.chatStore.sessions.find(s => s.id === sessionId)
      if (session) {
        // Issue #1371: Never replace local messages with empty/fewer backend
        // messages. The poller can get [] on transient API errors or stale
        // data before the backend has persisted the streaming response.
        if (messages.length === 0 && session.messages.length > 0) {
          logger.debug('Skipping update - backend returned empty but local has messages')
        } else if (messages.length < session.messages.length) {
          logger.debug(
            `Skipping update - backend has fewer messages (${messages.length}) than local (${session.messages.length})`
          )
        } else {
          // Only update if message count or last message content changed
          const lastExisting = session.messages[session.messages.length - 1]
          const lastNew = messages[messages.length - 1]
          const hasChanges = session.messages.length !== messages.length ||
            lastExisting?.content !== lastNew?.content

          if (hasChanges) {
            logger.debug(`Updating messages (${session.messages.length} -> ${messages.length})`)
            session.messages = messages as typeof session.messages
          } else {
            logger.debug(`No message changes, skipping update`)
          }
        }

        // Only switch session if not already current
        if (this.chatStore.currentSessionId !== sessionId) {
          this.chatStore.switchToSession(sessionId)
        }
      } else {
        // #6766: session list may not be loaded yet during startup race.
        // Downgrade to warn — the caller will retry once sessions are populated.
        logger.warn(`Session ${sessionId} not found in store (may still be loading)`)
      }

    } catch (error: unknown) {
      logger.error('Failed to load messages:', error)
      this.getAppStore()?.setGlobalError(`Failed to load messages: ${extractErrorMessage(error, 'Unknown error')}`)
    } finally {
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

    } catch (error: unknown) {
      logger.error('Failed to save chat session:', error)
      this.getAppStore()?.setGlobalError(`Failed to save chat: ${extractErrorMessage(error, 'Unknown error')}`)
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
    } catch (error: unknown) {
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
    } catch (error: unknown) {
      logger.error('Failed to preserve session facts:', error)
      throw error
    }
  }

  async deleteChatSession(
    sessionId: string,
    fileAction?: 'delete' | 'transfer_kb' | 'transfer_shared',
    fileOptions?: Record<string, unknown>
  ): Promise<void> {
    try {

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
      } catch (error: unknown) {
        logger.error('Backend deletion failed:', error)
        // Don't throw yet - we'll handle this based on error type

        // If it's a 404 (chat not found), still proceed with local deletion
        const errStatus = (error as { status?: number }).status
        if (errStatus === 404) {
          logger.warn('Chat not found on backend, proceeding with local deletion')
          backendDeleteSucceeded = true // Treat as success since it's already gone
        } else {
          // For other errors, show user error but still try local deletion
          logger.warn('Backend deletion failed, but proceeding with local deletion to maintain consistency')
          this.getAppStore()?.setGlobalError(`Backend deletion failed: ${extractErrorMessage(error, 'Unknown error')}. Chat removed locally.`)
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
              const persistedSession = parsed.sessions?.find(
                (s: { id?: string }) => s.id === sessionId
              )
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
      } catch (error: unknown) {
        logger.error('Store deletion failed:', error)
        throw new Error(`Failed to delete chat from local storage: ${extractErrorMessage(error, 'Unknown error')}`)
      }

      // Step 3: Report final status
      if (storeDeleteSucceeded) {
        logger.debug(`Chat session ${sessionId} successfully deleted (Backend: ${backendDeleteSucceeded ? 'Success' : 'Failed'}, Store: Success)`)
      } else {
        throw new Error('Failed to delete chat from local storage')
      }

    } catch (error: unknown) {
      logger.error('Failed to delete chat session:', error)
      this.getAppStore()?.setGlobalError(`Failed to delete chat: ${extractErrorMessage(error, 'Unknown error')}`)
      throw error // Re-throw to let caller handle
    } finally {
    }
  }

  // Settings operations
  updateChatSettings(settings: Partial<Record<string, unknown>>): void {
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

    } catch (error: unknown) {
      this.getAppStore()?.setGlobalError(`Failed to reset chat: ${extractErrorMessage(error, 'Unknown error')}`)
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

      // Note: cleanupAllChatData doesn't exist in repository, clearing from store only
      this.chatStore.clearAllSessions()

      logger.debug('All chats cleared successfully')

    } catch (error: unknown) {
      this.getAppStore()?.setGlobalError(`Failed to clear chats: ${extractErrorMessage(error, 'Unknown error')}`)
      throw error
    } finally {
    }
  }

  async resetCurrentChat(): Promise<void> {
    return this.resetChat()
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
    }
  }

  /**
   * Submit a user approval decision for an agent-loop sensitive operation (#4092).
   *
   * Publishes an APPROVAL_RESPONSE via the LiveEventService WebSocket so the
   * backend ``AgentLoop._request_approval()`` polling loop can pick it up.
   *
   * @param approvalId   - Correlation ID from the APPROVAL_REQUIRED event
   * @param approved     - True to allow the operation, false to deny it
   * @param comment      - Optional human comment attached to the decision
   * @returns true if the decision was delivered to the WebSocket, false otherwise
   */
  /**
   * Issue #4431: Push local-only sessions to the backend before bidirectional sync.
   *
   * After receiving the backend session list, any local session that has real messages
   * and is absent from the backend is POSTed (created + messages saved) so it survives
   * the subsequent syncSessionsWithBackend() call.
   *
   * @param backendSessionIds - Set of session IDs already present on the backend
   */
  async pushLocalOnlySessions(backendSessionIds: Set<string>): Promise<void> {
    const localOnly = this.chatStore.sessions.filter(
      (s: ChatSession) => !backendSessionIds.has(s.id) && s.messages.length > 0
    )
    if (localOnly.length === 0) return

    logger.debug(`[Issue #4431] Pushing ${localOnly.length} local-only session(s) to backend`)

    await Promise.allSettled(
      localOnly.map(async (session: ChatSession) => {
        try {
          const newSession = await chatRepository.createNewChat(session.title)
          const backendId = newSession?.id ?? session.id
          await chatRepository.saveChatMessages({
            chatId: backendId,
            messages: session.messages,
            name: session.title || ''
          })
          logger.debug(`[Issue #4431] Pushed local session ${session.id} to backend as ${backendId}`)
        } catch (error) {
          logger.warn(`[Issue #4431] Failed to push local session ${session.id}:`, error)
        }
      })
    )
  }

  /**
   * Submit a user approval decision for an agent-loop sensitive operation (#4092 #4952).
   *
   * Calls POST /api/agent-terminal/tools/approve/{approvalId} so the backend
   * _request_approval() pub/sub loop receives an APPROVAL_RESPONSE event.
   *
   * Prefer the useToolApproval() composable for Vue components — this method
   * exists for non-component callers (e.g. Slack webhook relay).
   *
   * Returns a Promise that resolves to true on success, false on HTTP error.
   */
  async submitApprovalDecision(
    approvalId: string,
    approved: boolean,
    comment?: string,
    taskId?: string
  ): Promise<boolean> {
    try {
      // Lazy import to avoid circular dependency at module load time
       
      // @ts-ignore
      const { fetchWithAuth } = require('@/utils/fetchWithAuth') as { fetchWithAuth: typeof import('@/utils/fetchWithAuth').fetchWithAuth }
       
      // @ts-ignore
      const appConfig = (require('@/config/AppConfig.js') as { default: { getApiUrl: (p: string) => Promise<string> } }).default
       
      // @ts-ignore
      const { getApiBase } = require('@/config/ssot-config') as { getApiBase: () => string }

      const resolvedTaskId = taskId ?? this.chatStore.currentSessionId ?? null
      const url = await appConfig.getApiUrl(
        `${getApiBase()}/agent-terminal/tools/approve/${encodeURIComponent(approvalId)}`
      )
      const response = await fetchWithAuth(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ approved, comment: comment ?? null, task_id: resolvedTaskId }),
      })
      if (!response.ok) {
        logger.error(
          'submitApprovalDecision: server returned %d for approval_id=%s',
          response.status,
          approvalId,
        )
        return false
      }
      logger.debug('submitApprovalDecision: approval_id=%s approved=%s', approvalId, approved)
      return true
    } catch (err) {
      logger.error('submitApprovalDecision: unexpected error:', err)
      return false
    }
  }
}
