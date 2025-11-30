import apiClient from '../utils/ApiClient.js';
import { createLogger } from '@/utils/debugUtils';

// Create scoped logger for HealthService
const logger = createLogger('HealthService');

class HealthService {
  constructor() {
    this.healthData = {
      backend: { connected: false, status: 'disconnected', message: 'Not checked' },
      llm: { connected: false, status: 'disconnected', message: 'Not checked', current_model: null },
      redis: { connected: false, status: 'disconnected', message: 'Not checked' }
    };
    this.listeners = [];
    this.checkInterval = null;
  }

  // Subscribe to health status changes
  subscribe(callback) {
    this.listeners.push(callback);
    // Immediately notify with current state
    callback(this.healthData);
    return () => {
      this.listeners = this.listeners.filter(listener => listener !== callback);
    };
  }

  // Notify all listeners of health status changes
  notifyListeners() {
    this.listeners.forEach(callback => callback(this.healthData));
  }

  // Check all system health
  async checkHealth() {
    try {
      const data = await apiClient.checkHealth();

      // Backend status
      this.healthData.backend = {
        connected: true,
        status: 'connected',
        message: 'Backend server is responding'
      };

      // LLM status
      if (data.ollama === 'connected') {
        // Get current LLM info from health response details
        const currentModel = data.details?.ollama?.model || 'Unknown';
        this.healthData.llm = {
          connected: true,
          status: 'connected',
          message: 'LLM service is available',
          current_model: currentModel,
          provider: 'ollama'
        };
      } else {
        this.healthData.llm = {
          connected: false,
          status: 'disconnected',
          message: 'LLM service not available',
          current_model: null,
          provider: null
        };
      }

      // Redis status
      if (data.redis_status === 'connected') {
        this.healthData.redis = {
          connected: true,
          status: 'connected',
          message: data.redis_search_module_loaded ?
            'Redis with RediSearch available' :
            'Redis connected but RediSearch not loaded',
          search_module: data.redis_search_module_loaded
        };
      } else {
        this.healthData.redis = {
          connected: false,
          status: 'disconnected',
          message: 'Redis service not available',
          search_module: false
        };
      }

      this.notifyListeners();
      return this.healthData;

    } catch (error) {
      // Backend is down
      this.healthData.backend = {
        connected: false,
        status: 'disconnected',
        message: `Backend connection failed: ${error.message}`
      };

      this.healthData.llm = {
        connected: false,
        status: 'disconnected',
        message: 'LLM status unknown (backend disconnected)',
        current_model: null,
        provider: null
      };

      this.healthData.redis = {
        connected: false,
        status: 'disconnected',
        message: 'Redis status unknown (backend disconnected)',
        search_module: false
      };

      this.notifyListeners();
      throw error;
    }
  }

  // Get current LLM display string
  getCurrentLLMDisplay() {
    if (!this.healthData.llm.connected) {
      return 'Disconnected';
    }
    if (this.healthData.llm.current_model) {
      const provider = this.healthData.llm.provider || 'Unknown';
      return `${provider ? provider.charAt(0).toUpperCase() + provider.slice(1) : 'Unknown'} - ${this.healthData.llm.current_model}`;
    }
    return 'Connected (No Model)';
  }

  // Start periodic health checking
  startMonitoring(interval = 10000) {
    if (this.checkInterval) {
      clearInterval(this.checkInterval);
    }

    // Initial check
    this.checkHealth().catch(err => logger.error('Health check failed:', err));

    // Periodic checks
    this.checkInterval = setInterval(() => {
      this.checkHealth().catch(err => logger.error('Health check failed:', err));
    }, interval);
  }

  // Stop periodic health checking
  stopMonitoring() {
    if (this.checkInterval) {
      clearInterval(this.checkInterval);
      this.checkInterval = null;
    }
  }

  // Get current health status (synchronous)
  getHealthStatus() {
    return { ...this.healthData };
  }
}

// Export singleton instance
export const healthService = new HealthService();
export default healthService;
