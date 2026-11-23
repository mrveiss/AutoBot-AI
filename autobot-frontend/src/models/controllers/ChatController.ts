// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import { useChatStore, type ChatSession } from '@/stores/useChatStore'
import { useAppStore } from '@/stores/useAppStore'
import { chatRepository } from '@/models/repositories'
import apiClient from '@/utils/ApiClient'
import { createLogger } from '@/utils/debugUtils'
import { extractErrorMessage, isRequestTimeout, streamErrorText } from '@/utils/errorExtract'
import i18n from '@/i18n'
import type { ChatMessage } from '@/types/api'
import { requestQueue } from '@/composables/useRequestQueue'
import { stripBracketTags } from '@/utils/llmProtocolTags'
import { showAttachmentNotice } from '@/utils/attachmentNotice'
import { keepUnansweredQuestions } from './stallQuestions'
import { ActiveStreams } from './activeStreams'
import { StreamThrottle } from './streamThrottle'
import { mapMessageType } from './streamFormat'

const logger = createLogger('ChatController')

/** Shape of a buffered (non-streaming) JSON response from the chat backend */
interface ChatJsonResponseData {
  response?: string
  content?: string
  // #11843: stable backend message id — reused so a later poll / live-event
  // echo of the same reply dedups instead of rendering a second bubble.
  message_id?: string
  id?: string
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

/** #21357: per-stream state; `sessionId` is the chat the stream was started in, fixed for its whole life. */
interface StreamState {
  reportedError: boolean
  sessionId?: string
}

export class ChatController {
  // FIXED: Lazy initialization - stores only created when accessed, not at module load
  private _chatStore?: ReturnType<typeof useChatStore>
  private _appStore?: ReturnType<typeof useAppStore>
  private retryAttempts = 3
  private retryDelay = 1000

