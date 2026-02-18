/**
 * AppConfigService - Centralized Frontend Configuration Management
 *
 * Replaces all hardcoded URLs and provides dynamic service discovery.
 * Single source of truth for all frontend configuration needs.
 */

import ServiceDiscovery from './ServiceDiscovery.js';
import { NetworkConstants } from '../constants/network.ts';
import { createLogger } from '@/utils/debugUtils';

const logger = createLogger('AppConfig');

export class AppConfigService {
  constructor() {
    this.serviceDiscovery = new ServiceDiscovery();
    this.config = this.initializeConfig();
    this.configLoaded = false;
    this.configLoadingPromise = null; // Issue #677: Track in-flight config request
    this.debugMode = import.meta.env.DEV || import.meta.env.VITE_ENABLE_DEBUG === 'true';

    this.log('AppConfigService initialized');
  }

  /**
   * Initialize configuration with environment variables and defaults
   */
  initializeConfig() {
    return {
      // Service URLs - Will be resolved dynamically
      services: {
        backend: {
          host: import.meta.env.VITE_BACKEND_HOST,
          port: import.meta.env.VITE_BACKEND_PORT || '8001',
          protocol: import.meta.env.VITE_HTTP_PROTOCOL || 'http'
        },
        redis: {
          host: import.meta.env.VITE_REDIS_HOST,
          port: import.meta.env.VITE_REDIS_PORT || '6379',
          protocol: 'redis'
        },
        vnc: {
          desktop: {
            host: import.meta.env.VITE_DESKTOP_VNC_HOST,
            port: import.meta.env.VITE_DESKTOP_VNC_PORT || '6080',
            password: import.meta.env.VITE_DESKTOP_VNC_PASSWORD || 'autobot',
            protocol: 'http'
          },
          terminal: {
            host: import.meta.env.VITE_TERMINAL_VNC_HOST,
            port: import.meta.env.VITE_TERMINAL_VNC_PORT || '6080',
            password: import.meta.env.VITE_TERMINAL_VNC_PASSWORD || 'autobot',
            protocol: 'http'
          },
          playwright: {
            host: import.meta.env.VITE_PLAYWRIGHT_VNC_HOST,
            port: import.meta.env.VITE_PLAYWRIGHT_VNC_PORT || '6081',
            password: import.meta.env.VITE_PLAYWRIGHT_VNC_PASSWORD || 'playwright',
            protocol: 'http'
          }
        },
        npu: {
          worker: {
            host: import.meta.env.VITE_NPU_WORKER_HOST,
            port: import.meta.env.VITE_NPU_WORKER_PORT || '8081',
            protocol: 'http'
          }
        },
        ollama: {
          host: import.meta.env.VITE_OLLAMA_HOST,
          port: import.meta.env.VITE_OLLAMA_PORT || '11434',
          protocol: 'http'
        },
        playwright: {
          host: import.meta.env.VITE_PLAYWRIGHT_HOST,
          port: import.meta.env.VITE_PLAYWRIGHT_PORT || '3000',
          protocol: 'http'
        }
      },

      // Infrastructure Configuration - Uses NetworkConstants for VM IPs
      infrastructure: {
        machines: {
          vm0: {
            id: 'vm0',
            name: 'VM0 - Backend',
            ip: import.meta.env.VITE_VM0_IP || NetworkConstants.MAIN_MACHINE_IP,
            role: 'backend',
            icon: 'fas fa-server'
          },
          vm1: {
            id: 'vm1',
            name: 'VM1 - Frontend',
            ip: import.meta.env.VITE_VM1_IP || NetworkConstants.FRONTEND_VM_IP,
            role: 'frontend',
            icon: 'fas fa-desktop'
          },
          vm2: {
            id: 'vm2',
            name: 'VM2 - NPU Worker',
            ip: import.meta.env.VITE_VM2_IP || NetworkConstants.NPU_WORKER_VM_IP,
            role: 'worker',
            icon: 'fas fa-microchip'
          },
          vm3: {
            id: 'vm3',
            name: 'VM3 - Redis Database',
            ip: import.meta.env.VITE_VM3_IP || NetworkConstants.REDIS_VM_IP,
            role: 'database',
            icon: 'fas fa-database'
          },
          vm4: {
            id: 'vm4',
            name: 'VM4 - AI Stack',
            ip: import.meta.env.VITE_VM4_IP || NetworkConstants.AI_STACK_VM_IP,
            role: 'ai',
            icon: 'fas fa-brain'
          },
          vm5: {
            id: 'vm5',
            name: 'VM5 - Browser Service',
            ip: import.meta.env.VITE_VM5_IP || NetworkConstants.BROWSER_VM_IP,
            role: 'browser',
            icon: 'fas fa-globe'
          }
        }
      },

      // API Configuration - SINGLE SOURCE OF TRUTH for all timeouts (Issue #598)
      // All timeout values in milliseconds
      api: {
        // Default timeout for standard API calls (30 seconds)
        timeout: parseInt(import.meta.env.VITE_API_TIMEOUT || '30000'),
        retryAttempts: parseInt(import.meta.env.VITE_API_RETRY_ATTEMPTS || '3'),
        retryDelay: parseInt(import.meta.env.VITE_API_RETRY_DELAY || '1000'),
        cacheBustVersion: import.meta.env.VITE_APP_VERSION || Date.now().toString(),
        disableCache: import.meta.env.VITE_DISABLE_CACHE === 'true',
        // Backward compatibility alias (Issue #598: prefer using timeouts.knowledge)
        knowledgeTimeout: parseInt(import.meta.env.VITE_KNOWLEDGE_TIMEOUT || '300000'),

        // Operation-specific timeouts (Issue #598: centralized timeout management)
        // These are THE source of truth - all ApiClient implementations MUST use these
        timeouts: {
          // Standard API operations (30s)
          default: parseInt(import.meta.env.VITE_API_TIMEOUT || '30000'),
          // Knowledge base / vectorization operations (5 minutes)
          knowledge: parseInt(import.meta.env.VITE_KNOWLEDGE_TIMEOUT || '300000'),
          // File upload operations (5 minutes)
          upload: parseInt(import.meta.env.VITE_UPLOAD_TIMEOUT || '300000'),
          // Health check operations (5 seconds)
          health: 5000,
          // Quick operations (5 seconds)
          short: 5000,
          // Long-running operations (2 minutes)
          long: 120000,
          // Analytics/reporting operations (3 minutes)
          analytics: 180000,
          // Search operations (30 seconds)
          search: 30000
        }
      },

      // Feature Flags
      features: {
        enableDebug: import.meta.env.VITE_ENABLE_DEBUG === 'true',
        enableRum: import.meta.env.VITE_ENABLE_RUM !== 'false',
        enableWebSockets: import.meta.env.VITE_ENABLE_WEBSOCKETS !== 'false',
        enableVncDesktop: import.meta.env.VITE_ENABLE_VNC_DESKTOP !== 'false',
        enableNpuWorker: import.meta.env.VITE_ENABLE_NPU_WORKER !== 'false'
      },

      // Environment Information
      environment: {
        isDev: import.meta.env.DEV,
        isProd: import.meta.env.PROD,
        mode: import.meta.env.MODE,
        nodeEnv: import.meta.env.NODE_ENV
      }
    };
  }

