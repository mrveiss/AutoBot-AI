// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import appConfig from '@/config/AppConfig.js';
import { createLogger } from '@/utils/debugUtils';
import { getApiBase } from '@/config/ssot-config';
import { getSelectedCompanyId } from '@/utils/orgContext';

// Create scoped logger for ApiClient
const logger = createLogger('ApiClient');

// Type definitions for API client

export interface UploadProgressEvent {
  loaded: number;
  total?: number;
  lengthComputable?: boolean;
}

export interface RequestOptions {
  headers?: Record<string, string>;
  timeout?: number;
  maxRetries?: number;
  onUploadProgress?: (progressEvent: UploadProgressEvent) => void;
  responseType?: string;
  signal?: AbortSignal;
  /**
   * When true, the client does not emit a WARN log on final failure. Use for
   * endpoints whose absence/timeout is handled gracefully by the caller
   * (optional widgets, health probes) so they don't generate console noise.
   */
  suppressErrorLog?: boolean;
}

export interface ChatMessageOptions {
  chatId?: string;
  session_id?: string;
  message_type?: string;
  metadata?: Record<string, unknown>;
}

export interface TerminalSessionConfig {
  user_id?: string;
  security_level?: string;
  enable_logging?: boolean;
  enable_workflow_control?: boolean;
  initial_directory?: string;
}

export interface AgentTerminalSessionConfig {
  agent_id?: string;
  agent_role?: string;
  conversation_id?: string;
  host?: string;
  metadata?: Record<string, unknown>;
}

export interface TerminalCommandOptions {
  timeout?: number;
  cwd?: string;
  env?: Record<string, string>;
}

export interface ChatBrowserSessionConfig {
  conversation_id?: string;
  headless?: boolean;
  initial_url?: string;
}

export interface ErrorInfo {
  status: number;
  message: string;
  details: Record<string, unknown> | null;
}

