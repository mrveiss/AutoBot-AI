// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * Unified Orchestration Management Composable (Issue #850 Phase 3)
 *
 * Combines:
 * - useOrchestration (service definitions, fleet status, bulk actions)
 * - Fleet services API (per-node service control from Phase 1)
 * - Fleet store integration
 * - WebSocket management for real-time updates
 *
 * Provides single interface for all orchestration operations.
 */

import { ref, computed, readonly, reactive } from 'vue'
import { makeAxiosCompatClient } from '@/utils/slmApiCompat'
import { useFleetStore } from '@/stores/fleet'
import { useSlmWebSocket } from '@/composables/useSlmWebSocket'
import { createLogger } from '@/utils/debugUtils'
import type {
  ServiceDefinition,
  ServiceActionRequest,
  ServiceMigrateRequest,
  ServiceActionResponse,
  FleetStatusResponse,
  BulkActionRequest,
  BulkActionResponse,
} from '@/composables/useOrchestration'
import type { components } from '@/types/generated/api'

const logger = createLogger('useOrchestrationManagement')

// SLM backend transport: the canonical `slmApiClient` behind the axios-shaped
// facade (#13079/#13140). This composable used to hold its own
// `axios.create({ baseURL: getSlmApiBase(), timeout: 30000 })` with a
// `sessionStorage`-only bearer interceptor and no 401 handling. `slmApiClient`
// supplies the sessionStorage->localStorage token fallback (ApiClient.ts:113),
// an equivalent env-sourced 30s budget (:44-48) and the 401 session teardown
// (:128-151). Endpoints stay relative to the API base, resolved by the client
// via `getSlmApiBase()` (:104).
const client = makeAxiosCompatClient()

// =============================================================================
// Additional Type Definitions (Fleet Services)
// =============================================================================

// GET /api/orchestration/fleet/services -> FleetServiceStatus.nodes
// (autobot-slm-backend/api/orchestration.py:102)
export type FleetServiceNodeStatus = components['schemas']['FleetServiceNodeStatus']

export interface FleetServiceStatus {
  service_name: string
  category: string
  nodes: FleetServiceNodeStatus[]
  running_count: number
  stopped_count: number
  failed_count: number
  total_nodes: number
}

export interface FleetServicesResponse {
  services: FleetServiceStatus[]
  total_services: number
}

/**
 * PATCH /api/orchestration/services/{name}/category
 * (autobot-slm-backend/api/orchestration.py:131).
 *
 * The server constrains the value with `pattern="^(autobot|system)$"`
 * (`orchestration.py:134`), but a Pydantic `pattern` is emitted as a JSON
 * Schema `pattern` and openapi-typescript can only render that as `string`.
 * The narrowing therefore restates a real server-side constraint that the
 * generated type is structurally unable to carry — sending anything else is a
 * guaranteed 422 — so it is kept rather than widened.
 */
export type ServiceCategoryUpdate = components['schemas']['ServiceCategoryUpdate'] & {
  category: 'autobot' | 'system'
}

// =============================================================================
// Composable
// =============================================================================

