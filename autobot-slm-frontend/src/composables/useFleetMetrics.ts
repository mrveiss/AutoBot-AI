// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * useFleetMetrics — the fleet's monitoring metrics for SLM Admin
 *
 * Provides access to monitoring metrics from the SLM backend API. It was
 * usePrometheusMetrics until #18225: the user app's composable of that name
 * reads one install's backend, a different concept (owner decision 2026-10-24),
 * so each now carries its own name and the headline numbers come from the kit's
 * useMetricsSummary.
 * Uses local SLM monitoring endpoints for fleet metrics, alerts, and health.
 * Issue #729 - Integrated monitoring into SLM.
 */

import { ref, onMounted } from 'vue'
import { throwUnlessLoaded, useDashboardPoller } from '@/composables/useDashboardPoller'
import { createLogger } from '@/utils/debugUtils'
import { slmApiClient } from '@/utils/ApiClient'
import { POLLED_READ_MAX_RETRIES } from '@/constants/api-timeouts'
import type { GPUNodeStatus } from '@/types/slm'
import { HttpError, useMetricsSummary } from '@autobot/ui'
// Types and the pure summary helper live in fleetMetricsModel.ts (#18225).
import { summariseGpus } from './fleetMetricsModel'
import type {
  DashboardViewModel,
  NodeMetricsDetailed,
  FleetMetricsDetailed,
  PerformanceOverview,
  NPUFleetMetrics,
  DashboardWire,
  MonitoringHealthWire,
  MonitoringAlertsWire,
  NpuNodesWire,
} from './fleetMetricsModel'
// Metric shapes shared with autobot-frontend's useInstallMetrics.ts — see the kit
// file's doc comment for which fields are main-app-only extensions (#14907).
// ServiceHealth is used only inside ServicesSummary's shape (not referenced
// directly in this file), so it is re-exported but not locally imported —
// avoids an unused-import lint failure while keeping the export surface.
import type {
  GPUMetrics,
  NPUMetrics,
  ServicesSummary,
  PerformanceAlert,
  AlertsSummary,
  OptimizationRecommendation,
  UsePrometheusMetricsOptions,
} from '@autobot/ui'
export type {
  GPUMetrics,
  NPUMetrics,
  ServiceHealth,
  ServicesSummary,
  PerformanceAlert,
  AlertsSummary,
  OptimizationRecommendation,
  UsePrometheusMetricsOptions,
} from '@autobot/ui'

const logger = createLogger('useFleetMetrics')

/**
 * Every read below goes through `slmApiClient` (#13140), which owns the
 * `getSlmApiBase()` origin, the bearer token, the request timeout and the 401
 * handler. Three things changed at this seam and were decided, not inherited:
 *
 *  1. The bearer used to be built from `authStore.token`. That ref is seeded
 *     from storage ONCE, at store construction (`stores/auth.ts:66`), so it is
 *     correct for a page that loaded with a session already in place and stale
 *     for every token that lands afterwards — a login in another tab, or a
 *     refresh performed through a different store instance. When it was null
 *     `getHeaders()` omitted the header silently and the poll went out
 *     anonymous. The client re-reads sessionStorage (localStorage fallback) on
 *     every request, so there is no window in which the two disagree.
 *  2. `get()` retries a 5xx three times with exponential backoff (~3s). These
 *     are POLLED reads on a 30s tick, so every one passes
 *     `POLLED_READ_MAX_RETRIES` — a failed tick is retried by the NEXT tick
 *     rather than by holding the current one open.
 *  3. A non-OK response used to be dropped by `if (response.ok)` with no else
 *     in `fetchServices`/`fetchAlerts`/`fetchNPUDetails`. `get()` throws, so the
 *     surrounding catch now runs: the same rendered outcome (state left stale),
 *     but the failure is logged instead of vanishing.
 */

/** Polled read options — single-shot, see note 2 above. */
const POLL_OPTS = { maxRetries: POLLED_READ_MAX_RETRIES } as const

