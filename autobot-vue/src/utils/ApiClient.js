// ApiClient.js - Unified API client for all backend operations
// RumAgent is accessed via window.rum global

import { API_CONFIG, ENDPOINTS, getApiUrl } from '@/config/environment.js';
import errorHandler from '@/utils/ErrorHandler.js';
import { EnhancedFetch } from '@/utils/ApiCircuitBreaker.js';

class ApiClient {
  constructor() {
    this.baseUrl = API_CONFIG.BASE_URL;
    this.timeout = API_CONFIG.TIMEOUT;  // Kept for compatibility but not used for timeouts
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
    console.log('[ApiClient] Constructor initialization:');
    console.log('[ApiClient] - Initial baseUrl from config:', this.baseUrl);
    console.log('[ApiClient] - API_CONFIG.DEV_MODE:', API_CONFIG.DEV_MODE);
    console.log('[ApiClient] - window.location.port:', window.location.port);
    console.log('[ApiClient] - Settings loaded:', this.settings);

    // CRITICAL: Don't override baseUrl when using Vite proxy (port 5173 in development)
    // Check if we're running on port 5173 AND in development mode (Vite dev server) 
    const isViteDevMode = window.location.port === '5173' && API_CONFIG.DEV_MODE;
    
    if (isViteDevMode) {
      console.log('[ApiClient] PROXY MODE: Running on port 5173, forcing proxy usage');
      console.log('[ApiClient] PROXY MODE: Ignoring any localStorage settings');
      // Force empty baseUrl to ensure relative URLs trigger Vite proxy
      this.baseUrl = '';
    } else {
      // Only in production mode, consider localStorage settings override
      if (this.settings?.backend?.api_endpoint && !API_CONFIG.DEV_MODE) {
        console.log('[ApiClient] PRODUCTION MODE: Overriding baseUrl with settings:', this.settings.backend.api_endpoint);
        this.baseUrl = this.settings.backend.api_endpoint;
      } else {
        console.log('[ApiClient] PRODUCTION MODE: Using config baseUrl:', this.baseUrl);
      }
    }

    console.log('[ApiClient] Final baseUrl:', this.baseUrl);
    console.log('[ApiClient] Proxy mode active:', isViteDevMode);

    // PERFORMANCE OPTIMIZATION: Add caching layer for frequently accessed data
    this.cache = new Map();
    this.cacheConfig = {
      defaultTTL: API_CONFIG.CACHE_DEFAULT_TTL || 5 * 60 * 1000, // 5 minutes
      maxSize: API_CONFIG.CACHE_MAX_SIZE || 100,
      endpoints: API_CONFIG.CACHE_ENDPOINTS || {
        '/api/settings/': 10 * 60 * 1000, // 10 minutes for settings
        '/api/system/health': 30 * 1000,   // 30 seconds for health
        '/api/prompts/': 15 * 60 * 1000,   // 15 minutes for prompts (they change rarely)
        '/api/chats': 2 * 60 * 1000,  // 2 minutes for chat list
      }
    };

    // Cleanup expired cache entries periodically
    const cacheCleanupInterval = API_CONFIG.CACHE_CLEANUP_INTERVAL || 2 * 60 * 1000; // Every 2 minutes
    this.cacheCleanupInterval = setInterval(() => {
      this.cleanupCache();
    }, cacheCleanupInterval);
  }

  // Cache management methods
  getCacheKey(endpoint, params = {}) {
    return `${endpoint}:${JSON.stringify(params)}`;
  }

  getCachedData(cacheKey) {
    const entry = this.cache.get(cacheKey);
    if (!entry) return null;

    if (Date.now() > entry.expires) {
      this.cache.delete(cacheKey);
      return null;
    }

    return entry.data;
  }

  setCachedData(cacheKey, data, endpoint) {
    // Determine TTL based on endpoint or use default
    const ttl = this.cacheConfig.endpoints[endpoint] || this.cacheConfig.defaultTTL;
    const expires = Date.now() + ttl;

    // Manage cache size
    if (this.cache.size >= this.cacheConfig.maxSize) {
      // Remove oldest entry
      const firstKey = this.cache.keys().next().value;
      this.cache.delete(firstKey);
    }

    this.cache.set(cacheKey, {
      data,
      expires,
      endpoint
    });
  }