export function useOrchestrationManagement() {
  // Initialize dependencies
  const fleetStore = useFleetStore()
  const { connect, subscribeAll, onServiceStatus, connected } = useSlmWebSocket()

  // ===========================================================================
  // Reactive State
  // ===========================================================================

  // Service definitions and fleet status (from useOrchestration)
  const serviceDefinitions = ref<ServiceDefinition[]>([])
  const fleetStatus = ref<FleetStatusResponse | null>(null)

  // Fleet services (per-node detail)
  const fleetServices = ref<FleetServiceStatus[]>([])
  const totalFleetServices = ref(0)

  // Loading and error states
  const loading = ref(false)
  const error = ref<string | null>(null)
  const lastRefresh = ref<Date | null>(null)

  // Action tracking
  const actionInProgress = ref(false)
  const activeAction = ref<{
    nodeId: string
    serviceName: string
    action: string
  } | null>(null)

  // ===========================================================================
  // Computed Properties
  // ===========================================================================

  const serviceDefinitionCount = computed(() => serviceDefinitions.value.length)
  const healthyCount = computed(() => fleetStatus.value?.healthy_count ?? 0)
  const unhealthyCount = computed(() => fleetStatus.value?.unhealthy_count ?? 0)

  // Aggregate counts from fleet services
  const totalRunning = computed(() =>
    fleetServices.value.reduce((sum, svc) => sum + svc.running_count, 0)
  )
  const totalStopped = computed(() =>
    fleetServices.value.reduce((sum, svc) => sum + svc.stopped_count, 0)
  )
  const totalFailed = computed(() =>
    fleetServices.value.reduce((sum, svc) => sum + svc.failed_count, 0)
  )

  // ===========================================================================
  // Error Handling Helper
  // ===========================================================================

  function extractErrorMessage(e: unknown, fallback: string): string {
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
  // Service Definitions API (from useOrchestration)
  // ===========================================================================

  async function fetchServiceDefinitions(): Promise<ServiceDefinition[]> {
    loading.value = true
    error.value = null

    try {
      const response = await client.get<ServiceDefinition[]>('/orchestration/services')
      serviceDefinitions.value = response.data
      lastRefresh.value = new Date()
      return response.data
    } catch (e) {
      error.value = extractErrorMessage(e, 'Failed to fetch service definitions')
      logger.error('Failed to fetch service definitions:', e)
      return []
    } finally {
      loading.value = false
    }
  }

  async function fetchServiceDefinition(
    serviceName: string
  ): Promise<ServiceDefinition | null> {
    try {
      const response = await client.get<ServiceDefinition>(
        `/orchestration/services/${serviceName}`
      )
      return response.data
    } catch (e) {
      error.value = extractErrorMessage(e, 'Failed to fetch service definition')
      logger.error(`Failed to fetch service definition ${serviceName}:`, e)
      return null
    }
  }

  // ===========================================================================
  // Fleet Status API (from useOrchestration)
  // ===========================================================================

  async function fetchFleetStatus(): Promise<FleetStatusResponse | null> {
    loading.value = true
    error.value = null

    try {
      const response = await client.get<FleetStatusResponse>('/orchestration/status')
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
  // Fleet Services API (Phase 1 new endpoints)
  // ===========================================================================

  async function fetchFleetServices(): Promise<FleetServicesResponse | null> {
    loading.value = true
    error.value = null
    logger.info('Fetching fleet services from /fleet/services')

    try {
      const response = await client.get<FleetServicesResponse>(
        '/fleet/services'
      )
      logger.info('Fleet services response:', {
        serviceCount: response.data.services?.length,
        totalServices: response.data.total_services,
      })
      fleetServices.value = response.data.services
      totalFleetServices.value = response.data.total_services
      lastRefresh.value = new Date()
      return response.data
    } catch (e) {
      // Same reason as `extractErrorMessage`: the compat adapter's rejection is
      // axios-shaped but not an axios instance. `statusText` is not carried on
      // that shape (the underlying `Response` is consumed as JSON), so the HTTP
      // status + body are logged and the text status is dropped.
      const httpError = e as { response?: { status?: number; data?: unknown } }
      if (httpError?.response?.status !== undefined) {
        logger.error('Fleet services API error:', {
          status: httpError.response.status,
          data: httpError.response.data,
          message: e instanceof Error ? e.message : String(e),
        })
      } else {
        logger.error('Failed to fetch fleet services:', e)
      }
      error.value = extractErrorMessage(e, 'Failed to fetch fleet services')
      return null
    } finally {
      loading.value = false
      logger.info('Fleet services loading complete, loading=false')
    }
  }

  async function updateServiceCategory(
    serviceName: string,
    category: 'autobot' | 'system'
  ): Promise<boolean> {
    error.value = null

    try {
      await client.patch(`/fleet/services/${serviceName}/category`, {
        category,
      } as ServiceCategoryUpdate)
      logger.info(`Updated ${serviceName} category to ${category}`)
      return true
    } catch (e) {
      error.value = extractErrorMessage(e, 'Failed to update service category')
      logger.error(`Failed to update ${serviceName} category:`, e)
      return false
    }
  }

  async function startFleetService(serviceName: string): Promise<ServiceActionResponse | null> {
    error.value = null

    try {
      const response = await client.post<ServiceActionResponse>(
        `/fleet/services/${serviceName}/start`
      )
      logger.info(`Fleet start ${serviceName}:`, response.data.message)
      return response.data
    } catch (e) {
      error.value = extractErrorMessage(e, `Failed to start ${serviceName} fleet-wide`)
      logger.error(`Failed to start ${serviceName} fleet-wide:`, e)
      return null
    }
  }

  async function stopFleetService(serviceName: string): Promise<ServiceActionResponse | null> {
    error.value = null

    try {
      const response = await client.post<ServiceActionResponse>(
        `/fleet/services/${serviceName}/stop`
      )
      logger.info(`Fleet stop ${serviceName}:`, response.data.message)
      return response.data
    } catch (e) {
      error.value = extractErrorMessage(e, `Failed to stop ${serviceName} fleet-wide`)
      logger.error(`Failed to stop ${serviceName} fleet-wide:`, e)
      return null
    }
  }

  async function restartFleetService(serviceName: string): Promise<ServiceActionResponse | null> {
    error.value = null

    try {
      const response = await client.post<ServiceActionResponse>(
        `/fleet/services/${serviceName}/restart`
      )
      logger.info(`Fleet restart ${serviceName}:`, response.data.message)
      return response.data
    } catch (e) {
      error.value = extractErrorMessage(e, `Failed to restart ${serviceName} fleet-wide`)
      logger.error(`Failed to restart ${serviceName} fleet-wide:`, e)
      return null
    }
  }

  // ===========================================================================
  // Individual Service Control (from useOrchestration)
  // ===========================================================================

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
      error.value = extractErrorMessage(e, `Failed to restart ${serviceName}`)
      logger.error(`Failed to restart service ${serviceName}:`, e)
      return null
    }
  }

  // ===========================================================================
  // Service Migration (from useOrchestration)
  // ===========================================================================

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
      error.value = extractErrorMessage(e, `Failed to migrate ${serviceName}`)
      logger.error(`Failed to migrate service ${serviceName}:`, e)
      return null
    }
  }

  // ===========================================================================
  // Bulk Actions (from useOrchestration)
  // ===========================================================================

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
      error.value = extractErrorMessage(e, 'Failed to restart all services')
      logger.error('Failed to restart all services:', e)
      return null
    } finally {
      loading.value = false
    }
  }

  // ===========================================================================
  // WebSocket Integration
  // ===========================================================================

  function initializeWebSocket(
    onStatusUpdate?: (nodeId: string, data: { service_name: string; status: string }) => void
  ): void {
    connect()
    subscribeAll()

    if (onStatusUpdate) {
      onServiceStatus(onStatusUpdate)
    }
  }

  // ===========================================================================
  // Utility Methods
  // ===========================================================================

  function clearError(): void {
    error.value = null
  }

  function reset(): void {
    serviceDefinitions.value = []
    fleetStatus.value = null
    fleetServices.value = []
    totalFleetServices.value = 0
    loading.value = false
    error.value = null
    lastRefresh.value = null
    actionInProgress.value = false
    activeAction.value = null
  }

  function setActiveAction(nodeId: string, serviceName: string, action: string): void {
    actionInProgress.value = true
    activeAction.value = { nodeId, serviceName, action }
  }

  function clearActiveAction(): void {
    actionInProgress.value = false
    activeAction.value = null
  }

  // ===========================================================================
  // Return Public API
  // ===========================================================================

  return reactive({
    // State (auto-unwrapped via reactive() so template/computed can access values directly)
    serviceDefinitions: readonly(serviceDefinitions),
    fleetStatus: readonly(fleetStatus),
    fleetServices: readonly(fleetServices),
    totalFleetServices: readonly(totalFleetServices),
    loading: readonly(loading),
    error: readonly(error),
    lastRefresh: readonly(lastRefresh),
    actionInProgress: readonly(actionInProgress),
    activeAction: readonly(activeAction),
    connected,

    // Computed
    serviceDefinitionCount,
    healthyCount,
    unhealthyCount,
    totalRunning,
    totalStopped,
    totalFailed,

    // Service definitions
    fetchServiceDefinitions,
    fetchServiceDefinition,

    // Fleet status
    fetchFleetStatus,

    // Fleet services
    fetchFleetServices,
    updateServiceCategory,
    startFleetService,
    stopFleetService,
    restartFleetService,

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

    // WebSocket
    initializeWebSocket,

    // Utilities
    clearError,
    reset,
    setActiveAction,
    clearActiveAction,

    // Fleet store access
    fleetStore,
  })
}
