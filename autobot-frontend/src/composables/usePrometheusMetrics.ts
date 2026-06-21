// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
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

import { ref, computed, onMounted, getCurrentInstance } from 'vue'
import type { Ref, ComputedRef } from 'vue'
import { useApiClient } from '@/plugins/api'
import { createLogger } from '@/utils/debugUtils'
import { getApiBase } from '@/config/ssot-config'
import { useWebSocket } from '@/composables/useWebSocket'
import { usePollingJob } from '@/composables/usePollingJob'
import { useLoadingState } from './useLoadingState'

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
    useWebSocket: enableWebSocket = false,
    wsUpdateInterval = 2
  } = options

  // Get API client
  const api = useApiClient()

  // State
  const dashboard = ref<DashboardOverview | null>(null)
  const services = ref<ServicesSummary | null>(null)
  const alerts = ref<AlertsSummary | null>(null)
  const recommendations = ref<OptimizationRecommendation[]>([])
  const gpuDetails = ref<GPUMetrics | null>(null)
  const npuDetails = ref<NPUMetrics | null>(null)

  const { isLoading, wrap } = useLoadingState()
  const error = ref<string | null>(null)
  const lastUpdate = ref<Date | null>(null)
  const isConnected = ref(false)

  // Build the monitoring WebSocket URL
  const _buildWsUrl = (): string => {
    const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const wsHost = import.meta.env.VITE_API_BASE_URL?.replace(/^https?:\/\//, '') ||
                   `${import.meta.env.VITE_BACKEND_HOST || window.location.hostname}:${import.meta.env.VITE_BACKEND_PORT || '8443'}`
    return `${wsProtocol}//${wsHost}/api/monitoring/realtime`
  }

  // WebSocket managed via useWebSocket composable
  const {
    isConnected: wsIsConnected,
    send: wsSend,
    connect: wsConnect,
    disconnect: wsDisconnectInner,
  } = useWebSocket(_buildWsUrl(), {
    autoConnect: false,
    autoReconnect: false,
    parseJSON: false,
    onOpen: () => {
      isConnected.value = true
      logger.info('WebSocket connected')
      wsSend(JSON.stringify({
        type: 'update_interval',
        interval: wsUpdateInterval,
      }))
    },
    onClose: () => {
      isConnected.value = false
      logger.info('WebSocket disconnected')
    },
    onError: (event: Event) => {
      logger.error('WebSocket error:', event)
      error.value = 'WebSocket connection error'
    },
    onMessage: (data: unknown) => {
      if (typeof data !== 'string') return
      try {
        const msg = JSON.parse(data)
        if (msg.type === 'performance_update' && msg.data) {
          dashboard.value = {
            ...dashboard.value,
            ...msg.data,
            timestamp: msg.timestamp,
          }
          lastUpdate.value = new Date()
        } else if (msg.type === 'performance_alerts' && msg.alerts) {
          alerts.value = {
            ...alerts.value,
            alerts: msg.alerts,
            total_count: msg.alerts.length,
            timestamp: msg.timestamp,
          } as AlertsSummary
        }
      } catch (err) {
        logger.warn('Failed to parse WebSocket message:', err)
      }
    },
  })

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
      dashboard.value = await api.get<DashboardOverview>(`${getApiBase()}/monitoring/dashboard/overview`)
      lastUpdate.value = new Date()
      error.value = null
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to fetch dashboard'
      logger.error('Failed to fetch dashboard:', err)
      error.value = message
    }
  }

  async function fetchServices(): Promise<void> {
    try {
      services.value = await api.get<ServicesSummary>(`${getApiBase()}/monitoring/services/health`)
      error.value = null
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to fetch services'
      logger.error('Failed to fetch services:', err)
      error.value = message
    }
  }

  async function fetchAlerts(): Promise<void> {
    try {
      alerts.value = await api.get<AlertsSummary>(`${getApiBase()}/monitoring/alerts/check`)
      error.value = null
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to fetch alerts'
      logger.error('Failed to fetch alerts:', err)
      error.value = message
    }
  }

  async function fetchRecommendations(): Promise<void> {
    try {
      recommendations.value = await api.get<OptimizationRecommendation[]>(`${getApiBase()}/monitoring/optimization/recommendations`)
      error.value = null
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to fetch recommendations'
      logger.error('Failed to fetch recommendations:', err)
      error.value = message
    }
  }

  async function fetchGPUDetails(): Promise<void> {
    try {
      gpuDetails.value = await api.get<GPUMetrics>(`${getApiBase()}/monitoring/hardware/gpu`)
      error.value = null
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to fetch GPU details'
      logger.error('Failed to fetch GPU details:', err)
      error.value = message
    }
  }

  async function fetchNPUDetails(): Promise<void> {
    try {
      npuDetails.value = await api.get<NPUMetrics>(`${getApiBase()}/monitoring/hardware/npu`)
      error.value = null
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to fetch NPU details'
      logger.error('Failed to fetch NPU details:', err)
      error.value = message
    }
  }

  async function fetchAll(): Promise<void> {
    return wrap(async () => {
      await Promise.all([
        fetchDashboard(),
        fetchServices(),
        fetchAlerts(),
        fetchRecommendations(),
        fetchGPUDetails(),
        fetchNPUDetails()
      ])
      lastUpdate.value = new Date()
    })
  }

  async function refresh(): Promise<void> {
    await fetchAll()
  }

  // ===== Polling Methods =====

  const { start: _startDashboardPoller, stop: stopPolling } = usePollingJob<void>(
    async () => { await fetchAll() },
    { intervalMs: pollInterval }
  )

  function startPolling(): void {
    logger.debug(`Starting polling with interval: ${pollInterval}ms`)
    _startDashboardPoller('')
  }

  // ===== WebSocket Methods =====

  function connectWebSocket(): void {
    if (wsIsConnected.value) return // Already connected
    logger.debug('Connecting WebSocket to monitoring endpoint')
    wsConnect()
  }

  function disconnectWebSocket(): void {
    wsDisconnectInner()
    isConnected.value = false
  }

  // ===== Lifecycle =====

  if (getCurrentInstance()) {
    onMounted(() => {
      if (autoFetch) {
        fetchAll()
      }

      if (enableWebSocket) {
        connectWebSocket()
      } else if (pollInterval > 0) {
        startPolling()
      }
    })
  }

  // usePollingJob handles polling cleanup via its own onScopeDispose hook.
  // useWebSocket handles WebSocket cleanup via its own scope-dispose hook.

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
  const api = useApiClient()

  const metrics = ref<SystemMetrics | null>(null)
  const { isLoading, wrap } = useLoadingState()
  const error = ref<string | null>(null)

  async function fetch() {
    return wrap(async () => {
      try {
        const data = await api.get<{ metrics?: { system?: SystemMetrics } }>(`${getApiBase()}/monitoring/metrics/current`)
        metrics.value = data.metrics?.system || null
        error.value = null
      } catch (err) {
        error.value = err instanceof Error ? err.message : 'Failed to fetch metrics'
      }
    })
  }

  const { start: startPolling, stop: stopPolling } = usePollingJob<void>(
    async () => { await fetch() },
    { intervalMs: pollInterval }
  )

  if (getCurrentInstance()) {
    onMounted(() => {
      startPolling('')
    })
  }

  return {
    metrics,
    isLoading,
    error,
    fetch,
    startPolling: () => startPolling(''),
    stopPolling
  }
}

