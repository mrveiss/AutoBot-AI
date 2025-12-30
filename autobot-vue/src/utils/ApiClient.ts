import appConfig from '@/config/AppConfig.js';
import { NetworkConstants } from '@/constants/network';
import { createLogger } from '@/utils/debugUtils';

// Create scoped logger for ApiClient
const logger = createLogger('ApiClient');

// Type definitions for API client
export interface RequestOptions {
  headers?: Record<string, string>;
  timeout?: number;
  onUploadProgress?: (progressEvent: any) => void; // For upload progress tracking
  responseType?: string; // For response type specification (e.g., 'blob')
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
// Issue #598: All timeouts now sourced from AppConfig (SINGLE SOURCE OF TRUTH)
export class ApiClient {
  private baseUrl: string;
  private defaultHeaders: Record<string, string>;
  private baseUrlPromise: Promise<string> | null;
  private defaultTimeout: number;

  constructor() {
    this.baseUrl = ''; // Will be loaded async
    this.defaultHeaders = {
      'Content-Type': 'application/json',
    };
    this.baseUrlPromise = null;
    // Issue #598: Use AppConfig as single source of truth for timeout
    this.defaultTimeout = appConfig.getTimeout('default');
    this.initializeBaseUrl();
  }

  // Public setter for base URL (used by plugin configuration)
  setBaseUrl(url: string): void {
    this.baseUrl = url;
  }

  // Public setter for default timeout (used by plugin configuration)
  setTimeout(timeout: number): void {
    this.defaultTimeout = timeout;
  }

  // Invalidate cache (placeholder for future caching implementation)
  invalidateCache(): void {
    // Currently no caching implemented
    // This method exists for future caching functionality
  }

