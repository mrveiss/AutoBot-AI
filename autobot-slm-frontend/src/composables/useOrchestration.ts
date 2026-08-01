// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
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
import { makeAxiosCompatClient } from '@/utils/slmApiCompat'
import { createLogger } from '@/utils/debugUtils'
import type { components } from '@/types/generated/api'

const logger = createLogger('useOrchestration')

// SLM backend transport: the canonical `slmApiClient` behind the axios-shaped
// facade (#13079/#13140). This composable used to hold its own
// `axios.create({ baseURL: getSlmApiBase() })` with a `sessionStorage`-only
// bearer interceptor, NO timeout and no 401 handling. `slmApiClient` supplies
// the sessionStorage->localStorage token fallback (ApiClient.ts:113), the
// `VITE_SLM_API_TIMEOUT_MS` budget (:44-48) and the 401 session teardown
// (:128-151). Endpoints below stay relative to the API base, which the client
// resolves via `getSlmApiBase()` (:104).
const client = makeAxiosCompatClient()

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

// POST /api/orchestration/services/{name}/{start,stop,restart}
// (autobot-slm-backend/models/schemas.py:841).
//
// `Partial<>` rather than a bare alias: `force` carries a server-side default
// (`default=False`), and openapi-typescript emits defaulted fields as REQUIRED
// because the *response* always has them. On a request body that is backwards —
// every field of this model is optional to send. `Omit`/`Pick` cannot be used
// here: the generated types are intersected with an `additionalProperties`
// index signature, so `keyof` is `string | number` and those helpers collapse
// the named members away. `Partial` is homomorphic and preserves them.
export type ServiceActionRequest = Partial<
  components['schemas']['ServiceActionRequest']
>

// POST /api/orchestration/services/{name}/migrate
// (autobot-slm-backend/models/schemas.py, ServiceMigrateRequest)
export type ServiceMigrateRequest = components['schemas']['ServiceMigrateRequest']

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

/**
 * GET /api/orchestration/status (autobot-slm-backend/api/orchestration.py:75).
 *
 * The backend declares `services: dict` (`orchestration.py:79`) with no value
 * model, so the contract can only say `{ [key: string]: unknown }`. Deriving
 * that verbatim would delete a real, load-bearing guarantee — every consumer
 * reads `.status`/`.host`/`.port` off the entries. The intersection keeps the
 * derivation for the scalar fields (so a renamed/added count is caught) while
 * pinning the element shape the endpoint actually builds.
 */
export type FleetStatusResponse = components['schemas']['FleetStatusResponse'] & {
  services: Record<string, FleetServiceEntry>
}

// POST /api/orchestration/{start,stop,restart}-all
// (autobot-slm-backend/api/orchestration.py:84). `exclude` has a
// `default_factory=list`, so it is optional to send — see ServiceActionRequest.
export type BulkActionRequest = Partial<components['schemas']['BulkActionRequest']>

export interface BulkActionResult {
  success: boolean
  message?: string
  stop_success?: boolean
  stop_message?: string
  start_success?: boolean
  start_message?: string
}

// POST /api/orchestration/{start,stop,restart}-all
// (autobot-slm-backend/api/orchestration.py:93). `results` is a bare `dict`
// server-side (`orchestration.py:97`) — same reasoning as FleetStatusResponse.
export type BulkActionResponse = components['schemas']['BulkActionResponse'] & {
  results: Record<string, BulkActionResult>
}

// =============================================================================
// Composable
// =============================================================================

export function useOrchestration() {
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
    // `slmApiCompat` rejects with an axios-SHAPED error (`err.response.status`
    // / `.data`) but not an axios instance, so `axios.isAxiosError` would miss
    // it and every backend `detail` would degrade to `HTTP <n>`. Read the shape
    // directly instead.
    const detail = (e as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
    if (typeof detail === 'string' && detail.length > 0) {
      return detail
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
