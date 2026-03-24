// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * Composable: useDashboardLoaders
 *
 * Encapsulates the dashboard overview panel data loaders for the
 * Enhanced Analytics Dashboard Cards section: system overview,
 * communication patterns, code quality, and performance metrics.
 *
 * Issue #1579: Extracted from CodebaseAnalytics.vue
 */

import { ref } from 'vue'
import { fetchWithAuth } from '@/utils/fetchWithAuth'
import appConfig from '@/config/AppConfig.js'
import { useBackgroundTask } from '@/composables/useBackgroundTask'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('useDashboardLoaders')

export interface SystemOverviewData {
  api_requests_per_minute: number
  average_response_time: number
  active_connections: number
  system_health: string
}

export interface CommunicationPatternsData {
  websocket_connections: number
  api_call_frequency: number
  data_transfer_rate: number
  unique_endpoints: number
}

export interface CodeQualityData {
  overall_score: number
  test_coverage: number
  code_duplicates: number
  technical_debt: number
}

export interface PerformanceMetricsData {
  efficiency_score: number
  memory_usage: number
  cpu_usage: number
  load_time: number
}

export interface UseDashboardLoadersDeps {
  /** Helper that appends ?source_id= to a URL. */
  withSourceId: (url: string) => string
  /** Additional refresh callbacks to run during refreshAllMetrics. */
  additionalRefreshCallbacks: () => Promise<void>[]
}