  /**
   * Get service URL - Replaces all hardcoded URLs
   */
  async getServiceUrl(serviceName, options = {}) {
    return this.serviceDiscovery.getServiceUrl(serviceName, options);
  }

  /**
   * Get VNC URL with auto-connection parameters
   */
  async getVncUrl(type = 'desktop', options = {}) {
    const vncConfig = this.config.services.vnc[type];
    if (!vncConfig) {
      throw new Error(`Unknown VNC type: ${type}`);
    }

    // Use backend VNC proxy for agent observation
    // This routes VNC traffic through backend (NetworkConstants.MAIN_MACHINE_IP:8001)
    // allowing the agent to observe and log VNC connections
    const backendUrl = await this.serviceDiscovery.getServiceUrl('backend');
    const proxyPath = type === 'playwright' ? 'browser' : type; // Map 'playwright' → 'browser'

    const params = new URLSearchParams({
      autoconnect: options.autoconnect !== false ? 'true' : 'false',
      password: options.password || vncConfig.password,
      resize: options.resize || 'remote',
      reconnect: options.reconnect !== false ? 'true' : 'false',
      quality: options.quality || '9',
      compression: options.compression || '9',
      ...options.extraParams
    });

    const url = `${backendUrl}/api/vnc-proxy/${proxyPath}/vnc.html?${params.toString()}`;
    this.log(`Generated VNC URL for ${type} (via backend proxy):`, url);
    return url;
  }

