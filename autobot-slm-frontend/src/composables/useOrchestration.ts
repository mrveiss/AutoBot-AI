// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * Orchestration Composable (Issue #838)
 *
 * Provides REST API integration for all SLM orchestration endpoints.
 * Manages portable AutoBot service orchestration across machines:
 * service definitions, fleet status, start/stop/restart, migration,
 * and bulk actions.
 */

import { ref, computed, readonly } from 'vue'
import axios, { type AxiosInstance } from 'axios'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('useOrchestration')

// SLM Admin uses the local SLM backend API
const API_BASE = '/api'

// =============================================================================
// Type Definitions
// =============================================================================

export interface ServiceDefinition {
  name: string
  service_type: string
  default_host: string
  default_port: number
  systemd_service: string | null
  description: string
  health_check_type: string
}

export interface ServiceActionRequest {
  node_id?: string | null
  force?: boolean
}

export interface ServiceMigrateRequest {
  source_node_id: string
  target_node_id: string
}

export interface ServiceActionResponse {
  service_name: string
  action: string
  success: boolean
  message: string
  node_id: string | null
  host: string | null
}

export interface FleetServiceEntry {
  status: string
  host: string
  port: number
  message: string
}

export interface FleetStatusResponse {
  timestamp: string
  services: Record<string, FleetServiceEntry>
  healthy_count: number
  unhealthy_count: number
}

export interface BulkActionRequest {
  exclude?: string[]
}

export interface BulkActionResult {
  success: boolean
  message?: string
  stop_success?: boolean
  stop_message?: string
  start_success?: boolean
  start_message?: string
}

export interface BulkActionResponse {
  action: string
  results: Record<string, BulkActionResult>
  success_count: number
  failure_count: number
}

// =============================================================================
// Composable
// =============================================================================

