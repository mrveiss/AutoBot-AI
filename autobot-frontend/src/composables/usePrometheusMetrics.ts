// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss
/**
 * Vue Composable for Prometheus Metrics Access
 *
 * Provides real-time access to Prometheus metrics from the backend monitoring API.
 * Supports automatic polling, WebSocket real-time updates, and parsed metric data.
 *
 * All metrics are fetched from real backend endpoints - no mock data.
 * Resolved: Issue #76 - Replaced mockup data with real backend metrics
 */

import { ref, computed, onMounted, onUnmounted } from 'vue'
import type { Ref, ComputedRef } from 'vue'
import { useApi } from './useApi'
import { createLogger } from '@/utils/debugUtils'

// Create scoped logger
const logger = createLogger('usePrometheusMetrics')

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
  // Issue #469: Extended fields for Prometheus metrics
  gpu_id?: string
  thermal_throttling?: boolean
  power_throttling?: boolean
}

export interface NPUMetrics {
  available: boolean
  utilization_percent: number
  acceleration_ratio: number
  inference_count: number
  wsl_limitation?: boolean
  // Issue #469: Extended fields for Prometheus metrics
  hardware_detected?: boolean
  driver_available?: boolean
  openvino_support?: boolean
}

// Issue #469: Performance metrics from Prometheus
export interface PerformanceScores {
  performance_score: number
  health_score: number
  bottlenecks: string[]
}

export interface MultiModalMetrics {
  text_processing_ms: number
  image_processing_ms: number
  audio_processing_ms: number
  operations_total: number
  success_rate: number
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

/**
 * Performance alert from monitoring system.
 * Issue #474: Extended to support AlertManager fields.
 */
export interface PerformanceAlert {
  category: string
  severity: 'info' | 'warning' | 'critical' | 'high'
  message: string
  recommendation: string
  timestamp: number
  // Issue #474: AlertManager-specific fields (optional for backward compatibility)
  source?: 'alertmanager' | 'autobot_monitor'
  alertname?: string
  fingerprint?: string
  description?: string
  starts_at?: string
  ends_at?: string | null
  status?: string
  labels?: Record<string, string>
}

/**
 * Alert summary from backend.
 * Issue #474: Extended to include high_count and source breakdown.
 */
export interface AlertsSummary {
  total_count: number
  critical_count: number
  warning_count: number
  high_count?: number  // Issue #474: Added for AlertManager severity
  alerts: PerformanceAlert[]
  sources?: {
    alertmanager: number
    autobot_monitor: number
  }
}

export interface OptimizationRecommendation {
  category: string
  priority: 'high' | 'medium' | 'low'
  recommendation: string
  action: string
  expected_improvement: string
}

export interface DashboardAnalysis {
  overall_health: string
  performance_score: number
  bottlenecks: string[]
  resource_utilization: Record<string, number>
}

export interface DashboardOverview {
  system_metrics?: SystemMetrics
  gpu_metrics?: GPUMetrics
  npu_metrics?: NPUMetrics
  hardware_acceleration?: Record<string, boolean>
  analysis?: DashboardAnalysis
  timestamp?: number
}

export interface WorkflowMetrics {
  active_workflows: number
  executions_total: number
  success_rate: number
  avg_duration_seconds: number
}

export interface GithubMetrics {
  operations_total: number
  rate_limit_remaining: number
  commits_today: number
  pull_requests_open: number
  issues_open: number
}

export interface PrometheusMetricsState {
  // Core metrics
  dashboard: Ref<DashboardOverview | null>
  services: Ref<ServicesSummary | null>
  alerts: Ref<AlertsSummary | null>
  recommendations: Ref<OptimizationRecommendation[]>

  // Hardware metrics
  gpuDetails: Ref<GPUMetrics | null>
  npuDetails: Ref<NPUMetrics | null>

  // Status
  isLoading: Ref<boolean>
  error: Ref<string | null>
  lastUpdate: Ref<Date | null>
  isConnected: Ref<boolean>
}

export interface UsePrometheusMetricsOptions {
  /** Auto-fetch on mount (default: true) */
  autoFetch?: boolean
  /** Polling interval in milliseconds (default: 30000 = 30s) */
  pollInterval?: number
  /** Enable WebSocket real-time updates (default: false) */
  useWebSocket?: boolean
  /** WebSocket update interval in seconds (default: 2) */
  wsUpdateInterval?: number
}

export interface UsePrometheusMetricsReturn extends PrometheusMetricsState {
  // Computed values
  systemHealth: ComputedRef<'healthy' | 'degraded' | 'critical' | 'unknown'>
  cpuUsage: ComputedRef<number>
  memoryUsage: ComputedRef<number>
  diskUsage: ComputedRef<number>
  gpuUsage: ComputedRef<number>
  npuUsage: ComputedRef<number>
  healthScore: ComputedRef<number>
  activeAlertCount: ComputedRef<number>

