// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * Composable: useApiEndpointAnalysis
 *
 * API endpoint coverage scanning and endpoint group management.
 * Extracted from useSpecializedAnalysis (Issue #2372).
 * Migrated from useAnalyticsFetch + hand-rolled fetchWithAuth to a
 * single useFetchEndpoint instance (Issue #5208).
 */

import { useFetchEndpoint } from '@/composables/api/useFetchEndpoint'
import { runTimed } from '@/composables/api/useTimedNotify'
import type {
  UseCodeIntelAnalysisDeps,
  ApiEndpointAnalysisResult,
} from './codeIntelTypes'

interface EndpointAnalysisRaw {
  status: string
  analysis?: ApiEndpointAnalysisResult
}

export function useApiEndpointAnalysis(deps: UseCodeIntelAnalysisDeps) {
  const { withSourceId, t, notify } = deps

  const endpoint = useFetchEndpoint<
    EndpointAnalysisRaw,
    ApiEndpointAnalysisResult
  >(
    {
      path: '/api/analytics/codebase/endpoint-analysis',
      scopeToSource: true,
      pickData: (r) =>
        r.status === 'success' && r.analysis ? r.analysis : null,
    },
    { withSourceId },
  )

  // Silent cached load — callers read endpoint.data reactively.
  const loadApiEndpointAnalysis = () => endpoint.load()

  // User-initiated coverage refresh — identical endpoint, adds a timed
  // success/error toast with coverage metrics.
  const getApiEndpointCoverage = () =>
    runTimed(
      async () => {
        await endpoint.load()
        if (endpoint.error.value) {
          throw new Error(endpoint.error.value)
        }
      },
      (_result, time) => {
        const a = endpoint.data.value
        const coverage = a?.coverage_percentage?.toFixed(1) ?? 0
        const orphaned = a?.orphaned_endpoints ?? 0
        const missing = a?.missing_endpoints ?? 0
        notify(
          t('analytics.codebase.notify.apiCoverageResult', {
            coverage,
            orphaned,
            missing,
            time,
          }),
          'success',
        )
      },
      (message, time) => {
        notify(
          t('analytics.codebase.notify.apiAnalysisFailed', {
            error: message,
            time,
          }),
          'error',
        )
      },
    )

  const getCoverageClass = (percentage: number): string => {
    if (!percentage || percentage < 50) return 'critical'
    if (percentage < 75) return 'warning'
    if (percentage < 90) return 'info'
    return 'success'
  }

  return {
    apiEndpointAnalysis: endpoint.data,
    loadingApiEndpoints: endpoint.loading,
    apiEndpointsError: endpoint.error,
    loadApiEndpointAnalysis,
    getApiEndpointCoverage,
    getCoverageClass,
  }
}
