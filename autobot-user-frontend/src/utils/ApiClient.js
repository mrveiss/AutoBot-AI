// ApiClient.js - Unified API client for all backend operations
// RumAgent is accessed via window.rum global
// MIGRATED: Now uses AppConfig.js for better configuration management
// Issue #598: All timeouts now sourced from AppConfig (SINGLE SOURCE OF TRUTH)

// MIGRATED: Using AppConfig.js for centralized configuration
import appConfig from '@/config/AppConfig.js';
import { EnhancedFetch } from '@/utils/ApiCircuitBreaker.js';
import { NetworkConstants } from '@/constants/network';
import { createLogger } from '@/utils/debugUtils';

const logger = createLogger('ApiClient');

class ApiClient {
  constructor() {
    // Initialize with defaults first, async config loads separately
    this.baseUrl = '';
    // Issue #598: Use AppConfig as single source of truth for timeout
    this.timeout = appConfig.getTimeout('default');
    this.isDevMode = false;
    this.enableDebug = false;

    this.settings = this.loadSettings();

    // Initialize circuit breaker-based HTTP client
    this.enhancedFetch = new EnhancedFetch({
      baseUrl: this.baseUrl,
      circuitBreaker: {
        failureThreshold: 3,
        recoveryTime: 30000,  // 30 seconds before retry
        monitoringWindow: 60000  // 1 minute monitoring window
      },
      headers: {
        'Content-Type': 'application/json'
      }
    });

    // Extensive logging for debugging proxy issues

    // CRITICAL: Proxy mode detection for Vite dev server
    const isViteDevMode = window.location.port === '5173' && this.isDevMode;

    if (isViteDevMode) {
      // Force empty baseUrl to ensure relative URLs trigger Vite proxy
      this.baseUrl = '';
    } else {
      // Only in production mode, consider localStorage settings override
      if (this.settings?.backend?.api_endpoint && !this.isDevMode) {
        this.baseUrl = this.settings.backend.api_endpoint;
      } else {
      }
    }

    // Update circuit breaker with final baseUrl
    this.enhancedFetch.updateBaseUrl(this.baseUrl);

  }

  // MIGRATED: Initialize configuration from AppConfig.js
  async initializeConfiguration() {
    try {
      // Get backend service URL from AppConfig
      this.baseUrl = await appConfig.getServiceUrl('backend');
      this.timeout = appConfig.getTimeout('default');
      this.isDevMode = appConfig.get('environment.isDev', false);
      this.enableDebug = appConfig.get('features.enableDebug', false);

    } catch (error) {
      logger.warn('Failed to initialize from AppConfig, using fallback:', error.message);

      // Fallback to environment variables
      this.baseUrl = this.detectBaseUrl();
      // Issue #598: Use AppConfig timeout as fallback (consistent with SSOT)
      this.timeout = appConfig.getTimeout('default');
      this.isDevMode = import.meta.env.DEV;
      this.enableDebug = import.meta.env.VITE_ENABLE_DEBUG === 'true';
    }
  }

  // Fallback method for base URL detection
  detectBaseUrl() {
    const backendHost = import.meta.env.VITE_BACKEND_HOST;
    const backendPort = import.meta.env.VITE_BACKEND_PORT;
    const protocol = import.meta.env.VITE_HTTP_PROTOCOL;

    // PROXY MODE: When running on Vite dev server (port 5173), use empty baseUrl for proxy
    const isViteDevServer = window.location.port === '5173';

    if (isViteDevServer && import.meta.env.DEV) {
      return ''; // Empty string forces relative URLs which go through Vite proxy
    }

    // DIRECT MODE: Use actual backend IP for production or non-proxy environments
    if (backendHost && backendPort && protocol) {
      const directUrl = `${protocol}://${backendHost}:${backendPort}`;
      return directUrl;
    }

    // Final fallback - use NetworkConstants instead of hardcoded IP
    const fallbackUrl = `http://${NetworkConstants.MAIN_MACHINE_IP}:${NetworkConstants.BACKEND_PORT}`;
    return fallbackUrl;
  }

  loadSettings() {
    try {
      const stored = localStorage.getItem('autobot_backend_settings');
      return stored ? JSON.parse(stored) : {};
    } catch (error) {
      logger.warn('Failed to load settings:', error);
      return {};
    }
  }

