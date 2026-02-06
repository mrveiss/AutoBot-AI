/**
 * OptimizedServiceIntegration - Enhanced API Service Layer
 *
 * Provides optimized frontend-backend integration with:
 * - Intelligent backend fallback and discovery
 * - Performance monitoring and optimization
 * - Real-time connection status tracking
 * - Enhanced error handling and recovery
 */

import backendFallback from './BackendFallback.js';
import { createLogger } from '@/utils/debugUtils';

const logger = createLogger('OptimizedServiceIntegration');

export class OptimizedServiceIntegration {
  constructor() {
    this.performanceMetrics = {
      requests: 0,
      totalTime: 0,
      errors: 0,
      slowRequests: 0
    };

    this.connectionStatus = 'initializing';
    this.statusListeners = [];

    // Performance thresholds
    this.slowRequestThreshold = 2000; // 2 seconds
    this.errorRateThreshold = 0.1; // 10%

    this.log('OptimizedServiceIntegration initialized');
    this.setupConnectionMonitoring();
  }

  /**
   * Setup connection monitoring
   */
  setupConnectionMonitoring() {
    backendFallback.addConnectionListener((status) => {
      this.connectionStatus = status.status;
      this.notifyStatusChange(status);

      if (status.status === 'connected') {
        this.log(`🔗 Backend connected: ${status.backendUrl}`);
      } else if (status.mockMode) {
        this.log('🎭 Running in mock mode - backend unavailable');
      }
    });
  }

