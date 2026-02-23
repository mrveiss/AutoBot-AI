import axios from 'axios'
import type { AxiosInstance, AxiosResponse } from 'axios'
import { getBackendUrl } from '@/config/ssot-config'
import { createLogger } from '@/utils/debugUtils'

// Create scoped logger for ChatRepository
const logger = createLogger('ChatRepository')

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant' | 'system'
  content: string
  timestamp?: string
  metadata?: {
    model?: string
    tokens?: number
    duration?: number
  }
}

export interface ChatSession {
  id: string
  title?: string
  messages: ChatMessage[]
  created_at: string
  updated_at: string
}

export interface ChatStreamResponse {
  content: string
  done: boolean
  metadata?: {
    model?: string
    tokens?: number
    duration?: number
  }
}

/**
 * Options for sending chat messages
 * Supports file attachments and additional metadata
 */
export interface SendMessageOptions {
  /** File IDs from conversation-files API to attach to this message */
  attachments?: string[]
  /** Additional metadata to include with the message */
  metadata?: Record<string, any>
  /** Allow any additional options to be passed through */
  [key: string]: any
}

/**
 * Response type for sendMessage - supports both streaming and non-streaming
 */
export interface SendMessageResponse {
  type: 'streaming' | 'buffered'
  response?: Response  // For streaming responses
  data?: any           // For buffered responses (backward compatibility)
}

/**
 * Issue #547: Session fact for pre-deletion preview
 */
export interface SessionFact {
  id: string
  content: string
  full_content: string
  category: string
  tags: string[]
  important: boolean
  preserve: boolean
  created_at?: string
}

/**
 * Issue #547: Response from getSessionFacts endpoint
 */
export interface SessionFactsResponse {
  status: string
  session_id: string
  fact_count: number
  facts: SessionFact[]
}

/**
 * Issue #547: Response from preserveSessionFacts endpoint
 */
export interface PreserveFactsResponse {
  status: 'success' | 'partial'
  session_id: string
  updated_count: number
  failed_count: number
  errors?: string[]
}

/**
 * Issue #547: KB cleanup result from session deletion
 */
export interface KBCleanupResult {
  facts_deleted: number
  facts_preserved: number
  cleanup_error?: string | null
}

/**
 * Repository for chat-related API operations
 * Handles communication with backend chat endpoints
 */
export class ChatRepository {
  private axios: AxiosInstance
  private baseURL: string

  constructor(baseURL?: string) {
    this.baseURL = baseURL || import.meta.env.VITE_API_URL || getBackendUrl()
    this.axios = axios.create({
      baseURL: this.baseURL,
      timeout: 60000, // 60 second timeout for chat operations
      headers: {
        'Content-Type': 'application/json'
      }
    })

    // Inject auth token on every request
    this.axios.interceptors.request.use(config => {
      const token = this._getAuthToken()
      if (token) {
        config.headers['Authorization'] = `Bearer ${token}`
      }
      return config
    })

    // Add response interceptor — redirect to login on 401 (#967)
    this.axios.interceptors.response.use(
      response => response,
      error => {
        logger.error('Request failed:', error)
        if (
          error?.response?.status === 401 &&
          typeof window !== 'undefined' &&
          !window.location.pathname.includes('/login')
        ) {
          logger.warn('401 Unauthorized — clearing auth and redirecting to login')
          localStorage.removeItem('autobot_auth')
          localStorage.removeItem('autobot_user')
          const redirect = encodeURIComponent(window.location.pathname)
          window.location.href = `/login?redirect=${redirect}`
        }
        return Promise.reject(error)
      }
    )
  }

  private _getAuthToken(): string | null {
    try {
      const stored = localStorage.getItem('autobot_auth')
      if (stored) {
        const auth = JSON.parse(stored)
        if (auth.token && auth.token !== 'single_user_mode') {
          return auth.token
        }
      }
    } catch {
      // ignore parse errors
    }
    return null
  }