export interface ChatMessageResponse {
  type: 'streaming' | 'json';
  response?: Response;
  data?: Record<string, unknown>;
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
  private settings: Record<string, unknown>;
  // BUG5: cache the /api/settings/ response for the session so it isn't
  // re-fetched (and re-timed-out) on every route navigation.
  private _apiSettingsCache: Record<string, unknown> | null = null;

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
    } catch {
      Object.keys(localStorage).forEach(key => {
        if (key.startsWith('autobot_api_') || key.startsWith('autobot_config_')) {
          localStorage.removeItem(key);
        }
      });
    }
  }

  getConfiguration(): Record<string, unknown> {
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

  private _loadSettings(): Record<string, unknown> {
    try {
      const stored = localStorage.getItem('autobot_backend_settings');
      return stored ? JSON.parse(stored) : {};
    } catch (error) {
      logger.warn('Failed to load settings:', error);
      return {};
    }
  }

  saveLocalSettings(settings: Record<string, unknown>): void {
    try {
      localStorage.setItem('autobot_backend_settings', JSON.stringify(settings));
      this.settings = settings;
    } catch (error) {
      logger.error('Failed to save settings:', error);
    }
  }

  loadLocalSettings(): Record<string, unknown> {
    this.settings = this._loadSettings();
    return this.settings;
  }

  // ==================================================================================
  // BASE URL INITIALIZATION
  // ==================================================================================

  private async initializeBaseUrl(): Promise<void> {
    try {
      this.baseUrl = await appConfig.getApiUrl('');
    } catch {
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
        // Check expiry before returning — expired tokens cause widespread 401s (#979)
        if (auth.expiresAt && new Date(auth.expiresAt) <= new Date()) {
          logger.warn('Auth token expired, clearing stale localStorage');
          localStorage.removeItem('autobot_auth');
          localStorage.removeItem('autobot_user');
          return null;
        }
        return auth.token;
      }
      return null;
    } catch {
      return null;
    }
  }

  // Handle 401 — clear stored auth and redirect to login (#827).
  // Only destructive when the request carried a bearer token (#10750 A12):
  // a 401 on a token-less background call is not a session rejection.
  private _handleUnauthorized(endpoint: string, tokenWasAttached: boolean): void {
    if (!tokenWasAttached) {
      logger.debug(
        '401 on token-less request — not clearing session (no session to invalidate):',
        endpoint
      );
      return;
    }
    logger.warn('401 Unauthorized, clearing auth:', endpoint);
    localStorage.removeItem('autobot_auth');
    localStorage.removeItem('autobot_user');
    // Also clear Pinia store to prevent stale isAuthenticated blocking login redirect (#972)
    import('@/stores/useUserStore').then(({ useUserStore }) => {
      try { useUserStore().logout(); } catch { /* ignore if store unavailable */ }
    });
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
    body?: unknown;
  } = {}): Promise<Response> {
    const {
      method = 'GET',
      headers = {},
      body,
      timeout = options.timeout || this.defaultTimeout,
      signal: externalSignal,
    } = options;

    const baseUrl = await this.ensureBaseUrl();
    const url = baseUrl ? `${baseUrl}${endpoint}` : endpoint;

    const controller = new AbortController();
    let timedOut = false;
    const timeoutId = window.setTimeout(() => {
      timedOut = true;
      controller.abort();
    }, timeout);

    // Forward external cancellation into the internal controller (#6257)
    let externalAbortHandler: (() => void) | null = null;
    if (externalSignal) {
      if (externalSignal.aborted) {
        controller.abort();
      } else {
        externalAbortHandler = () => controller.abort();
        externalSignal.addEventListener('abort', externalAbortHandler);
      }
    }

    const cleanup = () => {
      clearTimeout(timeoutId);
      if (externalSignal && externalAbortHandler) {
        externalSignal.removeEventListener('abort', externalAbortHandler);
      }
    };

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

      // Inject the selected company as org/tenant context (#10750 A5). Omitted
      // when no company is selected, so non-LLC requests are unaffected.
      const orgId = getSelectedCompanyId();
      if (orgId) {
        const orgHdrs = fetchOptions.headers as Record<string, string>;
        if (!orgHdrs['X-Organization-Id']) {
          orgHdrs['X-Organization-Id'] = orgId;
        }
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
      cleanup();

      // Handle 401 — redirect to login (skip for auth endpoints).
      // Pass whether THIS request actually carried a bearer token so the handler
      // only clears + redirects on a genuine rejection of an authenticated request
      // (#10750 A12). Token-less background/optional probes (e.g. the load-time
      // telemetry-consent check or version poll) that 401 must NOT log the user out.
      if (
        response.status === 401 &&
        !endpoint.includes(`${getApiBase()}/auth/`)
      ) {
        this._handleUnauthorized(endpoint, authToken != null);
      }

      return response;
    } catch (error) {
      cleanup();
      if (error instanceof Error && error.name === 'AbortError') {
        if (timedOut) throw new Error(`Request timeout after ${timeout}ms`);
        throw error;
      }
      throw error;
    }
  }

  // ==================================================================================
  // CONVENIENCE METHODS — return parsed JSON data (not Response)
  // ==================================================================================

  private async _extractErrorInfo(response: Response): Promise<ErrorInfo> {
    try {
      const errorData = await response.json();
      return {
        status: response.status,
        message: (() => {
          const raw = errorData.error || errorData.message || errorData.detail;
          if (raw == null) return JSON.stringify(errorData) || 'Unknown error';
          return typeof raw === 'string' ? raw : JSON.stringify(raw);
        })(),
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
  async get<T = unknown>(endpoint: string, options: RequestOptions = {}): Promise<T> {
    let lastError: Error | undefined;
    const maxRetries = options.maxRetries !== undefined ? options.maxRetries : 3;
    let attemptsMade = 0;

    for (let attempt = 1; attempt <= maxRetries; attempt++) {
      attemptsMade = attempt;
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
        // Per-attempt failures are debug-level only — a single summary line is
        // logged once below so retries don't flood the console (BUG4/BUG5).
        logger.debug(
          `GET attempt ${attempt} failed for ${endpoint}: ${lastError.message}`
        );

        // Don't retry 4xx client errors — they won't succeed on retry.
        if (lastError.message.includes('HTTP 4')) {
          break;
        }

        if (attempt < maxRetries) {
          const delay = Math.min(1000 * Math.pow(2, attempt - 1), 5000);
          await new Promise(resolve => window.setTimeout(resolve, delay));
        }
      }
    }

    // Single final log with the ACTUAL attempt count (was always "maxRetries").
    // Callers that handle the failure gracefully pass suppressErrorLog.
    if (!options.suppressErrorLog) {
      logger.warn(
        `GET failed for ${endpoint} after ${attemptsMade} attempt(s): ${lastError?.message}`
      );
    }
    throw lastError;
  }

  // POST — returns parsed JSON (handles 204 No Content: #822)
  async post<T = unknown>(endpoint: string, data?: unknown, options: RequestOptions = {}): Promise<T> {
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
  async put<T = unknown>(endpoint: string, data?: unknown, options: RequestOptions = {}): Promise<T> {
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
  async delete<T = unknown>(endpoint: string, options: RequestOptions = {}): Promise<T> {
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
  async patch<T = unknown>(endpoint: string, data?: unknown, options: RequestOptions = {}): Promise<T> {
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
  ): Promise<Record<string, unknown>> {
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

    const uploadPromise = new Promise<Record<string, unknown>>((resolve, reject) => {
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

  async sendChatMessage(message: string, options: ChatMessageOptions = {}): Promise<ChatMessageResponse> {
    const response = await this.rawRequest(`${getApiBase()}/chat`, {
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

  async createNewChat(): Promise<Record<string, unknown>> {
    return await this.post(`${getApiBase()}/chat/sessions`, {});
  }

  async getChatList(options: RequestOptions = {}): Promise<Record<string, unknown>> {
    const timeout = options.timeout || appConfig.getTimeout('short');
    return await this.get(`${getApiBase()}/chat/sessions`, { ...options, timeout });
  }

  async getChatMessages(chatId: string): Promise<Record<string, unknown>> {
    return await this.get(`${getApiBase()}/chat/sessions/${chatId}`);
  }

  async saveChatMessages(chatId: string, messages: Record<string, unknown>[]): Promise<Record<string, unknown>> {
    return await this.post(`${getApiBase()}/chats/${chatId}/save`, {
      data: { messages, name: '' },
    });
  }

  async deleteChat(chatId: string): Promise<Record<string, unknown>> {
    return await this.delete(`${getApiBase()}/chat/sessions/${chatId}`);
  }

  async updateChatSession(chatId: string, updates: Record<string, unknown>): Promise<Record<string, unknown>> {
    return await this.put(`${getApiBase()}/chat/sessions/${chatId}`, updates);
  }

  // ==================================================================================
  // STREAMING METHODS
  // ==================================================================================

  async sendStreamingMessage(message: string, options: ChatMessageOptions = {}): Promise<Response> {
    return await this.rawRequest(`${getApiBase()}/chat/stream`, {
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
      `${getApiBase()}/chat/sessions/${sessionId}/export?format=${format}`,
      { method: 'GET' }
    );
    return response.blob();
  }

  async getChatStats(): Promise<Record<string, unknown>> {
    return await this.get(`${getApiBase()}/chat/stats`);
  }

  // ==================================================================================
  // SETTINGS & HEALTH API METHODS
  // ==================================================================================

  async getSettings(options: RequestOptions = {}): Promise<Record<string, unknown>> {
    // BUG5: serve from the per-session cache so navigating between routes does
    // not re-fetch /api/settings/ (which was timing out and spamming WARNs).
    if (this._apiSettingsCache) return this._apiSettingsCache;

    const timeout = options.timeout || appConfig.getTimeout('short');
    try {
      const data = await this.get<Record<string, unknown>>(
        `${getApiBase()}/settings/`,
        // One attempt only, and don't emit console noise — failure falls back
        // to built-in defaults that are cached for the rest of the session.
        { ...options, timeout, maxRetries: 1, suppressErrorLog: true },
      );
      this._apiSettingsCache = data;
      return data;
    } catch {
      logger.debug('Settings unavailable on startup — using defaults for this session');
      this._apiSettingsCache = {};
      return this._apiSettingsCache;
    }
  }

  async saveSettings(settings: Record<string, unknown>): Promise<Record<string, unknown>> {
    const saved = await this.post<Record<string, unknown>>(`${getApiBase()}/settings/`, settings);
    // Keep the session cache in sync with what we just persisted.
    this._apiSettingsCache = saved ?? settings;
    return saved;
  }

  async getSystemHealth(): Promise<Record<string, unknown>> {
    return await this.get(`${getApiBase()}/system/health`, {
      timeout: appConfig.getTimeout('health'),
    });
  }

  async getServiceHealth(): Promise<Record<string, unknown>> {
    return await this.get(`${getApiBase()}/monitoring/services/health`, {
      timeout: appConfig.getTimeout('health'),
    });
  }

  async checkHealth(): Promise<boolean> {
    try {
      const health = await this.get<Record<string, unknown>>(`${getApiBase()}/health`, {
        timeout: appConfig.getTimeout('health'),
      });
      return health?.status === 'healthy';
    } catch (error) {
      logger.warn('Health check failed:', error);
      return false;
    }
  }

  async checkChatHealth(): Promise<Record<string, unknown>> {
    return await this.get(`${getApiBase()}/chat/health`, {
      timeout: appConfig.getTimeout('health'),
    });
  }

  async validateConnection(): Promise<boolean> {
    try {
      return await appConfig.validateConnection();
    } catch {
      return await this.checkHealth();
    }
  }

  // ==================================================================================
  // TERMINAL API METHODS — corrected endpoints from #73, #552
  // ==================================================================================

  async createTerminalSession(config: TerminalSessionConfig = {}): Promise<Record<string, unknown>> {
    const payload = {
      user_id: config.user_id || 'default',
      security_level: config.security_level || 'standard',
      enable_logging: config.enable_logging !== undefined ? config.enable_logging : false,
      enable_workflow_control: config.enable_workflow_control !== undefined
        ? config.enable_workflow_control : true,
      initial_directory: config.initial_directory || null,
    };
    return await this.post(`${getApiBase()}/terminal/sessions`, payload);
  }

  async createAgentTerminalSession(config: AgentTerminalSessionConfig = {}): Promise<Record<string, unknown>> {
    const payload = {
      agent_id: config.agent_id || `agent_${Date.now()}`,
      agent_role: config.agent_role || 'chat_agent',
      conversation_id: config.conversation_id || null,
      host: config.host || 'main',
      metadata: config.metadata || null,
    };
    return await this.post(`${getApiBase()}/agent-terminal/sessions`, payload);
  }

  async getTerminalSessions(): Promise<Record<string, unknown>[]> {
    const response = await this.get<Record<string, unknown>>(`${getApiBase()}/terminal/sessions`);
    return (response.sessions || []) as Record<string, unknown>[];
  }

  async getAgentTerminalSessions(filters: {
    agent_id?: string;
    conversation_id?: string;
  } = {}): Promise<Record<string, unknown>[]> {
    const params = new URLSearchParams();
    if (filters.agent_id) params.append('agent_id', filters.agent_id);
    if (filters.conversation_id) params.append('conversation_id', filters.conversation_id);
    const query = params.toString() ? `?${params.toString()}` : '';
    const response = await this.get<Record<string, unknown>>(`${getApiBase()}/agent-terminal/sessions${query}`);
    return (response.sessions || []) as Record<string, unknown>[];
  }

  async getTerminalSessionInfo(sessionId: string): Promise<Record<string, unknown>> {
    return await this.get(`${getApiBase()}/terminal/sessions/${sessionId}`);
  }

  async getAgentTerminalSessionInfo(sessionId: string): Promise<Record<string, unknown>> {
    return await this.get(`${getApiBase()}/agent-terminal/sessions/${sessionId}`);
  }

  async deleteTerminalSession(sessionId: string): Promise<Record<string, unknown>> {
    return await this.delete(`${getApiBase()}/terminal/sessions/${sessionId}`);
  }

  async deleteAgentTerminalSession(sessionId: string): Promise<Record<string, unknown>> {
    return await this.delete(`${getApiBase()}/agent-terminal/sessions/${sessionId}`);
  }

  async executeTerminalCommand(command: string, options: TerminalCommandOptions = {}): Promise<Record<string, unknown>> {
    return await this.post(`${getApiBase()}/terminal/command`, {
      command,
      timeout: options.timeout || 30000,
      cwd: options.cwd || null,
      env: options.env || {},
    });
  }

  // ==================================================================================
  // BROWSER SESSION API METHODS — from Issue #73
  // ==================================================================================

  async getOrCreateChatBrowserSession(config: ChatBrowserSessionConfig = {}): Promise<Record<string, unknown>> {
    return await this.post(`${getApiBase()}/research-browser/chat-session`, {
      conversation_id: config.conversation_id,
      headless: config.headless || false,
      initial_url: config.initial_url || null,
    });
  }

  async getChatBrowserSession(conversationId: string): Promise<Record<string, unknown>> {
    return await this.get(`${getApiBase()}/research-browser/chat-session/${conversationId}`);
  }

  async deleteChatBrowserSession(conversationId: string): Promise<Record<string, unknown>> {
    return await this.delete(`${getApiBase()}/research-browser/chat-session/${conversationId}`);
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
  apply(_target, _thisArg, _args) {
    return getApiClient();
  }
});
