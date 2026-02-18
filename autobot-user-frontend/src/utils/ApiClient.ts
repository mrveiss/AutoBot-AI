import appConfig from '@/config/AppConfig.js';
import { createLogger } from '@/utils/debugUtils';

// Create scoped logger for ApiClient
const logger = createLogger('ApiClient');

// Type definitions for API client
export interface RequestOptions {
  headers?: Record<string, string>;
  timeout?: number;
  maxRetries?: number;
  onUploadProgress?: (progressEvent: any) => void;
  responseType?: string;
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

// Enhanced ApiClient — consolidated from JS and TS implementations (#810)
// Issue #598: All timeouts sourced from AppConfig (SINGLE SOURCE OF TRUTH)
// Convenience methods (get/post/put/delete) return parsed JSON data.
// Use rawRequest() for raw Response access (streaming, blobs).
export class ApiClient {
  private baseUrl: string;
  private defaultHeaders: Record<string, string>;
  private baseUrlPromise: Promise<string> | null;
  private defaultTimeout: number;
  private settings: Record<string, any>;

  constructor() {
    this.baseUrl = '';
    this.defaultHeaders = {
      'Content-Type': 'application/json',
    };
    this.baseUrlPromise = null;
    this.defaultTimeout = appConfig.getTimeout('default');
    this.settings = this._loadSettings();
    // Don't call initializeBaseUrl() in constructor to avoid circular dependency
    // It will be called lazily on first API request
  }

  // Public setter for base URL (used by plugin configuration)
  setBaseUrl(url: string): void {
    this.baseUrl = url;
  }

  // Public setter for default timeout (used by plugin configuration)
  setTimeout(timeout: number): void {
    this.defaultTimeout = timeout;
  }

  updateBaseUrl(newBaseUrl: string): void {
    this.baseUrl = newBaseUrl;
  }

  invalidateCache(): void {
    try {
      appConfig.invalidateCache();
    } catch (_error) {
      Object.keys(localStorage).forEach(key => {
        if (key.startsWith('autobot_api_') || key.startsWith('autobot_config_')) {
          localStorage.removeItem(key);
        }
      });
    }
  }

  getConfiguration(): Record<string, any> {
    return {
      baseUrl: this.baseUrl,
      timeout: this.defaultTimeout,
      proxyMode: !this.baseUrl,
      settings: this.settings,
    };
  }

  // ==================================================================================
  // LOCAL SETTINGS (localStorage-based configuration)
  // ==================================================================================

  private _loadSettings(): Record<string, any> {
    try {
      const stored = localStorage.getItem('autobot_backend_settings');
      return stored ? JSON.parse(stored) : {};
    } catch (error) {
      logger.warn('Failed to load settings:', error);
      return {};
    }
  }

  saveLocalSettings(settings: Record<string, any>): void {
    try {
      localStorage.setItem('autobot_backend_settings', JSON.stringify(settings));
      this.settings = settings;
    } catch (error) {
      logger.error('Failed to save settings:', error);
    }
  }

  loadLocalSettings(): Record<string, any> {
    this.settings = this._loadSettings();
    return this.settings;
  }

  // ==================================================================================
  // BASE URL INITIALIZATION
  // ==================================================================================

  private async initializeBaseUrl(): Promise<void> {
    try {
      this.baseUrl = await appConfig.getApiUrl('');
    } catch (_error) {
      logger.warn('AppConfig initialization failed, using proxy mode fallback');
      this.baseUrl = this._detectBaseUrl();
    }
  }

  private _detectBaseUrl(): string {
    const backendHost = import.meta.env.VITE_BACKEND_HOST;
    const backendPort = import.meta.env.VITE_BACKEND_PORT;
    const protocol = import.meta.env.VITE_HTTP_PROTOCOL;

    // Proxy mode: Vite dev server uses empty baseUrl for proxy
    const isViteDevServer = typeof window !== 'undefined' && window.location.port === '5173';
    if (isViteDevServer && import.meta.env.DEV) {
      return '';
    }

    if (backendHost && backendPort && protocol) {
      return `${protocol}://${backendHost}:${backendPort}`;
    }

    // Default to proxy mode (empty = relative URLs via nginx) (#919)
    return '';
  }