export function useDashboardLoaders(deps: UseDashboardLoadersDeps) {
  const dashboardTask = useBackgroundTask('/api/analytics/dashboard/overview')

  const systemOverview = ref<SystemOverviewData | null>(null)
  const communicationPatterns = ref<CommunicationPatternsData | null>(null)
  const codeQuality = ref<CodeQualityData | null>(null)
  const performanceMetrics = ref<PerformanceMetricsData | null>(null)
  const realTimeEnabled = ref(false)
  const refreshInterval = ref<ReturnType<typeof setInterval> | null>(null)

  const loadSystemOverview = async () => {
    try {
      const ok = await dashboardTask.start()
      if (ok && dashboardTask.result.value) {
        const result = dashboardTask.result.value as Record<string, unknown>

        const commPatterns = (result.communication_patterns || {}) as Record<string, unknown>
        const perfMetrics = (result.performance_metrics || {}) as Record<string, unknown>
        const sysHealth = (result.system_health || {}) as Record<string, unknown>
        const realtimeMetrics = (result.realtime_metrics || {}) as Record<string, unknown>

        const totalCalls = (commPatterns.total_api_calls as number) || 0
        const avgResponseTime = (commPatterns.avg_response_time as number)
          || (perfMetrics.avg_response_time as number) || 0
        const activeConns = (realtimeMetrics.active_connections as Record<string, unknown>)
        const activeConnections = (sysHealth.active_connections as number)
          || (activeConns?.value as number) || 0

        let healthStatus = 'Unknown'
        if (sysHealth.status) {
          healthStatus = sysHealth.status as string
        } else if (sysHealth.cpu_percent !== undefined) {
          healthStatus = (sysHealth.cpu_percent as number) < 80 ? 'Healthy' : 'Warning'
        }

        systemOverview.value = {
          api_requests_per_minute: totalCalls,
          average_response_time: Math.round(avgResponseTime * 1000),
          active_connections: activeConnections,
          system_health: healthStatus,
        }
      }
    } catch (error: unknown) {
      logger.error('loadSystemOverview failed:', error)
      systemOverview.value = null
    }
  }

  const loadCommunicationPatterns = async () => {
    try {
      const backendUrl = await appConfig.getServiceUrl('backend')
      const response = await fetchWithAuth(`${backendUrl}/api/analytics/communication/patterns`)

      if (!response.ok) {
        throw new Error(`Status ${response.status}`)
      }

      const result = await response.json()

      const wsActivity = result.websocket_activity || {}
      const apiPatterns = result.api_patterns || []
      const totalCalls = result.total_api_calls || 0
      const uniqueEndpoints = result.unique_endpoints || 0

      const wsConnections = Object.keys(wsActivity).length || 0

      /* eslint-disable @typescript-eslint/no-explicit-any */
      const apiFrequency = apiPatterns.length > 0
        ? Math.round(apiPatterns.reduce(
          (sum: number, p: any) => sum + (p.frequency || 0), 0,
        ) / Math.max(apiPatterns.length, 1))
        : totalCalls
      /* eslint-enable @typescript-eslint/no-explicit-any */

      const avgResponseTime = result.avg_response_time || 0
      const estimatedDataRate = Math.round((totalCalls * avgResponseTime * 10) / 100) / 10

      communicationPatterns.value = {
        websocket_connections: wsConnections,
        api_call_frequency: apiFrequency,
        data_transfer_rate: estimatedDataRate,
        unique_endpoints: uniqueEndpoints,
      }
    } catch (error: unknown) {
      logger.error('loadCommunicationPatterns failed:', error)
      communicationPatterns.value = null
    }
  }

  const loadCodeQuality = async () => {
    try {
      const backendUrl = await appConfig.getServiceUrl('backend')

      const healthResponse = await fetchWithAuth(`${backendUrl}/api/quality/health-score`)
      const healthData = healthResponse.ok ? await healthResponse.json() : null

      const duplicatesResponse = await fetchWithAuth(
        deps.withSourceId(`${backendUrl}/api/analytics/codebase/duplicates`),
      )
      const duplicatesData = duplicatesResponse.ok ? await duplicatesResponse.json() : null

      const debtResponse = await fetchWithAuth(`${backendUrl}/api/debt/summary`)
      const debtData = debtResponse.ok ? await debtResponse.json() : null

      if (healthData?.status === 'no_data' && debtData?.status === 'no_data') {
        codeQuality.value = null
        logger.debug('No code quality data - run indexing first')
        return
      }

      const testCoverage = healthData?.breakdown?.testability || 50
      const performanceScore = healthData?.breakdown?.performance || 0
      const overallScore = healthData?.health_score || performanceScore

      let duplicateCount = 0
      if (duplicatesData?.status === 'success') {
        duplicateCount = duplicatesData.total_duplicates || duplicatesData.count || 0
      }

      const technicalDebt = debtData?.total_debt_hours || debtData?.total_items || 0

      codeQuality.value = {
        overall_score: Math.round(overallScore),
        test_coverage: Math.round(testCoverage),
        code_duplicates: duplicateCount,
        technical_debt: technicalDebt,
      }
    } catch (error: unknown) {
      logger.error('loadCodeQuality failed:', error)
      codeQuality.value = null
    }
  }

  const loadPerformanceMetrics = async () => {
    try {
      const backendUrl = await appConfig.getServiceUrl('backend')

      const summaryResponse = await fetchWithAuth(`${backendUrl}/api/performance/summary`)
      const summaryData = summaryResponse.ok ? await summaryResponse.json() : null

      const monitoringResponse = await fetchWithAuth(`${backendUrl}/api/monitoring/status`)
      const monitoringData = monitoringResponse.ok ? await monitoringResponse.json() : null

      const qualityResponse = await fetchWithAuth(`${backendUrl}/api/quality/health-score`)
      const qualityData = qualityResponse.ok ? await qualityResponse.json() : null

      if (summaryData?.status === 'no_data' && qualityData?.status === 'no_data') {
        performanceMetrics.value = null
        logger.debug('No performance metrics data - run indexing first')
        return
      }

      const performanceScore = qualityData?.breakdown?.performance || 0
      const efficiencyScore = summaryData?.average_score || performanceScore
      const patternsEnabled = summaryData?.patterns_enabled || 0

      performanceMetrics.value = {
        efficiency_score: Math.round(efficiencyScore) || Math.round(performanceScore),
        memory_usage: patternsEnabled > 0 ? patternsEnabled * 15 : 0,
        cpu_usage: Math.round(100 - performanceScore),
        load_time: monitoringData?.uptime_seconds
          ? Math.round(monitoringData.uptime_seconds)
          : 0,
      }
    } catch (error: unknown) {
      logger.error('loadPerformanceMetrics failed:', error)
    }
  }

  const refreshAllMetrics = async () => {
    await Promise.all([
      loadCommunicationPatterns(),
      loadCodeQuality(),
      loadPerformanceMetrics(),
      ...deps.additionalRefreshCallbacks(),
    ])
  }

  const toggleRealTime = () => {
    if (realTimeEnabled.value) {
      refreshInterval.value = setInterval(refreshAllMetrics, 30000)
    } else {
      if (refreshInterval.value) {
        clearInterval(refreshInterval.value)
        refreshInterval.value = null
      }
    }
  }

  return {
    // State
    systemOverview,
    communicationPatterns,
    codeQuality,
    performanceMetrics,
    realTimeEnabled,
    refreshInterval,
    // Functions
    loadSystemOverview,
    loadCommunicationPatterns,
    loadCodeQuality,
    loadPerformanceMetrics,
    refreshAllMetrics,
    toggleRealTime,
  }
}
