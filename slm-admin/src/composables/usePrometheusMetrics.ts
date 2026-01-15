// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * Prometheus Metrics Composable for SLM Admin
 *
 * Provides access to monitoring metrics from the main AutoBot backend.
 * Used for GPU/NPU metrics, service health, and performance monitoring.
 */

import { ref, computed, onMounted, onUnmounted } from 'vue'
import type { Ref, ComputedRef } from 'vue'
import { getBackendUrl } from '@/config/ssot-config'
import { createLogger } from '@/utils/debugUtils'

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

export interface UsePrometheusMetricsOptions {
  autoFetch?: boolean
  pollInterval?: number
  useWebSocket?: boolean
}

// ===== Composable Implementation =====

export function usePrometheusMetrics(options: UsePrometheusMetricsOptions = {}) {
  const { autoFetch = true, pollInterval = 30000 } = options

  const backendUrl = getBackendUrl()

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
      const response = await fetch(`${backendUrl}/monitoring/dashboard/overview`)
      if (response.ok) {
        dashboard.value = await response.json()
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
      const response = await fetch(`${backendUrl}/api/monitoring/services/health`)
      if (response.ok) {
        services.value = await response.json()
        error.value = null
      }
    } catch (err) {
      logger.error('Failed to fetch services:', err)
    }
  }

  async function fetchAlerts(): Promise<void> {
    try {
      const response = await fetch(`${backendUrl}/api/monitoring/alerts/check`)
      if (response.ok) {
        alerts.value = await response.json()
        error.value = null
      }
    } catch (err) {
      logger.error('Failed to fetch alerts:', err)
    }
  }

  async function fetchRecommendations(): Promise<void> {
    try {
      const response = await fetch(`${backendUrl}/api/monitoring/optimization/recommendations`)
      if (response.ok) {
        recommendations.value = await response.json()
        error.value = null
      }
    } catch (err) {
      logger.error('Failed to fetch recommendations:', err)
    }
  }

  async function fetchGPUDetails(): Promise<void> {
    try {
      const response = await fetch(`${backendUrl}/api/monitoring/hardware/gpu`)
      if (response.ok) {
        gpuDetails.value = await response.json()
        error.value = null
      }
    } catch (err) {
      logger.error('Failed to fetch GPU details:', err)
    }
  }

  async function fetchNPUDetails(): Promise<void> {
    try {
      const response = await fetch(`${backendUrl}/api/monitoring/hardware/npu`)
      if (response.ok) {
        npuDetails.value = await response.json()
        error.value = null
      }
    } catch (err) {
      logger.error('Failed to fetch NPU details:', err)
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
  }
}

export default usePrometheusMetrics