  saveSettings(settings) {
    try {
      localStorage.setItem('autobot_backend_settings', JSON.stringify(settings));
      this.settings = settings;
    } catch (error) {
      logger.error('Failed to save settings:', error);
    }
  }

  // MIGRATED: Enhanced API URL construction using AppConfig
  async getApiUrl(endpoint = '', options = {}) {
    try {
      // Use AppConfig for URL construction when available
      return await appConfig.getApiUrl(endpoint, options);
    } catch (error) {
      logger.warn('AppConfig URL construction failed, using fallback:', error.message);

      // Fallback to manual construction
      const baseUrl = this.baseUrl;
      let fullUrl;

      // Handle proxy mode properly
      if (!baseUrl) {
        // Proxy mode - use relative URL
        fullUrl = endpoint;
      } else {
        // Direct mode - construct full URL
        fullUrl = `${baseUrl}${endpoint}`;
      }

      // Add cache-busting parameters if enabled
      if (options.cacheBust !== false && appConfig) {
        const separator = fullUrl.includes('?') ? '&' : '?';
        const cacheBustVersion = appConfig.get('api.cacheBustVersion', Date.now().toString());
        const cacheBustParam = `_cb=${cacheBustVersion}`;
        const timestampParam = `_t=${Date.now()}`;
        fullUrl = `${fullUrl}${separator}${cacheBustParam}&${timestampParam}`;
      }

      return fullUrl;
    }
  }

  // Enhanced fetch method with AppConfig integration
  async fetchWithConfig(endpoint, options = {}) {
    try {
      // Try to use AppConfig fetch if available
      return await appConfig.fetchApi(endpoint, options);
    } catch (error) {
      logger.warn('AppConfig fetch failed, using fallback:', error.message);

      // Fallback to manual fetch
      const url = await this.getApiUrl(endpoint, options);

      const defaultHeaders = {
        'Cache-Control': 'no-cache, no-store, must-revalidate',
        'Pragma': 'no-cache',
        'Expires': '0',
        'X-Request-Time': Date.now().toString(),
        'Content-Type': 'application/json'
      };

      const headers = {
        ...defaultHeaders,
        ...options.headers
      };

      const fetchOptions = {
        ...options,
        headers,
        cache: 'no-store'
      };

      // Add timeout handling
      const controller = new AbortController();
      const timeout = options.timeout || this.timeout;
      const timeoutId = setTimeout(() => controller.abort(), timeout);
      fetchOptions.signal = controller.signal;

      try {
        const response = await fetch(url, fetchOptions);
        clearTimeout(timeoutId);
        return response;
      } catch (fetchError) {
        clearTimeout(timeoutId);
        throw fetchError;
      }
    }
  }

  // GET request with enhanced error handling and retries
  // Issue #671: Added configurable maxRetries option (default: 3)
  async get(endpoint, options = {}) {

    let lastError;
    // Issue #671: Allow caller to reduce retries for faster failure on init calls
    const maxRetries = options.maxRetries !== undefined ? options.maxRetries : 3;

    for (let attempt = 1; attempt <= maxRetries; attempt++) {
      try {
        const response = await this.fetchWithConfig(endpoint, {
          ...options,
          method: 'GET'
        });

        if (!response.ok) {
          const errorData = await this.extractErrorInfo(response);
          throw new Error(`HTTP ${response.status}: ${errorData.message || response.statusText}`);
        }

        const data = await response.json();

        // Log successful response for debugging
        if (this.enableDebug) {
        }

        return data;

      } catch (error) {
        lastError = error;
        logger.warn(`GET attempt ${attempt} failed for ${endpoint}:`, error.message);

        // Don't retry on 4xx errors (client errors)
        if (error.message.includes('HTTP 4')) {
          break;
        }

        // Wait before retrying (exponential backoff)
        if (attempt < maxRetries) {
          const delay = Math.min(1000 * Math.pow(2, attempt - 1), 5000);
          await new Promise(resolve => setTimeout(resolve, delay));
        }
      }
    }

    // All retries failed
    logger.error(`GET failed after ${maxRetries} attempts: ${endpoint}`, lastError);
    throw lastError;
  }