  /**
   * Enhanced API request with performance monitoring
   */
  async request(endpoint, options = {}) {
    const startTime = performance.now();
    const requestId = `req_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;

    this.log(`🚀 Request ${requestId}: ${options.method || 'GET'} ${endpoint}`);

    try {
      // Use backend fallback service
      const response = await backendFallback.fetchWithFallback(endpoint, {
        ...options,
        headers: {
          'X-Request-ID': requestId,
          'X-Frontend-Timestamp': Date.now().toString(),
          ...options.headers
        }
      });

      const endTime = performance.now();
      const duration = endTime - startTime;

      // Update performance metrics
      this.updatePerformanceMetrics(duration, response.ok);

      const isMockResponse = response.headers.get('X-Mock-Mode') === 'true';

      this.log(`✅ Response ${requestId}: ${response.status} (${duration.toFixed(2)}ms)${isMockResponse ? ' [MOCK]' : ''}`);

      return response;
    } catch (error) {
      const endTime = performance.now();
      const duration = endTime - startTime;

      this.updatePerformanceMetrics(duration, false);
      this.log(`❌ Request ${requestId} failed after ${duration.toFixed(2)}ms:`, error.message);

      throw error;
    }
  }

  /**
   * Optimized GET request
   */
  async get(endpoint, options = {}) {
    return this.request(endpoint, { ...options, method: 'GET' });
  }

  /**
   * Optimized POST request
   */
  async post(endpoint, data, options = {}) {
    return this.request(endpoint, {
      ...options,
      method: 'POST',
      body: JSON.stringify(data),
      headers: {
        'Content-Type': 'application/json',
        ...options.headers
      }
    });
  }

  /**
   * Optimized PUT request
   */
  async put(endpoint, data, options = {}) {
    return this.request(endpoint, {
      ...options,
      method: 'PUT',
      body: JSON.stringify(data),
      headers: {
        'Content-Type': 'application/json',
        ...options.headers
      }
    });
  }

  /**
   * Optimized DELETE request
   */
  async delete(endpoint, options = {}) {
    return this.request(endpoint, { ...options, method: 'DELETE' });
  }

  /**
   * Enhanced JSON response handling
   */
  async getJson(endpoint, options = {}) {
    const response = await this.get(endpoint, options);

    if (!response.ok) {
      const errorText = await response.text().catch(() => 'Unknown error');
      throw new Error(`HTTP ${response.status}: ${errorText}`);
    }

    const contentType = response.headers.get('content-type');
    if (!contentType || !contentType.includes('application/json')) {
      throw new Error('Response is not JSON');
    }

    return await response.json();
  }

  /**
   * Enhanced POST JSON request
   */
  async postJson(endpoint, data, options = {}) {
    const response = await this.post(endpoint, data, options);

    if (!response.ok) {
      const errorText = await response.text().catch(() => 'Unknown error');
      throw new Error(`HTTP ${response.status}: ${errorText}`);
    }

    // Handle empty responses
    const contentLength = response.headers.get('content-length');
    if (contentLength === '0' || response.status === 204) {
      return null;
    }

    const contentType = response.headers.get('content-type');
    if (contentType && contentType.includes('application/json')) {
      return await response.json();
    }

    return null;
  }

  /**
   * WebSocket connection with fallback
   */
  createWebSocket(endpoint = '', protocols = []) {
    const wsUrl = backendFallback.getWebSocketUrl();
    const fullUrl = endpoint ? `${wsUrl}${endpoint}` : wsUrl;

    this.log(`🔌 Creating WebSocket connection: ${fullUrl}`);

    if (fullUrl.includes('mock-websocket')) {
      // Return mock WebSocket for development
      return this.createMockWebSocket();
    }

    try {
      const ws = new WebSocket(fullUrl, protocols);

      ws.addEventListener('open', () => {
        this.log('🔌 WebSocket connected');
      });

      ws.addEventListener('close', (event) => {
        this.log(`🔌 WebSocket closed: ${event.code} ${event.reason}`);
      });

      ws.addEventListener('error', (error) => {
        this.log('🔌 WebSocket error:', error);
      });

      return ws;
    } catch (error) {
      this.log('🔌 WebSocket creation failed:', error);
      return this.createMockWebSocket();
    }
  }

  /**
   * Create mock WebSocket for development
   */
  createMockWebSocket() {
    this.log('🎭 Creating mock WebSocket for development mode');

    return {
      readyState: WebSocket.CONNECTING,
      send: (data) => {
        this.log('🎭 Mock WebSocket send:', data);
      },
      close: () => {
        this.readyState = WebSocket.CLOSED;
        this.log('🎭 Mock WebSocket closed');
      },
      addEventListener: (type, listener) => {
        if (type === 'open') {
          setTimeout(() => {
            this.readyState = WebSocket.OPEN;
            listener(new Event('open'));
          }, 100);
        }
      },
      removeEventListener: () => {},
      CONNECTING: WebSocket.CONNECTING,
      OPEN: WebSocket.OPEN,
      CLOSING: WebSocket.CLOSING,
      CLOSED: WebSocket.CLOSED
    };
  }

  /**
   * Batch requests for improved performance
   */
  async batchRequests(requests) {
    this.log(`📦 Executing batch of ${requests.length} requests`);

    const promises = requests.map(async ({ endpoint, options, id }) => {
      try {
        const response = await this.request(endpoint, options);
        return { id, response, error: null };
      } catch (error) {
        return { id, response: null, error };
      }
    });

    const results = await Promise.all(promises);
    this.log(`📦 Batch completed: ${results.filter(r => !r.error).length}/${results.length} succeeded`);

    return results;
  }

  /**
   * Health check with performance metrics
   */
  async healthCheck() {
    const startTime = performance.now();

    try {
      const response = await this.get('/api/health', { timeout: 5000 });
      const endTime = performance.now();
      const duration = endTime - startTime;

      const isHealthy = response.ok;
      const isMock = response.headers.get('X-Mock-Mode') === 'true';

      return {
        healthy: isHealthy,
        responseTime: duration,
        mock: isMock,
        status: response.status,
        backend: backendFallback.currentBackend
      };
    } catch (error) {
      const endTime = performance.now();
      const duration = endTime - startTime;

      return {
        healthy: false,
        responseTime: duration,
        mock: false,
        error: error.message,
        backend: null
      };
    }
  }

  /**
   * Update performance metrics
   */
  updatePerformanceMetrics(duration, success) {
    this.performanceMetrics.requests++;
    this.performanceMetrics.totalTime += duration;

    if (!success) {
      this.performanceMetrics.errors++;
    }

    if (duration > this.slowRequestThreshold) {
      this.performanceMetrics.slowRequests++;
    }
  }

  /**
   * Get performance statistics
   */
  getPerformanceStats() {
    const metrics = this.performanceMetrics;
    const avgResponseTime = metrics.requests > 0 ? metrics.totalTime / metrics.requests : 0;
    const errorRate = metrics.requests > 0 ? metrics.errors / metrics.requests : 0;
    const slowRequestRate = metrics.requests > 0 ? metrics.slowRequests / metrics.requests : 0;

    return {
      requests: metrics.requests,
      averageResponseTime: avgResponseTime,
      errorRate: errorRate,
      slowRequestRate: slowRequestRate,
      connectionStatus: this.connectionStatus,
      backend: backendFallback.currentBackend,
      mockMode: backendFallback.mockMode
    };
  }

  /**
   * Force backend reconnection
   */
  async forceReconnect() {
    this.log('🔄 Forcing backend reconnection...');
    await backendFallback.forceReconnect();
  }

  /**
   * Add status change listener
   */
  addStatusListener(listener) {
    this.statusListeners.push(listener);
  }

  /**
   * Remove status change listener
   */
  removeStatusListener(listener) {
    const index = this.statusListeners.indexOf(listener);
    if (index > -1) {
      this.statusListeners.splice(index, 1);
    }
  }

  /**
   * Notify status change listeners
   */
  notifyStatusChange(status) {
    this.statusListeners.forEach(listener => {
      try {
        listener(status);
      } catch (error) {
        this.log('Error notifying status listener:', error);
      }
    });
  }

  /**
   * Get connection status
   */
  getConnectionStatus() {
    return {
      status: this.connectionStatus,
      ...backendFallback.getConnectionStatus()
    };
  }

  /**
   * Debug logging
   */
  log(...args) {
    if (import.meta.env.DEV || import.meta.env.VITE_ENABLE_DEBUG === 'true') {
      logger.debug('[OptimizedServiceIntegration]', ...args);
    }
  }

  /**
   * Clean up resources
   */
  destroy() {
    this.statusListeners = [];
    backendFallback.destroy();
  }
}

// Singleton instance
const serviceIntegration = new OptimizedServiceIntegration();

export default serviceIntegration;