  /**
   * Get infrastructure machine configuration
   */
  getInfrastructureMachines() {
    return this.config.infrastructure.machines;
  }

  /**
   * Get specific machine configuration by ID
   */
  getMachine(machineId) {
    const machine = this.config.infrastructure.machines[machineId];
    if (!machine) {
      throw new Error(`Unknown machine ID: ${machineId}`);
    }
    return machine;
  }

  /**
   * Get all machines as array
   */
  getMachinesArray() {
    return Object.values(this.config.infrastructure.machines);
  }

  /**
   * Get WebSocket URL
   */
  async getWebSocketUrl(endpoint = '') {
    const baseUrl = await this.serviceDiscovery.getWebSocketUrl();
    return endpoint ? `${baseUrl}${endpoint}` : baseUrl;
  }

  /**
   * Get API endpoint URL with cache busting
   */
  async getApiUrl(endpoint = '', options = {}) {
    // CRITICAL FIX: Detect if endpoint is already a full URL
    if (endpoint.startsWith('http://') || endpoint.startsWith('https://')) {
      this.log(`Endpoint is already full URL: ${endpoint}`);
      return endpoint; // Already a full URL, don't prepend base URL
    }

    const baseUrl = await this.serviceDiscovery.getServiceUrl('backend');

    // CRITICAL FIX: Handle proxy mode when baseUrl is empty
    let fullUrl;
    if (!baseUrl) {
      // Proxy mode - use relative URL
      fullUrl = endpoint;
    } else {
      // Direct mode - construct full URL
      fullUrl = `${baseUrl}${endpoint}`;
    }

    // Add cache-busting parameters if enabled
    // ONLY add cache-busting if we have an actual endpoint (not empty or just base URL)
    if (!this.config.api.disableCache && options.cacheBust !== false && endpoint && endpoint.length > 0) {
      const separator = fullUrl.includes('?') ? '&' : '?';
      const cacheBustParam = `_cb=${this.config.api.cacheBustVersion}`;
      const timestampParam = `_t=${Date.now()}`;
      fullUrl = `${fullUrl}${separator}${cacheBustParam}&${timestampParam}`;
    }

    this.log(`Generated API URL: ${fullUrl} (proxy mode: ${!baseUrl})`);
    return fullUrl;
  }