  // POST request with retry logic
  async post(endpoint, data = {}, options = {}) {

    try {
      // Check if data is FormData (for file uploads and form submissions)
      const isFormData = data instanceof FormData;

      const fetchOptions = {
        ...options,
        method: 'POST',
        body: isFormData ? data : JSON.stringify(data)
      };

      // Only set Content-Type for JSON, let browser set it for FormData
      if (!isFormData) {
        fetchOptions.headers = {
          'Content-Type': 'application/json',
          ...options.headers
        };
      } else {
        fetchOptions.headers = {
          ...options.headers
        };
      }

      const response = await this.fetchWithConfig(endpoint, fetchOptions);

      if (!response.ok) {
        const errorData = await this.extractErrorInfo(response);
        throw new Error(`HTTP ${response.status}: ${errorData.message || response.statusText}`);
      }

      const responseData = await response.json();
      return responseData;

    } catch (error) {
      logger.error(`POST failed: ${endpoint}`, error);
      throw error;
    }
  }

  // PUT request
  async put(endpoint, data = {}, options = {}) {

    try {
      const response = await this.fetchWithConfig(endpoint, {
        ...options,
        method: 'PUT',
        body: JSON.stringify(data),
        headers: {
          'Content-Type': 'application/json',
          ...options.headers
        }
      });

      if (!response.ok) {
        const errorData = await this.extractErrorInfo(response);
        throw new Error(`HTTP ${response.status}: ${errorData.message || response.statusText}`);
      }

      const responseData = await response.json();
      return responseData;

    } catch (error) {
      logger.error(`PUT failed: ${endpoint}`, error);
      throw error;
    }
  }

  // DELETE request
  async delete(endpoint, options = {}) {

    try {
      const response = await this.fetchWithConfig(endpoint, {
        ...options,
        method: 'DELETE'
      });

      if (!response.ok) {
        const errorData = await this.extractErrorInfo(response);
        throw new Error(`HTTP ${response.status}: ${errorData.message || response.statusText}`);
      }

      // DELETE might return empty response
      const contentType = response.headers.get('content-type');
      let responseData = {};

      if (contentType && contentType.includes('application/json')) {
        responseData = await response.json();
      }

      return responseData;

    } catch (error) {
      logger.error(`DELETE failed: ${endpoint}`, error);
      throw error;
    }
  }

  // File upload with progress tracking
  async uploadFile(endpoint, file, progressCallback = null, options = {}) {
    logger.debug(`File Upload: ${endpoint}`, {
      filename: file.name,
      size: file.size,
      type: file.type
    });

    try {
      const formData = new FormData();
      formData.append('file', file);

      // Add any additional form fields
      if (options.fields) {
        Object.entries(options.fields).forEach(([key, value]) => {
          formData.append(key, value);
        });
      }

      // Get URL before creating Promise
      const url = await this.getApiUrl(endpoint, { cacheBust: false });
      const xhr = new XMLHttpRequest();

      // Promise wrapper for XMLHttpRequest
      const uploadPromise = new Promise((resolve, reject) => {
        xhr.onload = () => {
          if (xhr.status >= 200 && xhr.status < 300) {
            try {
              const data = JSON.parse(xhr.responseText);
              resolve(data);
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
              const progress = Math.round((e.loaded / e.total) * 100);
              progressCallback(progress);
            }
          };
        }

        xhr.open('POST', url);

        // Issue #598: Use upload-specific timeout from AppConfig
        xhr.timeout = options.timeout || appConfig.getTimeout('upload');

        xhr.send(formData);
      });

      const result = await uploadPromise;
      return result;

    } catch (error) {
      logger.error(`File Upload failed: ${endpoint}`, error);
      throw error;
    }
  }

  // Enhanced error information extraction
  async extractErrorInfo(response) {
    try {
      const errorData = await response.json();
      return {
        status: response.status,
        message: errorData.message || errorData.detail || 'Unknown error',
        details: errorData
      };
    } catch {
      return {
        status: response.status,
        message: response.statusText || 'Unknown error',
        details: null
      };
    }
  }

  // Health check method
  async checkHealth() {
    try {
      // Issue #598: Use health-specific timeout from AppConfig
      const health = await this.get('/api/health', { timeout: appConfig.getTimeout('health') });
      return health?.status === 'healthy';
    } catch (error) {
      logger.warn('Health check failed:', error.message);
      return false;
    }
  }

