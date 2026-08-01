// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * Prometheus Metrics Composable for SLM Admin
 *
 * Provides access to monitoring metrics from the SLM backend API.
 * Uses local SLM monitoring endpoints for fleet metrics, alerts, and health.
 * Issue #729 - Integrated monitoring into SLM.
 */

import { ref, computed, onMounted, onUnmounted } from 'vue'
import { createLogger } from '@/utils/debugUtils'
import { slmApiClient } from '@/utils/ApiClient'
import { POLLED_READ_MAX_RETRIES } from '@/constants/api-timeouts'

const logger = createLogger('usePrometheusMetrics')

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

// ===== Type Definitions =====

/**
 * Host-level metrics as this composable presents them — a client-side
 * VIEW-MODEL, not a wire shape.
 *
 * Renamed from `SystemMetrics` in #13138: it collided with the generated
 * `components['schemas']['SystemMetrics']` (the `/health/metrics` response,
 * autobot-slm-backend/api/health.py:59) while sharing almost nothing with it —
 * `fetchDashboard` below synthesises every field from `/monitoring/dashboard`'s
 * `fleet_metrics` averages, and `timestamp` here is `Date.now()`, not an ISO
 * string. Deriving it would have been actively harmful.
 */
export interface SystemMetricsViewModel {
  cpu_percent: number
  memory_percent: number
  disk_percent: number
  network_bytes_sent: number
  network_bytes_recv: number
  process_count: number
  timestamp: number
}

export interface GPUMetrics {
  available: boolean
  utilization_percent: number
  memory_utilization_percent: number
  temperature_celsius: number
  power_watts: number
  name?: string
  thermal_throttling?: boolean
}

export interface NPUMetrics {
  available: boolean
  utilization_percent: number
  acceleration_ratio: number
  inference_count: number
  wsl_limitation?: boolean
}

export interface ServiceHealth {
  name: string
  host: string
  port: number
  status: 'healthy' | 'degraded' | 'critical' | 'offline'
  response_time_ms: number
  health_score: number
  uptime_hours: number
}

export interface ServicesSummary {
  total_services: number
  healthy_services: number
  degraded_services: number
  critical_services: number
  overall_status: 'healthy' | 'degraded' | 'critical'
  health_percentage: number
  services: ServiceHealth[]
}

export interface PerformanceAlert {
  category: string
  severity: 'info' | 'warning' | 'critical' | 'high'
  message: string
  recommendation: string
  timestamp: number
}

export interface AlertsSummary {
  total_count: number
  critical_count: number
  warning_count: number
  alerts: PerformanceAlert[]
}

export interface OptimizationRecommendation {
  category: string
  priority: 'high' | 'medium' | 'low'
  recommendation: string
  action: string
  expected_improvement: string
}

/**
 * Dashboard shape this composable exposes — a client-side VIEW-MODEL.
 *
 * Renamed from `DashboardOverview` in #13138: it collided with the generated
 * `components['schemas']['DashboardOverview']` (api/monitoring.py:118), which
 * `fetchDashboard` deliberately REMAPS into this shape (see the mapping right
 * below). The real wire model is derived, under its own name, in
 * `types/api-responses.ts`.
 */
export interface DashboardViewModel {
  system_metrics?: SystemMetricsViewModel
  gpu_metrics?: GPUMetrics
  npu_metrics?: NPUMetrics
  hardware_acceleration?: Record<string, boolean>
  analysis?: {
    overall_health: string
    performance_score: number
    bottlenecks: string[]
    resource_utilization: Record<string, number>
  }
  timestamp?: number
}

export interface NodeMetricsDetailed {
  node_id: string
  hostname: string
  ip_address: string
  status: string
  cpu_percent: number
  memory_percent: number
  disk_percent: number
  last_heartbeat: string | null
  services_running: number
  services_failed: number
}

export interface FleetMetricsDetailed {
  total_nodes: number
  online_nodes: number
  degraded_nodes: number
  offline_nodes: number
  avg_cpu_percent: number
  avg_memory_percent: number
  avg_disk_percent: number
  total_services: number
  running_services: number
  failed_services: number
  nodes: NodeMetricsDetailed[]
  timestamp: string
}

export interface PerformanceOverview {
  avg_response_time_ms: number
  p50_response_time_ms: number
  p95_response_time_ms: number
  p99_response_time_ms: number
  request_rate: number
  error_rate: number
  trace_count: number
  error_count: number
  timestamp: string
}

export interface NPUFleetMetrics {
  total_npu_nodes: number
  online_npu_nodes: number
  total_workers: number
  active_workers: number
  avg_utilization_percent: number
  total_inferences: number
  avg_inference_time_ms: number
}

export interface UsePrometheusMetricsOptions {
  autoFetch?: boolean
  pollInterval?: number
  useWebSocket?: boolean
}

/**
 * Transport-local wire shapes for the four endpoints whose responses this
 * composable REMAPS rather than assigns. They exist only to type the
 * `slmApiClient.get<T>()` calls that replace an untyped `response.json()`;
 * deriving and naming them from the generated contract is #13138's scope and is
 * deliberately not widened here.
 */
interface DashboardWire {
  fleet_metrics?: {
    avg_cpu_percent?: number
    avg_memory_percent?: number
    avg_disk_percent?: number
    total_services?: number
  }
  health_summary?: {
    overall_status?: string
    health_score?: number
    issues?: string[]
  }
}