  // Methods
  fetchDashboard: () => Promise<void>
  fetchServices: () => Promise<void>
  fetchAlerts: () => Promise<void>
  fetchRecommendations: () => Promise<void>
  fetchGPUDetails: () => Promise<void>
  fetchNPUDetails: () => Promise<void>
  fetchAll: () => Promise<void>
  startPolling: () => void
  stopPolling: () => void
  connectWebSocket: () => void
  disconnectWebSocket: () => void
  refresh: () => Promise<void>
}

// ===== Composable Implementation =====

export function usePrometheusMetrics(
  options: UsePrometheusMetricsOptions = {}
): UsePrometheusMetricsReturn {
  const {
    autoFetch = true,
    pollInterval = 30000,
    useWebSocket = false,
    wsUpdateInterval = 2
  } = options

  // Get API client
  const api = useApi()

  // State
  const dashboard = ref<DashboardOverview | null>(null)
  const services = ref<ServicesSummary | null>(null)
  const alerts = ref<AlertsSummary | null>(null)
  const recommendations = ref<OptimizationRecommendation[]>([])
  const gpuDetails = ref<GPUMetrics | null>(null)
  const npuDetails = ref<NPUMetrics | null>(null)

  const isLoading = ref(false)
  const error = ref<string | null>(null)
  const lastUpdate = ref<Date | null>(null)
  const isConnected = ref(false)

  // Polling and WebSocket state
  let pollingInterval: ReturnType<typeof setInterval> | null = null
  let websocket: WebSocket | null = null

  // ===== Computed Values =====

  const systemHealth = computed<'healthy' | 'degraded' | 'critical' | 'unknown'>(() => {
    if (!services.value) return 'unknown'
    return services.value.overall_status
  })

  const cpuUsage = computed(() => {
    return dashboard.value?.system_metrics?.cpu_percent ?? 0
  })

  const memoryUsage = computed(() => {
    return dashboard.value?.system_metrics?.memory_percent ?? 0
  })

  const diskUsage = computed(() => {
    return dashboard.value?.system_metrics?.disk_percent ?? 0
  })

  const gpuUsage = computed(() => {
    if (!gpuDetails.value?.available) return 0
    return gpuDetails.value.utilization_percent ?? 0
  })

  const npuUsage = computed(() => {
    if (!npuDetails.value?.available) return 0
    return npuDetails.value.utilization_percent ?? 0
  })

  const healthScore = computed(() => {
    return dashboard.value?.analysis?.performance_score ?? 0
  })

  const activeAlertCount = computed(() => {
    return alerts.value?.total_count ?? 0
  })

  // ===== API Methods =====

  async function fetchDashboard(): Promise<void> {
    try {
      const response = await api.get('/api/monitoring/dashboard/overview')
      if (response.ok) {
        dashboard.value = await response.json()
        lastUpdate.value = new Date()
        error.value = null
      } else {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`)
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to fetch dashboard'
      logger.error('Failed to fetch dashboard:', err)
      error.value = message
    }
  }

  async function fetchServices(): Promise<void> {
    try {
      const response = await api.get('/api/monitoring/services/health')
      if (response.ok) {
        services.value = await response.json()
        error.value = null
      } else {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`)
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to fetch services'
      logger.error('Failed to fetch services:', err)
      error.value = message
    }
  }

  async function fetchAlerts(): Promise<void> {
    try {
      const response = await api.get('/api/monitoring/alerts/check')
      if (response.ok) {
        alerts.value = await response.json()
        error.value = null
      } else {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`)
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to fetch alerts'
      logger.error('Failed to fetch alerts:', err)
      error.value = message
    }
  }

  async function fetchRecommendations(): Promise<void> {
    try {
      const response = await api.get('/api/monitoring/optimization/recommendations')
      if (response.ok) {
        recommendations.value = await response.json()
        error.value = null
      } else {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`)
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to fetch recommendations'
      logger.error('Failed to fetch recommendations:', err)
      error.value = message
    }
  }

  async function fetchGPUDetails(): Promise<void> {
    try {
      const response = await api.get('/api/monitoring/hardware/gpu')
      if (response.ok) {
        gpuDetails.value = await response.json()
        error.value = null
      } else {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`)
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to fetch GPU details'
      logger.error('Failed to fetch GPU details:', err)
      error.value = message
    }
  }

  async function fetchNPUDetails(): Promise<void> {
    try {
      const response = await api.get('/api/monitoring/hardware/npu')
      if (response.ok) {
        npuDetails.value = await response.json()
        error.value = null
      } else {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`)
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to fetch NPU details'
      logger.error('Failed to fetch NPU details:', err)
      error.value = message
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
        fetchNPUDetails()
      ])
      lastUpdate.value = new Date()
    } finally {
      isLoading.value = false
    }
  }

  async function refresh(): Promise<void> {
    await fetchAll()
  }

  // ===== Polling Methods =====

  function startPolling(): void {
    if (pollingInterval) return // Already polling

    logger.debug(`Starting polling with interval: ${pollInterval}ms`)
    pollingInterval = setInterval(() => {
      fetchAll()
    }, pollInterval)
  }

  function stopPolling(): void {
    if (pollingInterval) {
      clearInterval(pollingInterval)
      pollingInterval = null
      logger.debug('Polling stopped')
    }
  }

  // ===== WebSocket Methods =====

  function connectWebSocket(): void {
    if (websocket) return // Already connected

    const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const wsHost = import.meta.env.VITE_API_BASE_URL?.replace(/^https?:\/\//, '') ||
                   `${import.meta.env.VITE_BACKEND_HOST || window.location.hostname}:${import.meta.env.VITE_BACKEND_PORT || '8443'}`
    const wsUrl = `${wsProtocol}//${wsHost}/api/monitoring/realtime`

    logger.debug(`Connecting WebSocket to: ${wsUrl}`)

    try {
      websocket = new WebSocket(wsUrl)

      websocket.onopen = () => {
        isConnected.value = true
        logger.info('WebSocket connected')

        // Request update interval
        if (websocket && websocket.readyState === WebSocket.OPEN) {
          websocket.send(JSON.stringify({
            type: 'update_interval',
            interval: wsUpdateInterval
          }))
        }
      }

      websocket.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data)

          if (data.type === 'performance_update' && data.data) {
            // Update dashboard with real-time data
            dashboard.value = {
              ...dashboard.value,
              ...data.data,
              timestamp: data.timestamp
            }
            lastUpdate.value = new Date()
          } else if (data.type === 'performance_alerts' && data.alerts) {
            // Update alerts
            alerts.value = {
              ...alerts.value,
              alerts: data.alerts,
              total_count: data.alerts.length,
              timestamp: data.timestamp
            } as AlertsSummary
          }
        } catch (err) {
          logger.warn('Failed to parse WebSocket message:', err)
        }
      }

      websocket.onerror = (event) => {
        logger.error('WebSocket error:', event)
        error.value = 'WebSocket connection error'
      }

      websocket.onclose = () => {
        isConnected.value = false
        websocket = null
        logger.info('WebSocket disconnected')
      }
    } catch (err) {
      logger.error('Failed to create WebSocket connection:', err)
      error.value = 'Failed to establish WebSocket connection'
    }
  }

  function disconnectWebSocket(): void {
    if (websocket) {
      websocket.close()
      websocket = null
      isConnected.value = false
      logger.debug('WebSocket disconnected')
    }
  }

  // ===== Lifecycle =====

  onMounted(() => {
    if (autoFetch) {
      fetchAll()
    }

    if (useWebSocket) {
      connectWebSocket()
    } else if (pollInterval > 0) {
      startPolling()
    }
  })

  onUnmounted(() => {
    stopPolling()
    disconnectWebSocket()
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
    refresh
  }
}

