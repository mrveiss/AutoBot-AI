// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
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
import { useAuthStore } from '@/stores/auth'

const logger = createLogger('usePrometheusMetrics')

// SLM Admin uses the local SLM backend API
const API_BASE = '/api'

// ===== Type Definitions =====

export interface SystemMetrics {
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

export interface DashboardOverview {
  system_metrics?: SystemMetrics
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

// ===== Composable Implementation =====

export function usePrometheusMetrics(options: UsePrometheusMetricsOptions = {}) {
  const { autoFetch = true, pollInterval = 30000 } = options

  const authStore = useAuthStore()

  // Helper to get auth headers
  function getHeaders(): Record<string, string> {
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
    }
    if (authStore.token) {
      headers.Authorization = `Bearer ${authStore.token}`
    }
    return headers
  }

  // State
  const dashboard = ref<DashboardOverview | null>(null)
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
      const response = await fetch(`${API_BASE}/monitoring/dashboard`, {
        headers: getHeaders(),
      })
      if (response.ok) {
        const data = await response.json()
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
      } else {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`)
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to fetch dashboard'
      logger.error('Failed to fetch dashboard:', err)
      error.value = message
      isConnected.value = false
    }
  }

  async function fetchServices(): Promise<void> {
    try {
      const response = await fetch(`${API_BASE}/monitoring/health`, {
        headers: getHeaders(),
      })
      if (response.ok) {
        const data = await response.json()
        // Map SLM health response to services format
        services.value = {
          total_services: 0,
          healthy_services: 0,
          degraded_services: 0,
          critical_services: 0,
          overall_status: data.overall_status === 'healthy' ? 'healthy' :
                          data.overall_status === 'degraded' ? 'degraded' : 'critical',
          health_percentage: data.health_score,
          services: [],
        }
        error.value = null
      }
    } catch (err) {
      logger.error('Failed to fetch services:', err)
    }
  }

  async function fetchAlerts(): Promise<void> {
    try {
      const response = await fetch(`${API_BASE}/monitoring/alerts`, {
        headers: getHeaders(),
      })
      if (response.ok) {
        const data = await response.json()
        alerts.value = {
          total_count: data.total_count ?? 0,
          critical_count: data.critical_count ?? 0,
          warning_count: data.warning_count ?? 0,
          alerts: (data.alerts ?? []).map((a: Record<string, unknown>) => ({
            category: String(a.category ?? ''),
            severity: String(a.severity ?? 'info'),
            message: String(a.message ?? ''),
            recommendation: '',
            timestamp: new Date(String(a.timestamp ?? '')).getTime(),
          })),
        }
        error.value = null
      }
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
      const response = await fetch(`${API_BASE}/npu/nodes`, {
        headers: getHeaders(),
      })
      if (response.ok) {
        const data = await response.json()
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
      const response = await fetch(`${API_BASE}/monitoring/metrics/fleet`, {
        headers: getHeaders(),
      })
      if (response.ok) {
        fleetMetrics.value = await response.json()
        error.value = null
      } else {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`)
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to fetch fleet metrics'
      logger.error('Failed to fetch fleet metrics:', err)
      error.value = message
    }
  }

  async function fetchNodeMetricsDetailed(nodeId: string): Promise<void> {
    try {
      const response = await fetch(`${API_BASE}/monitoring/metrics/node/${nodeId}`, {
        headers: getHeaders(),
      })
      if (response.ok) {
        const data = await response.json()
        nodeMetrics.value.set(nodeId, data)
        error.value = null
      } else {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`)
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to fetch node metrics'
      logger.error(`Failed to fetch node metrics for ${nodeId}:`, err)
      error.value = message
    }
  }

  async function fetchPerformanceOverview(): Promise<void> {
    try {
      const response = await fetch(`${API_BASE}/performance/overview`, {
        headers: getHeaders(),
      })
      if (response.ok) {
        performanceOverview.value = await response.json()
        error.value = null
      } else {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`)
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to fetch performance overview'
      logger.error('Failed to fetch performance overview:', err)
      error.value = message
    }
  }

  async function fetchNPUFleetMetrics(): Promise<void> {
    try {
      const response = await fetch(`${API_BASE}/npu/metrics`, {
        headers: getHeaders(),
      })
      if (response.ok) {
        npuFleetMetrics.value = await response.json()
        error.value = null
      } else {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`)
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to fetch NPU fleet metrics'
      logger.error('Failed to fetch NPU fleet metrics:', err)
      error.value = message
    }
  }

  async function fetchPrometheusExport(): Promise<void> {
    try {
      const response = await fetch(`${API_BASE}/performance/metrics/prometheus`, {
        headers: getHeaders(),
      })
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
