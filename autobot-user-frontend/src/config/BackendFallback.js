/**
 * BackendFallbackService - Intelligent Backend Connection Management
 *
 * Provides smart backend connection handling with proper error states:
 * - Automatic backend discovery and health checking
 * - Clear error states when backend unavailable (no mock data)
 * - Graceful degradation with user-visible error messages
 * - Real-time connection recovery with automatic retry
 */

import { NetworkConstants } from '../constants/network';
import { createLogger } from '@/utils/debugUtils';

const logger = createLogger('BackendFallback');

export class BackendFallbackService {
  constructor() {
    // SINGLE FRONTEND SERVER ARCHITECTURE:
    // Frontend VM connects to Backend VM using centralized constants
    this.backendHosts = [
      `${NetworkConstants.MAIN_MACHINE_IP}:${NetworkConstants.BACKEND_PORT}`,  // Primary: Backend VM
      `${NetworkConstants.LOCALHOST_NAME}:${NetworkConstants.BACKEND_PORT}`,   // Fallback: Local development
      `${NetworkConstants.LOCALHOST_IP}:${NetworkConstants.BACKEND_PORT}`      // Final fallback
    ];

    this.currentBackend = null;
    this.connectionStatus = 'checking';
    this.lastHealthCheck = 0;
    this.healthCheckInterval = 30000; // 30 seconds
    this.connectionListeners = [];
    this.retryAttempts = 0;
    this.maxRetryAttempts = 3;
    this.retryDelay = 5000; // 5 seconds between retries

    this.log('BackendFallbackService initialized');
    this.startBackendDiscovery();
  }

  /**
   * Start automatic backend discovery
   */
  async startBackendDiscovery() {
    this.log('Starting backend discovery...');
    this.connectionStatus = 'checking';
    this.notifyConnectionChange('checking', null);

    for (const host of this.backendHosts) {
      const protocol = window.location.protocol === 'https:' ? 'https' : 'http';
      const backendUrl = `${protocol}://${host}`;

      try {
        this.log(`Testing backend: ${backendUrl}`);
        const isHealthy = await this.checkBackendHealth(backendUrl);

        if (isHealthy) {
          this.currentBackend = backendUrl;
          this.connectionStatus = 'connected';
          this.retryAttempts = 0; // Reset retry counter on success
          this.log(`✅ Connected to backend: ${backendUrl}`);
          this.notifyConnectionChange('connected', backendUrl);
          this.startHealthMonitoring();
          return;
        }
      } catch (error) {
        this.log(`❌ Failed to connect to ${backendUrl}:`, error.message);
      }
    }

    // No backend available - show error state (NOT mock data)
    this.handleBackendUnavailable();
  }

  /**
   * Handle backend unavailable state with proper error UI
   * NO mock data - show clear error to user
   */
  handleBackendUnavailable() {
    this.log('❌ No backend available - showing error state');
    this.connectionStatus = 'disconnected';
    this.currentBackend = null;
    this.retryAttempts++;
    this.notifyConnectionChange('disconnected', null);

    // Show user notification about backend being unavailable
    this.showBackendUnavailableNotification();

    // Schedule retry if under max attempts
    if (this.retryAttempts < this.maxRetryAttempts) {
      const delay = this.retryDelay * Math.min(this.retryAttempts, 3); // Exponential backoff up to 3x
      this.log(`🔄 Scheduling retry ${this.retryAttempts}/${this.maxRetryAttempts} in ${delay/1000}s`);
      setTimeout(() => this.startBackendDiscovery(), delay);
    } else {
      this.log('❌ Max retry attempts reached. Manual reconnect required.');
      this.showMaxRetriesNotification();
    }
  }

