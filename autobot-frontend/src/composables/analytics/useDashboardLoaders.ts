// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
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
import { useFetchEndpoint } from '@/composables/api/useFetchEndpoint'
import { useBackgroundTask } from '@/composables/useBackgroundTask'
import { createLogger } from '@/utils/debugUtils'
import { getApiBase } from '@/config/ssot-config'

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
  const dashboardTask = useBackgroundTask(`${getApiBase()}/analytics/dashboard/overview`)

  const systemOverview = ref<SystemOverviewData | null>(null)
  const communicationPatterns = ref<CommunicationPatternsData | null>(null)
  const codeQuality = ref<CodeQualityData | null>(null)
  const performanceMetrics = ref<PerformanceMetricsData | null>(null)
  const realTimeEnabled = ref(false)
  const refreshInterval = ref<ReturnType<typeof setInterval> | null>(null)

  // --- Endpoints (#5257) ---------------------------------------------------
  // All but `duplicatesEndpoint` are non-codebase (quality / debt /
  // performance / monitoring / communication). Default scopeToSource: false
  // applies. pickData returns the raw response so per-loader synthesis can
  // access nested fields (health_score, breakdown, patterns_enabled, etc.).

  type Raw = Record<string, unknown>

  const commPatternsEndpoint = useFetchEndpoint<Raw, Raw>({
    path: '/api/analytics/communication/patterns',
    pickData: (r) => r,
    label: 'Communication patterns',
  })

  const qualityHealthEndpoint = useFetchEndpoint<Raw, Raw>({
    path: '/api/quality/health-score',
    pickData: (r) => r,
    label: 'Quality health score',
  })

  const duplicatesEndpoint = useFetchEndpoint<Raw, Raw>(
    {
      path: '/api/analytics/codebase/duplicates',
      scopeToSource: true,
      pickData: (r) => r,
      label: 'Codebase duplicates',
    },
    { withSourceId: deps.withSourceId },
  )

  const debtSummaryEndpoint = useFetchEndpoint<Raw, Raw>({
    path: '/api/debt/summary',
    pickData: (r) => r,
    label: 'Technical debt summary',
  })

  const performanceSummaryEndpoint = useFetchEndpoint<Raw, Raw>({
    path: '/api/performance/summary',
    pickData: (r) => r,
    label: 'Performance summary',
  })

  const monitoringStatusEndpoint = useFetchEndpoint<Raw, Raw>({
    path: '/api/monitoring/status',
    pickData: (r) => r,
    label: 'Monitoring status',
  })

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
    await commPatternsEndpoint.load()
    if (commPatternsEndpoint.error.value || !commPatternsEndpoint.data.value) {
      communicationPatterns.value = null
      return
    }
    const result = commPatternsEndpoint.data.value as Record<string, unknown>

    const wsActivity = (result.websocket_activity as Record<string, unknown>) || {}
    const apiPatterns = (result.api_patterns as Array<Record<string, unknown>>) || []
    const totalCalls = (result.total_api_calls as number) || 0
    const uniqueEndpoints = (result.unique_endpoints as number) || 0

    const wsConnections = Object.keys(wsActivity).length || 0

    const apiFrequency = apiPatterns.length > 0
      ? Math.round(apiPatterns.reduce(
        (sum: number, p) => sum + ((p.frequency as number) || 0), 0,
      ) / Math.max(apiPatterns.length, 1))
      : totalCalls

    const avgResponseTime = (result.avg_response_time as number) || 0
    const estimatedDataRate = Math.round((totalCalls * avgResponseTime * 10) / 100) / 10

    communicationPatterns.value = {
      websocket_connections: wsConnections,
      api_call_frequency: apiFrequency,
      data_transfer_rate: estimatedDataRate,
      unique_endpoints: uniqueEndpoints,
    }
  }

  const loadCodeQuality = async () => {
    // Three parallel loads; each endpoint tolerates !ok silently by
    // returning data.value = null. Downstream synthesis handles missing
    // fields with `??` fallbacks.
    await Promise.all([
      qualityHealthEndpoint.load(),
      duplicatesEndpoint.load(),
      debtSummaryEndpoint.load(),
    ])
    const healthData = qualityHealthEndpoint.data.value as Record<string, unknown> | null
    const duplicatesData = duplicatesEndpoint.data.value as Record<string, unknown> | null
    const debtData = debtSummaryEndpoint.data.value as Record<string, unknown> | null

    if (healthData?.status === 'no_data' && debtData?.status === 'no_data') {
      codeQuality.value = null
      logger.debug('No code quality data - run indexing first')
      return
    }

    const breakdown = (healthData?.breakdown as Record<string, number>) || {}
    const testCoverage = breakdown.testability || 50
    const performanceScore = breakdown.performance || 0
    const overallScore = (healthData?.health_score as number) || performanceScore

    let duplicateCount = 0
    if (duplicatesData?.status === 'success') {
      duplicateCount =
        (duplicatesData.total_duplicates as number) ||
        (duplicatesData.count as number) ||
        0
    }

    const technicalDebt =
      (debtData?.total_debt_hours as number) ||
      (debtData?.total_items as number) ||
      0

    codeQuality.value = {
      overall_score: Math.round(overallScore),
      test_coverage: Math.round(testCoverage),
      code_duplicates: duplicateCount,
      technical_debt: technicalDebt,
    }
  }

  const loadPerformanceMetrics = async () => {
    // qualityHealthEndpoint is shared with loadCodeQuality — re-loading is
    // cheap and keeps the two paths decoupled (caller doesn't have to know
    // what the other already fetched).
    await Promise.all([
      performanceSummaryEndpoint.load(),
      monitoringStatusEndpoint.load(),
      qualityHealthEndpoint.load(),
    ])
    const summaryData = performanceSummaryEndpoint.data.value as Record<string, unknown> | null
    const monitoringData = monitoringStatusEndpoint.data.value as Record<string, unknown> | null
    const qualityData = qualityHealthEndpoint.data.value as Record<string, unknown> | null

    if (summaryData?.status === 'no_data' && qualityData?.status === 'no_data') {
      performanceMetrics.value = null
      logger.debug('No performance metrics data - run indexing first')
      return
    }

    const breakdown = (qualityData?.breakdown as Record<string, number>) || {}
    const performanceScore = breakdown.performance || 0
    const efficiencyScore =
      (summaryData?.average_score as number) || performanceScore
    const patternsEnabled = (summaryData?.patterns_enabled as number) || 0

    performanceMetrics.value = {
      efficiency_score: Math.round(efficiencyScore) || Math.round(performanceScore),
      memory_usage: patternsEnabled > 0 ? patternsEnabled * 15 : 0,
      cpu_usage: Math.round(100 - performanceScore),
      load_time: monitoringData?.uptime_seconds
        ? Math.round(monitoringData.uptime_seconds as number)
        : 0,
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
