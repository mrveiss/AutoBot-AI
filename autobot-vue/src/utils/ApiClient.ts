import appConfig from '@/config/AppConfig.js';
import { NetworkConstants } from '@/constants/network-constants.js';

// Type definitions for API client
export interface RequestOptions {
  headers?: Record<string, string>;
  timeout?: number;
}

export interface ApiResponse {
  ok: boolean;
  status: number;
  statusText: string;
  headers: Headers;
  json(): Promise<any>;
  text(): Promise<string>;
  blob(): Promise<Blob>;
}

// Enhanced ApiClient with TypeScript support
export class ApiClient {
  private baseUrl: string;
  private defaultHeaders: Record<string, string>;
  private baseUrlPromise: Promise<string> | null;

  constructor() {
    this.baseUrl = ''; // Will be loaded async
    this.defaultHeaders = {
      'Content-Type': 'application/json',
    };
    this.baseUrlPromise = null;
    this.initializeBaseUrl();
  }

  // Initialize base URL async
  private async initializeBaseUrl(): Promise<void> {
    try {
      this.baseUrl = await appConfig.getApiUrl('');
    } catch (error) {
      console.warn('[ApiClient.ts] AppConfig initialization failed, using NetworkConstants fallback');
      // Use NetworkConstants instead of hardcoded IP
      this.baseUrl = `http://${NetworkConstants.MAIN_MACHINE_IP}:${NetworkConstants.BACKEND_PORT}`;
    }
  }

  // Ensure base URL is loaded before making requests
  private async ensureBaseUrl(): Promise<string> {
    if (this.baseUrl) {
      return this.baseUrl;
    }

    if (!this.baseUrlPromise) {
      this.baseUrlPromise = this.initializeBaseUrl().then(() => this.baseUrl);
    }

    return await this.baseUrlPromise;
  }