  /**
   * Enhanced fetch with standardized configuration
   */
  async fetchApi(endpoint, options = {}) {
    let url;
    try {
      url = await this.getApiUrl(endpoint, options);
    } catch (urlError) {
      this.log('Failed to resolve API URL:', urlError.message);
      throw new Error(`Service URL resolution failed: ${urlError.message}`);
    }

    const defaultHeaders = {
      'Cache-Control': 'no-cache, no-store, must-revalidate',
      'Pragma': 'no-cache',
      'Expires': '0',
      'X-Cache-Bust': this.config.api.cacheBustVersion,
      'X-Request-Time': Date.now().toString(),
      'Content-Type': 'application/json'
    };

    // Merge headers
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
    const timeout = options.timeout || this.config.api.timeout;
    const timeoutId = setTimeout(() => controller.abort(), timeout);
    fetchOptions.signal = controller.signal;

    try {
      this.log(`API Request: ${options.method || 'GET'} ${url}`);
      const response = await fetch(url, fetchOptions);
      clearTimeout(timeoutId);

      this.log(`API Response: ${response.status} ${response.statusText}`);
      return response;
    } catch (error) {
      clearTimeout(timeoutId);

      // Enhanced error logging and categorization
      if (error.name === 'AbortError') {
        this.log(`API request timeout after ${timeout}ms: ${url}`);
        throw new Error(`Request timeout (${timeout}ms): ${endpoint}`);
      } else if (error.message.includes('Failed to fetch')) {
        this.log(`Network error for ${url}:`, error.message);
        throw new Error(`Network connectivity error: ${endpoint}`);
      } else {
        this.log('API fetch failed:', error);
        throw error;
      }
    }
  }

  /**
   * Load configuration from backend
   * Issue #677: Uses request deduplication to prevent multiple concurrent loads
   */
  async loadRemoteConfig() {
    // Issue #677: If already loaded, return immediately
    if (this.configLoaded) {
      this.log('Config already loaded, skipping duplicate request');
      return;
    }

    // Issue #677: If a load is in progress, return the existing promise
    if (this.configLoadingPromise) {
      this.log('Config load already in progress, reusing existing request');
      return this.configLoadingPromise;
    }

    // Issue #677: Store the promise to deduplicate concurrent calls
    this.configLoadingPromise = this._doLoadRemoteConfig();

    try {
      await this.configLoadingPromise;
    } finally {
      this.configLoadingPromise = null;
    }
  }

  /**
   * Internal method to actually load remote config
   */
  async _doLoadRemoteConfig() {
    try {
      const response = await this.fetchApi('/api/frontend-config', {
        timeout: 5000, // Short timeout for config loading
        cacheBust: false // Don't cache bust config requests
      });
      if (response.ok) {
        const remoteConfig = await response.json();
        this.mergeConfig(remoteConfig);
        this.configLoaded = true;
        this.log('Remote configuration loaded successfully');
      } else if (response.status === 404) {
        this.log('Remote configuration endpoint not available, using local defaults');
        this.configLoaded = true; // Mark as loaded to prevent retries
      } else {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }
    } catch (error) {
      this.log('Failed to load remote configuration, using defaults:', error.message);
      this.configLoaded = true; // Mark as loaded to prevent infinite retries

      // If it's a network error, we should still function with defaults
      if (error.message.includes('Failed to fetch') ||
          error.message.includes('Network Error') ||
          error.name === 'AbortError') {
        this.log('Network connectivity issues detected, continuing with local configuration');
      }
    }
  }

  /**
   * Merge remote configuration with local config
   */
  mergeConfig(remoteConfig) {
    this.config = {
      ...this.config,
      ...remoteConfig,
      services: {
        ...this.config.services,
        ...remoteConfig.services
      },
      api: {
        ...this.config.api,
        ...remoteConfig.api
      },
      features: {
        ...this.config.features,
        ...remoteConfig.features
      }
    };
  }

  /**
   * Get configuration value with dot notation
   */
  get(path, defaultValue = null) {
    return path.split('.').reduce((obj, key) =>
      (obj && obj[key] !== undefined) ? obj[key] : defaultValue, this.config
    );
  }

  /**
   * Check if feature is enabled
   */
  isFeatureEnabled(featureName) {
    return this.get(`features.${featureName}`, false);
  }