  private async ensureBaseUrl(): Promise<string> {
    if (this.baseUrl) {
      return this.baseUrl;
    }
    if (!this.baseUrlPromise) {
      this.baseUrlPromise = this.initializeBaseUrl().then(() => this.baseUrl);
    }
    return await this.baseUrlPromise;
  }

  // ==================================================================================
  // AUTH TOKEN — retrieves JWT from localStorage (#827)
  // ==================================================================================

  private _getAuthToken(): string | null {
    try {
      const stored = localStorage.getItem('autobot_auth');
      if (!stored) return null;
      const auth = JSON.parse(stored);
      if (auth.token && auth.token !== 'single_user_mode') {
        return auth.token;
      }
      return null;
    } catch {
      return null;
    }
  }

  // Handle 401 — clear stored auth and redirect to login (#827)
  private _handleUnauthorized(endpoint: string): void {
    logger.warn('401 Unauthorized, clearing auth:', endpoint);
    localStorage.removeItem('autobot_auth');
    localStorage.removeItem('autobot_user');
    if (
      typeof window !== 'undefined' &&
      !window.location.pathname.includes('/login')
    ) {
      const redirect = encodeURIComponent(
        window.location.pathname
      );
      window.location.href = `/login?redirect=${redirect}`;
    }
  }

  // ==================================================================================
  // RAW REQUEST — returns Response object (for streaming, blobs, etc.)
  // ==================================================================================

  async rawRequest(endpoint: string, options: RequestOptions & {
    method?: string;
    body?: any;
  } = {}): Promise<Response> {
    const {
      method = 'GET',
      headers = {},
      body,
      timeout = options.timeout || this.defaultTimeout,
    } = options;

    const baseUrl = await this.ensureBaseUrl();
    const url = baseUrl ? `${baseUrl}${endpoint}` : endpoint;

    const controller = new AbortController();
    const timeoutId = window.setTimeout(
      () => controller.abort(), timeout
    );

    try {
      const fetchOptions: RequestInit = {
        method,
        headers: { ...this.defaultHeaders, ...headers },
        signal: controller.signal,
      };

      // Inject auth token if available (#827)
      const authToken = this._getAuthToken();
      if (authToken) {
        const hdrs = fetchOptions.headers as Record<string, string>;
        hdrs['Authorization'] = `Bearer ${authToken}`;
      }

      // Handle body — support FormData (don't stringify, remove Content-Type)
      if (body instanceof FormData) {
        fetchOptions.body = body;
        const hdrs = fetchOptions.headers as Record<string, string>;
        delete hdrs['Content-Type'];
      } else if (body !== undefined) {
        fetchOptions.body = JSON.stringify(body);
      }

      const response = await fetch(url, fetchOptions);
      clearTimeout(timeoutId);

      // Handle 401 — redirect to login (skip for auth endpoints)
      if (
        response.status === 401 &&
        !endpoint.includes('/api/auth/')
      ) {
        this._handleUnauthorized(endpoint);
      }

      return response;
    } catch (error) {
      clearTimeout(timeoutId);
      if (error instanceof Error && error.name === 'AbortError') {
        throw new Error(`Request timeout after ${timeout}ms`);
      }
      throw error;
    }
  }

  // ==================================================================================
  // CONVENIENCE METHODS — return parsed JSON data (not Response)
  // ==================================================================================

  private async _extractErrorInfo(response: Response): Promise<{
    status: number; message: string; details: any;
  }> {
    try {
      const errorData = await response.json();
      return {
        status: response.status,
        message: errorData.message || errorData.detail || 'Unknown error',
        details: errorData,
      };
    } catch {
      return {
        status: response.status,
        message: response.statusText || 'Unknown error',
        details: null,
      };
    }
  }

