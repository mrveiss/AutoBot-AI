/**
 * Centralized Configuration Service
 *
 * Eliminates hardcoded values throughout the application by providing
 * a single source of truth for all configuration parameters.
 */

import appConfig from '@/config/AppConfig.js';
import { ApiClient } from '@/utils/ApiClient.js';
import { createLogger } from '@/utils/debugUtils';

// Create scoped logger for ConfigService
const logger = createLogger('ConfigService');

// Create ApiClient instance for config operations
const apiClient = new ApiClient();

export class ConfigService {
  constructor() {
    // Initialize with empty config - all values loaded from external sources
    this.config = {};

    // Load configuration from all sources
    this.loadConfiguration();
  }

  /**
   * Load configuration from multiple sources in priority order:
   * 1. Environment variables (highest priority)
   * 2. External config file from backend
   * 3. Runtime localStorage overrides
   * 4. Built-in fallback defaults (lowest priority)
   */
  async loadConfiguration() {
    // Built-in fallback defaults (only used if no other source provides values)
    const fallbackDefaults = {
      api: {
        backend_url: '', // Will be loaded from AppConfig
        ollama_url: '', // Will be loaded from AppConfig
        timeout: appConfig.getConfig().api.timeout,
        retry_attempts: appConfig.getConfig().api.retryAttempts
      },
      paths: {
        data_directory: 'data',
        config_directory: 'config',
        chat_history_file: 'data/chat_history.json',
        knowledge_base_file: 'data/knowledge_base.db'
      },
      defaults: {
        welcome_message: "Hello! How can I assist you today?",
        model_name: import.meta.env.VITE_DEFAULT_MODEL || '',  // Loaded from backend config
        max_chat_messages: 100,
        connection_check_interval: 10000
      },
      ui: {
        theme: 'light',
        font_size: 'medium',
        sidebar_width: '250px',
        auto_scroll: true
      },
      features: {
        streaming_enabled: true,
        debug_mode: false,
        voice_enabled: false,
        knowledge_base_enabled: true
      }
    };

    // Load dynamic URLs from AppConfig first
    try {
      fallbackDefaults.api.backend_url = await appConfig.getApiUrl('');
      fallbackDefaults.api.ollama_url = await appConfig.getServiceUrl('ollama');
    } catch (error) {
      logger.warn('AppConfig URL loading failed, using defaults from appConfig:', error.message);
      // Use appConfig defaults instead of hardcoded IPs
      const defaults = appConfig.get('defaults', {});
      fallbackDefaults.api.backend_url = defaults.backendUrl || '';
      fallbackDefaults.api.ollama_url = defaults.ollamaUrl || '';
    }

    // Start with fallback defaults
    this.config = { ...fallbackDefaults };

    // Load from external config file (from backend)
    await this.loadExternalConfig();

    // Apply environment variables (override external config)
    this.loadEnvironmentConfig();

    // Apply runtime localStorage overrides (highest priority)
    this.loadRuntimeConfig();
  }

  /**
   * Load configuration from backend config endpoint
   */
  async loadExternalConfig() {
    try {
      const response = await apiClient.loadFrontendConfig();
      if (response && response.status === 'success' && response.config) {
        // The backend provides a complete config structure
        const backendConfig = response.config;

        // Transform backend config to match our expected structure
        const externalConfig = {
          api: {
            backend_url: API_CONFIG.BASE_URL, // Keep the bootstrap URL
            ollama_url: backendConfig.services.ollama.url,
            timeout: backendConfig.api.timeout,
            retry_attempts: backendConfig.api.retry_attempts,
            // Add all service URLs
            playwright_vnc_url: backendConfig.services.playwright.vnc_url,
            playwright_api_url: backendConfig.services.playwright.api_url,
            lmstudio_url: backendConfig.services.lmstudio.url,
          },
          defaults: backendConfig.defaults,
          ui: backendConfig.ui,
          features: backendConfig.features,
          services: backendConfig.services, // Keep full service config for reference
        };

        this.config = this.mergeDeep(this.config, externalConfig);
        logger.info('Loaded dynamic configuration from backend:', externalConfig);
      }
    } catch (error) {
      logger.warn('Could not load external configuration from backend:', error.message);
      // Continue with current config - this is not a fatal error
    }
  }