  // Initialize base URL async
  private async initializeBaseUrl(): Promise<void> {
    try {
      this.baseUrl = await appConfig.getApiUrl('');
    } catch (_error) {
      logger.warn('[ApiClient.ts] AppConfig initialization failed, using NetworkConstants fallback');
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
      timeout = options.timeout || this.defaultTimeout,
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
   * Issue #671: Added optional options parameter for timeout control
   */
  async getChatList(options: RequestOptions = {}): Promise<any> {
    // Issue #671: Use short timeout for init calls to prevent UI freezing
    const timeout = options.timeout || appConfig.getTimeout('short');
    const response = await this.get('/api/chats', { ...options, timeout });
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
      logger.error('Failed to save chat messages:', error);
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

  /**
   * Get user settings
   * Issue #671: Added optional options parameter for timeout control
   */
  async getSettings(options: RequestOptions = {}): Promise<any> {
    // Issue #671: Use short timeout for init calls
    const timeout = options.timeout || appConfig.getTimeout('short');
    const response = await this.get('/api/settings/', { ...options, timeout });
    return response.json();
  }

  async saveSettings(settings: any): Promise<any> {
    const response = await this.post('/api/settings/', settings);
    return response.json();
  }

  async getSystemHealth(): Promise<any> {
    // Issue #598: Use health-specific timeout from AppConfig
    const response = await this.get('/api/system/health', { timeout: appConfig.getTimeout('health') });
    return response.json();
  }

  async getServiceHealth(): Promise<any> {
    // Use monitoring services health endpoint
    // Issue #598: Use health-specific timeout from AppConfig
    const response = await this.get('/api/monitoring/services/health', { timeout: appConfig.getTimeout('health') });
    return response.json();
  }

  async checkHealth(): Promise<any> {
    // Issue #598: Use health-specific timeout from AppConfig
    const response = await this.get('/api/health', { timeout: appConfig.getTimeout('health') });
    return response.json();
  }

  async checkChatHealth(): Promise<any> {
    // Issue #598: Use health-specific timeout from AppConfig
    const response = await this.get('/api/chat/health', { timeout: appConfig.getTimeout('health') });
    return response.json();
  }

  // ==================================================================================
  // TERMINAL API METHODS
  // ==================================================================================

  /**
   * Create a new terminal session (Tools Terminal - direct PTY)
   * Backend endpoint: POST /api/terminal/sessions
   *
   * NOTE: This is for Tools Terminal (standalone, no agent control).
   * For Chat Terminal with agent control, use createAgentTerminalSession().
   * Issue #73: Fixed to use correct endpoint for Tools Terminal
   */
  async createTerminalSession(options: any): Promise<any> {
    const response = await this.post('/api/terminal/sessions', options);
    return response.json();
  }

  /**
   * Create an agent terminal session (Chat Terminal - with agent control)
   * Backend endpoint: POST /api/agent-terminal/sessions
   *
   * NOTE: This is for Chat Terminal with AI agent control and approval workflow.
   * For Tools Terminal (direct PTY), use createTerminalSession().
   * Issue #73: Agent Terminal for Chat Terminal with approval workflow
   */
  async createAgentTerminalSession(options: {
    agent_id?: string;
    agent_role?: string;
    conversation_id?: string;
    host?: string;
    metadata?: Record<string, any>;
  }): Promise<any> {
    const payload = {
      agent_id: options.agent_id || `agent_${Date.now()}`,
      agent_role: options.agent_role || 'chat_agent',
      conversation_id: options.conversation_id || null,
      host: options.host || 'main',
      metadata: options.metadata || null
    };
    const response = await this.post('/api/agent-terminal/sessions', payload);
    return response.json();
  }

  /**
   * Get all terminal sessions (Tools Terminal)
   * Backend endpoint: GET /api/terminal/sessions
   * Issue #73: Fixed to use correct endpoint
   */
  async getTerminalSessions(): Promise<any> {
    const response = await this.get('/api/terminal/sessions');
    return response.json();
  }

  /**
   * Get all agent terminal sessions (Chat Terminal)
   * Backend endpoint: GET /api/agent-terminal/sessions
   */
  async getAgentTerminalSessions(filters: {
    agent_id?: string;
    conversation_id?: string;
  } = {}): Promise<any> {
    const params = new URLSearchParams();
    if (filters.agent_id) params.append('agent_id', filters.agent_id);
    if (filters.conversation_id) params.append('conversation_id', filters.conversation_id);
    const query = params.toString() ? `?${params.toString()}` : '';
    const response = await this.get(`/api/agent-terminal/sessions${query}`);
    return response.json();
  }

  /**
   * Get terminal session info (Tools Terminal)
   * Backend endpoint: GET /api/terminal/sessions/{sessionId}
   * Issue #73: Fixed to use correct endpoint
   */
  async getTerminalSessionInfo(sessionId: string): Promise<any> {
    const response = await this.get(`/api/terminal/sessions/${sessionId}`);
    return response.json();
  }

  /**
   * Get agent terminal session info (Chat Terminal)
   * Backend endpoint: GET /api/agent-terminal/sessions/{sessionId}
   */
  async getAgentTerminalSessionInfo(sessionId: string): Promise<any> {
    const response = await this.get(`/api/agent-terminal/sessions/${sessionId}`);
    return response.json();
  }

  /**
   * Delete terminal session (Tools Terminal)
   * Backend endpoint: DELETE /api/terminal/sessions/{sessionId}
   * Issue #73: Fixed to use correct endpoint
   */
  async deleteTerminalSession(sessionId: string): Promise<any> {
    const response = await this.delete(`/api/terminal/sessions/${sessionId}`);
    return response.json();
  }

  /**
   * Delete agent terminal session (Chat Terminal)
   * Backend endpoint: DELETE /api/agent-terminal/sessions/{sessionId}
   */
  async deleteAgentTerminalSession(sessionId: string): Promise<any> {
    const response = await this.delete(`/api/agent-terminal/sessions/${sessionId}`);
    return response.json();
  }

  /**
   * Execute terminal command (deprecated - use WebSocket for real-time I/O)
   * Backend endpoint: POST /api/terminal/command
   * Issue #552: Fixed path - backend uses /command not /execute
   */
  async executeTerminalCommand(command: string, options: any = {}): Promise<any> {
    const response = await this.post('/api/terminal/command', {
      command,
      ...options
    });
    return response.json();
  }
}

// Export singleton instance
const apiClient = new ApiClient();
export default apiClient;