interface MonitoringHealthWire {
  overall_status?: string
  health_score?: number
}

interface MonitoringAlertsWire {
  total_count?: number
  critical_count?: number
  warning_count?: number
  alerts?: Record<string, unknown>[]
}

interface NpuNodesWire {
  nodes?: Record<string, unknown>[]
}

// ===== Composable Implementation =====

export function usePrometheusMetrics(options: UsePrometheusMetricsOptions = {}) {
  const { autoFetch = true, pollInterval = 30000 } = options

  // State
  const dashboard = ref<DashboardViewModel | null>(null)
  const services = ref<ServicesSummary | null>(null)
  const alerts = ref<AlertsSummary | null>(null)
  const recommendations = ref<OptimizationRecommendation[]>([])
  const gpuDetails = ref<GPUMetrics | null>(null)
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

  let pollingInterval: ReturnType<typeof setInterval> | null = null

  // ===== Computed Values =====

  const systemHealth = computed<'healthy' | 'degraded' | 'critical' | 'unknown'>(() => {
    if (!services.value) return 'unknown'
    return services.value.overall_status
  })

  const cpuUsage = computed(() => dashboard.value?.system_metrics?.cpu_percent ?? 0)
  const memoryUsage = computed(() => dashboard.value?.system_metrics?.memory_percent ?? 0)
  const diskUsage = computed(() => dashboard.value?.system_metrics?.disk_percent ?? 0)
  const gpuUsage = computed(() => gpuDetails.value?.available ? gpuDetails.value.utilization_percent : 0)
  const npuUsage = computed(() => npuDetails.value?.available ? npuDetails.value.utilization_percent : 0)
  const healthScore = computed(() => dashboard.value?.analysis?.performance_score ?? 0)
  const activeAlertCount = computed(() => alerts.value?.total_count ?? 0)

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

  async function fetchAlerts(): Promise<void> {
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
    } catch (err) {
      logger.error('Failed to fetch alerts:', err)
    }
  }

  async function fetchRecommendations(): Promise<void> {
    // SLM doesn't have a recommendations endpoint yet
    // Return empty recommendations for now
    recommendations.value = []
  }

  async function fetchGPUDetails(): Promise<void> {
    // No GPU metrics endpoint in SLM backend - no GPU nodes in fleet
    gpuDetails.value = {
      available: false,
      utilization_percent: 0,
      memory_utilization_percent: 0,
      temperature_celsius: 0,
      power_watts: 0,
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

  async function fetchFleetMetrics(): Promise<void> {
    try {
      fleetMetrics.value = await slmApiClient.get<FleetMetricsDetailed>(
        '/monitoring/metrics/fleet',
        POLL_OPTS
      )
      error.value = null
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to fetch fleet metrics'
      logger.error('Failed to fetch fleet metrics:', err)
      error.value = message
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

  async function fetchPerformanceOverview(): Promise<void> {
    try {
      performanceOverview.value = await slmApiClient.get<PerformanceOverview>(
        '/performance/overview',
        POLL_OPTS
      )
      error.value = null
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to fetch performance overview'
      logger.error('Failed to fetch performance overview:', err)
      error.value = message
    }
  }

  async function fetchNPUFleetMetrics(): Promise<void> {
    try {
      npuFleetMetrics.value = await slmApiClient.get<NPUFleetMetrics>(
        '/npu/metrics',
        POLL_OPTS
      )
      error.value = null
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to fetch NPU fleet metrics'
      logger.error('Failed to fetch NPU fleet metrics:', err)
      error.value = message
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
        throw new Error(`HTTP ${response.status}: ${response.statusText}`)
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to fetch Prometheus export'
      logger.error('Failed to fetch Prometheus export:', err)
      error.value = message
    }
  }

  async function refreshMetrics(): Promise<void> {
    isLoading.value = true
    try {
      await Promise.all([
        fetchFleetMetrics(),
        fetchPerformanceOverview(),
        fetchNPUFleetMetrics(),
      ])
      lastUpdate.value = new Date()
    } finally {
      isLoading.value = false
    }
  }

  // ===== Polling Methods =====

  function startPolling(): void {
    if (pollingInterval) return
    logger.debug(`Starting polling with interval: ${pollInterval}ms`)
    pollingInterval = setInterval(fetchAll, pollInterval)
  }

  function stopPolling(): void {
    if (pollingInterval) {
      clearInterval(pollingInterval)
      pollingInterval = null
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
    if (autoFetch) {
      fetchAll()
    }
    if (pollInterval > 0) {
      startPolling()
    }
  })

  onUnmounted(() => {
    stopPolling()
  })

  return {
    // State
    dashboard,
    services,
    alerts,
    recommendations,
    gpuDetails,
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
    systemHealth,
    cpuUsage,
    memoryUsage,
    diskUsage,
    gpuUsage,
    npuUsage,
    healthScore,
    activeAlertCount,

    // Methods
    fetchDashboard,
    fetchServices,
    fetchAlerts,
    fetchRecommendations,
    fetchGPUDetails,
    fetchNPUDetails,
    fetchAll,
    startPolling,
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

export default usePrometheusMetrics