export type {
  SystemMetricsViewModel,
  DashboardViewModel,
  NodeMetricsDetailed,
  FleetMetricsDetailed,
  PerformanceOverview,
  NPUFleetMetrics,
} from './fleetMetricsModel'

// ===== Composable Implementation =====

export function useFleetMetrics(options: UsePrometheusMetricsOptions = {}) {
  const { autoFetch = true, pollInterval = 30000 } = options

  // State
  const dashboard = ref<DashboardViewModel | null>(null)
  const services = ref<ServicesSummary | null>(null)
  const alerts = ref<AlertsSummary | null>(null)
  // #15226: null while the SLM has no recommendations source -- unavailable, not "none"
  const recommendations = ref<OptimizationRecommendation[] | null>(null)
  const gpuDetails = ref<GPUMetrics | null>(null)
  // #15226: each node's GPU state from its heartbeat; gpuDetails summarises it
  const gpuNodes = ref<GPUNodeStatus[]>([])
  const gpuUnavailable = ref(false)
  const npuDetails = ref<NPUMetrics | null>(null)

  // New metrics state (Issue #896)
  const fleetMetrics = ref<FleetMetricsDetailed | null>(null)
  const nodeMetrics = ref<Map<string, NodeMetricsDetailed>>(new Map())
  const performanceOverview = ref<PerformanceOverview | null>(null)
  const npuFleetMetrics = ref<NPUFleetMetrics | null>(null)
  const prometheusExport = ref<string | null>(null)

  const isLoading = ref(false)
  const error = ref<string | null>(null)
  const lastUpdate = ref<Date | null>(null)
  const isConnected = ref(false)


  // ===== Computed Values =====

  const summary = useMetricsSummary({ dashboard, services, alerts, gpuDetails, npuDetails })

  // ===== API Methods =====

  async function fetchDashboard(): Promise<void> {
    try {
      const data = await slmApiClient.get<DashboardWire>('/monitoring/dashboard', POLL_OPTS)
      // Map SLM dashboard response to expected format
      dashboard.value = {
        system_metrics: {
          cpu_percent: data.fleet_metrics?.avg_cpu_percent ?? 0,
          memory_percent: data.fleet_metrics?.avg_memory_percent ?? 0,
          disk_percent: data.fleet_metrics?.avg_disk_percent ?? 0,
          network_bytes_sent: 0,
          network_bytes_recv: 0,
          process_count: data.fleet_metrics?.total_services ?? 0,
          timestamp: Date.now(),
        },
        analysis: {
          overall_health: data.health_summary?.overall_status ?? 'unknown',
          performance_score: data.health_summary?.health_score ?? 0,
          bottlenecks: data.health_summary?.issues ?? [],
          resource_utilization: {
            cpu: data.fleet_metrics?.avg_cpu_percent ?? 0,
            memory: data.fleet_metrics?.avg_memory_percent ?? 0,
            disk: data.fleet_metrics?.avg_disk_percent ?? 0,
          },
        },
        timestamp: Date.now(),
      }
      lastUpdate.value = new Date()
      error.value = null
      isConnected.value = true
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to fetch dashboard'
      logger.error('Failed to fetch dashboard:', err)
      error.value = message
      isConnected.value = false
    }
  }

  async function fetchServices(): Promise<void> {
    try {
      const data = await slmApiClient.get<MonitoringHealthWire>('/monitoring/health', POLL_OPTS)
      // Map SLM health response to services format
      services.value = {
        total_services: 0,
        healthy_services: 0,
        degraded_services: 0,
        critical_services: 0,
        overall_status: data.overall_status === 'healthy' ? 'healthy' :
                        data.overall_status === 'degraded' ? 'degraded' : 'critical',
        health_percentage: data.health_score ?? 0,
        services: [],
      }
      error.value = null
    } catch (err) {
      logger.error('Failed to fetch services:', err)
    }
  }

  async function fetchAlerts(): Promise<boolean> {
    try {
      const data = await slmApiClient.get<MonitoringAlertsWire>('/monitoring/alerts', POLL_OPTS)
      alerts.value = {
        total_count: data.total_count ?? 0,
        critical_count: data.critical_count ?? 0,
        warning_count: data.warning_count ?? 0,
        alerts: (data.alerts ?? []).map((a: Record<string, unknown>) => {
          // Normalize backend 'error' severity → 'high' so it matches
          // the frontend severity breakdown (critical/high/warning/info). (#995)
          const rawSeverity = String(a.severity ?? 'info')
          const severity = rawSeverity === 'error' ? 'high' : rawSeverity
          return {
            category: String(a.category ?? ''),
            severity,
            message: String(a.message ?? ''),
            recommendation: '',
            timestamp: new Date(String(a.timestamp ?? '')).getTime(),
          }
        }) as PerformanceAlert[],
      }
      error.value = null
      return true
    } catch (err) {
      logger.error('Failed to fetch alerts:', err)
      return false
    }
  }

  async function fetchRecommendations(): Promise<void> {
    // #15226: the SLM has no recommendations source yet. Say so (null) rather
    // than return an empty list, which the UI would read as "nothing to fix".
    recommendations.value = null
  }

  async function fetchGPUDetails(): Promise<void> {
    // #15226: each node's GPUs, as its agent's heartbeat reported them (#16280, #16281)
    try {
      const data = await slmApiClient.getContract('/api/monitoring/gpu/nodes', POLL_OPTS)
      gpuNodes.value = data.nodes
      gpuDetails.value = summariseGpus(data.nodes)
      gpuUnavailable.value = false
    } catch (err) {
      logger.error('Failed to fetch GPU state:', err)
      gpuNodes.value = []
      gpuDetails.value = null
      gpuUnavailable.value = true
    }
  }

  async function fetchNPUDetails(): Promise<void> {
    // Issue #835 - query actual NPU node status from SLM backend
    try {
      const data = await slmApiClient.get<NpuNodesWire>('/npu/nodes', POLL_OPTS)
      const nodes = data.nodes || []
      if (nodes.length > 0) {
        const activeNodes = nodes.filter(
          (n: Record<string, unknown>) => n.status === 'online'
        )
        npuDetails.value = {
          available: activeNodes.length > 0,
          utilization_percent: 0,
          acceleration_ratio: 0,
          inference_count: activeNodes.length,
        }
        return
      }
    } catch (err) {
      logger.error('Failed to fetch NPU details:', err)
    }
    npuDetails.value = {
      available: false,
      utilization_percent: 0,
      acceleration_ratio: 0,
      inference_count: 0,
    }
  }

  async function fetchAll(): Promise<void> {
    isLoading.value = true
    try {
      await Promise.all([
        fetchDashboard(),
        fetchServices(),
        fetchAlerts(),
        fetchRecommendations(),
        fetchGPUDetails(),
        fetchNPUDetails(),
      ])
      lastUpdate.value = new Date()
    } finally {
      isLoading.value = false
    }
  }

  async function refresh(): Promise<void> {
    await fetchAll()
  }

  // ===== New Metrics Methods (Issue #896) =====

  async function fetchFleetMetrics(): Promise<boolean> {
    try {
      fleetMetrics.value = await slmApiClient.get<FleetMetricsDetailed>(
        '/monitoring/metrics/fleet',
        POLL_OPTS
      )
      error.value = null
      return true
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to fetch fleet metrics'
      logger.error('Failed to fetch fleet metrics:', err)
      error.value = message
      return false
    }
  }

  async function fetchNodeMetricsDetailed(nodeId: string): Promise<void> {
    try {
      const data = await slmApiClient.get<NodeMetricsDetailed>(
        `/monitoring/metrics/node/${nodeId}`,
        POLL_OPTS
      )
      nodeMetrics.value.set(nodeId, data)
      error.value = null
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to fetch node metrics'
      logger.error(`Failed to fetch node metrics for ${nodeId}:`, err)
      error.value = message
    }
  }

  async function fetchPerformanceOverview(): Promise<boolean> {
    try {
      performanceOverview.value = await slmApiClient.get<PerformanceOverview>(
        '/performance/overview',
        POLL_OPTS
      )
      error.value = null
      return true
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to fetch performance overview'
      logger.error('Failed to fetch performance overview:', err)
      error.value = message
      return false
    }
  }

  async function fetchNPUFleetMetrics(): Promise<boolean> {
    try {
      npuFleetMetrics.value = await slmApiClient.get<NPUFleetMetrics>(
        '/npu/metrics',
        POLL_OPTS
      )
      error.value = null
      return true
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to fetch NPU fleet metrics'
      logger.error('Failed to fetch NPU fleet metrics:', err)
      error.value = message
      return false
    }
  }

  async function fetchPrometheusExport(): Promise<void> {
    try {
      // `rawRequest`, NOT `get()`: this endpoint returns the Prometheus text
      // exposition format, and `get()` parses the body as JSON. This is the one
      // read in this composable with a genuine transport reason to keep the
      // Response object — it still takes the base URL, bearer, timeout and 401
      // handling from the client (#13140).
      const response = await slmApiClient.rawRequest('/performance/metrics/prometheus')
      if (response.ok) {
        prometheusExport.value = await response.text()
        error.value = null
      } else {
        throw new HttpError(response.status, response.statusText)
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to fetch Prometheus export'
      logger.error('Failed to fetch Prometheus export:', err)
      error.value = message
    }
  }

  /** Resolves false when every read failed, so a poller counts the tick as a failure (#19482). */
  async function refreshMetrics(): Promise<boolean> {
    isLoading.value = true
    try {
      const results = await Promise.all([
        fetchFleetMetrics(),
        fetchPerformanceOverview(),
        fetchNPUFleetMetrics(),
      ])
      lastUpdate.value = new Date()
      return results.some(Boolean)
    } finally {
      isLoading.value = false
    }
  }

  // ===== Polling Methods =====

  // #19482: the shared dashboard policy (stops with the owning scope and after repeated
  // failures; the view shows PollingPausedAlert and Retry calls `poller.start('')`).
  // fetchDashboard is the only writer of isConnected, so it decides whether a tick failed.
  const poller = useDashboardPoller(async () => {
    await fetchAll()
    throwUnlessLoaded(isConnected.value)
  }, pollInterval)

  /** Start polling; its first tick is a full fetchAll. */
  function startPolling(): void {
    if (poller.isPolling.value) return
    logger.debug(`Starting polling with interval: ${pollInterval}ms`)
    poller.start('')
  }

  function stopPolling(): void {
    if (poller.isPolling.value) {
      poller.stop()
      logger.debug('Polling stopped')
    }
  }

  // Stub WebSocket methods for compatibility
  function connectWebSocket(): void {
    logger.debug('WebSocket not implemented for SLM admin - using polling')
  }

  function disconnectWebSocket(): void {
    // No-op
  }

  // ===== Lifecycle =====

  onMounted(() => {
    if (pollInterval > 0) {
      // The poller's first tick is the fetchAll. A caller that sets autoFetch off owns its
      // own reads (and its own poller), so it is not polled behind its back.
      if (autoFetch) startPolling()
    } else if (autoFetch) {
      fetchAll()
    }
  })

  return {
    // State
    dashboard,
    services,
    alerts,
    recommendations,
    gpuDetails,
    gpuNodes,
    gpuUnavailable,
    npuDetails,
    isLoading,
    error,
    lastUpdate,
    isConnected,

    // New metrics state (Issue #896)
    fleetMetrics,
    nodeMetrics,
    performanceOverview,
    npuFleetMetrics,
    prometheusExport,

    // Computed
    ...summary,

    // Methods
    fetchDashboard,
    fetchServices,
    fetchAlerts,
    fetchRecommendations,
    fetchGPUDetails,
    fetchNPUDetails,
    fetchAll,
    startPolling,
    poller,
    stopPolling,
    connectWebSocket,
    disconnectWebSocket,
    refresh,

    // New metrics methods (Issue #896)
    fetchFleetMetrics,
    fetchNodeMetricsDetailed,
    fetchPerformanceOverview,
    fetchNPUFleetMetrics,
    fetchPrometheusExport,
    refreshMetrics,
  }
}

export default useFleetMetrics
