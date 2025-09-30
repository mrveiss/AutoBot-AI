// ApiClient.js - Unified API client for all backend operations
// RumAgent is accessed via window.rum global
// MIGRATED: Now uses AppConfig.js for better configuration management

// MIGRATED: Using AppConfig.js for centralized configuration
import appConfig from '@/config/AppConfig.js';
import errorHandler from '@/utils/ErrorHandler.js';
import { EnhancedFetch } from '@/utils/ApiCircuitBreaker.js';

class ApiClient {
  constructor() {
    // Initialize with defaults first, async config loads separately
    this.baseUrl = '';
    this.timeout = 10000;
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
    console.log('[ApiClient] Constructor initialization:');
    console.log('[ApiClient] - Initial baseUrl from AppConfig:', this.baseUrl);
    console.log('[ApiClient] - Development mode:', this.isDevMode);
    console.log('[ApiClient] - window.location.port:', window.location.port);
    console.log('[ApiClient] - Settings loaded:', this.settings);

    // CRITICAL: Proxy mode detection for Vite dev server
    const isViteDevMode = window.location.port === '5173' && this.isDevMode;

    if (isViteDevMode) {
      console.log('[ApiClient] PROXY MODE: Running on port 5173, forcing proxy usage');
      console.log('[ApiClient] PROXY MODE: Ignoring any localStorage settings');
      // Force empty baseUrl to ensure relative URLs trigger Vite proxy
      this.baseUrl = '';
    } else {
      // Only in production mode, consider localStorage settings override
      if (this.settings?.backend?.api_endpoint && !this.isDevMode) {
        console.log('[ApiClient] PRODUCTION MODE: Overriding baseUrl with settings:', this.settings.backend.api_endpoint);
        this.baseUrl = this.settings.backend.api_endpoint;
      } else {
        console.log('[ApiClient] PRODUCTION MODE: Using AppConfig baseUrl:', this.baseUrl);
      }
    }

    // Update circuit breaker with final baseUrl
    this.enhancedFetch.updateBaseUrl(this.baseUrl);

    console.log('[ApiClient] - Final baseUrl after proxy detection:', this.baseUrl);
    console.log('[ApiClient] - Proxy mode active:', !this.baseUrl);
  }

  // MIGRATED: Initialize configuration from AppConfig.js
  async initializeConfiguration() {
    try {
      // Get backend service URL from AppConfig
      this.baseUrl = await appConfig.getServiceUrl('backend');
      this.timeout = appConfig.getTimeout('default');
      this.isDevMode = appConfig.get('environment.isDev', false);
      this.enableDebug = appConfig.get('features.enableDebug', false);

      console.log('[ApiClient] Configuration initialized from AppConfig');
    } catch (error) {
      console.warn('[ApiClient] Failed to initialize from AppConfig, using fallback:', error.message);

      // Fallback to environment variables
      this.baseUrl = this.detectBaseUrl();
      this.timeout = parseInt(import.meta.env.VITE_API_TIMEOUT || '60000');
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
      console.log('[ApiClient] FALLBACK PROXY MODE: Using Vite proxy (empty baseUrl)');
      return ''; // Empty string forces relative URLs which go through Vite proxy
    }

    // DIRECT MODE: Use actual backend IP for production or non-proxy environments
    if (backendHost && backendPort && protocol) {
      const directUrl = `${protocol}://${backendHost}:${backendPort}`;
      console.log('[ApiClient] FALLBACK DIRECT MODE: Using backend URL:', directUrl);
      return directUrl;
    }

    // Final fallback
    return 'http://172.16.168.20:8001';
  }

  loadSettings() {
    try {
      const stored = localStorage.getItem('autobot_backend_settings');
      return stored ? JSON.parse(stored) : {};
    } catch (error) {
      console.warn('[ApiClient] Failed to load settings:', error);
      return {};
    }
  }

  saveSettings(settings) {
    try {
      localStorage.setItem('autobot_backend_settings', JSON.stringify(settings));
      this.settings = settings;
    } catch (error) {
      console.error('[ApiClient] Failed to save settings:', error);
    }
  }