// ===== Specialized Composables =====

/**
 * Simplified composable for system metrics only
 * Lighter weight for components that just need basic metrics
 */
export function useSystemMetrics(pollInterval = 10000) {
  const api = useApi()

  const metrics = ref<SystemMetrics | null>(null)
  const isLoading = ref(false)
  const error = ref<string | null>(null)

  let interval: ReturnType<typeof setInterval> | null = null

  async function fetch() {
    isLoading.value = true
    try {
      const response = await api.get('/api/monitoring/metrics/current')
      if (response.ok) {
        const data = await response.json()
        metrics.value = data.metrics?.system || null
        error.value = null
      }
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Failed to fetch metrics'
    } finally {
      isLoading.value = false
    }
  }

  function startPolling() {
    if (interval) return
    fetch()
    interval = setInterval(fetch, pollInterval)
  }

  function stopPolling() {
    if (interval) {
      clearInterval(interval)
      interval = null
    }
  }

  onMounted(() => {
    startPolling()
  })

  onUnmounted(() => {
    stopPolling()
  })

  return {
    metrics,
    isLoading,
    error,
    fetch,
    startPolling,
    stopPolling
  }
}

/**
 * Composable for service health monitoring
 * Optimized for the service status panel
 */
export function useServiceHealth(pollInterval = 15000) {
  const api = useApi()

  const services = ref<ServiceHealth[]>([])
  const summary = ref<Pick<ServicesSummary, 'total_services' | 'healthy_services' | 'degraded_services' | 'critical_services' | 'overall_status' | 'health_percentage'> | null>(null)
  const isLoading = ref(false)
  const error = ref<string | null>(null)

  let interval: ReturnType<typeof setInterval> | null = null

  async function fetch() {
    isLoading.value = true
    try {
      const response = await api.get('/api/monitoring/services/health')
      if (response.ok) {
        const data: ServicesSummary = await response.json()
        services.value = data.services || []
        summary.value = {
          total_services: data.total_services,
          healthy_services: data.healthy_services,
          degraded_services: data.degraded_services,
          critical_services: data.critical_services,
          overall_status: data.overall_status,
          health_percentage: data.health_percentage
        }
        error.value = null
      }
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Failed to fetch services'
    } finally {
      isLoading.value = false
    }
  }

  const healthyCount = computed(() => summary.value?.healthy_services ?? 0)
  const totalCount = computed(() => summary.value?.total_services ?? 0)
  const healthPercentage = computed(() => summary.value?.health_percentage ?? 0)
  const overallStatus = computed(() => summary.value?.overall_status ?? 'unknown')

  function startPolling() {
    if (interval) return
    fetch()
    interval = setInterval(fetch, pollInterval)
  }

  function stopPolling() {
    if (interval) {
      clearInterval(interval)
      interval = null
    }
  }

  onMounted(() => {
    startPolling()
  })

  onUnmounted(() => {
    stopPolling()
  })

  return {
    services,
    summary,
    healthyCount,
    totalCount,
    healthPercentage,
    overallStatus,
    isLoading,
    error,
    fetch,
    startPolling,
    stopPolling
  }
}

