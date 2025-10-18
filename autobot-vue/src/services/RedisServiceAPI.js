/**
 * Redis Service Management API Client
 *
 * Provides methods for controlling Redis service on VM3 (172.16.168.23)
 * Follows AutoBot API service patterns with error handling
 */

import apiClient from '@/utils/ApiClient'

/**
 * Redis Service API - Service lifecycle management
 */
class RedisServiceAPI {
  constructor() {
    this.client = apiClient
    // Note: Redis service control endpoints require paramiko (SSH library)
    // which is not currently installed. Temporarily disabled.
    // this.baseEndpoint = '/api/redis-service'
    this.baseEndpoint = '/api/service-monitor/services'  // Use monitoring endpoint for now
  }

  /**
   * Core HTTP methods with JSON parsing
   */
  async get(endpoint) {
    const response = await this.client.get(endpoint)
    return await response.json()
  }

  async post(endpoint, data = null) {
    const response = await this.client.post(endpoint, data)
    return await response.json()
  }

  /**
   * Start Redis service
   * @returns {Promise<Object>} Operation result
   */
  async startService() {
    try {
      const result = await this.post(`${this.baseEndpoint}/start`)
      return result
    } catch (error) {
      console.error('[RedisServiceAPI] Start service failed:', error)
      throw error
    }
  }

  /**
   * Stop Redis service (requires admin role)
   * @param {boolean} confirmation - User confirmation required
   * @returns {Promise<Object>} Operation result
   */
  async stopService(confirmation = false) {
    try {
      const result = await this.post(`${this.baseEndpoint}/stop`, { confirmation })
      return result
    } catch (error) {
      console.error('[RedisServiceAPI] Stop service failed:', error)
      throw error
    }
  }

  /**
   * Restart Redis service
   * @returns {Promise<Object>} Operation result
   */
  async restartService() {
    try {
      const result = await this.post(`${this.baseEndpoint}/restart`)
      return result
    } catch (error) {
      console.error('[RedisServiceAPI] Restart service failed:', error)
      throw error
    }
  }

  /**
   * Get current service status
   * @returns {Promise<Object>} Service status information
   */
  async getStatus() {
    try {
      const status = await this.get(`${this.baseEndpoint}/status`)
      return status
    } catch (error) {
      console.error('[RedisServiceAPI] Get status failed:', error)
      throw error
    }
  }

  /**
   * Get detailed health information
   * @returns {Promise<Object>} Health check results
   */
  async getHealth() {
    try {
      const health = await this.get(`${this.baseEndpoint}/health`)
      return health
    } catch (error) {
      console.error('[RedisServiceAPI] Get health failed:', error)
      throw error
    }
  }

  /**
   * Get service logs (admin only)
   * @param {number} lines - Number of log lines to retrieve
   * @param {string} since - ISO timestamp to get logs since
   * @param {string} level - Log level filter (error, warning, info)
   * @returns {Promise<Object>} Service logs
   */
  async getLogs(lines = 50, since = null, level = null) {
    try {
      const params = new URLSearchParams()
      if (lines) params.append('lines', lines)
      if (since) params.append('since', since)
      if (level) params.append('level', level)

      const queryString = params.toString()
      const endpoint = queryString
        ? `${this.baseEndpoint}/logs?${queryString}`
        : `${this.baseEndpoint}/logs`

      const logs = await this.get(endpoint)
      return logs
    } catch (error) {
      console.error('[RedisServiceAPI] Get logs failed:', error)
      throw error
    }
  }
}

// Create and export singleton instance
export const redisServiceAPI = new RedisServiceAPI()
export default redisServiceAPI