  cleanupCache() {
    const now = Date.now();
    for (const [key, entry] of this.cache.entries()) {
      if (now > entry.expires) {
        this.cache.delete(key);
      }
    }
  }

  clearCache(pattern = null) {
    if (pattern) {
      for (const [key] of this.cache.entries()) {
        if (key.includes(pattern)) {
          this.cache.delete(key);
        }
      }
    } else {
      this.cache.clear();
    }
  }

  // Alias method for compatibility with ChatController
  invalidateCache(pattern = null) {
    this.clearCache(pattern);
  }

  // Load settings from localStorage
  loadSettings() {
    try {
      const savedSettings = localStorage.getItem('chat_settings');
      let settings = savedSettings ? JSON.parse(savedSettings) : {};
      
      // CRITICAL FIX: Automatically update localStorage if it contains localhost URLs
      // This prevents old cached settings from overriding correct environment variables
      const correctBackendUrl = API_CONFIG.BASE_URL;
      const hasLocalhostUrl = settings.backend?.api_endpoint?.includes('localhost') || 
                              settings.backend?.api_endpoint?.includes('127.0.0.1');
      
      if (correctBackendUrl && hasLocalhostUrl) {
        console.log('[ApiClient] FIXING LOCALSTORAGE: Detected localhost URL in settings:', settings.backend?.api_endpoint);
        console.log('[ApiClient] FIXING LOCALHOST: Updating with correct URL:', correctBackendUrl);
        
        // Initialize backend settings if not present
        settings.backend = settings.backend || {};
        
        // Update with correct backend URL from environment variables
        settings.backend.api_endpoint = correctBackendUrl;
        
        // Save corrected settings back to localStorage
        localStorage.setItem('chat_settings', JSON.stringify(settings));
        
        console.log('[ApiClient] LOCALHOST FIXED: Settings updated in localStorage');
      }
      
      return settings;
    } catch (error) {
      console.error('Error loading settings:', error);
      return {};
    }
  }


  // Generic request method with error handling, timeout, and retry logic
  async request(endpoint, options = {}) {
    return this.requestWithRetry(endpoint, options);
  }

