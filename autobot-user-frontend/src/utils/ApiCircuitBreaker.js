/**
 * API Circuit Breaker - Replaces timeout-based API calls with intelligent failure handling
 * No arbitrary timeouts - immediate success/failure with smart fallback
 */

import { createLogger } from '@/utils/debugUtils';

// Create scoped logger for ApiCircuitBreaker
const logger = createLogger('CircuitBreaker');

class ApiCircuitBreaker {
  constructor(options = {}) {
    // Circuit breaker settings
    this.failureThreshold = options.failureThreshold || 3;
    this.recoveryTime = options.recoveryTime || 30000; // 30 seconds before trying again
    this.monitoringWindow = options.monitoringWindow || 60000; // 1 minute window

    // State tracking
    this.state = 'CLOSED'; // CLOSED, OPEN, HALF_OPEN
    this.failureCount = 0;
    this.lastFailureTime = null;
    this.lastSuccessTime = null;
    this.requestCount = 0;
    this.successCount = 0;

    // Performance tracking
    this.responseTimeHistory = [];
    this.maxHistorySize = 10;

    logger.info('Initialized with settings:', {
      failureThreshold: this.failureThreshold,
      recoveryTime: this.recoveryTime,
      monitoringWindow: this.monitoringWindow
    });
  }

  /**
   * Check if circuit breaker should allow request
   */
  canExecute() {
    const now = Date.now();

    switch (this.state) {
      case 'CLOSED':
        return true;

      case 'OPEN':
        // Check if recovery time has elapsed
        if (this.lastFailureTime && (now - this.lastFailureTime) >= this.recoveryTime) {
          this.state = 'HALF_OPEN';
          return true;
        }
        return false;

      case 'HALF_OPEN':
        return true;

      default:
        return true;
    }
  }

  /**
   * Record successful API call
   */
  recordSuccess(responseTime = null) {
    this.lastSuccessTime = Date.now();
    this.successCount++;
    this.requestCount++;

    if (responseTime !== null) {
      this.responseTimeHistory.push(responseTime);
      if (this.responseTimeHistory.length > this.maxHistorySize) {
        this.responseTimeHistory.shift();
      }
    }

    // Reset failure tracking on success
    if (this.state === 'HALF_OPEN') {
      this.state = 'CLOSED';
      this.failureCount = 0;
    } else if (this.state === 'CLOSED') {
      // Gradual failure count reduction on continued success
      if (this.failureCount > 0) {
        this.failureCount = Math.max(0, this.failureCount - 1);
      }
    }
  }

  /**
   * Record failed API call
   */
  recordFailure(error = null) {
    this.lastFailureTime = Date.now();
    this.failureCount++;
    this.requestCount++;

    logger.debug('Recording failure:', {
      failureCount: this.failureCount,
      threshold: this.failureThreshold,
      error: error?.message || 'Unknown error'
    });

    // Open circuit if threshold exceeded
    if (this.failureCount >= this.failureThreshold) {
      if (this.state !== 'OPEN') {
        this.state = 'OPEN';
      }
    }

    // In HALF_OPEN state, any failure immediately opens circuit
    if (this.state === 'HALF_OPEN') {
      this.state = 'OPEN';
    }
  }

  /**
   * Get current circuit breaker status
   */
  getStatus() {
    const now = Date.now();
    const _windowStart = now - this.monitoringWindow; // Available for future time-windowed metrics

    return {
      state: this.state,
      failureCount: this.failureCount,
      requestCount: this.requestCount,
      successCount: this.successCount,
      successRate: this.requestCount > 0 ? (this.successCount / this.requestCount * 100).toFixed(1) : 0,
      lastFailureTime: this.lastFailureTime,
      lastSuccessTime: this.lastSuccessTime,
      averageResponseTime: this.getAverageResponseTime(),
      canExecute: this.canExecute(),
      timeUntilRecovery: this.state === 'OPEN' && this.lastFailureTime ?
        Math.max(0, this.recoveryTime - (now - this.lastFailureTime)) : 0
    };
  }

  /**
   * Get average response time from history
   */
  getAverageResponseTime() {
    if (this.responseTimeHistory.length === 0) return 0;
    const sum = this.responseTimeHistory.reduce((a, b) => a + b, 0);
    return Math.round(sum / this.responseTimeHistory.length);
  }

  /**
   * Execute API call with circuit breaker protection
   */
  async execute(apiCall, fallbackHandler = null) {
    const startTime = Date.now();

    // Check if circuit allows execution
    if (!this.canExecute()) {
      const error = new Error('Circuit breaker is OPEN - service temporarily unavailable');
      error.name = 'CircuitBreakerError';
      error.circuitState = this.state;
      error.status = this.getStatus();

      // Try fallback if available
      if (fallbackHandler && typeof fallbackHandler === 'function') {
        try {
          return await fallbackHandler();
        } catch (fallbackError) {
          logger.error('Fallback also failed:', fallbackError);
          throw error;
        }
      }

      throw error;
    }

    try {
      // Execute the API call without timeout
      const result = await apiCall();

      // Record success with response time
      const responseTime = Date.now() - startTime;
      this.recordSuccess(responseTime);

      logger.debug('API call successful', {
        responseTime: `${responseTime}ms`,
        state: this.state
      });

      return result;

    } catch (error) {
      // Record failure
      this.recordFailure(error);

      logger.error('API call failed:', {
        error: error.message,
        state: this.state,
        failureCount: this.failureCount
      });

      throw error;
    }
  }

