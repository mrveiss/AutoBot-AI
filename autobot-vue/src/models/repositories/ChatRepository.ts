import axios from 'axios'
import type { AxiosInstance, AxiosResponse } from 'axios'
import { NetworkConstants } from '@/constants/network-constants.js'

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
 * Repository for chat-related API operations
 * Handles communication with backend chat endpoints
 */
export class ChatRepository {
  private axios: AxiosInstance
  private baseURL: string

  constructor(baseURL?: string) {
    this.baseURL = baseURL || import.meta.env.VITE_API_URL || `http://${NetworkConstants.MAIN_MACHINE_IP}:${NetworkConstants.BACKEND_PORT}`
    this.axios = axios.create({
      baseURL: this.baseURL,
      timeout: 60000, // 60 second timeout for chat operations
      headers: {
        'Content-Type': 'application/json'
      }
    })

    // Add response interceptor for error handling
    this.axios.interceptors.response.use(
      response => response,
      error => {
        console.error('[ChatRepository] Request failed:', error)
        return Promise.reject(error)
      }
    )
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
      const response = await fetch(url, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
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
      console.error('Failed to send message:', error)
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
              console.warn('Failed to parse streaming chunk:', e)
            }
          }
        }
      }
    } catch (error: any) {
      console.error('Failed to send streaming message:', error)
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
      console.error('Failed to create new chat:', error)
      throw error
    }
  }

  // Get chat sessions
  async getSessions(): Promise<ChatSession[]> {
    try {
      const response = await this.get('/api/chat/sessions')
      return response.data?.sessions || []
    } catch (error: any) {
      console.error('Failed to get sessions:', error)
      throw error
    }
  }

  // Get single session by ID
  async getSession(sessionId: string): Promise<ChatSession> {
    try {
      const response = await this.get(`/api/chat/sessions/${sessionId}`)
      return response.data
    } catch (error: any) {
      console.error('Failed to get session:', error)
      throw error
    }
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
      console.error('Failed to delete chat:', error)
      throw error
    }
  }

  // Reset chat (clear current session)
  async resetChat(): Promise<any> {
    try {
      const response = await this.post('/api/reset')
      return response.data || response
    } catch (error: any) {
      console.error('Failed to reset chat:', error)
      throw error
    }
  }

  // Get chat history (legacy endpoint)
  async getChatHistory(): Promise<any> {
    try {
      const response = await this.get('/api/history')
      return response.data || response
    } catch (error: any) {
      console.warn('Failed to get chat history (legacy):', error)
      return { messages: [] }
    }
  }

  async saveChatMessages(params: { chatId: string; messages: any[] }): Promise<any> {
    try {
      const response = await this.post(`/api/chats/${params.chatId}/save`, {
        messages: params.messages
      })
      return response.data || response
    } catch (error: any) {
      console.error('Failed to save chat messages:', error)
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