  // MIGRATED: Enhanced API URL construction using AppConfig
  async getApiUrl(endpoint = '', options = {}) {
    try {
      // Use AppConfig for URL construction when available
      return await appConfig.getApiUrl(endpoint, options);
    } catch (error) {
      console.warn('[ApiClient] AppConfig URL construction failed, using fallback:', error.message);

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
      console.warn('[ApiClient] AppConfig fetch failed, using fallback:', error.message);

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
  async get(endpoint, options = {}) {
    console.log(`[ApiClient] GET Request: ${endpoint}`);

    // Log the full URL being accessed for debugging
    const fullUrl = await this.getApiUrl(endpoint, options);
    console.log(`[ApiClient] - Full URL: ${fullUrl}`);
    console.log(`[ApiClient] - Proxy mode: ${!this.baseUrl}`);

    let lastError;
    const maxRetries = 3;

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
        console.log(`[ApiClient] GET Success: ${endpoint} (attempt ${attempt})`);

        // Log successful response for debugging
        if (this.enableDebug) {
          console.log(`[ApiClient] Response data:`, data);
        }

        return data;

      } catch (error) {
        lastError = error;
        console.warn(`[ApiClient] GET attempt ${attempt} failed for ${endpoint}:`, error.message);

        // Don't retry on 4xx errors (client errors)
        if (error.message.includes('HTTP 4')) {
          break;
        }

        // Wait before retrying (exponential backoff)
        if (attempt < maxRetries) {
          const delay = Math.min(1000 * Math.pow(2, attempt - 1), 5000);
          console.log(`[ApiClient] Retrying ${endpoint} in ${delay}ms...`);
          await new Promise(resolve => setTimeout(resolve, delay));
        }
      }
    }

    // All retries failed
    console.error(`[ApiClient] GET failed after ${maxRetries} attempts: ${endpoint}`, lastError);
    throw lastError;
  }

  // POST request with retry logic
  async post(endpoint, data = {}, options = {}) {
    console.log(`[ApiClient] POST Request: ${endpoint}`);

    try {
      const response = await this.fetchWithConfig(endpoint, {
        ...options,
        method: 'POST',
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
      console.log(`[ApiClient] POST Success: ${endpoint}`);
      return responseData;

    } catch (error) {
      console.error(`[ApiClient] POST failed: ${endpoint}`, error);
      throw error;
    }
  }

  // PUT request
  async put(endpoint, data = {}, options = {}) {
    console.log(`[ApiClient] PUT Request: ${endpoint}`);

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
      console.log(`[ApiClient] PUT Success: ${endpoint}`);
      return responseData;

    } catch (error) {
      console.error(`[ApiClient] PUT failed: ${endpoint}`, error);
      throw error;
    }
  }

  // DELETE request
  async delete(endpoint, options = {}) {
    console.log(`[ApiClient] DELETE Request: ${endpoint}`);

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

      console.log(`[ApiClient] DELETE Success: ${endpoint}`);
      return responseData;

    } catch (error) {
      console.error(`[ApiClient] DELETE failed: ${endpoint}`, error);
      throw error;
    }
  }

  // File upload with progress tracking
  async uploadFile(endpoint, file, progressCallback = null, options = {}) {
    console.log(`[ApiClient] File Upload: ${endpoint}`, {
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

        // Set timeout (default 5 minutes for file uploads)
        xhr.timeout = options.timeout || 300000;

        xhr.send(formData);
      });

      const result = await uploadPromise;
      console.log(`[ApiClient] File Upload Success: ${endpoint}`);
      return result;

    } catch (error) {
      console.error(`[ApiClient] File Upload failed: ${endpoint}`, error);
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
      const health = await this.get('/api/health', { timeout: 5000 });
      return health?.status === 'healthy';
    } catch (error) {
      console.warn('[ApiClient] Health check failed:', error.message);
      return false;
    }
  }

  // Connection validation using AppConfig
  async validateConnection() {
    try {
      // Use AppConfig validation if available
      return await appConfig.validateConnection();
    } catch (error) {
      console.warn('[ApiClient] AppConfig validation failed, using fallback:', error.message);
      return await this.checkHealth();
    }
  }

  // Cache invalidation
  invalidateCache() {
    try {
      // Use AppConfig cache invalidation if available
      appConfig.invalidateCache();
    } catch (error) {
      console.warn('[ApiClient] AppConfig cache invalidation failed:', error.message);

      // Fallback cache invalidation
      Object.keys(localStorage).forEach(key => {
        if (key.startsWith('autobot_api_') || key.startsWith('autobot_config_')) {
          localStorage.removeItem(key);
        }
      });
    }
  }

  // Update base URL (useful for settings changes)
  updateBaseUrl(newBaseUrl) {
    console.log(`[ApiClient] Updating base URL from ${this.baseUrl} to ${newBaseUrl}`);
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
    console.warn('[ApiClient] Async configuration initialization failed:', error.message);
  });
}

// Export both the class and the singleton instance
export { ApiClient };
export default apiClientInstance;