  /**
   * Check backend health
   */
  async checkBackendHealth(backendUrl, timeout = 5000) {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), timeout);

    try {
      const response = await fetch(`${backendUrl}/api/health`, {
        method: 'GET',
        signal: controller.signal,
        headers: {
          'Cache-Control': 'no-cache',
          'X-Health-Check': Date.now().toString()
        }
      });

      clearTimeout(timeoutId);
      return response.ok;
    } catch (_error) {
      clearTimeout(timeoutId);
      return false;
    }
  }

  /**
   * Start health monitoring for connected backend
   */
  startHealthMonitoring() {
    if (this.healthMonitorInterval) {
      clearInterval(this.healthMonitorInterval);
    }

    this.healthMonitorInterval = setInterval(async () => {
      if (this.currentBackend) {
        const isHealthy = await this.checkBackendHealth(this.currentBackend);
        this.lastHealthCheck = Date.now();

        if (!isHealthy && this.connectionStatus === 'connected') {
          this.log('❌ Backend health check failed - attempting reconnection');
          this.retryAttempts = 0; // Reset for new reconnection attempt
          this.startBackendDiscovery();
        }
      }
    }, this.healthCheckInterval);
  }

  /**
   * Enhanced fetch with proper error handling (no mock fallback)
   */
  async fetchWithFallback(endpoint, options = {}) {
    // If no backend available, throw a proper error
    if (!this.currentBackend) {
      const error = new Error('Backend unavailable');
      error.code = 'BACKEND_UNAVAILABLE';
      error.isConnectionError = true;
      throw error;
    }

    const url = `${this.currentBackend}${endpoint}`;
    const fetchOptions = {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        'X-Frontend-Version': '1.0.0',
        ...options.headers
      }
    };

    try {
      this.log(`🌐 API Request: ${options.method || 'GET'} ${url}`);
      const response = await fetch(url, fetchOptions);

      if (response.ok) {
        this.log(`✅ API Response: ${response.status}`);
        return response;
      } else {
        this.log(`⚠️ API Response: ${response.status} ${response.statusText}`);
        return response; // Let caller handle non-200 responses
      }
    } catch (error) {
      this.log(`❌ API Request failed:`, error.message);

      // If network error, trigger reconnection attempt
      if (error.message.includes('Failed to fetch') || error.name === 'AbortError') {
        this.log('🔄 Network error detected - attempting backend rediscovery');
        this.retryAttempts = 0;
        setTimeout(() => this.startBackendDiscovery(), 1000);

        // Throw a clear error instead of returning mock data
        const connectionError = new Error('Backend connection lost. Attempting to reconnect...');
        connectionError.code = 'CONNECTION_LOST';
        connectionError.isConnectionError = true;
        connectionError.originalError = error;
        throw connectionError;
      }

      throw error;
    }
  }

  /**
   * Get WebSocket URL - returns null if backend unavailable
   */
  getWebSocketUrl() {
    if (!this.currentBackend) {
      // Return null when backend unavailable - caller should handle this
      return null;
    }

    const wsProtocol = this.currentBackend.startsWith('https') ? 'wss' : 'ws';
    const wsUrl = this.currentBackend.replace(/^https?/, wsProtocol);
    return `${wsUrl}/ws`;
  }

  /**
   * Check if backend is currently available
   */
  isBackendAvailable() {
    return this.connectionStatus === 'connected' && this.currentBackend !== null;
  }

  /**
   * Add connection change listener
   */
  addConnectionListener(listener) {
    this.connectionListeners.push(listener);
  }

  /**
   * Remove connection change listener
   */
  removeConnectionListener(listener) {
    const index = this.connectionListeners.indexOf(listener);
    if (index > -1) {
      this.connectionListeners.splice(index, 1);
    }
  }

  /**
   * Notify listeners of connection changes
   */
  notifyConnectionChange(status, backendUrl) {
    this.connectionListeners.forEach(listener => {
      try {
        listener({
          status,
          backendUrl,
          isAvailable: status === 'connected',
          retryAttempts: this.retryAttempts,
          maxRetryAttempts: this.maxRetryAttempts
        });
      } catch (error) {
        this.log('Error notifying connection listener:', error);
      }
    });
  }

  /**
   * Show backend unavailable notification to user
   */
  showBackendUnavailableNotification() {
    // Remove any existing notification first
    this.removeExistingNotification();

    const notification = document.createElement('div');
    notification.id = 'backend-status-notification';
    notification.className = 'fixed top-4 right-4 bg-red-600 text-white px-4 py-3 rounded-lg shadow-lg z-50 max-w-md';
    notification.innerHTML = `
      <div class="flex items-start">
        <svg class="w-6 h-6 mr-3 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
          <path fill-rule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7 4a1 1 0 11-2 0 1 1 0 012 0zm-1-9a1 1 0 00-1 1v4a1 1 0 102 0V6a1 1 0 00-1-1z" clip-rule="evenodd"></path>
        </svg>
        <div class="flex-1">
          <p class="font-semibold">Backend Unavailable</p>
          <p class="text-sm opacity-90">Unable to connect to the server. Retrying... (${this.retryAttempts}/${this.maxRetryAttempts})</p>
        </div>
        <button onclick="this.parentElement.parentElement.remove()" class="ml-3 text-white hover:text-gray-200">
          <svg class="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
            <path fill-rule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clip-rule="evenodd"></path>
          </svg>
        </button>
      </div>
    `;

    document.body.appendChild(notification);
  }

  /**
   * Show max retries reached notification
   */
  showMaxRetriesNotification() {
    // Remove any existing notification first
    this.removeExistingNotification();

    const notification = document.createElement('div');
    notification.id = 'backend-status-notification';
    notification.className = 'fixed top-4 right-4 bg-red-700 text-white px-4 py-3 rounded-lg shadow-lg z-50 max-w-md';
    notification.innerHTML = `
      <div class="flex items-start">
        <svg class="w-6 h-6 mr-3 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
          <path fill-rule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7 4a1 1 0 11-2 0 1 1 0 012 0zm-1-9a1 1 0 00-1 1v4a1 1 0 102 0V6a1 1 0 00-1-1z" clip-rule="evenodd"></path>
        </svg>
        <div class="flex-1">
          <p class="font-semibold">Connection Failed</p>
          <p class="text-sm opacity-90 mb-2">Unable to connect to the backend server after multiple attempts.</p>
          <button onclick="window.backendFallback && window.backendFallback.forceReconnect()"
                  class="bg-white text-red-700 px-3 py-1 rounded text-sm font-medium hover:bg-gray-100">
            Try Again
          </button>
        </div>
        <button onclick="this.parentElement.parentElement.remove()" class="ml-3 text-white hover:text-gray-200">
          <svg class="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
            <path fill-rule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clip-rule="evenodd"></path>
          </svg>
        </button>
      </div>
    `;

    document.body.appendChild(notification);

    // Make the service available globally for the retry button
    window.backendFallback = this;
  }

  /**
   * Remove existing notification
   */
  removeExistingNotification() {
    const existing = document.getElementById('backend-status-notification');
    if (existing) {
      existing.remove();
    }
  }

  /**
   * Force backend reconnection attempt
   */
  async forceReconnect() {
    this.log('🔄 Force reconnect requested');
    this.retryAttempts = 0; // Reset retry counter
    this.removeExistingNotification();
    clearInterval(this.healthMonitorInterval);
    await this.startBackendDiscovery();
  }

  /**
   * Get current connection status
   */
  getConnectionStatus() {
    return {
      status: this.connectionStatus,
      backend: this.currentBackend,
      isAvailable: this.isBackendAvailable(),
      lastCheck: this.lastHealthCheck,
      retryAttempts: this.retryAttempts,
      maxRetryAttempts: this.maxRetryAttempts
    };
  }

  /**
   * Debug logging
   */
  log(...args) {
    if (import.meta.env.DEV || import.meta.env.VITE_ENABLE_DEBUG === 'true') {
      logger.debug('[BackendFallback]', ...args);
    }
  }

  /**
   * Clean up resources
   */
  destroy() {
    if (this.healthMonitorInterval) {
      clearInterval(this.healthMonitorInterval);
    }
    this.connectionListeners = [];
  }
}

// Singleton instance
const backendFallback = new BackendFallbackService();

export default backendFallback;