  /**
   * Reset circuit breaker to initial state
   */
  reset() {
    this.state = 'CLOSED';
    this.failureCount = 0;
    this.requestCount = 0;
    this.successCount = 0;
    this.lastFailureTime = null;
    this.lastSuccessTime = null;
    this.responseTimeHistory = [];
  }
}

/**
 * Enhanced fetch wrapper with circuit breaker instead of timeouts
 */
class EnhancedFetch {
  constructor(options = {}) {
    this.circuitBreaker = new ApiCircuitBreaker(options.circuitBreaker);
    this.baseUrl = options.baseUrl || '';
    this.defaultHeaders = options.headers || {};
    this.retryAttempts = options.retryAttempts || 0;
    this.retryDelay = options.retryDelay || 1000;
  }

  /**
   * Execute fetch request with circuit breaker protection
   */
  async request(url, options = {}) {
    const fullUrl = this.baseUrl + url;

    // Prepare fetch options
    const fetchOptions = {
      ...options,
      headers: {
        ...this.defaultHeaders,
        ...options.headers
      }
    };

    // Define the actual fetch operation
    const apiCall = async () => {
      // Use AbortController for cancellation (not timeout)
      const controller = new AbortController();

      // Set signal for cancellation
      fetchOptions.signal = controller.signal;

      const response = await fetch(fullUrl, fetchOptions);

      if (!response.ok) {
        const errorText = await response.text();
        const error = new Error(`HTTP ${response.status}: ${errorText}`);
        error.status = response.status;
        error.response = response;
        throw error;
      }

      return response;
    };

    // Define fallback handler for when circuit is open
    const fallbackHandler = () => {
      // Return cached response if available
      const cacheKey = `${options.method || 'GET'}_${fullUrl}`;
      const cached = this.getFromCache(cacheKey);

      if (cached) {
        return Promise.resolve(cached);
      }

      // Return offline response
      return Promise.resolve(new Response(
        JSON.stringify({
          error: 'Service temporarily unavailable',
          offline: true,
          timestamp: Date.now()
        }),
        {
          status: 503,
          statusText: 'Service Unavailable',
          headers: { 'Content-Type': 'application/json' }
        }
      ));
    };

    // Execute with circuit breaker
    return await this.circuitBreaker.execute(apiCall, fallbackHandler);
  }

  /**
   * Simple cache for fallback responses
   */
  getFromCache(key) {
    try {
      const cached = sessionStorage.getItem(`api_cache_${key}`);
      if (cached) {
        const { data, timestamp } = JSON.parse(cached);
        // Use cache for up to 5 minutes
        if (Date.now() - timestamp < 300000) {
          return new Response(data, {
            status: 200,
            headers: { 'Content-Type': 'application/json' }
          });
        }
      }
    } catch (error) {
      logger.warn('Cache read error:', error);
    }
    return null;
  }

  /**
   * Store response in cache
   */
  setCache(key, response) {
    try {
      sessionStorage.setItem(`api_cache_${key}`, JSON.stringify({
        data: response,
        timestamp: Date.now()
      }));
    } catch (error) {
      logger.warn('Cache write error:', error);
    }
  }

  /**
   * GET request
   */
  async get(url, options = {}) {
    return this.request(url, { ...options, method: 'GET' });
  }

  /**
   * POST request
   */
  async post(url, data, options = {}) {
    return this.request(url, {
      ...options,
      method: 'POST',
      body: typeof data === 'string' ? data : JSON.stringify(data),
      headers: {
        'Content-Type': 'application/json',
        ...options.headers
      }
    });
  }

  /**
   * PUT request
   */
  async put(url, data, options = {}) {
    return this.request(url, {
      ...options,
      method: 'PUT',
      body: typeof data === 'string' ? data : JSON.stringify(data),
      headers: {
        'Content-Type': 'application/json',
        ...options.headers
      }
    });
  }

  /**
   * DELETE request
   */
  async delete(url, options = {}) {
    return this.request(url, { ...options, method: 'DELETE' });
  }

  /**
   * Get circuit breaker status
   */
  getCircuitStatus() {
    return this.circuitBreaker.getStatus();
  }

  /**
   * Reset circuit breaker
   */
  resetCircuit() {
    this.circuitBreaker.reset();
  }

  /**
   * Update base URL for requests
   */
  updateBaseUrl(newBaseUrl) {
    this.baseUrl = newBaseUrl || '';
  }
}

export { ApiCircuitBreaker, EnhancedFetch };