  // GET with retry logic and exponential backoff
  async get<T = any>(endpoint: string, options: RequestOptions = {}): Promise<T> {
    let lastError: Error | undefined;
    const maxRetries = options.maxRetries !== undefined ? options.maxRetries : 3;

    for (let attempt = 1; attempt <= maxRetries; attempt++) {
      try {
        const response = await this.rawRequest(endpoint, {
          method: 'GET', ...options,
        });

        if (!response.ok) {
          const errorData = await this._extractErrorInfo(response);
          throw new Error(
            `HTTP ${response.status}: ${errorData.message}`
          );
        }

        return await response.json();
      } catch (error) {
        lastError = error instanceof Error ? error : new Error(String(error));
        logger.warn(
          `GET attempt ${attempt} failed for ${endpoint}:`,
          lastError.message
        );

        // Don't retry 4xx client errors
        if (lastError.message.includes('HTTP 4')) {
          break;
        }

        if (attempt < maxRetries) {
          const delay = Math.min(1000 * Math.pow(2, attempt - 1), 5000);
          await new Promise(resolve => window.setTimeout(resolve, delay));
        }
      }
    }

    logger.error(`GET failed after ${maxRetries} attempts: ${endpoint}`, lastError);
    throw lastError;
  }

  // POST — returns parsed JSON (handles 204 No Content: #822)
  async post<T = any>(endpoint: string, data?: any, options: RequestOptions = {}): Promise<T> {
    const response = await this.rawRequest(endpoint, {
      method: 'POST', body: data, ...options,
    });

    if (!response.ok) {
      const errorData = await this._extractErrorInfo(response);
      throw new Error(`HTTP ${response.status}: ${errorData.message}`);
    }

    if (response.status === 204) return {} as T;
    const contentType = response.headers.get('content-type');
    if (contentType && contentType.includes('application/json')) {
      return await response.json() as T;
    }
    return {} as T;
  }

  // PUT — returns parsed JSON (handles 204 No Content: #822)
  async put<T = any>(endpoint: string, data?: any, options: RequestOptions = {}): Promise<T> {
    const response = await this.rawRequest(endpoint, {
      method: 'PUT', body: data, ...options,
    });

    if (!response.ok) {
      const errorData = await this._extractErrorInfo(response);
      throw new Error(`HTTP ${response.status}: ${errorData.message}`);
    }

    if (response.status === 204) return {} as T;
    const contentType = response.headers.get('content-type');
    if (contentType && contentType.includes('application/json')) {
      return await response.json() as T;
    }
    return {} as T;
  }

  // DELETE — returns parsed JSON (handles empty responses)
  async delete<T = any>(endpoint: string, options: RequestOptions = {}): Promise<T> {
    const response = await this.rawRequest(endpoint, {
      method: 'DELETE', ...options,
    });

    if (!response.ok) {
      const errorData = await this._extractErrorInfo(response);
      throw new Error(`HTTP ${response.status}: ${errorData.message}`);
    }

    const contentType = response.headers.get('content-type');
    if (contentType && contentType.includes('application/json')) {
      return await response.json() as T;
    }
    return {} as T;
  }

  // PATCH — partial update, returns parsed JSON (handles 204 No Content)
  async patch<T = any>(endpoint: string, data?: any, options: RequestOptions = {}): Promise<T> {
    const response = await this.rawRequest(endpoint, {
      method: 'PATCH', body: data, ...options,
    });

    if (!response.ok) {
      const errorData = await this._extractErrorInfo(response);
      throw new Error(`HTTP ${response.status}: ${errorData.message}`);
    }

    if (response.status === 204) return {} as T;
    const contentType = response.headers.get('content-type');
    if (contentType && contentType.includes('application/json')) {
      return await response.json() as T;
    }
    return {} as T;
  }

  // ==================================================================================
  // FILE UPLOAD with progress tracking
  // ==================================================================================

  async uploadFile(
    endpoint: string,
    file: File,
    progressCallback: ((progress: number) => void) | null = null,
    options: { fields?: Record<string, string>; timeout?: number } = {}
  ): Promise<any> {
    const formData = new FormData();
    formData.append('file', file);

    if (options.fields) {
      Object.entries(options.fields).forEach(([key, value]) => {
        formData.append(key, value);
      });
    }

    const baseUrl = await this.ensureBaseUrl();
    const url = baseUrl ? `${baseUrl}${endpoint}` : endpoint;
    const xhr = new XMLHttpRequest();

    const uploadPromise = new Promise<any>((resolve, reject) => {
      xhr.onload = () => {
        if (xhr.status >= 200 && xhr.status < 300) {
          try {
            resolve(JSON.parse(xhr.responseText));
          } catch {
            resolve({ success: true });
          }
        } else {
          reject(new Error(`Upload failed: HTTP ${xhr.status}`));
        }
      };

      xhr.onerror = () => reject(new Error('Upload failed: Network error'));
      xhr.ontimeout = () => reject(new Error('Upload failed: Timeout'));

      if (progressCallback) {
        xhr.upload.onprogress = (e) => {
          if (e.lengthComputable) {
            progressCallback(Math.round((e.loaded / e.total) * 100));
          }
        };
      }

      xhr.open('POST', url);
      xhr.timeout = options.timeout || appConfig.getTimeout('upload');
      xhr.send(formData);
    });

    return await uploadPromise;
  }

