// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * Composable: useCrossLanguageAnalysis
 *
 * Cross-language consistency analysis: summary, details, full scan,
 * DTO mismatches, API contract mismatches, validation duplications,
 * and semantic pattern matches.
 * Extracted from useSpecializedAnalysis (Issue #2372).
 */

import { ref, reactive } from 'vue'
import { fetchWithAuth } from '@/utils/fetchWithAuth'
import appConfig from '@/config/AppConfig.js'
import { createLogger } from '@/utils/debugUtils'
import type {
  UseCodeIntelAnalysisDeps,
  CrossLanguageAnalysisResult,
} from './codeIntelTypes'

const logger = createLogger('useCrossLanguageAnalysis')

function _mapCrossLanguageSummary(
  summary: Record<string, unknown>,
) {
  const files = summary.files_analyzed as
    | Record<string, number>
    | undefined
  const issues = summary.issues as
    | Record<string, number>
    | undefined
  const perf = summary.performance as
    | Record<string, number>
    | undefined
  return {
    analysis_id: summary.analysis_id,
    scan_timestamp: summary.scan_timestamp,
    python_files_analyzed: files?.python || 0,
    typescript_files_analyzed: files?.typescript || 0,
    vue_files_analyzed: files?.vue || 0,
    total_patterns: issues?.total || 0,
    critical_issues: issues?.critical || 0,
    high_issues: issues?.high || 0,
    medium_issues: issues?.medium || 0,
    low_issues: issues?.low || 0,
    dto_mismatches: [] as unknown[],
    validation_duplications: [] as unknown[],
    api_contract_mismatches: [] as unknown[],
    pattern_matches: [] as unknown[],
    analysis_time_ms: perf?.analysis_time_ms || 0,
  }
}

async function _fetchCrossLanguageSection(
  backendUrl: string,
  endpoint: string,
  withSourceId: (url: string) => string,
  extractFn: (data: Record<string, unknown>) => unknown[],
): Promise<unknown[]> {
  const response = await fetchWithAuth(
    withSourceId(`${backendUrl}/api/analytics/codebase/cross-language/${endpoint}`),
  )
  if (!response.ok) return []
  const data = await response.json()
  if (data.status !== 'success') return []
  return extractFn(data)
}

export function useCrossLanguageAnalysis(
  deps: UseCodeIntelAnalysisDeps,
) {
  const { withSourceId, t, notify } = deps

  const crossLanguageAnalysis =
    ref<CrossLanguageAnalysisResult | null>(null)
  const loadingCrossLanguage = ref(false)
  const crossLanguageError = ref('')
  const expandedCrossLanguageGroups = reactive({
    dtoMismatches: false,
    apiMismatches: false,
    validationDups: false,
    semanticMatches: false,
  })

  const loadCrossLanguageDetails = async () => {
    if (!crossLanguageAnalysis.value) return
    try {
      const backendUrl = await appConfig.getServiceUrl('backend')
      const analysis = crossLanguageAnalysis.value

      analysis.dto_mismatches = await _fetchCrossLanguageSection(
        backendUrl, 'dto-mismatches', withSourceId,
        (d) => (d.mismatches as unknown[]) || [],
      )
      analysis.api_contract_mismatches = await _fetchCrossLanguageSection(
        backendUrl, 'api-mismatches', withSourceId,
        (d) => {
          const orphaned = ((d.orphaned as unknown[]) || []).map(
            (m) => ({ ...(m as Record<string, unknown>), mismatch_type: 'orphaned_endpoint' }),
          )
          const missing = ((d.missing as unknown[]) || []).map(
            (m) => ({ ...(m as Record<string, unknown>), mismatch_type: 'missing_endpoint' }),
          )
          return [...missing, ...orphaned]
        },
      )
      analysis.validation_duplications = await _fetchCrossLanguageSection(
        backendUrl, 'validation-duplications', withSourceId,
        (d) => (d.duplications as unknown[]) || [],
      )
      analysis.pattern_matches = await _fetchCrossLanguageSection(
        backendUrl, 'semantic-matches?min_similarity=0.7&limit=20', withSourceId,
        (d) => (d.matches as unknown[]) || [],
      )
    } catch (error: unknown) {
      logger.warn(
        'Failed to load some cross-language details:',
        error,
      )
    }
  }

  function _handleCrossLanguageSuccess(
    summary: Record<string, unknown>,
    responseTime: number,
  ) {
    crossLanguageAnalysis.value = _mapCrossLanguageSummary(
      summary,
    ) as CrossLanguageAnalysisResult
    const issues = summary.issues as Record<string, number> | undefined
    notify(
      t('analytics.codebase.notify.crossLanguageResult', {
        total: issues?.total || 0,
        critical: issues?.critical || 0,
        high: issues?.high || 0,
        time: responseTime,
      }),
      'success',
    )
  }

  const getCrossLanguageAnalysis = async () => {
    loadingCrossLanguage.value = true
    crossLanguageError.value = ''
    const startTime = Date.now()
    try {
      const backendUrl = await appConfig.getServiceUrl('backend')
      const response = await fetchWithAuth(
        withSourceId(
          `${backendUrl}/api/analytics/codebase/cross-language/summary`,
        ),
      )
      if (!response.ok) {
        const errorText = await response.text()
        throw new Error(`Status ${response.status}: ${errorText}`)
      }
      const data = await response.json()
      if (data.status === 'success' && data.summary) {
        _handleCrossLanguageSuccess(data.summary, Date.now() - startTime)
        await loadCrossLanguageDetails()
      } else if (data.status === 'empty') {
        crossLanguageAnalysis.value = null
        logger.info('Cross-language analysis: No cached data available')
      } else {
        throw new Error('Invalid response format')
      }
    } catch (error: unknown) {
      const errorMessage =
        error instanceof Error ? error.message : String(error)
      logger.error('Cross-language analysis failed:', error)
      crossLanguageError.value = errorMessage
      notify(
        t('analytics.codebase.notify.crossLanguageFailed', {
          error: errorMessage,
          time: Date.now() - startTime,
        }),
        'error',
      )
    } finally {
      loadingCrossLanguage.value = false
    }
  }

  const runCrossLanguageAnalysis = async () => {
    loadingCrossLanguage.value = true
    crossLanguageError.value = ''
    const startTime = Date.now()
    try {
      const backendUrl = await appConfig.getServiceUrl('backend')
      const response = await fetchWithAuth(
        withSourceId(
          `${backendUrl}/api/analytics/codebase/cross-language/analyze`,
        ),
        {
          method: 'POST',
          headers: {
            Accept: 'application/json',
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            use_llm: true,
            use_cache: true,
          }),
        },
      )
      if (!response.ok) {
        const errorText = await response.text()
        throw new Error(`Status ${response.status}: ${errorText}`)
      }
      const data = await response.json()
      const responseTime = Date.now() - startTime
      if (data.status === 'success') {
        notify(
          t(
            'analytics.codebase.notify.crossLanguageScanComplete',
            { time: responseTime },
          ),
          'success',
        )
        await getCrossLanguageAnalysis()
      } else {
        throw new Error(data.message || 'Analysis failed')
      }
    } catch (error: unknown) {
      const responseTime = Date.now() - startTime
      const errorMessage =
        error instanceof Error ? error.message : String(error)
      logger.error('Cross-language analysis scan failed:', error)
      crossLanguageError.value = errorMessage
      notify(
        t(
          'analytics.codebase.notify.crossLanguageScanFailed',
          { error: errorMessage, time: responseTime },
        ),
        'error',
      )
    } finally {
      loadingCrossLanguage.value = false
    }
  }

  const getCrossLanguageSeverityClass = (
    severity: string,
  ): string => {
    switch (severity?.toLowerCase()) {
      case 'critical':
        return 'critical'
      case 'high':
        return 'warning'
      case 'medium':
        return 'info'
      case 'low':
        return 'success'
      default:
        return 'info'
    }
  }

  return {
    crossLanguageAnalysis,
    loadingCrossLanguage,
    crossLanguageError,
    expandedCrossLanguageGroups,
    getCrossLanguageAnalysis,
    runCrossLanguageAnalysis,
    getCrossLanguageSeverityClass,
  }
}