  /**
   * Get timeout for specific operation (Issue #598: SINGLE SOURCE OF TRUTH)
   *
   * Available operations:
   * - 'default': Standard API calls (30s)
   * - 'knowledge': Vectorization/knowledge base operations (5min)
   * - 'upload': File uploads (5min)
   * - 'health': Health checks (5s)
   * - 'short': Quick operations (5s)
   * - 'long': Long-running operations (2min)
   * - 'analytics': Analytics/reporting (3min)
   * - 'search': Search operations (30s)
   *
   * @param {string} operation - The operation type
   * @returns {number} Timeout in milliseconds
   */
  getTimeout(operation = 'default') {
    // Use the centralized timeouts object (Issue #598)
    const timeouts = this.config.api.timeouts;
    return timeouts[operation] || timeouts.default;
  }

  /**
   * Validate API connection
   */
  async validateConnection() {
    try {
      const response = await this.fetchApi('/api/system/health', {
        method: 'GET',
        timeout: 5000,
        cacheBust: true
      });

      if (response.ok) {
        this.log('API connection validation successful');
        return true;
      } else {
        this.log(`API connection validation failed: HTTP ${response.status}`);
        return false;
      }
    } catch (error) {
      this.log('API connection validation failed:', error.message);
      return false;
    }
  }

  /**
   * Invalidate cache
   */
  invalidateCache() {
    this.log('Invalidating cache...');

    // Update cache bust version
    this.config.api.cacheBustVersion = Date.now().toString();

    // Clear localStorage caches
    Object.keys(localStorage).forEach(key => {
      if (key.startsWith('autobot_api_') || key.startsWith('autobot_config_')) {
        localStorage.removeItem(key);
      }
    });

    // Clear sessionStorage caches
    Object.keys(sessionStorage).forEach(key => {
      if (key.startsWith('autobot_api_') || key.startsWith('autobot_config_')) {
        sessionStorage.removeItem(key);
      }
    });

    this.log('Cache invalidated');
  }

  /**
   * Debug logging
   */
  log(...args) {
    if (this.debugMode) {
      logger.debug('[AppConfig]', ...args);
    }
  }

  /**
   * Get all service URLs for debugging
   */
  async getAllServiceUrls() {
    const services = ['backend', 'redis', 'vnc_desktop', 'vnc_terminal', 'vnc_playwright', 'npu_worker', 'ollama', 'playwright'];
    const urls = {};

    for (const service of services) {
      try {
        urls[service] = await this.getServiceUrl(service);
      } catch (error) {
        urls[service] = `Error: ${error.message}`;
      }
    }

    return urls;
  }

  /**
   * Get backend configuration (for components that need raw config data)
   * This fetches the full configuration from backend including hosts, services, etc.
   */
  async getBackendConfig() {
    try {
      // First ensure we've loaded remote config
      if (!this.configLoaded) {
        await this.loadRemoteConfig();
      }

      // Try to fetch from backend API
      const response = await this.fetchApi('/api/system/frontend-config', {
        timeout: 5000,
        cacheBust: false
      });

      if (response.ok) {
        const backendConfig = await response.json();
        this.log('Backend configuration retrieved:', Object.keys(backendConfig));
        return backendConfig;
      } else {
        this.log('Backend config endpoint returned:', response.status);
        // Return current local config as fallback
        return this.config;
      }
    } catch (error) {
      this.log('Failed to get backend config, using local config:', error.message);
      // Return current local config as fallback
      return this.config;
    }
  }

  /**
   * Get cached frontend config - Issue #677
   * Returns already-loaded config or loads it first (with deduplication)
   * @returns {Promise<Object>} The frontend configuration
   */
  async getFrontendConfig() {
    if (!this.configLoaded) {
      await this.loadRemoteConfig();
    }
    return this.config;
  }

  /**
   * Get project root path from config - Issue #677
   * Convenience method for components that need the project root
   * @returns {Promise<string|null>} The project root path or null
   */
  async getProjectRoot() {
    const config = await this.getFrontendConfig();
    return config?.project?.root_path || null;
  }
}

// Singleton instance
const appConfig = new AppConfigService();

// Initialize remote configuration on load
if (typeof window !== 'undefined') {
  appConfig.loadRemoteConfig().catch((err) => logger.warn('Failed to load remote config:', err));
}

export default appConfig;
