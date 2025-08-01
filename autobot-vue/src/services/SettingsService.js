/**
 * Centralized Settings Service
 * 
 * Eliminates duplication between ChatInterface.vue and SettingsPanel.vue
 * by providing a single source of truth for all application settings.
 */

import apiClient from '@/utils/ApiClient.js';

export class SettingsService {
  constructor() {
    // Default settings structure
    this.defaultSettings = {
      message_display: {
        show_thoughts: true,
        show_json: false,
        show_utility: false,
        show_planning: true,
        show_debug: false
      },
      chat: {
        auto_scroll: true,
        max_messages: 100,
        default_welcome_message: "Hello! How can I assist you today?"
      },
      backend: {
        use_phi2: false,
        api_endpoint: 'http://localhost:8001',
        ollama_endpoint: 'http://localhost:11434',
        ollama_model: 'tinyllama:latest',
        streaming: false
      },
      ui: {
        theme: 'light',
        font_size: 'medium'
      }
    };
    
    this.settings = { ...this.defaultSettings };
    this.loadSettings();
  }

  /**
   * Load settings from localStorage with fallback to defaults
   */
  loadSettings() {
    try {
      const savedSettings = localStorage.getItem('chat_settings');
      if (savedSettings) {
        const parsed = JSON.parse(savedSettings);
        // Merge with defaults to ensure all properties exist
        this.settings = this.mergeDeep(this.defaultSettings, parsed);
      }
    } catch (error) {
      console.error('Error loading settings from localStorage:', error);
      this.settings = { ...this.defaultSettings };
    }
  }

  /**
   * Save settings to localStorage and backend
   */
  async saveSettings() {
    try {
      // Save to localStorage
      localStorage.setItem('chat_settings', JSON.stringify(this.settings));
      
      // Save to backend
      await apiClient.saveSettings(this.settings);
      console.log('Settings saved successfully');
    } catch (error) {
      console.error('Error saving settings:', error);
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
      console.error('Error saving settings to localStorage:', error);
    }
  }

  /**
   * Save backend-specific settings
   */
  async saveBackendSettings() {
    try {
      await apiClient.saveBackendSettings(this.settings.backend);
      console.log('Backend settings saved successfully');
    } catch (error) {
      console.error('Error saving backend settings:', error);
      throw error;
    }
  }

  /**
   * Fetch and merge backend settings
   */
  async fetchBackendSettings() {
    try {
      const backendSettings = await apiClient.getBackendSettings();
      this.settings.backend = { ...this.settings.backend, ...backendSettings };
      await this.saveSettings(); // Persist the merged settings
      console.log('Backend settings loaded and merged successfully');
    } catch (error) {
      console.error('Error loading backend settings:', error);
      throw error;
    }
  }

  /**
   * Get current settings (reactive copy)
   */
  getSettings() {
    return { ...this.settings };
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
      console.error('Failed to get developer config:', error);
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
      console.log('Developer config updated successfully');
      return true;
    } catch (error) {
      console.error('Failed to update developer config:', error);
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
      console.error('Failed to get API endpoints:', error);
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
      console.error('Failed to get system info:', error);
      return {};
    }
  }
}

// Export singleton instance
export const settingsService = new SettingsService();
export default settingsService;