  private _activeStreams = new ActiveStreams() // #21357
  private _throttle = new StreamThrottle({ // Issue #1312
    updateMessage: (id, updates, sid) => this.chatStore.updateMessage(id, updates, sid),
    setPreview: preview => this.chatStore.setStreamingPreview(preview),
    isOpenChat: sid => this.isOpenChat(sid)
  })

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
    let originSessionId: string | undefined // #21357: the chat this send started in
    let registered = false
    try {
      // #6693: don't toggle the global appStore.isLoading flag here. App.vue
      // wraps the entire <router-view> in a UnifiedLoadingView bound to it,
      // so flipping it on a per-message send blanks the chat history for the
      // duration of the request. chatStore.setTyping is the per-message UX.
      this.chatStore.setTyping(true)

      // #11690: merge any active request-context (e.g. { company_id } for the
      // CEO-chat route) so scoped views get their tools without ChatInterface
      // needing props. Explicit call-site options win. Empty by default → the
      // general /chat send is unchanged.
      const activeCtx = this.chatStore.activeChatContext
      if (activeCtx && Object.keys(activeCtx).length > 0) {
        options = { ...activeCtx, ...options }
      }

      // Validate message content
      const validation = this.validateMessage(content)
      if (!validation.valid) {
        throw new Error(validation.error)
      }

      // #6746: ensure session exists BEFORE addMessage. addMessage no longer
      // creates a session as a side effect (that was a major churn source —
      // see #6745). Order: session-first, then attach message.
      // #21357: keep the id creation returned; a concurrent send may have selected another chat by now
      originSessionId = this.chatStore.currentSessionId ?? (await this.createNewSession())
      this._activeStreams.begin(originSessionId) // before the POST: a switch away and back mid-request keeps the indicator
      registered = true
      const userMessageId = this.chatStore.addMessage({
        content,
        sender: 'user',
        status: 'sending'
      }, originSessionId)
      if (!userMessageId) {
        throw new Error('Failed to add user message — no current session')
      }

      let lastError: Error | null = null

      // Retry mechanism for message sending
      for (let attempt = 1; attempt <= this.retryAttempts; attempt++) {
        try {
          // Send to backend with timeout and retry logic
          // Issue #6313: Route through requestQueue for concurrency backpressure
          const chatId = originSessionId!
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
          this.chatStore.updateMessage(userMessageId, { status: 'sent' }, originSessionId)

          // Invalidate chat list cache since we added a new message
          apiClient.invalidateCache()

          // Handle response based on type
          if (response.type === 'streaming') {
            await this.handleStreamingResponse(response.response!, originSessionId, true)
          } else {
            this.handleJsonResponse(response.data, originSessionId)
          }

          return userMessageId // Success, exit retry loop

        } catch (error: unknown) {
          lastError = error instanceof Error ? error : Object.assign(new Error(extractErrorMessage(error, 'Unknown error')), { cause: error }) // cause keeps a non-Error rejection's type
          logger.warn(`Message send attempt ${attempt}/${this.retryAttempts} failed:`, lastError.message)

          if (attempt < this.retryAttempts) {
            // Wait before retrying
            await new Promise(resolve => setTimeout(resolve, this.retryDelay * attempt))

            // Update user message with retry status
            this.chatStore.updateMessage(userMessageId, {
              status: 'sending',
              metadata: { retrying: true, attempt: attempt + 1 }
            }, originSessionId)
          }
        }
      }

      // All retry attempts failed
      this.chatStore.updateMessage(userMessageId, { status: 'error' }, originSessionId)

      // Add helpful error message for user
      this.chatStore.addMessage({
        content: i18n.global.t('chat.errors.sendFailedAfterRetries', {
          attempts: this.retryAttempts,
          error: lastError?.message || 'Unknown error'
        }),
        sender: 'system',
        type: 'utility'
      }, originSessionId)

      throw lastError || new Error('Failed to send message')

    } catch (error: unknown) {
      // Enhanced error handling with user-friendly messages
      const userFriendlyMessage = this.getUserFriendlyErrorMessage(error)
      this.getAppStore()?.setGlobalError(userFriendlyMessage)
      throw error
    } finally {
      // #21357: typing belongs to the chat that sent; another open chat keeps its own indicator
      if (registered) this._activeStreams.end(originSessionId)
      this.syncTyping(originSessionId)
    }
  }

  /** #21357: the open chat shows typing while it has a generating operation that is not paused for approval. */
  private syncTyping(sessionId: string | undefined): void {
    if (!this.isOpenChat(sessionId)) return
    const generating = sessionId !== undefined && this._activeStreams.has(sessionId) && !this.chatStore.isPendingApproval(sessionId)
    this.chatStore.setTyping(generating)
  }

  /** Count `sessionId` as streaming while `run` (a resume POST plus its reply) is in flight; then recompute typing. */
  async withActiveStream<T>(sessionId: string, run: () => Promise<T>): Promise<T> {
    this._activeStreams.begin(sessionId)
    try {
      return await run()
    } finally {
      this._activeStreams.end(sessionId)
      this.syncTyping(sessionId)
    }
  }

  /** #21357: true when `sessionId` is unknown (legacy callers) or is the chat currently open. */
  private isOpenChat(sessionId: string | undefined): boolean {
    return sessionId === undefined || this.chatStore.currentSessionId === sessionId
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
        // #12401: keep .status on the re-wrapped error so the outer
        // getUserFriendlyErrorMessage() categorizes it as invalidFormat instead
        // of falling through to the generic sendFailed (which would double-wrap
        // this detail message).
        throw Object.assign(
          new Error(i18n.global.t('chat.errors.invalidFormatDetail', { error: errMsg })),
          { status: 422 }
        )
      }