  /**
   * Send chat message with proper SSE streaming support using fetch API
   *
   * @param message - Message content to send
   * @param chatId - Optional chat session ID
   * @param options - Optional attachments and metadata
   * @returns Streaming response or buffered response depending on backend
   */
  async sendMessage(
    message: string,
    chatId?: string,
    options?: SendMessageOptions
  ): Promise<SendMessageResponse> {
    try {
      // Ensure we have a chat ID
      if (!chatId) {
        throw new Error('Chat ID is required for sending messages')
      }

      // Build metadata object from options
      const metadata: Record<string, any> = {}

      if (options) {
        // Include attachments if provided
        if (options.attachments && options.attachments.length > 0) {
          metadata.attachments = options.attachments
        }

        // Merge any explicit metadata
        if (options.metadata) {
          Object.assign(metadata, options.metadata)
        }

        // Include any other options (excluding attachments and metadata to avoid duplication)
        Object.keys(options).forEach(key => {
          if (key !== 'attachments' && key !== 'metadata') {
            metadata[key] = options[key]
          }
        })
      }

      // Use native fetch API for proper SSE streaming support
      const url = `${this.baseURL}/api/chats/${chatId}/message`
      const fetchHeaders: Record<string, string> = { 'Content-Type': 'application/json' }
      const authToken = this._getAuthToken()
      if (authToken) fetchHeaders['Authorization'] = `Bearer ${authToken}`
      const response = await fetch(url, {
        method: 'POST',
        headers: fetchHeaders,
        body: JSON.stringify({
          message: message,
          context: metadata
        })
      })

      if (!response.ok) {
        const errorText = await response.text()
        throw new Error(`HTTP ${response.status}: ${errorText}`)
      }

      // Check if response is SSE streaming
      const contentType = response.headers.get('content-type')
      if (contentType && contentType.includes('text/event-stream')) {
        // Return streaming response for SSE
        return {
          type: 'streaming',
          response: response
        }
      } else {
        // Return buffered response for backward compatibility
        const data = await response.json()
        return {
          type: 'buffered',
          data: data
        }
      }
    } catch (error: any) {
      logger.error('Failed to send message:', error)
      throw error
    }
  }

