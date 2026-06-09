// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * Composable: useCrossLanguageAnalysis
 *
 * Cross-language consistency analysis: summary, details, full scan,
 * DTO mismatches, API contract mismatches, validation duplications,
 * and semantic pattern matches.
 *
 * Extracted from useSpecializedAnalysis (Issue #2372).
 * Migrated from hand-rolled fetchWithAuth to useFetchEndpoint (#5253)
 * using the `onResponse`, POST body factory, and path-parameterised
 * per-call patterns established in #5208 + #5235.
 */

import { ref, reactive } from 'vue'
import { useFetchEndpoint } from '@/composables/api/useFetchEndpoint'
import { runTimed } from '@/composables/api/useTimedNotify'
import { createLogger } from '@/utils/debugUtils'
import type {
  UseCodeIntelAnalysisDeps,
  CrossLanguageAnalysisResult,
  DTOMismatch,
  APIContractMismatch,
  ValidationDuplication,
  PatternMatch,
} from './codeIntelTypes'

const logger = createLogger('useCrossLanguageAnalysis')

interface CrossLanguageSummaryRaw {
  status: string
  summary?: Record<string, unknown>
  message?: string
}

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

/**
 * Fetch a single cross-language section (dto-mismatches / api-mismatches /
 * validation-duplications / semantic-matches). Each section is a GET with
 * a per-call path, so the endpoint instance is built inside the wrapper
 * (same pattern as useWorkflowTemplates.fetchTemplateDetail).
 *
 * Returns `[]` on any failure — the caller is best-effort and logs once
 * for the whole details batch rather than per-section.
 */
async function _fetchCrossLanguageSection(
  endpointPath: string,
  withSourceId: (url: string) => string,
  extractFn: (data: Record<string, unknown>) => unknown[],
): Promise<unknown[]> {
  const ep = useFetchEndpoint<Record<string, unknown>, unknown[]>(
    {
      path: `/api/analytics/codebase/cross-language/${endpointPath}`,
      scopeToSource: true,
      pickData: (data) =>
        data.status === 'success' ? extractFn(data) : [],
      label: `Cross-language ${endpointPath}`,
    },
    { withSourceId },
  )
  await ep.load()
  return ep.data.value ?? []
}

export function useCrossLanguageAnalysis(deps: UseCodeIntelAnalysisDeps) {
  const { withSourceId, t, notify } = deps

  const crossLanguageAnalysis = ref<CrossLanguageAnalysisResult | null>(null)
  const expandedCrossLanguageGroups = reactive({
    dtoMismatches: false,
    apiMismatches: false,
    validationDups: false,
    semanticMatches: false,
  })

  // --- Summary endpoint (#5253) --------------------------------------------

  const summaryEndpoint = useFetchEndpoint<
    CrossLanguageSummaryRaw,
    Record<string, unknown>
  >(
    {
      path: '/api/analytics/codebase/cross-language/summary',
      scopeToSource: true,
      pickData: (r) =>
        r.status === 'success' && r.summary ? r.summary : null,
      onNoData: () => {
        crossLanguageAnalysis.value = null
        logger.info('Cross-language analysis: No cached data available')
      },
      onResponse: async (response) => {
        const text = await response.text().catch(() => '')
        return `Status ${response.status}${text ? `: ${text}` : ''}`
      },
      label: 'Cross-language summary',
    },
    { withSourceId },
  )

  const loadingCrossLanguage = summaryEndpoint.loading
  const crossLanguageError = summaryEndpoint.error

  const loadCrossLanguageDetails = async () => {
    if (!crossLanguageAnalysis.value) return
    try {
      const analysis = crossLanguageAnalysis.value

      analysis.dto_mismatches = (await _fetchCrossLanguageSection(
        'dto-mismatches',
        withSourceId,
        (d) => (d.mismatches as unknown[]) || [],
      )) as DTOMismatch[]

      analysis.api_contract_mismatches = (await _fetchCrossLanguageSection(
        'api-mismatches',
        withSourceId,
        (d) => {
          const orphaned = ((d.orphaned as unknown[]) || []).map((m) => ({
            ...(m as Record<string, unknown>),
            mismatch_type: 'orphaned_endpoint',
          }))
          const missing = ((d.missing as unknown[]) || []).map((m) => ({
            ...(m as Record<string, unknown>),
            mismatch_type: 'missing_endpoint',
          }))
          return [...missing, ...orphaned]
        },
      )) as APIContractMismatch[]

      analysis.validation_duplications = (await _fetchCrossLanguageSection(
        'validation-duplications',
        withSourceId,
        (d) => (d.duplications as unknown[]) || [],
      )) as ValidationDuplication[]

      analysis.pattern_matches = (await _fetchCrossLanguageSection(
        'semantic-matches?min_similarity=0.7&limit=20',
        withSourceId,
        (d) => (d.matches as unknown[]) || [],
      )) as PatternMatch[]
    } catch (error: unknown) {
      logger.warn('Failed to load some cross-language details:', error)
    }
  }

  const getCrossLanguageAnalysis = () =>
    runTimed(
      async () => {
        await summaryEndpoint.load()
        if (summaryEndpoint.error.value) {
          throw new Error(summaryEndpoint.error.value)
        }
        if (summaryEndpoint.data.value) {
          crossLanguageAnalysis.value = _mapCrossLanguageSummary(
            summaryEndpoint.data.value,
          ) as CrossLanguageAnalysisResult
        }
      },
      async (_result, responseTime) => {
        if (!summaryEndpoint.data.value) return // no-data path already logged
        const issues = summaryEndpoint.data.value.issues as
          | Record<string, number>
          | undefined
        notify(
          t('analytics.codebase.notify.crossLanguageResult', {
            total: issues?.total || 0,
            critical: issues?.critical || 0,
            high: issues?.high || 0,
            time: responseTime,
          }),
          'success',
        )
        await loadCrossLanguageDetails()
      },
      (message, responseTime) => {
        notify(
          t('analytics.codebase.notify.crossLanguageFailed', {
            error: message,
            time: responseTime,
          }),
          'error',
        )
      },
    )

  // --- Run full analysis (POST) --------------------------------------------

  interface AnalyzeScanRaw {
    status: string
    message?: string
  }

  const runAnalyzeEndpoint = useFetchEndpoint<AnalyzeScanRaw, true>(
    {
      path: '/api/analytics/codebase/cross-language/analyze',
      method: 'POST',
      scopeToSource: true,
      body: () => ({ use_llm: true, use_cache: true }),
      pickData: (r) => (r.status === 'success' ? true : null),
      onResponse: async (response) => {
        const text = await response.text().catch(() => '')
        return `Status ${response.status}${text ? `: ${text}` : ''}`
      },
      label: 'Cross-language analyze',
    },
    { withSourceId },
  )

  const runCrossLanguageAnalysis = () =>
    runTimed(
      async () => {
        await runAnalyzeEndpoint.load()
        if (runAnalyzeEndpoint.error.value) {
          throw new Error(runAnalyzeEndpoint.error.value)
        }
        if (!runAnalyzeEndpoint.data.value) {
          throw new Error('Analysis failed')
        }
      },
      async (_result, responseTime) => {
        notify(
          t('analytics.codebase.notify.crossLanguageScanComplete', {
            time: responseTime,
          }),
          'success',
        )
        await getCrossLanguageAnalysis()
      },
      (message, responseTime) => {
        notify(
          t('analytics.codebase.notify.crossLanguageScanFailed', {
            error: message,
            time: responseTime,
          }),
          'error',
        )
      },
    )

  const getCrossLanguageSeverityClass = (severity: string): string => {
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