/**
 * Composable for service health monitoring
 * Optimized for the service status panel
 */
export function useServiceHealth(pollInterval = 15000) {
  const api = useApiClient()

  const services = ref<ServiceHealth[]>([])
  const summary = ref<Pick<ServicesSummary, 'total_services' | 'healthy_services' | 'degraded_services' | 'critical_services' | 'overall_status' | 'health_percentage'> | null>(null)
  const { isLoading, wrap } = useLoadingState()
  const error = ref<string | null>(null)

  async function fetch() {
    return wrap(async () => {
      try {
        const data = await api.get<ServicesSummary>(`${getApiBase()}/monitoring/services/health`)
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
      } catch (err) {
        error.value = err instanceof Error ? err.message : 'Failed to fetch services'
      }
    })
  }

  const healthyCount = computed(() => summary.value?.healthy_services ?? 0)
  const totalCount = computed(() => summary.value?.total_services ?? 0)
  const healthPercentage = computed(() => summary.value?.health_percentage ?? 0)
  const overallStatus = computed(() => summary.value?.overall_status ?? 'unknown')

  const { start: startPolling, stop: stopPolling } = usePollingJob<void>(
    async () => { await fetch() },
    { intervalMs: pollInterval }
  )

  if (getCurrentInstance()) {
    onMounted(() => {
      startPolling('')
    })
  }

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
    startPolling: () => startPolling(''),
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
  const api = useApiClient()

  const alerts = ref<PerformanceAlert[]>([])
  const criticalCount = ref(0)
  const warningCount = ref(0)
  const highCount = ref(0)  // Issue #474: Added for AlertManager 'high' severity
  const totalCount = ref(0)
  const { isLoading, wrap } = useLoadingState()
  const error = ref<string | null>(null)
  // Issue #474: Track alert sources
  const sources = ref<{ alertmanager: number; autobot_monitor: number }>({
    alertmanager: 0,
    autobot_monitor: 0
  })

  async function fetch() {
    return wrap(async () => {
      try {
        const data = await api.get<AlertsSummary>(`${getApiBase()}/monitoring/alerts/check`)
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
      } catch (err) {
        error.value = err instanceof Error ? err.message : 'Failed to fetch alerts'
      }
    })
  }

  const hasCritical = computed(() => criticalCount.value > 0)
  const hasWarning = computed(() => warningCount.value > 0)
  const hasHigh = computed(() => highCount.value > 0)  // Issue #474
  const hasAlerts = computed(() => totalCount.value > 0)
  // Issue #474: Computed for AlertManager-specific alerts
  const alertmanagerAlerts = computed(() =>
    alerts.value.filter((a: PerformanceAlert) => a.source === 'alertmanager')
  )

  const { start: startPolling, stop: stopPolling } = usePollingJob<void>(
    async () => { await fetch() },
    { intervalMs: pollInterval }
  )

  if (getCurrentInstance()) {
    onMounted(() => {
      startPolling('')
    })
  }

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
    startPolling: () => startPolling(''),
    stopPolling
  }
}

export default usePrometheusMetrics