  // Connection validation using AppConfig
  async validateConnection() {
    try {
      // Use AppConfig validation if available
      return await appConfig.validateConnection();
    } catch (error) {
      logger.warn('AppConfig validation failed, using fallback:', error.message);
      return await this.checkHealth();
    }
  }

  // Cache invalidation
  invalidateCache() {
    try {
      // Use AppConfig cache invalidation if available
      appConfig.invalidateCache();
    } catch (error) {
      logger.warn('AppConfig cache invalidation failed:', error.message);

      // Fallback cache invalidation
      Object.keys(localStorage).forEach(key => {
        if (key.startsWith('autobot_api_') || key.startsWith('autobot_config_')) {
          localStorage.removeItem(key);
        }
      });
    }
  }

  // ========== Chat API Methods ==========

  /**
   * Save chat messages in bulk to a session
   * Backend endpoint: POST /api/chats/{chat_id}/save
   * @param {string} chatId - The chat session ID
   * @param {Array} messages - Array of messages to save
   * @returns {Promise<Object>} Save result
   */
  async saveChatMessages(chatId, messages) {
    try {
      const response = await this.post(`/api/chats/${chatId}/save`, {
        data: {
          messages: messages,
          name: ""  // Optional session name
        }
      });

      // FIXED: Parse JSON response instead of returning raw Response object
      // This matches the TypeScript version behavior
      return response;
    } catch (error) {
      logger.error('Failed to save chat messages:', error);
      throw error;
    }
  }

  // ========== Terminal API Methods ==========

  /**
   * Create a new terminal session (Tools Terminal - direct PTY)
   *
   * NOTE: This is for Tools Terminal (standalone, no agent control).
   * For Chat Terminal with agent control, use createAgentTerminalSession().
   *
   * @param {Object} config - Session configuration
   * @returns {Promise<Object>} Session info with session_id
   */
  async createTerminalSession(config = {}) {
    const payload = {
      user_id: config.user_id || 'default',
      security_level: config.security_level || 'standard',
      enable_logging: config.enable_logging !== undefined ? config.enable_logging : false,
      enable_workflow_control: config.enable_workflow_control !== undefined ? config.enable_workflow_control : true,
      initial_directory: config.initial_directory || null
    };

    // Issue #73: Tools Terminal uses /api/terminal/sessions (direct PTY)
    // Chat Terminal uses /api/agent-terminal/sessions (agent control)
    return await this.post('/api/terminal/sessions', payload);
  }

  /**
   * Create an agent terminal session (Chat Terminal - with agent control)
   *
   * NOTE: This is for Chat Terminal with AI agent control and approval workflow.
   * For Tools Terminal (direct PTY), use createTerminalSession().
   *
   * @param {Object} config - Agent session configuration
   * @param {string} config.agent_id - Unique identifier for the agent
   * @param {string} config.agent_role - Role: chat_agent, automation_agent, system_agent, admin_agent
   * @param {string} config.conversation_id - Chat conversation ID to link
   * @param {string} config.host - Target host (main, frontend, npu-worker, redis, ai-stack, browser)
   * @returns {Promise<Object>} Session info with session_id and pty_session_id
   */
  async createAgentTerminalSession(config = {}) {
    const payload = {
      agent_id: config.agent_id || `agent_${Date.now()}`,
      agent_role: config.agent_role || 'chat_agent',
      conversation_id: config.conversation_id || null,
      host: config.host || 'main',
      metadata: config.metadata || null
    };

    // Issue #73: Agent Terminal for Chat Terminal with approval workflow
    return await this.post('/api/agent-terminal/sessions', payload);
  }

  /**
   * Delete a terminal session (Tools Terminal)
   * @param {string} sessionId - Session ID to delete
   * @returns {Promise<Object>} Deletion result
   */
  async deleteTerminalSession(sessionId) {
    // Issue #73: Tools Terminal uses /api/terminal/*
    return await this.delete(`/api/terminal/sessions/${sessionId}`);
  }

  /**
   * Delete an agent terminal session (Chat Terminal)
   * @param {string} sessionId - Agent session ID to delete
   * @returns {Promise<Object>} Deletion result
   */
  async deleteAgentTerminalSession(sessionId) {
    // Issue #73: Agent Terminal for Chat Terminal
    return await this.delete(`/api/agent-terminal/sessions/${sessionId}`);
  }