export function useOrchestration() {
  // Create axios client
  const client: AxiosInstance = axios.create({
    baseURL: API_BASE,
    headers: { 'Content-Type': 'application/json' },
  })

  // Add auth token to all requests
  client.interceptors.request.use((config) => {
    const token = localStorage.getItem('slm_access_token')
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  })

  // ===========================================================================
  // Reactive State
  // ===========================================================================

  const services = ref<ServiceDefinition[]>([])
  const fleetStatus = ref<FleetStatusResponse | null>(null)
  const loading = ref(false)
  const error = ref<string | null>(null)
  const lastRefresh = ref<Date | null>(null)

  // ===========================================================================
  // Computed Properties
  // ===========================================================================

  const serviceCount = computed(() => services.value.length)

  const healthyCount = computed(() => fleetStatus.value?.healthy_count ?? 0)

  const unhealthyCount = computed(() => fleetStatus.value?.unhealthy_count ?? 0)

  const totalFleetServices = computed(() => {
    if (!fleetStatus.value) return 0
    return Object.keys(fleetStatus.value.services).length
  })

  // ===========================================================================
  // Error Extraction Helper
  // ===========================================================================

  function extractErrorMessage(
    e: unknown,
    fallback: string
  ): string {
    if (axios.isAxiosError(e) && e.response?.data?.detail) {
      return e.response.data.detail
    }
    return e instanceof Error ? e.message : fallback
  }

  // ===========================================================================
  // Service Registry API Methods
  // ===========================================================================

  /**
   * Fetch all registered service definitions.
   */
  async function fetchServices(): Promise<ServiceDefinition[]> {
    loading.value = true
    error.value = null

    try {
      const response = await client.get<ServiceDefinition[]>(
        '/orchestration/services'
      )
      services.value = response.data
      lastRefresh.value = new Date()
      return response.data
    } catch (e) {
      error.value = extractErrorMessage(e, 'Failed to fetch services')
      logger.error('Failed to fetch orchestration services:', e)
      return []
    } finally {
      loading.value = false
    }
  }

  /**
   * Fetch a single service definition by name.
   */
  async function fetchService(
    serviceName: string
  ): Promise<ServiceDefinition | null> {
    try {
      const response = await client.get<ServiceDefinition>(
        `/orchestration/services/${serviceName}`
      )
      return response.data
    } catch (e) {
      error.value = extractErrorMessage(e, 'Failed to fetch service')
      logger.error(`Failed to fetch service ${serviceName}:`, e)
      return null
    }
  }

  // ===========================================================================
  // Fleet Status API Method
  // ===========================================================================

  /**
   * Fetch fleet-wide service status.
   */
  async function fetchFleetStatus(): Promise<FleetStatusResponse | null> {
    loading.value = true
    error.value = null

    try {
      const response = await client.get<FleetStatusResponse>(
        '/orchestration/status'
      )
      fleetStatus.value = response.data
      lastRefresh.value = new Date()
      return response.data
    } catch (e) {
      error.value = extractErrorMessage(e, 'Failed to fetch fleet status')
      logger.error('Failed to fetch fleet status:', e)
      return null
    } finally {
      loading.value = false
    }
  }

  // ===========================================================================
  // Individual Service Control API Methods
  // ===========================================================================

  /**
   * Start a specific service, optionally on a specific node.
   */
  async function startService(
    serviceName: string,
    options?: ServiceActionRequest
  ): Promise<ServiceActionResponse | null> {
    error.value = null

    try {
      const response = await client.post<ServiceActionResponse>(
        `/orchestration/services/${serviceName}/start`,
        options || {}
      )
      logger.info(`Start service ${serviceName}:`, response.data.message)
      return response.data
    } catch (e) {
      error.value = extractErrorMessage(e, `Failed to start ${serviceName}`)
      logger.error(`Failed to start service ${serviceName}:`, e)
      return null
    }
  }

  /**
   * Stop a specific service, optionally on a specific node.
   */
  async function stopService(
    serviceName: string,
    options?: ServiceActionRequest
  ): Promise<ServiceActionResponse | null> {
    error.value = null

    try {
      const response = await client.post<ServiceActionResponse>(
        `/orchestration/services/${serviceName}/stop`,
        options || {}
      )
      logger.info(`Stop service ${serviceName}:`, response.data.message)
      return response.data
    } catch (e) {
      error.value = extractErrorMessage(e, `Failed to stop ${serviceName}`)
      logger.error(`Failed to stop service ${serviceName}:`, e)
      return null
    }
  }

  /**
   * Restart a specific service, optionally on a specific node.
   */
  async function restartService(
    serviceName: string,
    options?: ServiceActionRequest
  ): Promise<ServiceActionResponse | null> {
    error.value = null

    try {
      const response = await client.post<ServiceActionResponse>(
        `/orchestration/services/${serviceName}/restart`,
        options || {}
      )
      logger.info(`Restart service ${serviceName}:`, response.data.message)
      return response.data
    } catch (e) {
      error.value = extractErrorMessage(
        e,
        `Failed to restart ${serviceName}`
      )
      logger.error(`Failed to restart service ${serviceName}:`, e)
      return null
    }
  }

  // ===========================================================================
  // Service Migration API Method
  // ===========================================================================

  /**
   * Migrate a service from one node to another.
   */
  async function migrateService(
    serviceName: string,
    request: ServiceMigrateRequest
  ): Promise<ServiceActionResponse | null> {
    error.value = null

    try {
      const response = await client.post<ServiceActionResponse>(
        `/orchestration/services/${serviceName}/migrate`,
        request
      )
      logger.info(`Migrate service ${serviceName}:`, response.data.message)
      return response.data
    } catch (e) {
      error.value = extractErrorMessage(
        e,
        `Failed to migrate ${serviceName}`
      )
      logger.error(`Failed to migrate service ${serviceName}:`, e)
      return null
    }
  }

  // ===========================================================================
  // Bulk Action API Methods
  // ===========================================================================

  /**
   * Start all registered services in dependency order.
   */
  async function startAllServices(
    options?: BulkActionRequest
  ): Promise<BulkActionResponse | null> {
    loading.value = true
    error.value = null

    try {
      const response = await client.post<BulkActionResponse>(
        '/orchestration/start-all',
        options || {}
      )
      logger.info('Start all services:', response.data)
      await fetchFleetStatus()
      return response.data
    } catch (e) {
      error.value = extractErrorMessage(e, 'Failed to start all services')
      logger.error('Failed to start all services:', e)
      return null
    } finally {
      loading.value = false
    }
  }

  /**
   * Stop all registered services in reverse dependency order.
   */
  async function stopAllServices(
    options?: BulkActionRequest
  ): Promise<BulkActionResponse | null> {
    loading.value = true
    error.value = null

    try {
      const response = await client.post<BulkActionResponse>(
        '/orchestration/stop-all',
        options || {}
      )
      logger.info('Stop all services:', response.data)
      await fetchFleetStatus()
      return response.data
    } catch (e) {
      error.value = extractErrorMessage(e, 'Failed to stop all services')
      logger.error('Failed to stop all services:', e)
      return null
    } finally {
      loading.value = false
    }
  }

  /**
   * Restart all registered services (stop then start in order).
   */
  async function restartAllServices(
    options?: BulkActionRequest
  ): Promise<BulkActionResponse | null> {
    loading.value = true
    error.value = null

    try {
      const response = await client.post<BulkActionResponse>(
        '/orchestration/restart-all',
        options || {}
      )
      logger.info('Restart all services:', response.data)
      await fetchFleetStatus()
      return response.data
    } catch (e) {
      error.value = extractErrorMessage(
        e,
        'Failed to restart all services'
      )
      logger.error('Failed to restart all services:', e)
      return null
    } finally {
      loading.value = false
    }
  }

  // ===========================================================================
  // Utility Methods
  // ===========================================================================

  /**
   * Clear the current error state.
   */
  function clearError(): void {
    error.value = null
  }

  /**
   * Reset all state to initial values.
   */
  function reset(): void {
    services.value = []
    fleetStatus.value = null
    loading.value = false
    error.value = null
    lastRefresh.value = null
  }

  // ===========================================================================
  // Return Public API
  // ===========================================================================

  return {
    // State (readonly to prevent external mutation)
    services: readonly(services),
    fleetStatus: readonly(fleetStatus),
    loading: readonly(loading),
    error: readonly(error),
    lastRefresh: readonly(lastRefresh),

    // Computed
    serviceCount,
    healthyCount,
    unhealthyCount,
    totalFleetServices,

    // Service registry methods
    fetchServices,
    fetchService,

    // Fleet status
    fetchFleetStatus,

    // Individual service control
    startService,
    stopService,
    restartService,

    // Service migration
    migrateService,

    // Bulk actions
    startAllServices,
    stopAllServices,
    restartAllServices,

    // Utilities
    clearError,
    reset,
  }
}