      // If it's a network error, add context
      const errName = (error as { name?: string }).name
      const errCode = (error as { code?: string }).code
      if (errName === 'NetworkError' || errCode === 'NETWORK_ERROR') {
        // #12401: keep name==='NetworkError' on the re-wrapped error so the outer
        // getUserFriendlyErrorMessage() surfaces networkFailed instead of the
        // generic sendFailed.
        throw Object.assign(
          new Error(i18n.global.t('chat.errors.networkFailedRetry')),
          { name: 'NetworkError' }
        )
      }

      throw error
    }
  }

  private getUserFriendlyErrorMessage(error: unknown): string {
    const status = (error as { status?: number }).status
    const message = extractErrorMessage(error, 'Unknown error')

    if (status === 422) {
      return i18n.global.t('chat.errors.invalidFormat')
    }
    if (status === 404) {
      return i18n.global.t('chat.errors.serviceUnavailable')
    }
    if (status === 500) {
      return i18n.global.t('chat.errors.serverError')
    }
    if ((error as { name?: string }).name === 'NetworkError') {
      return i18n.global.t('chat.errors.networkFailed')
    }
    // By type only: the send path is native fetch / the kit client, no producer of ours words a timeout as text (#21581)
    if (isRequestTimeout(error) || isRequestTimeout((error as { cause?: unknown } | null)?.cause)) {
      return i18n.global.t('chat.errors.timeout')
    }

    return i18n.global.t('chat.errors.sendFailed', { error: message })
  }

  private flushStreamUpdate(): void {
    this._throttle.flush()
  }

  /** Consume an SSE reply; resolves true when it carried an `error` event (HTTP 200 is not success, #21022). */
  async handleStreamingResponse(
    response: Response,
    sessionId: string | undefined = this.chatStore.currentSessionId ?? undefined, // #21357: bound once, at start
    registered = false // the caller already counts this stream (sendMessage registers before the POST)
  ): Promise<boolean> {
    const streamState: StreamState = { reportedError: false, sessionId } // per stream: overlapping streams must not share it
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
    if (!registered) this._activeStreams.begin(sessionId)

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
            fallbackMessageId = this._processStreamLine(line, messageIdMap, fallbackMessageId, streamState)
          }
        }
      }

      this._finalizeStreamMessages(messageIdMap, fallbackMessageId, sessionId)

    } catch (error) {
      logger.error('Streaming response error:', error)
      if (fallbackMessageId) {
        this.chatStore.updateMessage(fallbackMessageId, {
          content: 'Response was interrupted due to an error.',
          status: 'error'
        }, sessionId)
      }
      throw error
    } finally {
      if (!registered) {
        this._activeStreams.end(sessionId)
        this.syncTyping(sessionId) // the restored indicator must not outlive its stream
      }
      reader.releaseLock()
    }
    return streamState.reportedError
  }

  private _processStreamLine(
    line: string,
    messageIdMap: Map<string, string>,
    fallbackMessageId: string | null,
    streamState: StreamState = { reportedError: false }
  ): string | null {
    const sid = streamState.sessionId // #21357: every write below targets the originating chat
    try {
      const jsonStr = line.slice(6).trim()
      if (!jsonStr) return fallbackMessageId

      const data = JSON.parse(jsonStr)
      logger.debug('Received stream data:', data.type || 'unknown')

      if (data.type === 'start') {
        logger.debug('Stream started:', data.session_id)
        return fallbackMessageId
      }
      if (data.type === 'end' || data.type === 'cancelled') { // #17829: a stopped turn keeps its shown text
        logger.debug('Stream ended:', data.type)
        return fallbackMessageId
      }
      if (data.type === 'attachment_notice') { showAttachmentNotice(data.metadata); return fallbackMessageId } // #20195
      if (data.type === 'segment_complete') {
        logger.debug(`Segment complete: ${data.metadata?.completed_type}`)
        const backendId = data.metadata?.message_id
        if (backendId && messageIdMap.has(backendId)) {
          this.chatStore.updateMessage(messageIdMap.get(backendId)!, { status: 'sent' }, sid)
        }
        return fallbackMessageId
      }

      if (data.type === 'error') {
        logger.error('Stream error:', data.content)
        streamState.reportedError = true
        const errorMsgId = fallbackMessageId || this.chatStore.addMessage({
          content: '',
          sender: 'assistant'
        }, sid)
        if (!errorMsgId) return fallbackMessageId
        this.chatStore.updateMessage(errorMsgId, {
          content: streamErrorText(data),
          status: 'error'
        }, sid)
        return fallbackMessageId
      }

      if (!data.content && data.type !== 'command_approval_request') {
        return fallbackMessageId
      }

      // Map backend type to frontend type (must be before addMessage to set type immediately,
      // preventing the 80ms throttle window where the message appears as 'response' then
      // disappears when the real type is applied — issue #1364)
      const messageType = mapMessageType(data.type, data.metadata?.message_type)

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
          type: messageType,
          // #11843: persist the backend message id so a later poll / live-event
          // echo of this reply dedups against it instead of double-rendering.
          ...(backendMessageId ? { message_id: backendMessageId } : {})
        }, sid) as string
        if (!frontendMessageId) return fallbackMessageId // #21357: originating chat is gone: drop the stream's writes
        if (backendMessageId) {
          messageIdMap.set(backendMessageId, frontendMessageId)
        }
        fallbackMessageId = frontendMessageId
      }

      if (data.type === 'command_approval_request') {
        // #21357: typing is the open chat's; the approval flag is per chat, so it lands on the stream's own
        if (this.isOpenChat(sid)) this.chatStore.setTyping(false)
        // Issue #680: Set pending approval flag to prevent polling race conditions
        this.chatStore.setPendingApproval(true, sid)
        this.chatStore.updateMessage(frontendMessageId, {
          content: data.content || 'Command approval required',
          type: 'command_approval_request',
          metadata: {
            ...data.metadata,
            requires_approval: true
            // Note: approval_status is NOT set here - it's only set after user action
            // This allows the template to show approval buttons when !approval_status
          }
        }, sid)
        return fallbackMessageId
      }

      // Agent Zero Pattern: Backend sends CUMULATIVE content - just replace
      // Issue #1312: Throttle store updates to ~12fps instead of per-chunk
      // This reduces 200+ re-renders to ~20 per streaming response
      this._throttle.schedule({ sessionId: sid, messageId: frontendMessageId, content: data.content, type: messageType, metadata: data.metadata || {} })

      // Issue #1312: Throttle preview extraction to max every 200ms
      if (data.content && this.chatStore.isTyping && this.isOpenChat(sid)) {
        this._throttle.schedulePreview(data.content, messageType, sid)
      }

    } catch (e) {
      logger.warn('Failed to parse stream data:', { line, error: e })
    }

    return fallbackMessageId
  }

  private _finalizeStreamMessages(
    messageIdMap: Map<string, string>,
    fallbackMessageId: string | null,
    sessionId?: string
  ): void {
    // Issue #1312: Flush any remaining buffered update before finalization
    // #21357: the preview timer is shared; another running stream still needs it
    this._throttle.finish(this._activeStreams.total > 1)

    // Issue #1302: Finalize all messages and clean up truly empty ones
    // Check displayable content (after stripping internal tags) not raw content
    // to prevent deleting messages that have visible text between tags
    const allIds = [...messageIdMap.values()]
    if (fallbackMessageId && !allIds.includes(fallbackMessageId)) {
      allIds.push(fallbackMessageId)
    }

    for (const frontendId of allIds) {
      const owner = sessionId === undefined
        ? this.chatStore.currentSession
        : this.chatStore.sessions.find(s => s.id === sessionId) // #21357
      const msg = owner?.messages.find(m => m.id === frontendId)
      if (!msg) continue

      // `true` = strip a truncated marker ANYWHERE, not only at end-of-string.
      // This site was unanchored while the other two were anchored; the option
      // keeps that difference explicit instead of silently resolving it (#18065).
      const displayContent = stripBracketTags(msg.content || '', true).trim()

      if (displayContent) {
        if (msg.status !== 'error') {
          this.chatStore.updateMessage(frontendId, { status: 'sent' }, sessionId)
        }
      } else {
        this.chatStore.deleteMessage(frontendId, sessionId)
      }
    }
  }

  private handleJsonResponse(data: ChatJsonResponseData | undefined, sessionId?: string): void {
    if (!data) return
    // Add workflow messages first (thoughts, planning, debug, utility, sources)
    if (data.workflow_messages && Array.isArray(data.workflow_messages)) {
      data.workflow_messages.forEach((msg) => {
        this.chatStore.addMessage({
          content: msg.text || msg.content || '',
          sender: (msg.sender as 'user' | 'assistant' | 'system') || 'assistant',
          type: msg.type, // This enables filtering
          metadata: (msg.metadata || {}) as ChatMessage["metadata"]
        }, sessionId)
      })
    }

    // FIXED: Support both legacy (data.response) and new (data.content) formats
    // Backend streaming endpoint returns { success: true, data: { content: "...", role: "assistant", ... } }
    // Legacy format was: { response: "..." }
    const responseContent = data.response || data.content

    // Add final response with enhanced metadata.
    // #11843: route through addOrUpdateMessage keyed on the backend message id so
    // a later re-hydration / poll / live-event echo of the SAME reply reconciles
    // into this bubble instead of appending a duplicate. When the backend supplies
    // no id this behaves exactly like addMessage (a fresh id per distinct reply).
    if (responseContent) {
      const backendId = data.message_id || data.id
      this.chatStore.addOrUpdateMessage({
        ...(backendId ? { id: backendId, message_id: backendId } : {}),
        content: responseContent,
        sender: 'assistant',
        type: 'response', // Mark as final response
        metadata: {
          model: data.model,
          tokens: data.tokens_used,
          duration: data.response_time || data.processing_time,
        } as ChatMessage["metadata"]
      }, sessionId)
    }
  }

  // Enhanced session operations with error handling
  // #12685: optional metadata is forwarded to the backend as-is so callers
  // (e.g. CeoChatView) can stamp first-class tenancy scoping (company_id,
  // session_kind) on creation, instead of the title being the only signal —
  // the fragility that let agent conversations leak into the general list.
  async createNewSession(title?: string, metadata?: Record<string, unknown>): Promise<string> {
    // MVA-164: Client-mint UUID before any API call (server-round-trip-first pattern)
    // Generate UUID upfront
    const sessionId = crypto.randomUUID()

    // Call backend immediately with the client-minted UUID
    try {
      await chatRepository.createNewChat(title, metadata, sessionId)
      logger.debug('New chat session created on backend:', sessionId)
    } catch (error) {
      // Backend create failed - don't create local session if backend fails
      logger.error('Failed to create chat session on backend:', error)
      this.getAppStore()?.setGlobalError(i18n.global.t('chat.errors.createFailed', { error: extractErrorMessage(error, 'Unknown error') }))
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
          // #9724: the store needs isActive. Dates are taken as the repository
          // mapped them (#20865) — re-deriving them from snake_case fields the
          // repository does not return produced Invalid Date.
          this.chatStore.importSession({ ...session, title: session.title ?? '', isActive: false })
        })
        logger.debug(`Loaded ${sessions.length} chat sessions`)
      } else {
        logger.warn('getChatList() returned non-array value:', sessions)
      }

    } catch (error: unknown) {
      logger.error('Failed to load chat sessions:', error)
      // Don't throw error, allow app to continue with local sessions
      this.getAppStore()?.setGlobalError(i18n.global.t('chat.errors.loadSessionsFailed', { error: extractErrorMessage(error, 'Unknown error') }))
    }
  }

  async loadChatMessages(sessionId: string): Promise<void> {
    try {
      // Issue #680: skip while streaming or pending approval (polling data may be stale)
      if (this.chatStore.isTyping) {
        logger.debug(`Skipping message load - streaming in progress (isTyping=true)`)
        return
      }
      if (this.chatStore.hasPendingApproval) {
        logger.debug(`Skipping message load - pending approval (hasPendingApproval=true)`)
        return
      }

      logger.debug(`Loading messages for session: ${sessionId}`)

      // Update session with loaded messages
      const session = this.chatStore.sessions.find(s => s.id === sessionId)
      const loaded = await chatRepository.getChatMessages(sessionId)
      // #21022: a poll never replaces a question the person has not answered yet
      const messages = session ? keepUnansweredQuestions(session.messages, loaded) : loaded
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
      this.getAppStore()?.setGlobalError(i18n.global.t('chat.errors.loadMessagesFailed', { error: extractErrorMessage(error, 'Unknown error') }))
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
      this.getAppStore()?.setGlobalError(i18n.global.t('chat.errors.saveFailed', { error: extractErrorMessage(error, 'Unknown error') }))
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
    // Step 1: Delete from the backend FIRST. Removing the chat locally is only safe
    // once the server confirms the delete — otherwise the client and server diverge
    // and the "deleted" chat reappears on reload (#12327).
    try {
      await chatRepository.deleteChat(sessionId, fileAction, fileOptions)
      if (fileAction) {
        logger.debug(`File action executed: ${fileAction}`, fileOptions)
      }
      logger.debug('Chat successfully deleted from backend:', sessionId)
    } catch (error: unknown) {
      const errStatus = (error as { status?: number }).status
      if (errStatus !== 404) {
        // #12327: the backend rejected or never received the delete. Do NOT remove
        // the chat locally — keep it in place and surface an unambiguous failure so
        // the user can retry, instead of reporting a success that never happened.
        logger.error('Backend deletion failed; keeping chat locally:', error)
        this.getAppStore()?.setGlobalError(i18n.global.t('chat.errors.deleteFailed'))
        throw error
      }
      // 404 → the chat is already gone on the backend, so reconciling local state is
      // correct. Fall through to the local removal below.
      logger.warn('Chat not found on backend, reconciling local deletion:', sessionId)
    }

    // Step 2: Backend delete confirmed (or the chat was already gone) — remove it from
    // the local store and persisted state.
    try {
      const beforeCount = this.chatStore.sessions.length

      this.chatStore.deleteSession(sessionId)

      const afterCount = this.chatStore.sessions.length
      if (afterCount < beforeCount) {
        logger.debug('Chat successfully deleted from store:', sessionId)

        // Pinia persistence is automatic; give it a tick to flush to localStorage
        // before verifying below.
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
      }

      logger.debug(`Chat session ${sessionId} successfully deleted`)
    } catch (error: unknown) {
      logger.error('Store deletion failed:', error)
      this.getAppStore()?.setGlobalError(i18n.global.t('chat.errors.deleteFailed'))
      throw new Error(`Failed to delete chat from local storage: ${extractErrorMessage(error, 'Unknown error')}`)
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
    // #21357: the store resets typing on a switch; a chat whose stream is still running gets its indicator back
    if (this._activeStreams.has(sessionId) && !this.chatStore.isPendingApproval(sessionId)) this.chatStore.setTyping(true)
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
      this.getAppStore()?.setGlobalError(i18n.global.t('chat.errors.resetFailed', { error: extractErrorMessage(error, 'Unknown error') }))
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
      this.getAppStore()?.setGlobalError(i18n.global.t('chat.errors.clearFailed', { error: extractErrorMessage(error, 'Unknown error') }))
      throw error
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
      const { fetchWithAuth } = await import('@/utils/fetchWithAuth')
      const appConfig = (await import('@/config/AppConfig.js')).default
      const { getApiBase } = await import('@/config/ssot-config')

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
