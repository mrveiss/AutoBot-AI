/**
 * Centralized Settings Service
 *
 * Eliminates duplication between ChatInterface.vue and SettingsPanel.vue
 * by providing a single source of truth for all application settings.
 */

import apiClient from '@/utils/ApiClient';
import { reactive } from 'vue';
import appConfig from '@/config/AppConfig.js';
import cacheService from './CacheService.js';
import { createLogger } from '@/utils/debugUtils';

// Create scoped logger for SettingsService
const logger = createLogger('SettingsService');

export class SettingsService {
  constructor() {
    // Default settings structure
    this.defaultSettings = {
      message_display: {
        show_thoughts: true,
        show_json: false,
        show_utility: false,
        show_planning: true,
        show_debug: false,
        show_sources: true
      },
      chat: {
        auto_scroll: true,
        max_messages: 100,
        default_welcome_message: "Hello! How can I assist you today?"
      },
      backend: {
        use_phi2: false,
        api_endpoint: '', // Will be loaded async
        ollama_endpoint: '', // Will be loaded async
        ollama_model: import.meta.env.VITE_DEFAULT_MODEL || '',  // Loaded from backend config
        streaming: false
      },
      ui: {
        theme: 'light',
        font_size: 'medium'
      }
    };

    this.settings = reactive({ ...this.defaultSettings });
    this.initialized = false;
    this.loadSettings();
  }

  /**
   * Load settings from localStorage and backend with fallback to defaults
   */
  async loadSettings() {
    try {
      // Load dynamic URLs from AppConfig
      try {
        const backendUrl = await appConfig.getApiUrl('');
        const ollamaUrl = await appConfig.getServiceUrl('ollama');
        this.defaultSettings.backend.api_endpoint = backendUrl.replace(/\/$/, '');
        this.defaultSettings.backend.ollama_endpoint = ollamaUrl;
      } catch (_configError) {
        logger.warn('AppConfig loading failed, using appConfig defaults');
        // Use appConfig defaults instead of hardcoded IPs
        const defaults = appConfig.get('defaults', {});
        this.defaultSettings.backend.api_endpoint = defaults.backendUrl || '';
        this.defaultSettings.backend.ollama_endpoint = defaults.ollamaUrl || '';
      }

      // First, try to load from localStorage for immediate UI update
      const savedSettings = localStorage.getItem('chat_settings');
      if (savedSettings) {
        const parsed = JSON.parse(savedSettings);
        // Merge with defaults to ensure all properties exist
        const mergedSettings = this.mergeDeep(this.defaultSettings, parsed);
        Object.assign(this.settings, mergedSettings);
      }

      // Then, try to fetch latest settings from backend and merge
      try {
        // Check cache first
        const cacheKey = cacheService.createKey('/api/settings');
        let backendSettings = cacheService.get(cacheKey);

        if (!backendSettings) {
          backendSettings = await apiClient.getSettings();
          if (backendSettings) {
            // Cache the settings
            cacheService.set(cacheKey, backendSettings);
          }
        }

        if (backendSettings) {
          // Merge backend settings with current settings
          const finalSettings = this.mergeDeep(this.settings, backendSettings);
          Object.assign(this.settings, finalSettings);

          // Save the merged settings back to localStorage
          localStorage.setItem('chat_settings', JSON.stringify(this.settings));
        }
      } catch (backendError) {
        logger.warn('Could not load settings from backend, using localStorage/defaults:', backendError.message);
      }

      this.initialized = true;
    } catch (error) {
      logger.error('Error loading settings:', error);
      Object.assign(this.settings, this.defaultSettings);
      this.initialized = true;
    }
  }

  /**
   * Save settings to localStorage and backend
   */
  async saveSettings() {
    try {
      // Save to localStorage first for immediate persistence
      localStorage.setItem('chat_settings', JSON.stringify(this.settings));

      // Save to backend for server-side persistence
      await apiClient.saveSettings(this.settings);

      // Invalidate cache since settings changed
      cacheService.invalidateCategory('settings');
    } catch (error) {
      logger.error('Error saving settings:', error);
      // Even if backend save fails, localStorage save should work
      // so settings persist across page reloads locally
      throw error;
    }
  }

  /**
   * Save settings to localStorage only (for deep watchers)
   */
  saveSettingsToLocalStorage(settings) {
    try {
      localStorage.setItem('chat_settings', JSON.stringify(settings));
    } catch (error) {
      logger.error('Error saving settings to localStorage:', error);
    }
  }

  /**
   * Save backend-specific settings
   */
  async saveBackendSettings() {
    try {
      await apiClient.saveBackendSettings(this.settings.backend);
    } catch (error) {
      logger.error('Error saving backend settings:', error);
      throw error;
    }
  }

  /**
   * Fetch and merge backend settings
   */
  async fetchBackendSettings() {
    try {
      const backendSettings = await apiClient.getBackendSettings();
      Object.assign(this.settings.backend, backendSettings);
      await this.saveSettings(); // Persist the merged settings
    } catch (error) {
      logger.error('Error loading backend settings:', error);
      throw error;
    }
  }

  /**
   * Get current settings (reactive reference)
   * Ensures settings are loaded before returning
   */
  async getSettings() {
    if (!this.initialized) {
      await this.loadSettings();
    }
    return this.settings; // Return direct reactive reference
  }

  /**
   * Get settings synchronously (for compatibility)
   * Use this only when you're sure settings are already loaded
   */
  getSettingsSync() {
    return this.settings;
  }

  /**
   * Update specific setting
   */
  async updateSetting(path, value) {
    this.setNestedProperty(this.settings, path, value);
    await this.saveSettings();
  }

  /**
   * Reset settings to defaults
   */
  async resetToDefaults() {
    this.settings = { ...this.defaultSettings };
    await this.saveSettings();
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
   * Get nested property using dot notation
   */
  getNestedProperty(obj, path) {
    return path.split('.').reduce((current, key) => current?.[key], obj);
  }

  /**
   * Get developer mode configuration
   * @returns {Promise<Object>} Developer config
   */
  async getDeveloperConfig() {
    try {
      const response = await apiClient.get('/api/developer/config');
      return response.data || {};
    } catch (error) {
      logger.error('Failed to get developer config:', error);
      return {
        enabled: false,
        enhanced_errors: true,
        endpoint_suggestions: true,
        debug_logging: false
      };
    }
  }

  /**
   * Update developer mode configuration
   * @param {Object} config - Developer config to save
   * @returns {Promise<boolean>} Success status
   */
  async updateDeveloperConfig(config) {
    try {
      await apiClient.post('/api/developer/config', config);
      return true;
    } catch (error) {
      logger.error('Failed to update developer config:', error);
      return false;
    }
  }

  /**
   * Get all available API endpoints (developer mode)
   * @returns {Promise<Object>} API endpoints registry
   */
  async getApiEndpoints() {
    try {
      const response = await apiClient.get('/api/developer/endpoints');
      return response.data || {};
    } catch (error) {
      logger.error('Failed to get API endpoints:', error);
      return {};
    }
  }

  /**
   * Get system information for debugging (developer mode)
   * @returns {Promise<Object>} System info
   */
  async getSystemInfo() {
    try {
      const response = await apiClient.get('/api/developer/system-info');
      return response.data || {};
    } catch (error) {
      logger.error('Failed to get system info:', error);
      return {};
    }
  }
}

// Export singleton instance
export const settingsService = new SettingsService();
export default settingsService;