  // ==================================================================================
  // CHAT API METHODS — corrected endpoints from #552
  // ==================================================================================

  async sendChatMessage(message: string, options: any = {}): Promise<any> {
    const response = await this.rawRequest('/api/chat', {
      method: 'POST',
      body: {
        content: message,
        role: 'user',
        session_id: options.chatId || options.session_id || null,
        message_type: options.message_type || 'text',
        metadata: options.metadata || {},
      },
    });

    if (!response.ok) {
      const errorData = await this._extractErrorInfo(response);
      throw new Error(`HTTP ${response.status}: ${errorData.message}`);
    }

    const contentType = response.headers.get('content-type');
    if (contentType && contentType.includes('text/event-stream')) {
      return { type: 'streaming', response };
    }
    const data = await response.json();
    return { type: 'json', data };
  }

  async createNewChat(): Promise<any> {
    return await this.post('/api/chat/sessions', {});
  }

  async getChatList(options: RequestOptions = {}): Promise<any> {
    const timeout = options.timeout || appConfig.getTimeout('short');
    return await this.get('/api/chats', { ...options, timeout });
  }

  async getChatMessages(chatId: string): Promise<any> {
    return await this.get(`/api/chat/sessions/${chatId}`);
  }

  async saveChatMessages(chatId: string, messages: any[]): Promise<any> {
    return await this.post(`/api/chats/${chatId}/save`, {
      data: { messages, name: '' },
    });
  }

  async deleteChat(chatId: string): Promise<any> {
    return await this.delete(`/api/chat/sessions/${chatId}`);
  }

  async updateChatSession(chatId: string, updates: any): Promise<any> {
    return await this.put(`/api/chat/sessions/${chatId}`, updates);
  }

  // ==================================================================================
  // STREAMING METHODS
  // ==================================================================================

  async sendStreamingMessage(message: string, options: any = {}): Promise<Response> {
    return await this.rawRequest('/api/chat/stream', {
      method: 'POST',
      body: {
        content: message,
        role: 'user',
        session_id: options.chatId || options.session_id || null,
        message_type: options.message_type || 'text',
        metadata: options.metadata || {},
      },
    });
  }

  async exportChatSession(sessionId: string, format: string = 'json'): Promise<Blob> {
    const response = await this.rawRequest(
      `/api/chat/sessions/${sessionId}/export?format=${format}`,
      { method: 'GET' }
    );
    return response.blob();
  }

  async getChatStats(): Promise<any> {
    return await this.get('/api/chat/stats');
  }

  // ==================================================================================
  // SETTINGS & HEALTH API METHODS
  // ==================================================================================

  async getSettings(options: RequestOptions = {}): Promise<any> {
    const timeout = options.timeout || appConfig.getTimeout('short');
    return await this.get('/api/settings/', { ...options, timeout });
  }

  async saveSettings(settings: any): Promise<any> {
    return await this.post('/api/settings/', settings);
  }

  async getSystemHealth(): Promise<any> {
    return await this.get('/api/system/health', {
      timeout: appConfig.getTimeout('health'),
    });
  }

  async getServiceHealth(): Promise<any> {
    return await this.get('/api/monitoring/services/health', {
      timeout: appConfig.getTimeout('health'),
    });
  }

  async checkHealth(): Promise<boolean> {
    try {
      const health = await this.get('/api/health', {
        timeout: appConfig.getTimeout('health'),
      });
      return health?.status === 'healthy';
    } catch (error) {
      logger.warn('Health check failed:', error);
      return false;
    }
  }

  async checkChatHealth(): Promise<any> {
    return await this.get('/api/chat/health', {
      timeout: appConfig.getTimeout('health'),
    });
  }