  // Enhanced request method with retry logic based on MCP error analysis
  async requestWithRetry(endpoint, options = {}, retryCount = 0) {
    const url = `${this.baseUrl}${endpoint}`;
    const method = options.method || 'GET';
    const maxRetries = API_CONFIG.RETRY_ATTEMPTS || 3;
    const retryDelay = API_CONFIG.RETRY_DELAY || 2000;
    const startTime = performance.now();

    // Enhanced logging for proxy debugging
    const isViteDevMode = window.location.port === '5173';
    if (isViteDevMode) {
      console.log('[ApiClient] Request details:', {
        endpoint,
        baseUrl: this.baseUrl,
        fullUrl: url,
        method,
        isRelative: !this.baseUrl,
        willUseProxy: !this.baseUrl
      });
    }

    // PERFORMANCE OPTIMIZATION: Check cache for GET requests
    if (method === 'GET' && !options.skipCache) {
      const cacheKey = this.getCacheKey(endpoint, options.params || {});
      const cachedData = this.getCachedData(cacheKey);

      if (cachedData) {
        // Return cached response wrapped in a Response-like object
        return {
          ok: true,
          status: 200,
          json: async () => cachedData,
          headers: new Map([['x-cache', 'hit']])
        };
      }
    }

    // Standard timeout for all requests (background tasks return immediately)
    let requestTimeout = this.timeout;

    // Track API call start
    if (window.rum) {
      window.rum.trackUserInteraction('api_call_initiated', null, {
        method,
        endpoint,
        url,
        timeout: requestTimeout
      });
    }

    const config = {
      headers: {
        'Content-Type': 'application/json',
        ...options.headers
      },
      ...options
    };

    // ROOT CAUSE FIX: Replace timeout-based fetch with circuit breaker pattern
    try {
      // Use circuit breaker instead of arbitrary timeouts
      const response = await this.enhancedFetch.request(endpoint, {
        method,
        headers: config.headers,
        body: config.body
      });
      const endTime = performance.now();

      if (!response.ok) {
        // Track failed response
        if (window.rum) {
          window.rum.trackApiCall(method, endpoint, startTime, endTime, response.status);
        }

        // BETTER ERROR MESSAGES: More context for different HTTP errors
        let errorMessage = `HTTP ${response.status}: ${response.statusText}`;
        if (response.status === 504) {
          errorMessage += ` - Server timeout. The operation took too long to complete.`;
        } else if (response.status === 503) {
          errorMessage += ` - Service temporarily unavailable. Please try again.`;
        } else if (response.status === 404) {
          errorMessage += ` - Endpoint not found: ${endpoint}`;
        }

        throw new Error(errorMessage);
      }

      // Track successful response
      if (window.rum) {
        window.rum.trackApiCall(method, endpoint, startTime, endTime, response.status);
      }

      // PERFORMANCE OPTIMIZATION: Cache successful GET responses
      if (method === 'GET' && response.ok && !options.skipCache) {
        try {
          // Clone response to avoid consuming the stream
          const responseClone = response.clone();
          const data = await responseClone.json();
          const cacheKey = this.getCacheKey(endpoint, options.params || {});
          this.setCachedData(cacheKey, data, endpoint);
        } catch (error) {
          // Don't fail the request if caching fails
          console.warn('Failed to cache response:', error);
        }
      }

      return response;

    } catch (error) {
      const endTime = performance.now();

      // Handle circuit breaker errors
      if (error.name === 'CircuitBreakerError') {
        console.log('[ApiClient] Circuit breaker triggered:', {
          state: error.circuitState,
          endpoint,
          method
        });
        
        // Track circuit breaker activation
        if (window.rum) {
          window.rum.trackApiCall(method, endpoint, startTime, endTime, 503); // Service Unavailable
        }
        
        const cbError = new Error(`Service temporarily unavailable: Circuit breaker is ${error.circuitState}`);
        cbError.name = 'CircuitBreakerError';
        cbError.circuitState = error.circuitState;
        cbError.status = error.status;
        throw cbError;
      }

      // Legacy timeout error handling (should not occur with circuit breaker)
      if (error.name === 'AbortError') {
        let timeoutError;
        if (isTimedOut) {
          timeoutError = new Error(
            `Request timeout: ${method} ${endpoint} took longer than ${requestTimeout}ms. ` +
            `This usually indicates the backend is overloaded or the operation is complex.`
          );
        } else {
          timeoutError = new Error(
            `Request was cancelled: ${method} ${endpoint}. ` +
            `This may be due to navigation or component unmounting.`
          );
        }

        if (window.rum) {
          window.rum.trackApiCall(method, endpoint, startTime, endTime, 'timeout', timeoutError);
          window.rum.reportCriticalIssue('api_timeout', {
            method,
            endpoint,
            url,
            duration: endTime - startTime,
            timeout: requestTimeout,
            isTimedOut
          });
        }

        // Retry logic for timeout errors based on MCP insights
        if (retryCount < maxRetries && this.shouldRetry(error, method)) {
          console.warn(`[ApiClient] Timeout on attempt ${retryCount + 1}/${maxRetries + 1}, retrying in ${retryDelay * (retryCount + 1)}ms...`);
          
          // Exponential backoff
          const backoffDelay = retryDelay * Math.pow(2, retryCount);
          await this.delay(backoffDelay);
          
          return this.requestWithRetry(endpoint, options, retryCount + 1);
        }

        throw timeoutError;
      }

      // NETWORK ERROR HANDLING: Better messages for connection issues with retry logic
      if (this.shouldRetry(error, method) && retryCount < maxRetries) {
        console.warn(`[ApiClient] Network error on attempt ${retryCount + 1}/${maxRetries + 1}, retrying...`, error);
        
        const backoffDelay = retryDelay * Math.pow(2, retryCount);
        await this.delay(backoffDelay);
        
        return this.requestWithRetry(endpoint, options, retryCount + 1);
      }
      if (error.message === 'Failed to fetch' || error.name === 'TypeError') {
        const networkError = new Error(
          `Network error: Cannot connect to backend at ${this.baseUrl}. ` +
          `Please check if the backend service is running and accessible.`
        );
        networkError.originalError = error;

        if (window.rum) {
          window.rum.trackApiCall(method, endpoint, startTime, endTime, 'network_error', networkError);
          window.rum.reportCriticalIssue('network_error', {
            method,
            endpoint,
            url,
            baseUrl: this.baseUrl,
            originalError: error.message
          });
        }

        throw networkError;
      }

      // Track other errors with more context
      if (window.rum) {
        window.rum.trackApiCall(method, endpoint, startTime, endTime, 'error', error);
      }

      // Add context to generic errors
      error.endpoint = endpoint;
      error.method = method;
      error.url = url;

      throw error;
    }
  }

