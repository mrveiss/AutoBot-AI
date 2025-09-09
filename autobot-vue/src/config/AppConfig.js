/**
 * AppConfigService - Centralized Frontend Configuration Management
 * 
 * Replaces all hardcoded URLs and provides dynamic service discovery.
 * Single source of truth for all frontend configuration needs.
 */

import ServiceDiscovery from './ServiceDiscovery.js';

export class AppConfigService {
  constructor() {
    this.serviceDiscovery = new ServiceDiscovery();
    this.config = this.initializeConfig();
    this.configLoaded = false;
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

      // Infrastructure Configuration
      infrastructure: {
        machines: {
          vm0: {
            id: 'vm0',
            name: 'VM0 - Backend',
            ip: import.meta.env.VITE_VM0_IP || '172.16.168.20',
            role: 'backend',
            icon: 'fas fa-server'
          },
          vm1: {
            id: 'vm1', 
            name: 'VM1 - Frontend',
            ip: import.meta.env.VITE_VM1_IP || '172.16.168.21',
            role: 'frontend',
            icon: 'fas fa-desktop'
          },
          vm2: {
            id: 'vm2',
            name: 'VM2 - NPU Worker',
            ip: import.meta.env.VITE_VM2_IP || '172.16.168.22', 
            role: 'worker',
            icon: 'fas fa-microchip'
          },
          vm3: {
            id: 'vm3',
            name: 'VM3 - Redis Database',
            ip: import.meta.env.VITE_VM3_IP || '172.16.168.23',
            role: 'database',
            icon: 'fas fa-database'
          },
          vm4: {
            id: 'vm4',
            name: 'VM4 - AI Stack',
            ip: import.meta.env.VITE_VM4_IP || '172.16.168.24',
            role: 'ai',
            icon: 'fas fa-brain'
          },
          vm5: {
            id: 'vm5',
            name: 'VM5 - Browser Service',
            ip: import.meta.env.VITE_VM5_IP || '172.16.168.25',
            role: 'browser',
            icon: 'fas fa-globe'
          }
        }
      },

      // API Configuration
      api: {
        timeout: parseInt(import.meta.env.VITE_API_TIMEOUT || '30000'),
        retryAttempts: parseInt(import.meta.env.VITE_API_RETRY_ATTEMPTS || '3'),
        retryDelay: parseInt(import.meta.env.VITE_API_RETRY_DELAY || '1000'),
        knowledgeTimeout: parseInt(import.meta.env.VITE_KNOWLEDGE_TIMEOUT || '300000'),
        cacheBustVersion: import.meta.env.VITE_APP_VERSION || Date.now().toString(),
        disableCache: import.meta.env.VITE_DISABLE_CACHE === 'true'
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

    const baseUrl = await this.serviceDiscovery.getServiceUrl(`vnc_${type}`);
    const params = new URLSearchParams({
      autoconnect: options.autoconnect !== false ? 'true' : 'false',
      password: options.password || vncConfig.password,
      resize: options.resize || 'remote',
      reconnect: options.reconnect !== false ? 'true' : 'false',
      quality: options.quality || '9',
      compression: options.compression || '9',
      ...options.extraParams
    });

    const url = `${baseUrl}/vnc.html?${params.toString()}`;
    this.log(`Generated VNC URL for ${type}:`, url);
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
    const baseUrl = await this.serviceDiscovery.getServiceUrl('backend');
    let fullUrl = `${baseUrl}${endpoint}`;
    
    // Add cache-busting parameters if enabled
    if (!this.config.api.disableCache && options.cacheBust !== false) {
      const separator = fullUrl.includes('?') ? '&' : '?';
      const cacheBustParam = `_cb=${this.config.api.cacheBustVersion}`;
      const timestampParam = `_t=${Date.now()}`;
      fullUrl = `${fullUrl}${separator}${cacheBustParam}&${timestampParam}`;
    }
    
    this.log(`Generated API URL: ${fullUrl}`);
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
   */
  async loadRemoteConfig() {
    try {
      const response = await this.fetchApi('/api/system/frontend-config', {
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
   * Get timeout for specific operation
   */
  getTimeout(operation = 'default') {
    const timeouts = {
      default: this.config.api.timeout,
      knowledge: this.config.api.knowledgeTimeout,
      short: 5000,
      long: 60000
    };
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
      console.log('[AutoBot Config]', ...args);
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
}

// Singleton instance
const appConfig = new AppConfigService();

// Initialize remote configuration on load
if (typeof window !== 'undefined') {
  appConfig.loadRemoteConfig().catch(console.warn);
}

export default appConfig;