  async validateConnection(): Promise<boolean> {
    try {
      return await appConfig.validateConnection();
    } catch (_error) {
      return await this.checkHealth();
    }
  }

  // ==================================================================================
  // TERMINAL API METHODS — corrected endpoints from #73, #552
  // ==================================================================================

  async createTerminalSession(config: any = {}): Promise<any> {
    const payload = {
      user_id: config.user_id || 'default',
      security_level: config.security_level || 'standard',
      enable_logging: config.enable_logging !== undefined ? config.enable_logging : false,
      enable_workflow_control: config.enable_workflow_control !== undefined
        ? config.enable_workflow_control : true,
      initial_directory: config.initial_directory || null,
    };
    return await this.post('/api/terminal/sessions', payload);
  }

  async createAgentTerminalSession(config: {
    agent_id?: string;
    agent_role?: string;
    conversation_id?: string;
    host?: string;
    metadata?: Record<string, any>;
  } = {}): Promise<any> {
    const payload = {
      agent_id: config.agent_id || `agent_${Date.now()}`,
      agent_role: config.agent_role || 'chat_agent',
      conversation_id: config.conversation_id || null,
      host: config.host || 'main',
      metadata: config.metadata || null,
    };
    return await this.post('/api/agent-terminal/sessions', payload);
  }

  async getTerminalSessions(): Promise<any[]> {
    const response = await this.get('/api/terminal/sessions');
    return response.sessions || [];
  }

  async getAgentTerminalSessions(filters: {
    agent_id?: string;
    conversation_id?: string;
  } = {}): Promise<any[]> {
    const params = new URLSearchParams();
    if (filters.agent_id) params.append('agent_id', filters.agent_id);
    if (filters.conversation_id) params.append('conversation_id', filters.conversation_id);
    const query = params.toString() ? `?${params.toString()}` : '';
    const response = await this.get(`/api/agent-terminal/sessions${query}`);
    return response.sessions || [];
  }

  async getTerminalSessionInfo(sessionId: string): Promise<any> {
    return await this.get(`/api/terminal/sessions/${sessionId}`);
  }

  async getAgentTerminalSessionInfo(sessionId: string): Promise<any> {
    return await this.get(`/api/agent-terminal/sessions/${sessionId}`);
  }

  async deleteTerminalSession(sessionId: string): Promise<any> {
    return await this.delete(`/api/terminal/sessions/${sessionId}`);
  }

  async deleteAgentTerminalSession(sessionId: string): Promise<any> {
    return await this.delete(`/api/agent-terminal/sessions/${sessionId}`);
  }

  async executeTerminalCommand(command: string, options: any = {}): Promise<any> {
    return await this.post('/api/terminal/command', {
      command,
      timeout: options.timeout || 30000,
      cwd: options.cwd || null,
      env: options.env || {},
    });
  }

  // ==================================================================================
  // BROWSER SESSION API METHODS — from Issue #73
  // ==================================================================================

  async getOrCreateChatBrowserSession(config: {
    conversation_id?: string;
    headless?: boolean;
    initial_url?: string;
  } = {}): Promise<any> {
    return await this.post('/api/research-browser/chat-session', {
      conversation_id: config.conversation_id,
      headless: config.headless || false,
      initial_url: config.initial_url || null,
    });
  }

  async getChatBrowserSession(conversationId: string): Promise<any> {
    return await this.get(`/api/research-browser/chat-session/${conversationId}`);
  }

  async deleteChatBrowserSession(conversationId: string): Promise<any> {
    return await this.delete(`/api/research-browser/chat-session/${conversationId}`);
  }
}

// Lazy singleton to avoid circular dependency during module initialization
let apiClientInstance: ApiClient | null = null;

function getApiClient(): ApiClient {
  if (!apiClientInstance) {
    apiClientInstance = new ApiClient();
    // Initialize base URL asynchronously after instance creation
    apiClientInstance['initializeBaseUrl']();
  }
  return apiClientInstance;
}

// Export getter as default for backwards compatibility
export default new Proxy({} as ApiClient, {
  get(target, prop) {
    return getApiClient()[prop as keyof ApiClient];
  },
  apply(target, thisArg, args) {
    return getApiClient();
  }
});
