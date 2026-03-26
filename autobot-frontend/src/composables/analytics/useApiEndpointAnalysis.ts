// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * Composable: useApiEndpointAnalysis
 *
 * API endpoint coverage scanning and endpoint group management.
 * Extracted from useSpecializedAnalysis (Issue #2372).
 */

import { reactive } from 'vue'
import { fetchWithAuth } from '@/utils/fetchWithAuth'
import appConfig from '@/config/AppConfig.js'
import { useAnalyticsFetch } from '@/composables/useAnalyticsFetch'
import { createLogger } from '@/utils/debugUtils'
import type {
  UseCodeIntelAnalysisDeps,
  ApiEndpointAnalysisResult,
} from './codeIntelTypes'

const logger = createLogger('useApiEndpointAnalysis')

export function useApiEndpointAnalysis(
  deps: UseCodeIntelAnalysisDeps,
) {
  const { sourceIdQuery, withSourceId, t, notify } = deps

  const {
    data: apiEndpointAnalysis,
    loading: loadingApiEndpoints,
    error: apiEndpointsError,
    load: _loadApiEndpoints,
  } = useAnalyticsFetch<ApiEndpointAnalysisResult>(
    '/api/analytics/codebase/endpoint-analysis',
    (r) => {
      if (r.status === 'success' && r.analysis) {
        return r.analysis as unknown as ApiEndpointAnalysisResult
      }
      return undefined
    },
  )

  const expandedApiEndpointGroups = reactive({
    orphaned: false,
    missing: false,
    used: false,
  })

  const loadApiEndpointAnalysis = () =>
    _loadApiEndpoints(sourceIdQuery.value)

  const getApiEndpointCoverage = async () => {
    loadingApiEndpoints.value = true
    apiEndpointsError.value = ''
    const startTime = Date.now()
    try {
      const backendUrl = await appConfig.getServiceUrl('backend')
      const response = await fetchWithAuth(
        withSourceId(
          `${backendUrl}/api/analytics/codebase/endpoint-analysis`,
        ),
        {
          method: 'GET',
          headers: {
            Accept: 'application/json',
            'Content-Type': 'application/json',
          },
        },
      )
      if (!response.ok) {
        const errorText = await response.text()
        throw new Error(`Status ${response.status}: ${errorText}`)
      }
      const data = await response.json()
      const responseTime = Date.now() - startTime
      if (data.status === 'success' && data.analysis) {
        apiEndpointAnalysis.value = data.analysis
        const coverage =
          data.analysis.coverage_percentage?.toFixed(1) || 0
        const orphaned = data.analysis.orphaned_endpoints || 0
        const missing = data.analysis.missing_endpoints || 0
        notify(
          t('analytics.codebase.notify.apiCoverageResult', {
            coverage,
            orphaned,
            missing,
            time: responseTime,
          }),
          'success',
        )
      } else {
        throw new Error('Invalid response format')
      }
    } catch (error: unknown) {
      const responseTime = Date.now() - startTime
      const errorMessage =
        error instanceof Error ? error.message : String(error)
      logger.error('API Endpoint analysis failed:', error)
      apiEndpointsError.value = errorMessage
      notify(
        t('analytics.codebase.notify.apiAnalysisFailed', {
          error: errorMessage,
          time: responseTime,
        }),
        'error',
      )
    } finally {
      loadingApiEndpoints.value = false
    }
  }

  const getCoverageClass = (percentage: number): string => {
    if (!percentage || percentage < 50) return 'critical'
    if (percentage < 75) return 'warning'
    if (percentage < 90) return 'info'
    return 'success'
  }

  return {
    apiEndpointAnalysis,
    loadingApiEndpoints,
    apiEndpointsError,
    expandedApiEndpointGroups,
    loadApiEndpointAnalysis,
    getApiEndpointCoverage,
    getCoverageClass,
  }
}