  // Send streaming chat message
  async sendStreamingMessage(
    message: string,
    chatId?: string,
    onChunk?: (chunk: ChatStreamResponse) => void
  ): Promise<void> {
    try {
      const response = await this.axios.post(
        '/api/chat',
        {
          message,
          chat_id: chatId,
          stream: true
        },
        {
          responseType: 'stream',
          adapter: 'fetch' // Use fetch adapter for streaming
        }
      )

      // Handle streaming response
      const reader = response.data.getReader()
      const decoder = new TextDecoder()

      while (true) {
        const { done, value } = await reader.read()

        if (done) break

        const chunk = decoder.decode(value)
        const lines = chunk.split('\n').filter(line => line.trim())

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const data = line.slice(6)
            if (data === '[DONE]') continue

            try {
              const parsed = JSON.parse(data)
              if (onChunk) onChunk(parsed)
            } catch (e) {
              logger.warn('Failed to parse streaming chunk:', e)
            }
          }
        }
      }
    } catch (error: any) {
      logger.error('Failed to send streaming message:', error)
      throw error
    }
  }

  // Create new chat session
  async createNewChat(title?: string, metadata?: any): Promise<ChatSession> {
    try {
      const response = await this.post('/api/chat/sessions', {
        title: title || 'New Chat',
        metadata: metadata || {}
      })
      return response.data?.data || response.data
    } catch (error: any) {
      logger.error('Failed to create new chat:', error)
      throw error
    }
  }

  // Get chat sessions (alias for getChatList)
  async getSessions(): Promise<ChatSession[]> {
    return this.getChatList()
  }

  // Get list of all chat sessions (for compatibility with controller)
  async getChatList(): Promise<any[]> {
    try {
      const response = await this.get('/api/chat/sessions')
      // Fix: axios wraps response in .data, and API response has { data: { sessions: [...] } }
      const sessions = response.data?.data?.sessions || response.data?.sessions || []

      // Transform backend session format to frontend store format
      return sessions.map((session: any) => ({
        id: session.id || session.chatId,
        title: session.title || session.name || `Chat ${session.id?.slice(0, 8)}`,
        messages: [], // Sessions list doesn't include messages - loaded separately
        createdAt: new Date(session.createdAt || session.createdTime),
        updatedAt: new Date(session.updatedAt || session.lastModified),
        isActive: false // Will be set by store when session is selected
      }))
    } catch (error: any) {
      logger.error('Failed to get chat list:', error)
      return [] // Return empty array on error to prevent app crash
    }
  }

  // Get single session by ID
  async getSession(sessionId: string): Promise<ChatSession> {
    try {
      const response = await this.get(`/api/chat/sessions/${sessionId}`)
      return response.data
    } catch (error: any) {
      logger.error('Failed to get session:', error)
      throw error
    }
  }

  // Get messages for a chat session
  async getChatMessages(sessionId: string): Promise<ChatMessage[]> {
    try {
      logger.debug(`Fetching messages for session: ${sessionId}`)
      const response = await this.get(`/api/chat/sessions/${sessionId}`)
      const data = response.data
      logger.debug(`Raw API response:`, JSON.stringify(data).substring(0, 200))

      // Backend returns messages in data.messages
      const backendMessages = data.data?.messages || data.messages || []
      logger.debug(`Backend returned ${backendMessages.length} messages`)

      // Transform backend message format to frontend format
      const messages = backendMessages.map((msg: any, index: number) => {
        // Issue #680: Normalize message type to prevent wrong badges
        // Backend may save raw types like 'llm_response_chunk' which need mapping
        const rawType = msg.messageType || msg.type || 'message'
        const normalizedType = this.normalizeMessageType(rawType)

        const transformed = {
          id: msg.id || msg.metadata?.message_id || msg.rawData?.message_id || `${msg.sender}-${msg.timestamp}-${index}`,
          sender: this.normalizeSender(msg.sender),
          content: msg.text || msg.content || '',
          timestamp: new Date(msg.timestamp || new Date().toISOString()),
          type: normalizedType,
          // CRITICAL FIX: Backend saves approval metadata in rawData, not metadata
          // Check both rawData (old format) and metadata (new format) for backward compatibility
          metadata: msg.metadata || msg.rawData || {}
        }
        logger.debug(`Message ${index + 1}: sender=${msg.sender} → ${transformed.sender}, type=${rawType} → ${normalizedType}, content length=${transformed.content.length}`)
        return transformed
      })

      logger.debug(`Transformed ${messages.length} messages, returning to controller`)
      return messages
    } catch (error: any) {
      logger.error('Failed to get chat messages:', error)
      // Return empty array on error to prevent UI breakage
      return []
    }
  }

  /**
   * Normalize backend message types to frontend display types.
   * Issue #680: Prevents wrong type badges from showing on loaded messages.
   *
   * Maps backend types like 'llm_response_chunk' to display types like 'response'.
   */
  private normalizeMessageType(type: string): string {
    if (!type) return 'response'

    // Map streaming types to 'response'
    if (type === 'response' || type === 'llm_response' || type === 'llm_response_chunk') {
      return 'response'
    }

    // Map known semantic types
    if (type === 'thought' || type.includes('thought')) return 'thought'
    if (type.includes('planning')) return 'planning'
    if (type.includes('debug')) return 'debug'
    if (type.includes('utility')) return 'utility'
    if (type.includes('source')) return 'sources'
    if (type.includes('json')) return 'json'
    if (type === 'command_approval_request') return 'command_approval_request'
    if (type === 'terminal_output' || type === 'terminal_command') return type

    // Default to 'message' for unrecognized types
    return 'message'
  }

  // Helper to normalize sender field from backend to frontend format
  private normalizeSender(sender: string | undefined): 'user' | 'assistant' | 'system' {
    if (!sender) return 'system'

    // Normalize terminal-related senders to 'system'
    if (sender === 'agent_terminal' || sender === 'terminal') {
      return 'system'
    }

    if (sender === 'user' || sender === 'assistant' || sender === 'system') {
      return sender as 'user' | 'assistant' | 'system'
    }

    return 'assistant' // Default fallback
  }

  // Delete chat session - ENHANCED: Support file_action and file_options
  async deleteChat(
    chatId: string,
    fileAction?: 'delete' | 'transfer_kb' | 'transfer_shared',
    fileOptions?: any
  ): Promise<any> {
    try {
      const params: any = {}

      if (fileAction) {
        params.file_action = fileAction
      }

      if (fileOptions) {
        params.file_options = JSON.stringify(fileOptions)
      }

      const response = await this.delete(`/api/chat/sessions/${chatId}`, { params })
      return response.data || response
    } catch (error: any) {
      logger.error('Failed to delete chat:', error)
      throw error
    }
  }

  // Reset chat (clear current session)
  // Issue #552: Fixed path - backend uses /api/chat/reset
  async resetChat(): Promise<any> {
    try {
      const response = await this.post('/api/chat/reset')
      return response.data || response
    } catch (error: any) {
      logger.error('Failed to reset chat:', error)
      throw error
    }
  }

  // Get chat history (legacy endpoint)
  // Issue #552: Fixed path - backend uses /api/chat/sessions
  async getChatHistory(): Promise<any> {
    try {
      const response = await this.get('/api/chat/sessions')
      return response.data || response
    } catch (error: any) {
      logger.warn('Failed to get chat history (legacy):', error)
      return { messages: [] }
    }
  }

  async saveChatMessages(params: { chatId: string; messages: any[]; name?: string }): Promise<any> {
    try {
      // CRITICAL FIX Issue #259: Wrap messages in 'data' object to match backend expectation
      // Backend expects: { data: { messages: [...], name: "..." } }
      const response = await this.post(`/api/chats/${params.chatId}/save`, {
        data: {
          messages: params.messages,
          name: params.name || ''
        }
      })
      return response.data || response
    } catch (error: any) {
      logger.error('Failed to save chat messages:', error)
      throw error
    }
  }

  // ============================================================================
  // Session Facts API (Issue #547)
  // ============================================================================

  /**
   * Get all knowledge base facts created during a session.
   * Issue #547: Used for pre-deletion preview to let users select facts to preserve.
   */
  async getSessionFacts(sessionId: string): Promise<SessionFactsResponse> {
    try {
      // Issue #552: Fixed path - backend uses /api/chat-knowledge/chat/sessions/*
      const response = await this.get(`/api/chat-knowledge/chat/sessions/${sessionId}/facts`)
      return response.data || response
    } catch (error: any) {
      logger.error('Failed to get session facts:', error)
      throw error
    }
  }

  /**
   * Mark selected facts as preserved/important before session deletion.
   * Issue #547: Facts marked as preserved will not be deleted with the session.
   */
  async preserveSessionFacts(
    sessionId: string,
    factIds: string[],
    preserve: boolean = true
  ): Promise<PreserveFactsResponse> {
    try {
      // Issue #552: Fixed path - backend uses /api/chat-knowledge/chat/sessions/*
      const response = await this.post(`/api/chat-knowledge/chat/sessions/${sessionId}/facts/preserve`, {
        fact_ids: factIds,
        preserve
      })
      return response.data || response
    } catch (error: any) {
      logger.error('Failed to preserve session facts:', error)
      throw error
    }
  }

  // Helper methods for axios operations
  private async get(url: string, config?: any): Promise<AxiosResponse> {
    return this.axios.get(url, config)
  }

  private async post(url: string, data?: any, config?: any): Promise<AxiosResponse> {
    return this.axios.post(url, data, config)
  }

  private async delete(url: string, config?: any): Promise<AxiosResponse> {
    return this.axios.delete(url, config)
  }

  private async put(url: string, data?: any, config?: any): Promise<AxiosResponse> {
    return this.axios.put(url, data, config)
  }
}

// Export singleton instance
export const chatRepository = new ChatRepository()
