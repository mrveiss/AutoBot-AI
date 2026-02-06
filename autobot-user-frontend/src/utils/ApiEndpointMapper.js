/**
 * API Endpoint Mapper
 * Provides graceful fallback handling and caching for API endpoint calls
 */

import { NetworkConstants } from '@/constants/network';
import { createLogger } from '@/utils/debugUtils';

// Create scoped logger for ApiEndpointMapper
const logger = createLogger('ApiEndpointMapper');

class ApiEndpointMapper {
  constructor() {
    this.cache = new Map()
    this.fallbackData = new Map()
    // Use NetworkConstants instead of hardcoded IP
    this.baseUrl = import.meta.env.VITE_API_BASE_URL || `http://${NetworkConstants.MAIN_MACHINE_IP}:${NetworkConstants.BACKEND_PORT}`
  }

  /**
   * Fetch with fallback support
   * @param {string} endpoint - API endpoint to fetch
   * @param {Object} options - Fetch options including timeout
   * @returns {Promise<Response>} Response object with fallback flag
   */
  async fetchWithFallback(endpoint, options = {}) {
    const { timeout = 5000, ...fetchOptions } = options
    const url = `${this.baseUrl}${endpoint}`

    // Check cache first
    const cacheKey = `${endpoint}_${JSON.stringify(fetchOptions)}`
    const cachedData = this.cache.get(cacheKey)

    if (cachedData && Date.now() - cachedData.timestamp < 30000) {
      return this._createFallbackResponse(cachedData.data, false)
    }

    try {
      // Create abort controller for timeout
      const controller = new AbortController()
      const timeoutId = setTimeout(() => controller.abort(), timeout)

      const response = await fetch(url, {
        ...fetchOptions,
        signal: controller.signal
      })

      clearTimeout(timeoutId)

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`)
      }

      // Clone response to cache it
      const clonedResponse = response.clone()
      const data = await clonedResponse.json()

      // Cache successful response
      this.cache.set(cacheKey, {
        data,
        timestamp: Date.now()
      })

      // Also store as fallback data
      this.fallbackData.set(endpoint, data)

      return response
    } catch (error) {
      logger.warn(`[ApiEndpointMapper] Fetch failed for ${endpoint}, using fallback:`, error.message)

      // Use fallback data if available
      const fallback = this.fallbackData.get(endpoint) || this._getDefaultFallback(endpoint)
      return this._createFallbackResponse(fallback, true)
    }
  }

  /**
   * Create a Response-like object for fallback data
   * @param {any} data - Fallback data
   * @param {boolean} isFallback - Whether this is fallback data
   * @returns {Object} Response-like object
   */
  _createFallbackResponse(data, isFallback) {
    return {
      ok: true,
      status: isFallback ? 503 : 200,
      fallback: isFallback,
      json: async () => data,
      text: async () => JSON.stringify(data)
    }
  }

  /**
   * Get default fallback data for known endpoints
   * @param {string} endpoint - API endpoint
   * @returns {Object} Default fallback data
   */
  _getDefaultFallback(endpoint) {
    const defaults = {
      '/api/service-monitor/vms/status': {
        vms: [
          { name: 'Backend API', status: 'unknown', message: 'Status unavailable' },
          { name: 'NPU Worker', status: 'unknown', message: 'Status unavailable' },
          { name: 'Redis', status: 'unknown', message: 'Status unavailable' }
        ]
      },
      '/api/service-monitor/services': {
        services: {
          backend: { status: 'unknown', health: 'Status unavailable' },
          redis: { status: 'unknown', health: 'Status unavailable' },
          ollama: { status: 'unknown', health: 'Status unavailable' },
          npu_worker: { status: 'unknown', health: 'Status unavailable' },
          browser: { status: 'unknown', health: 'Status unavailable' }
        }
      }
    }

    return defaults[endpoint] || { error: 'No fallback data available' }
  }

  /**
   * Clear all cached data
   */
  clearCache() {
    this.cache.clear()
  }

  /**
   * Clear cache for specific endpoint
   * @param {string} endpoint - Endpoint to clear from cache
   */
  clearEndpointCache(endpoint) {
    for (const key of this.cache.keys()) {
      if (key.startsWith(endpoint)) {
        this.cache.delete(key)
      }
    }
  }

  /**
   * Set custom fallback data for an endpoint
   * @param {string} endpoint - API endpoint
   * @param {any} data - Fallback data to use
   */
  setFallbackData(endpoint, data) {
    this.fallbackData.set(endpoint, data)
  }
}

// Export singleton instance
const apiEndpointMapper = new ApiEndpointMapper()
export default apiEndpointMapper
