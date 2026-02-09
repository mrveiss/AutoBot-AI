/**
 * Redis Service Management API Client
 *
 * Provides methods for controlling Redis service on Redis VM
 * (Network configuration from NetworkConstants)
 * Follows AutoBot API service patterns with error handling
 *
 * AutoBot - AI-Powered Automation Platform
 * Copyright (c) 2025 mrveiss
 * Author: mrveiss
 */

import apiClient from '@/utils/ApiClient'
import { createLogger } from '@/utils/debugUtils'

// Create scoped logger for RedisServiceAPI
const logger = createLogger('RedisServiceAPI')

// ---------------------------------------------------------------------------
// Interfaces
// ---------------------------------------------------------------------------

/** Result of a service lifecycle operation (start, stop, restart). */
export interface ServiceOperationResult {
  success: boolean
  message?: string
}

/** Snapshot of the Redis service runtime status. */
export interface ServiceStatus {
  status: string
  pid: number | null
  uptime_seconds: number | null
  memory_mb: number | null
  connections: number | null
  commands_processed: number | null
  last_check: string | null
}

/** Health-check payload from the service-monitor endpoint. */
export interface ServiceHealth {
  status: string
  /** Additional fields depend on the backend implementation. */
  [key: string]: unknown
}

/** Log retrieval result from the service-monitor endpoint. */
export interface ServiceLogs {
  lines: string[]
  /** Additional fields depend on the backend implementation. */
  [key: string]: unknown
}

/** Valid log-level filter values accepted by the getLogs endpoint. */
export type LogLevel = 'error' | 'warning' | 'info'

/** Parameters for the stopService method. */
export interface StopServiceParams {
  confirmation: boolean
}

/** Parameters for the getLogs method. */
export interface GetLogsParams {
  lines?: number
  since?: string | null
  level?: LogLevel | null
}

// ---------------------------------------------------------------------------
// Implementation
// ---------------------------------------------------------------------------

/**
 * Redis Service API - Service lifecycle management
 *
 * Wraps the shared ApiClient to provide typed access to
 * the service-monitor endpoints for Redis.
 */
class RedisServiceAPI {
  private readonly client: typeof apiClient
  private readonly baseEndpoint: string

  constructor() {
    this.client = apiClient
    // Note: Redis service control endpoints require paramiko (SSH library)
    // which is not currently installed. Using monitoring endpoint for now.
    this.baseEndpoint = '/api/service-monitor/services'
  }

  /**
   * Core HTTP methods - ApiClient already handles JSON parsing
   */
  private async get<T>(endpoint: string): Promise<T> {
    return await this.client.get(endpoint) as T
  }

  private async post<T>(endpoint: string, data: unknown = null): Promise<T> {
    return await this.client.post(endpoint, data) as T
  }

  /**
   * Start Redis service.
   */
  async startService(): Promise<ServiceOperationResult> {
    try {
      return await this.post<ServiceOperationResult>(
        `${this.baseEndpoint}/start`,
      )
    } catch (error) {
      logger.error('Start service failed:', error)
      throw error
    }
  }

  /**
   * Stop Redis service (requires admin role).
   *
   * @param confirmation - User confirmation required
   */
  async stopService(confirmation = false): Promise<ServiceOperationResult> {
    try {
      const payload: StopServiceParams = { confirmation }
      return await this.post<ServiceOperationResult>(
        `${this.baseEndpoint}/stop`,
        payload,
      )
    } catch (error) {
      logger.error('Stop service failed:', error)
      throw error
    }
  }

  /**
   * Restart Redis service.
   */
  async restartService(): Promise<ServiceOperationResult> {
    try {
      return await this.post<ServiceOperationResult>(
        `${this.baseEndpoint}/restart`,
      )
    } catch (error) {
      logger.error('Restart service failed:', error)
      throw error
    }
  }

  /**
   * Get current service status.
   */
  async getStatus(): Promise<ServiceStatus> {
    try {
      return await this.get<ServiceStatus>(
        `${this.baseEndpoint}/status`,
      )
    } catch (error) {
      logger.error('Get status failed:', error)
      throw error
    }
  }

  /**
   * Get detailed health information.
   */
  async getHealth(): Promise<ServiceHealth> {
    try {
      return await this.get<ServiceHealth>(
        `${this.baseEndpoint}/health`,
      )
    } catch (error) {
      logger.error('Get health failed:', error)
      throw error
    }
  }

  /**
   * Get service logs (admin only).
   *
   * @param lines - Number of log lines to retrieve (default 50)
   * @param since - ISO timestamp to get logs since
   * @param level - Log level filter (error, warning, info)
   */
  async getLogs(
    lines = 50,
    since: string | null = null,
    level: LogLevel | null = null,
  ): Promise<ServiceLogs> {
    try {
      const endpoint = this._buildLogsEndpoint(lines, since, level)
      return await this.get<ServiceLogs>(endpoint)
    } catch (error) {
      logger.error('Get logs failed:', error)
      throw error
    }
  }

  /**
   * Build the logs endpoint URL with optional query parameters.
   *
   * Helper for getLogs.
   */
  private _buildLogsEndpoint(
    lines: number,
    since: string | null,
    level: LogLevel | null,
  ): string {
    const params = new URLSearchParams()
    if (lines) params.append('lines', String(lines))
    if (since) params.append('since', since)
    if (level) params.append('level', level)

    const queryString = params.toString()
    return queryString
      ? `${this.baseEndpoint}/logs?${queryString}`
      : `${this.baseEndpoint}/logs`
  }
}

// Create and export singleton instance
export const redisServiceAPI = new RedisServiceAPI()
export default redisServiceAPI