  /**
   * Get list of active terminal sessions (Tools Terminal)
   * @returns {Promise<Array>} List of sessions
   */
  async getTerminalSessions() {
    // Issue #73: Tools Terminal uses /api/terminal/*
    const response = await this.get('/api/terminal/sessions');
    return response.sessions || [];
  }

  /**
   * Get list of agent terminal sessions (Chat Terminal)
   * @param {Object} filters - Optional filters
   * @param {string} filters.agent_id - Filter by agent ID
   * @param {string} filters.conversation_id - Filter by conversation ID
   * @returns {Promise<Array>} List of agent sessions
   */
  async getAgentTerminalSessions(filters = {}) {
    // Issue #73: Agent Terminal for Chat Terminal
    const params = new URLSearchParams();
    if (filters.agent_id) params.append('agent_id', filters.agent_id);
    if (filters.conversation_id) params.append('conversation_id', filters.conversation_id);
    const query = params.toString() ? `?${params.toString()}` : '';
    const response = await this.get(`/api/agent-terminal/sessions${query}`);
    return response.sessions || [];
  }

  /**
   * Execute a terminal command (deprecated - use WebSocket for real-time I/O)
   * @param {string} command - Command to execute
   * @param {Object} options - Execution options
   * @returns {Promise<Object>} Command result
   */
  async executeTerminalCommand(command, options = {}) {
    const payload = {
      command: command,
      timeout: options.timeout || 30000,
      cwd: options.cwd || null,
      env: options.env || {}
    };

    // Issue #552: Fixed path - backend uses /command not /execute
    return await this.post('/api/terminal/command', payload);
  }

  /**
   * Get terminal session information
   * @param {string} sessionId - Session ID
   * @returns {Promise<Object>} Session info
   */
  async getTerminalSessionInfo(sessionId) {
    // Issue #73: Fixed path - Tools Terminal uses /api/terminal/*
    return await this.get(`/api/terminal/sessions/${sessionId}`);
  }

  // ========== Chat Browser Session API Methods (Issue #73) ==========

  /**
   * Get or create browser session for a chat conversation
   * Similar to how terminal sessions are tied to chat via agent-terminal API
   *
   * @param {Object} config - Session configuration
   * @param {string} config.conversation_id - Chat conversation ID
   * @param {boolean} config.headless - Run browser in headless mode (default: false)
   * @param {string} config.initial_url - Initial URL to navigate to
   * @returns {Promise<Object>} Session info with session_id
   */
  async getOrCreateChatBrowserSession(config = {}) {
    const payload = {
      conversation_id: config.conversation_id,
      headless: config.headless || false,
      initial_url: config.initial_url || null
    };

    // Issue #73: Chat browser sessions tied to conversations
    return await this.post('/api/research-browser/chat-session', payload);
  }

  /**
   * Get browser session info for a chat conversation
   *
   * @param {string} conversationId - Chat conversation ID
   * @returns {Promise<Object>} Session info
   */
  async getChatBrowserSession(conversationId) {
    // Issue #73: Chat browser sessions tied to conversations
    return await this.get(`/api/research-browser/chat-session/${conversationId}`);
  }

  /**
   * Close browser session for a chat conversation
   *
   * @param {string} conversationId - Chat conversation ID
   * @returns {Promise<Object>} Deletion result
   */
  async deleteChatBrowserSession(conversationId) {
    // Issue #73: Chat browser sessions tied to conversations
    return await this.delete(`/api/research-browser/chat-session/${conversationId}`);
  }

  // Update base URL (useful for settings changes)
  updateBaseUrl(newBaseUrl) {
    this.baseUrl = newBaseUrl;
    this.enhancedFetch.updateBaseUrl(newBaseUrl);
  }

  // Get current configuration summary
  getConfiguration() {
    return {
      baseUrl: this.baseUrl,
      timeout: this.timeout,
      isDevMode: this.isDevMode,
      enableDebug: this.enableDebug,
      proxyMode: !this.baseUrl,
      settings: this.settings
    };
  }
}

// Create singleton instance
const apiClientInstance = new ApiClient();

// Initialize configuration after construction
if (typeof window !== 'undefined') {
  apiClientInstance.initializeConfiguration().catch(error => {
    logger.warn('Async configuration initialization failed:', error.message);
  });
}

// Export both the class and the singleton instance
export { ApiClient };
export default apiClientInstance;