  // GET request
  async get(endpoint, options = {}) {
    return this.request(endpoint, { method: 'GET', ...options });
  }

  // POST request
  async post(endpoint, data = null, options = {}) {
    const config = { method: 'POST', ...options };

    if (data) {
      if (data instanceof FormData) {
        // Don't set Content-Type for FormData, let browser handle it
        delete config.headers['Content-Type'];
        config.body = data;
      } else {
        config.body = JSON.stringify(data);
      }
    }

    return this.request(endpoint, config);
  }

  // PUT request
  async put(endpoint, data = null, options = {}) {
    const config = { method: 'PUT', ...options };
    if (data) {
      config.body = JSON.stringify(data);
    }
    return this.request(endpoint, config);
  }

  // DELETE request
  async delete(endpoint, options = {}) {
    return this.request(endpoint, { method: 'DELETE', ...options });
  }

  // Chat API methods
  async sendChatMessage(message, options = {}) {
    // Use the correct endpoint for chat messages
    const response = await this.post(`/api/chat/message`, {
      content: message,
      role: "user",
      session_id: options.chatId || options.session_id || null
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

  async createNewChat() {
    const response = await this.post('/api/chat/sessions');
    return response.json();
  }

  async getChatList() {
    const response = await this.get('/api/chats');
    return response.json();
  }

  async getChatMessages(chatId) {
    const response = await this.get(`/api/chat/sessions/${chatId}`);
    return response.json();
  }

  async saveChatMessages(chatId, messages) {
    const response = await this.post(`/api/chat/sessions/${chatId}`, { messages });
    return response.json();
  }

  async deleteChat(chatId) {
    const response = await this.delete(`/api/chat/sessions/${chatId}`);
    return response.json();
  }

  async resetChat() {
    const response = await this.post('/api/reset');
    return response.json();
  }

  // Settings API methods
  async getSettings() {
    const response = await this.get('/api/settings/');
    return response.json();
  }

  async saveSettings(settings) {
    const response = await this.post('/api/settings/', settings);
    const result = await response.json();

    // Update local settings
    this.saveSettingsLocally(settings);

    return result;
  }

  async loadFrontendConfig() {
    // Load dynamic configuration from backend
    // This eliminates the need for hardcoded ports and URLs
    const response = await this.get('/api/frontend-config');
    return response.json();
  }

  // Save settings to localStorage only (renamed to avoid recursion)
  saveSettingsLocally(settings) {
    try {
      localStorage.setItem('chat_settings', JSON.stringify(settings));
      this.settings = settings;

      // CRITICAL: Don't update baseUrl when using Vite proxy
      const isViteDevMode = window.location.port === '5173';
      
      if (!isViteDevMode && settings?.backend?.api_endpoint) {
        console.log('[ApiClient] Updating baseUrl from settings:', settings.backend.api_endpoint);
        this.baseUrl = settings.backend.api_endpoint;
      } else if (isViteDevMode) {
        console.log('[ApiClient] Proxy mode: NOT updating baseUrl from settings');
      }
    } catch (error) {
      console.error('Error saving settings locally:', error);
    }
  }

  async getBackendSettings() {
    const response = await this.get('/api/settings/backend');
    return response.json();
  }

  async saveBackendSettings(backendSettings) {
    const response = await this.post('/api/settings/backend', { settings: backendSettings });
    return response.json();
  }

  // Knowledge Base API methods
  async searchKnowledge(query, limit = 10) {
    const response = await this.post(ENDPOINTS.KNOWLEDGE_SEARCH, { query, limit });
    return response.json();
  }

  async addTextToKnowledge(text, title = '', source = 'Manual Entry') {
    const response = await this.post(ENDPOINTS.KNOWLEDGE_ADD_TEXT, { text, title, source });
    return response.json();
  }

  async addUrlToKnowledge(url, method = 'fetch') {
    const response = await this.post('/api/knowledge_base/add_url', { url, method });
    return response.json();
  }

  async addFileToKnowledge(file) {
    const formData = new FormData();
    formData.append('file', file);
    const response = await this.post('/api/knowledge_base/add_file', formData);
    return response.json();
  }

  async exportKnowledge() {
    const response = await this.get('/api/knowledge_base/export');
    return response.blob();
  }

  async cleanupKnowledge() {
    const response = await this.post('/api/knowledge_base/cleanup');
    return response.json();
  }

  async getKnowledgeStats() {
    const response = await this.get(ENDPOINTS.KNOWLEDGE_STATS);
    return response.json();
  }

  async getDetailedKnowledgeStats() {
    const response = await this.get('/api/knowledge_base/detailed_stats');
    return response.json();
  }

  // Prompts API methods
  async getPrompts() {
    const response = await this.get('/api/prompts/');
    return response.json();
  }

  async savePrompt(promptId, content) {
    const response = await this.post(`/api/prompts/${promptId}`, { content });
    return response.json();
  }

  async revertPrompt(promptId) {
    const response = await this.post(`/api/prompts/${promptId}/revert`);
    return response.json();
  }

  // Health and status methods
  async checkHealth() {
    const response = await this.get(ENDPOINTS.HEALTH);
    return response.json();
  }

  async restartBackend() {
    const response = await this.post('/api/system/restart');
    return response.json();
  }

  // Cleanup methods (integrating chat_api functionality)
  async cleanupMessages() {
    const response = await this.post('/api/chats/cleanup_messages');
    return response.json();
  }

  async cleanupAllChatData() {
    const response = await this.post('/api/chats/cleanup_all');
    return response.json();
  }

  // File Management API methods
  async listFiles(path = '') {
    const response = await this.get(`/api/files/list?path=${encodeURIComponent(path)}`);
    return response.json();
  }

  async uploadFile(file, path = '', overwrite = false) {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('path', path);
    formData.append('overwrite', overwrite.toString());

    const response = await this.post('/api/files/upload', formData);
    return response.json();
  }

  async viewFile(path) {
    const response = await this.get(`/api/files/view/${encodeURIComponent(path)}`);
    return response.json();
  }

  async deleteFile(path) {
    const response = await this.delete('/api/files/delete', {
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path })
    });
    return response.json();
  }

  async downloadFile(path) {
    const response = await this.get(`/api/files/download/${encodeURIComponent(path)}`);
    return response.blob();
  }

  async createDirectory(path = '', name) {
    const formData = new FormData();
    formData.append('path', path);
    formData.append('name', name);

    const response = await this.post('/api/files/create_directory', formData);
    return response.json();
  }

  async getFileStats() {
    const response = await this.get('/api/files/stats');
    return response.json();
  }

  // Utility methods
  async uploadFileToEndpoint(endpoint, file, additionalData = {}) {
    const formData = new FormData();
    formData.append('file', file);

    // Add any additional data to the form
    Object.keys(additionalData).forEach(key => {
      formData.append(key, additionalData[key]);
    });

    const response = await this.post(endpoint, formData);
    return response.json();
  }

  async downloadFileFromEndpoint(endpoint, filename = null) {
    const response = await this.get(endpoint);
    const blob = await response.blob();

    if (filename) {
      // Create download link
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      window.URL.revokeObjectURL(url);
    }

    return blob;
  }

  // Connection testing
  async testConnection() {
    try {
      const start = Date.now();
      await this.checkHealth();
      const latency = Date.now() - start;

      return {
        connected: true,
        latency: latency,
        message: `Connected (${latency}ms)`
      };
    } catch (error) {
      return {
        connected: false,
        error: error.message,
        message: `Connection failed: ${error.message}`
      };
    }
  }

  // Batch operations
  async batchRequest(requests) {
    const results = [];

    for (const request of requests) {
      try {
        const result = await this.request(request.endpoint, request.options);
        results.push({
          success: true,
          data: await result.json(),
          request: request
        });
      } catch (error) {
        results.push({
          success: false,
          error: error.message,
          request: request
        });
      }
    }

    return results;
  }

  // Set custom timeout (kept for compatibility but circuit breaker replaces timeouts)
  setTimeout(timeout) {
    this.timeout = timeout;
    console.warn('[ApiClient] setTimeout called but circuit breaker is now handling request failures');
  }
  
  // Get circuit breaker status
  getCircuitStatus() {
    return this.enhancedFetch.getCircuitStatus();
  }
  
  // Reset circuit breaker
  resetCircuit() {
    this.enhancedFetch.resetCircuit();
    console.log('[ApiClient] Circuit breaker manually reset');
  }

  // Get current timeout
  getTimeout() {
    return this.timeout;
  }

  // Helper method to determine if request should be retried
  shouldRetry(error, method) {
    // Retry logic based on MCP error analysis
    const retryableErrors = [
      'timeout',
      'network',
      'Failed to fetch',
      'Connection refused',
      'ECONNREFUSED'
    ];
    
    // Don't retry write operations (POST, PUT, DELETE) unless specifically safe
    const safeToRetryMethods = ['GET', 'HEAD', 'OPTIONS'];
    if (!safeToRetryMethods.includes(method.toUpperCase())) {
      return false;
    }
    
    // Check if error message indicates a retryable condition
    return retryableErrors.some(errorType => 
      error.message && error.message.toLowerCase().includes(errorType.toLowerCase())
    );
  }

  // Helper method for delays with exponential backoff
  async delay(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
  }

  // Update base URL
  setBaseUrl(url) {
    // CRITICAL: Don't allow baseUrl changes when using Vite proxy
    const isViteDevMode = window.location.port === '5173';
    
    if (isViteDevMode) {
      console.warn('[ApiClient] Proxy mode: Cannot change baseUrl, ignoring setBaseUrl call');
      return;
    }

    this.baseUrl = url;

    // Also update in settings
    if (this.settings.backend) {
      this.settings.backend.api_endpoint = url;
    } else {
      this.settings.backend = { api_endpoint: url };
    }

    this.saveSettingsLocally(this.settings);
  }

  // Get current base URL
  getBaseUrl() {
    return this.baseUrl;
  }

  // Error handling helper
  handleApiError(error, context = '') {
    console.error(`API Error${context ? ` in ${context}` : ''}:`, error);

    let userMessage = 'An unexpected error occurred.';

    if (error.message.includes('timeout')) {
      userMessage = 'Request timed out. Please check your connection and try again.';
    } else if (error.message.includes('HTTP 404')) {
      userMessage = 'The requested resource was not found.';
    } else if (error.message.includes('HTTP 403')) {
      userMessage = 'Access denied. Please check your permissions.';
    } else if (error.message.includes('HTTP 500')) {
      userMessage = 'Server error. Please try again later.';
    } else if (error.message.includes('Failed to fetch')) {
      userMessage = 'Cannot connect to the server. Please check if the backend is running.';
    }

    return {
      error: error.message,
      userMessage: userMessage,
      context: context
    };
  }

  // Check if endpoint is available
  async isEndpointAvailable(endpoint) {
    try {
      await this.get(endpoint);
      return true;
    } catch (error) {
      return false;
    }
  }

  // Get API status summary
  async getApiStatus() {
    const endpoints = [
      '/api/system/health',
      '/api/chats',
      '/api/settings/',
      '/api/prompts'
    ];

    const status = {
      baseUrl: this.baseUrl,
      timestamp: new Date().toISOString(),
      endpoints: {}
    };

    for (const endpoint of endpoints) {
      try {
        const start = Date.now();
        await this.get(endpoint);
        status.endpoints[endpoint] = {
          available: true,
          latency: Date.now() - start
        };
      } catch (error) {
        status.endpoints[endpoint] = {
          available: false,
          error: error.message
        };
      }
    }

    return status;
  }

  // PERFORMANCE OPTIMIZATION: Cleanup method for proper resource management
  destroy() {
    if (this.cacheCleanupInterval) {
      clearInterval(this.cacheCleanupInterval);
      this.cacheCleanupInterval = null;
    }
    this.cache.clear();
  }

  // PERFORMANCE OPTIMIZATION: Get cache statistics for debugging
  getCacheStats() {
    const stats = {
      size: this.cache.size,
      maxSize: this.cacheConfig.maxSize,
      entries: [],
      hitRate: 0, // Would need to track hits/misses to calculate
    };

    for (const [key, entry] of this.cache.entries()) {
      stats.entries.push({
        key,
        endpoint: entry.endpoint,
        expiresIn: Math.max(0, entry.expires - Date.now()),
        size: JSON.stringify(entry.data).length
      });
    }

    return stats;
  }

  // FILE OPERATIONS
  async listFiles() {
    return this.get('/api/files/list');
  }

  async uploadFile(file, options = {}) {
    const formData = new FormData();
    formData.append('file', file);
    
    if (options.metadata) {
      formData.append('metadata', JSON.stringify(options.metadata));
    }

    return this.request('/api/files/upload', {
      method: 'POST',
      body: formData,
      // Don't set Content-Type header - let browser set it with boundary
      headers: {},
      cache: 'no-cache'
    });
  }

  async viewFile(filePath) {
    return this.request(`/api/files/view/${encodeURIComponent(filePath)}`, {
      method: 'GET',
      // Return raw response for file content
      parseJson: false
    });
  }

  async deleteFile(filePath) {
    return this.request(`/api/files/delete`, {
      method: 'POST',
      body: JSON.stringify({ file_path: filePath }),
      headers: { 'Content-Type': 'application/json' }
    });
  }

  async extractFileText(filePath) {
    return this.get(`/api/files/extract-text/${encodeURIComponent(filePath)}`);
  }

  // LLM MODEL OPERATIONS  
  async loadLlmModels() {
    return this.get('/api/llm/models', { cache: 'no-cache' });
  }

  async loadEmbeddingModels() {
    return this.get('/api/llm/embedding/models', { cache: 'no-cache' });
  }

  // WORKFLOW OPERATIONS
  async executeWorkflow(goal, autoApprove = false) {
    return this.post('/api/workflow/execute', {
      goal,
      auto_approve: autoApprove,
      timestamp: new Date().toISOString()
    });
  }

  // KNOWLEDGE BASE OPERATIONS
  async addUrlToKnowledge(url, method = 'crawl') {
    return this.post('/api/knowledge_base/crawl_url', {
      url,
      method
    });
  }

  async crawlUrlForEntry(entryId, url) {
    return this.post('/api/knowledge_base/crawl_url', {
      entry_id: entryId,
      url
    });
  }

  async createKnowledgeEntry(entryData) {
    return this.post('/api/knowledge_base/entries', entryData);
  }

  async updateKnowledgeEntry(entryId, entryData) {
    return this.put(`/api/knowledge_base/entries/${entryId}`, entryData);
  }

  async importSystemDocumentation(forceRefresh = false) {
    return this.post('/api/knowledge_base/system_knowledge/import_documentation', { 
      force_refresh: forceRefresh 
    });
  }

  async importSystemPrompts(forceRefresh = false) {
    return this.post('/api/knowledge_base/system_knowledge/import_prompts', { 
      force_refresh: forceRefresh 
    });
  }

  async getKnowledgeEntries() {
    return this.get('/api/knowledge_base/entries');
  }

  // VALIDATION OPERATIONS
  async getValidationReport() {
    return this.get('/api/validation-dashboard/report');
  }

  // CHAT OPERATIONS (enhanced)
  async sendChatMessage(chatId, message, options = {}) {
    return this.post(`/api/chat/message`, {
      content: message,
      role: "user",
      session_id: chatId,
      files: options.files || [],
      timestamp: new Date().toISOString(),
      ...options
    });
  }

  // CONFIGURATION OPERATIONS
  async loadFrontendConfig() {
    return this.get('/api/config/frontend', { cache: 'default' });
  }

  // TERMINAL OPERATIONS
  async createTerminalSession(options = {}) {
    return this.post('/api/terminal/sessions', {
      user_id: 'default',
      security_level: 'standard',
      enable_logging: false,
      ...options
    });
  }

  async deleteTerminalSession(sessionId) {
    return this.request(`/api/terminal/sessions/${sessionId}`, {
      method: 'DELETE'
    });
  }

  async getTerminalSessions() {
    return this.get('/api/terminal/sessions');
  }

  async executeTerminalCommand(command, options = {}) {
    const terminalTimeout = API_CONFIG.TERMINAL_TIMEOUT || 30000;
    return this.post('/api/terminal/command', {
      command: command,
      timeout: options.timeout || terminalTimeout,
      working_directory: options.cwd,
      environment: options.env || {},
      ...options
    });
  }

  async getTerminalSessionInfo(sessionId) {
    return this.get(`/api/terminal/consolidated/sessions/${sessionId}`);
  }
}

// Create and export a singleton instance
const apiClient = new ApiClient();

// PERFORMANCE OPTIMIZATION: Cleanup on page unload
if (typeof window !== 'undefined') {
  window.addEventListener('beforeunload', () => {
    apiClient.destroy();
  });

  // Make cache stats available globally for debugging
  if (!window.PRODUCTION_MODE) {
    window.apiClientStats = () => apiClient.getCacheStats();
    window.clearApiCache = (pattern) => apiClient.clearCache(pattern);
  }
}

export default apiClient;
export { ApiClient };