/**
 * Composable for alert monitoring
 * Optimized for alert notifications and summaries
 *
 * Issue #474: Now fetches alerts from both Prometheus AlertManager and AutoBot
 * internal monitor. AlertManager alerts include richer metadata.
 */
export function useAlerts(pollInterval = 30000) {
  const api = useApi()

  const alerts = ref<PerformanceAlert[]>([])
  const criticalCount = ref(0)
  const warningCount = ref(0)
  const highCount = ref(0)  // Issue #474: Added for AlertManager 'high' severity
  const totalCount = ref(0)
  const isLoading = ref(false)
  const error = ref<string | null>(null)
  // Issue #474: Track alert sources
  const sources = ref<{ alertmanager: number; autobot_monitor: number }>({
    alertmanager: 0,
    autobot_monitor: 0
  })

  let interval: ReturnType<typeof setInterval> | null = null

  async function fetch() {
    isLoading.value = true
    try {
      const response = await api.get('/api/monitoring/alerts/check')
      if (response.ok) {
        const data: AlertsSummary = await response.json()
        alerts.value = data.alerts || []
        criticalCount.value = data.critical_count
        warningCount.value = data.warning_count
        highCount.value = data.high_count || 0  // Issue #474
        totalCount.value = data.total_count
        // Issue #474: Track sources
        if (data.sources) {
          sources.value = data.sources
        }
        error.value = null
      }
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Failed to fetch alerts'
    } finally {
      isLoading.value = false
    }
  }

  const hasCritical = computed(() => criticalCount.value > 0)
  const hasWarning = computed(() => warningCount.value > 0)
  const hasHigh = computed(() => highCount.value > 0)  // Issue #474
  const hasAlerts = computed(() => totalCount.value > 0)
  // Issue #474: Computed for AlertManager-specific alerts
  const alertmanagerAlerts = computed(() =>
    alerts.value.filter(a => a.source === 'alertmanager')
  )

  function startPolling() {
    if (interval) return
    fetch()
    interval = setInterval(fetch, pollInterval)
  }

  function stopPolling() {
    if (interval) {
      clearInterval(interval)
      interval = null
    }
  }

  onMounted(() => {
    startPolling()
  })

  onUnmounted(() => {
    stopPolling()
  })

  return {
    alerts,
    criticalCount,
    warningCount,
    highCount,  // Issue #474
    totalCount,
    hasCritical,
    hasWarning,
    hasHigh,  // Issue #474
    hasAlerts,
    alertmanagerAlerts,  // Issue #474
    sources,  // Issue #474
    isLoading,
    error,
    fetch,
    startPolling,
    stopPolling
  }
}

export default usePrometheusMetrics