  /**
   * Load configuration from environment variables
   */
  loadEnvironmentConfig() {
    const envConfig = {
      api: {
        backend_url: process.env.VUE_APP_BACKEND_URL,
        ollama_url: process.env.VUE_APP_OLLAMA_URL,
        timeout: process.env.VUE_APP_API_TIMEOUT ? parseInt(process.env.VUE_APP_API_TIMEOUT) : undefined,
        retry_attempts: process.env.VUE_APP_RETRY_ATTEMPTS ? parseInt(process.env.VUE_APP_RETRY_ATTEMPTS) : undefined
      },
      paths: {
        data_directory: process.env.VUE_APP_DATA_DIR,
        config_directory: process.env.VUE_APP_CONFIG_DIR,
        chat_history_file: process.env.VUE_APP_CHAT_HISTORY_FILE,
        knowledge_base_file: process.env.VUE_APP_KB_FILE
      },
      defaults: {
        welcome_message: process.env.VUE_APP_WELCOME_MESSAGE,
        model_name: process.env.VUE_APP_DEFAULT_MODEL,
        max_chat_messages: process.env.VUE_APP_MAX_CHAT_MESSAGES ? parseInt(process.env.VUE_APP_MAX_CHAT_MESSAGES) : undefined,
        connection_check_interval: process.env.VUE_APP_CONNECTION_CHECK_INTERVAL ? parseInt(process.env.VUE_APP_CONNECTION_CHECK_INTERVAL) : undefined
      },
      ui: {
        theme: process.env.VUE_APP_DEFAULT_THEME,
        font_size: process.env.VUE_APP_DEFAULT_FONT_SIZE,
        sidebar_width: process.env.VUE_APP_SIDEBAR_WIDTH,
        auto_scroll: process.env.VUE_APP_AUTO_SCROLL ? process.env.VUE_APP_AUTO_SCROLL !== 'false' : undefined
      },
      features: {
        streaming_enabled: process.env.VUE_APP_STREAMING_ENABLED ? process.env.VUE_APP_STREAMING_ENABLED !== 'false' : undefined,
        debug_mode: process.env.VUE_APP_DEBUG_MODE ? process.env.VUE_APP_DEBUG_MODE === 'true' : undefined,
        voice_enabled: process.env.VUE_APP_VOICE_ENABLED ? process.env.VUE_APP_VOICE_ENABLED === 'true' : undefined,
        knowledge_base_enabled: process.env.VUE_APP_KB_ENABLED ? process.env.VUE_APP_KB_ENABLED !== 'false' : undefined
      }
    };

    // Only merge defined environment variables (filter out undefined values)
    const definedEnvConfig = this.filterUndefined(envConfig);
    this.config = this.mergeDeep(this.config, definedEnvConfig);
  }

  /**
   * Filter out undefined values from nested object
   */
  filterUndefined(obj) {
    const filtered = {};

    for (const key in obj) {
      if (obj[key] && typeof obj[key] === 'object' && !Array.isArray(obj[key])) {
        const nested = this.filterUndefined(obj[key]);
        if (Object.keys(nested).length > 0) {
          filtered[key] = nested;
        }
      } else if (obj[key] !== undefined) {
        filtered[key] = obj[key];
      }
    }

    return filtered;
  }

  /**
   * Load runtime configuration from localStorage or API
   */
  loadRuntimeConfig() {
    try {
      const runtimeConfig = localStorage.getItem('app_config');
      if (runtimeConfig) {
        const parsed = JSON.parse(runtimeConfig);
        this.config = this.mergeDeep(this.config, parsed);
      }
    } catch (error) {
      logger.error('Error loading runtime configuration:', error);
    }
  }

  /**
   * Save runtime configuration
   */
  saveRuntimeConfig() {
    try {
      localStorage.setItem('app_config', JSON.stringify(this.config));
    } catch (error) {
      logger.error('Error saving runtime configuration:', error);
    }
  }

  /**
   * Get configuration value by path
   */
  get(path, defaultValue = null) {
    return this.getNestedProperty(this.config, path) ?? defaultValue;
  }

  /**
   * Set configuration value by path
   */
  set(path, value) {
    this.setNestedProperty(this.config, path, value);
    this.saveRuntimeConfig();
  }

  /**
   * Get API configuration
   */
  getApiConfig() {
    return { ...this.config.api };
  }

  /**
   * Get backend URL with optional path
   */
  getBackendUrl(path = '') {
    const baseUrl = this.config.api.backend_url.replace(/\/$/, '');
    const cleanPath = path.replace(/^\//, '');
    return cleanPath ? `${baseUrl}/${cleanPath}` : baseUrl;
  }

  /**
   * Get Ollama URL with optional path
   */
  getOllamaUrl(path = '') {
    const baseUrl = this.config.api.ollama_url.replace(/\/$/, '');
    const cleanPath = path.replace(/^\//, '');
    return cleanPath ? `${baseUrl}/${cleanPath}` : baseUrl;
  }

  /**
   * Get file paths configuration
   */
  getPaths() {
    return { ...this.config.paths };
  }

  /**
   * Get default values
   */
  getDefaults() {
    return { ...this.config.defaults };
  }

  /**
   * Get UI configuration
   */
  getUIConfig() {
    return { ...this.config.ui };
  }

  /**
   * Get feature flags
   */
  getFeatures() {
    return { ...this.config.features };
  }

  /**
   * Check if feature is enabled
   */
  isFeatureEnabled(featureName) {
    return this.config.features[featureName] === true;
  }

  /**
   * Deep merge objects
   */
  mergeDeep(target, source) {
    const result = { ...target };

    for (const key in source) {
      if (source[key] && typeof source[key] === 'object' && !Array.isArray(source[key])) {
        result[key] = this.mergeDeep(target[key] || {}, source[key]);
      } else {
        result[key] = source[key];
      }
    }

    return result;
  }

  /**
   * Get nested property using dot notation
   */
  getNestedProperty(obj, path) {
    return path.split('.').reduce((current, key) => current?.[key], obj);
  }

  /**
   * Set nested property using dot notation
   */
  setNestedProperty(obj, path, value) {
    const keys = path.split('.');
    let current = obj;

    for (let i = 0; i < keys.length - 1; i++) {
      if (!(keys[i] in current)) {
        current[keys[i]] = {};
      }
      current = current[keys[i]];
    }

    current[keys[keys.length - 1]] = value;
  }

  /**
   * Reset configuration to defaults
   */
  resetToDefaults() {
    localStorage.removeItem('app_config');
    this.loadRuntimeConfig();
  }
}

// Export singleton instance
export const configService = new ConfigService();
export default configService;