  // Base request method with error handling and timeout support
  async request(endpoint: string, options: RequestOptions & {
    method?: string;
    body?: any;
  } = {}): Promise<ApiResponse> {
    const {
      method = 'GET',
      headers = {},
      body,
      timeout = appConfig.get('api.timeout', 30000),
    } = options;

    // Ensure base URL is loaded
    const baseUrl = await this.ensureBaseUrl();
    const url = baseUrl ? `${baseUrl}${endpoint}` : endpoint;

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), timeout);

    try {
      const response = await fetch(url, {
        method,
        headers: { ...this.defaultHeaders, ...headers },
        body: body ? JSON.stringify(body) : undefined,
        signal: controller.signal,
      });

      clearTimeout(timeoutId);
      return response as ApiResponse;
    } catch (error) {
      clearTimeout(timeoutId);
      if (error instanceof Error && error.name === 'AbortError') {
        throw new Error(`Request timeout after ${timeout}ms`);
      }
      throw error;
    }
  }

  // GET request
  async get(endpoint: string, options: RequestOptions = {}): Promise<ApiResponse> {
    return this.request(endpoint, { method: 'GET', ...options });
  }

  // POST request
  async post(endpoint: string, data?: any, options: RequestOptions = {}): Promise<ApiResponse> {
    const result = await this.request(endpoint, { method: 'POST', body: data, ...options });
    return result;
  }

  // PUT request
  async put(endpoint: string, data?: any, options: RequestOptions = {}): Promise<ApiResponse> {
    return this.request(endpoint, { method: 'PUT', body: data, ...options });
  }

  // DELETE request
  async delete(endpoint: string, options: RequestOptions = {}): Promise<ApiResponse> {
    return this.request(endpoint, { method: 'DELETE', ...options });
  }

  // ==================================================================================
  // CHAT API METHODS - FIXED TO MATCH BACKEND
  // ==================================================================================

  /**
   * Send a chat message using the correct backend endpoint
   * Backend expects: POST /api/chat with ChatMessage format
   */
  async sendChatMessage(message: string, options: any = {}): Promise<any> {
    // Use the correct endpoint: /api/chat (not /api/chat/message)
    const response = await this.post('/api/chat', {
      content: message,
      role: "user",
      session_id: options.chatId || options.session_id || null,
      message_type: options.message_type || "text",
      metadata: options.metadata || {}
    });

    // Check if it's a streaming response
    const contentType = response.headers.get('content-type');
    if (contentType && contentType.includes('text/event-stream')) {
      return {
        type: 'streaming',
        response: response
      };
    } else {
      const data = await response.json();
      return {
        type: 'json',
        data: data
      };
    }
  }

  /**
   * Create a new chat session
   * Backend endpoint: POST /api/chat/sessions
   * Backend expects SessionCreate model: { title?: string, metadata?: dict }
   */
  async createNewChat(): Promise<any> {
    const response = await this.post('/api/chat/sessions', {});
    return response.json();
  }

  /**
   * Get list of chat sessions
   * Backend endpoint: GET /api/chats
   */
  async getChatList(): Promise<any> {
    const response = await this.get('/api/chats');
    return response.json();
  }

  /**
   * Get messages for a specific chat session
   * Backend endpoint: GET /api/chat/sessions/{session_id}
   */
  async getChatMessages(chatId: string): Promise<any> {
    const response = await this.get(`/api/chat/sessions/${chatId}`);
    return response.json();
  }

  /**
   * Save chat messages in bulk to a session
   * Backend endpoint: POST /api/chats/{chat_id}/save
   * @param chatId - The chat session ID
   * @param messages - Array of messages to save
   * @returns Promise with save result
   */
  async saveChatMessages(chatId: string, messages: any[]): Promise<any> {
    try {
      const response = await this.post(`/api/chats/${chatId}/save`, {
        data: {
          messages: messages,
          name: ""  // Optional session name
        }
      });

      const result = await response.json();
      return result;
    } catch (error) {
      console.error('Failed to save chat messages:', error);
      throw error;
    }
  }

  /**
   * Delete a chat session
   * Backend endpoint: DELETE /api/chat/sessions/{session_id}
   */
  async deleteChat(chatId: string): Promise<any> {
    const response = await this.delete(`/api/chat/sessions/${chatId}`);
    return response.json();
  }

  /**
   * Update a chat session (title, metadata)
   * Backend endpoint: PUT /api/chat/sessions/{session_id}
   */
  async updateChatSession(chatId: string, updates: any): Promise<any> {
    const response = await this.put(`/api/chat/sessions/${chatId}`, updates);
    return response.json();
  }

  // ==================================================================================
  // STREAMING METHODS FOR REAL-TIME CHAT
  // ==================================================================================

  /**
   * Send streaming chat message
   * Backend endpoint: POST /api/chat/stream
   */
  async sendStreamingMessage(message: string, options: any = {}): Promise<ApiResponse> {
    const response = await this.post('/api/chat/stream', {
      content: message,
      role: "user",
      session_id: options.chatId || options.session_id || null,
      message_type: options.message_type || "text",
      metadata: options.metadata || {}
    });

    return response; // Return the streaming response directly
  }

  /**
   * Export chat session
   * Backend endpoint: GET /api/chat/sessions/{session_id}/export
   */
  async exportChatSession(sessionId: string, format: string = 'json'): Promise<Blob> {
    const response = await this.get(`/api/chat/sessions/${sessionId}/export?format=${format}`);
    return response.blob();
  }

  /**
   * Get chat statistics
   * Backend endpoint: GET /api/chat/stats
   */
  async getChatStats(): Promise<any> {
    const response = await this.get('/api/chat/stats');
    return response.json();
  }

  // ==================================================================================
  // OTHER API METHODS
  // ==================================================================================

  async getSettings(): Promise<any> {
    const response = await this.get('/api/settings/');
    return response.json();
  }

  async saveSettings(settings: any): Promise<any> {
    const response = await this.post('/api/settings/', settings);
    return response.json();
  }

  async getSystemHealth(): Promise<any> {
    const response = await this.get('/api/system/health');
    return response.json();
  }

  async getServiceHealth(): Promise<any> {
    // Use monitoring services health endpoint
    const response = await this.get('/api/monitoring/services/health');
    return response.json();
  }

  async checkHealth(): Promise<any> {
    const response = await this.get('/api/health');
    return response.json();
  }

  async checkChatHealth(): Promise<any> {
    const response = await this.get('/api/chat/health');
    return response.json();
  }

  // ==================================================================================
  // TERMINAL API METHODS
  // ==================================================================================

  /**
   * Create a new terminal session
   * Backend endpoint: POST /api/agent-terminal/sessions
   */
  async createTerminalSession(options: any): Promise<any> {
    const response = await this.post('/api/terminal/sessions', options);
    return response.json();
  }

  /**
   * Get all terminal sessions
   * Backend endpoint: GET /api/agent-terminal/sessions
   */
  async getTerminalSessions(): Promise<any> {
    const response = await this.get('/api/agent-terminal/sessions');
    return response.json();
  }

  /**
   * Get terminal session info
   * Backend endpoint: GET /api/agent-terminal/sessions/{sessionId}
   */
  async getTerminalSessionInfo(sessionId: string): Promise<any> {
    const response = await this.get(`/api/agent-terminal/sessions/${sessionId}`);
    return response.json();
  }

  /**
   * Delete terminal session
   * Backend endpoint: DELETE /api/agent-terminal/sessions/{sessionId}
   */
  async deleteTerminalSession(sessionId: string): Promise<any> {
    const response = await this.delete(`/api/agent-terminal/sessions/${sessionId}`);
    return response.json();
  }

  /**
   * Execute terminal command
   * Backend endpoint: POST /api/agent-terminal/execute
   */
  async executeTerminalCommand(command: string, options: any = {}): Promise<any> {
    const response = await this.post('/api/agent-terminal/execute', {
      command,
      ...options
    });
    return response.json();
  }
}

// Export singleton instance
const apiClient = new ApiClient();
export default apiClient;
