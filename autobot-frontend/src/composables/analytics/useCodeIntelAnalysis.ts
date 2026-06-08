// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * Composable: useCodeIntelAnalysis (facade)
 *
 * Encapsulates Code Intelligence analysis state and operations:
 * security/performance/redis scores, findings, code smells,
 * environment analysis, ownership, cross-language analysis,
 * bug prediction, config duplicates, and API endpoint coverage.
 *
 * Issues #2228, #2230: Extracted from CodebaseAnalytics.vue
 * Issue #2260: Decomposed into sub-composables
 */

import { ref, computed } from 'vue'
import { useFetchEndpoint } from '@/composables/api/useFetchEndpoint'
import { useCodeIntelligence } from '@/composables/useCodeIntelligence'
import { createLogger } from '@/utils/debugUtils'
import type {
  SecurityFinding,
  PerformanceFinding,
  RedisOptimizationFinding,
  Severity,
} from '@/types/codeIntelligence'

import { useCodeIntelScores } from './useCodeIntelScores'
import { useCodeSmellAnalysis } from './useCodeSmellAnalysis'
import { useBugPrediction } from './useBugPrediction'
import { useSpecializedAnalysis } from './useSpecializedAnalysis'

// Re-export types and deps interface from shared types module
export type { UseCodeIntelAnalysisDeps } from './codeIntelTypes'
export type {
  BugPredictionFile,
  BugPredictionResult,
  TopRiskFactor,
} from './codeIntelTypes'

import type { UseCodeIntelAnalysisDeps } from './codeIntelTypes'

const logger = createLogger('useCodeIntelAnalysis')

export function useCodeIntelAnalysis(
  deps: UseCodeIntelAnalysisDeps,
) {
  const { rootPath, t, notify } = deps

  // --- useCodeIntelligence composable (stays in facade) ---

  const {
    isLoading: codeIntelLoading,
    suggestions: codeIntelSuggestions,
    healthScore: codeIntelHealthScore,
    qualityScore: codeIntelQualityScore,
    analysisHistory: codeIntelAnalysisHistory,
    analyzeCode: codeIntelAnalyzeCode,
    getSuggestions: codeIntelGetSuggestions,
    getHealthScore: codeIntelGetHealthScore,
    getQualityScore: codeIntelGetQualityScore,
    getAnalysisHistory: codeIntelGetAnalysisHistory,
    batchAnalyze: codeIntelBatchAnalyze,
  } = useCodeIntelligence()
  // #5365: codeIntel{Security,Performance,Redis}Findings are declared
  // as computed adapters further down, after `scores` is constructed.
  const codeIntelFindingsLoading = ref(false)
  const codeIntelFindingsFetched = ref({
    security: false,
    performance: false,
    redis: false,
  })

  const codeIntelTotalFindings = computed(
    () => codeIntelSuggestions.value.length,
  )

  // --- Cache clearing (stays in facade) ---

  const clearingCache = ref(false)

  // #5174: routed through useFetchEndpoint DELETE. The caller injects
  // withSourceId; localStateResetFn fires on success; toasts come from the
  // composable's hooks. `clearingCache` is the public loading ref.
  async function clearCache(
    withSourceIdFn: (url: string) => string,
    localStateResetFn: () => void,
  ) {
    const cacheEndpoint = useFetchEndpoint<
      { deleted_keys?: number; message?: string },
      number
    >(
      {
        path: '/api/analytics/codebase/cache',
        method: 'DELETE',
        scopeToSource: true,
        pickData: (raw) => raw.deleted_keys ?? 0,
        onSuccess: (count) => {
          localStateResetFn()
          notify(
            t('analytics.codebase.notify.cacheCleared', { count }),
            'success',
          )
        },
        onError: (message) => {
          logger.error('Cache clear failed:', message)
          notify(
            t('analytics.codebase.notify.cacheClearFailed', { error: message }),
            'error',
          )
        },
        label: 'Cache clear',
      },
      { withSourceId: withSourceIdFn },
    )
    clearingCache.value = true
    try {
      await cacheEndpoint.load()
    } finally {
      clearingCache.value = false
    }
  }

  // --- Code Intelligence analysis functions (stay in facade) ---

  async function runCodeIntelligenceAnalysis() {
    if (!rootPath.value) return
    logger.info(
      'Running Code Intelligence analysis on:',
      rootPath.value,
    )
    codeIntelFindingsFetched.value = {
      security: false,
      performance: false,
      redis: false,
    }
    codeIntelFindingsLoading.value = true
    try {
      // #5365: fire the analyze endpoints so securityFindings,
      // performanceFindings, and redisOptimizations (scores sub-composable)
      // are populated. The adapter computeds above re-expose them under
      // the legacy `codeIntel*Findings` names for the panel.
      //
      // #5387: use `Promise.allSettled` so one failing endpoint doesn't
      // discard the other 4 successful results. `fetched` flags + toast
      // reflect per-endpoint outcome (all-success / partial / all-fail).
      const [
        ,
        ,
        securityResult,
        performanceResult,
        redisResult,
      ] = await Promise.allSettled([
        codeIntelAnalyzeCode({ code: rootPath.value }),
        codeIntelGetSuggestions(rootPath.value),
        scores.loadSecurityFindings(),
        scores.loadPerformanceFindings(),
        scores.loadRedisOptimizations(),
      ])
      codeIntelFindingsFetched.value = {
        security: securityResult.status === 'fulfilled',
        performance: performanceResult.status === 'fulfilled',
        redis: redisResult.status === 'fulfilled',
      }
      const findingFailures = [
        securityResult,
        performanceResult,
        redisResult,
      ].filter((r) => r.status === 'rejected')
      if (findingFailures.length === 0) {
        notify(
          t('analytics.codebase.notify.codeIntelComplete', {
            count: codeIntelTotalFindings.value,
          }),
          'success',
        )
      } else if (findingFailures.length < 3) {
        // Partial success: surface a warning so the user knows which
        // tabs have data. Successful arrays still render via the
        // computed adapters (codeIntel*Findings above).
        logger.warn(
          'Code Intelligence analysis: partial failure',
          findingFailures.map((r) => (r as PromiseRejectedResult).reason),
        )
        notify(
          t('analytics.codebase.notify.codeIntelPartial', {
            count: codeIntelTotalFindings.value,
          }),
          'warning',
        )
      } else {
        logger.error(
          'Code Intelligence analysis failed:',
          findingFailures.map((r) => (r as PromiseRejectedResult).reason),
        )
        notify(t('analytics.codebase.notify.codeIntelFailed'), 'error')
      }
    } finally {
      codeIntelFindingsLoading.value = false
    }
  }

  async function handleFileScan(
    filePath: string,
    _types: {
      security: boolean
      performance: boolean
      redis: boolean
    },
  ) {
    codeIntelFindingsLoading.value = true
    try {
      const results = await codeIntelBatchAnalyze([
        { code: filePath, filename: filePath },
      ])
      if (results.length > 0) {
        codeIntelFindingsFetched.value = {
          security: true,
          performance: true,
          redis: true,
        }
        notify(
          t('analytics.codebase.notify.fileScanComplete', {
            count: results.length,
          }),
          'info',
        )
      } else {
        notify(
          t('analytics.codebase.notify.fileScanNoIssues'),
          'success',
        )
      }
    } catch (e) {
      logger.error('File scan failed:', e)
      notify(
        t('analytics.codebase.notify.fileScanFailed'),
        'error',
      )
    } finally {
      codeIntelFindingsLoading.value = false
    }
  }

  // --- Delegate to sub-composables ---

  const scores = useCodeIntelScores(deps)
  const smells = useCodeSmellAnalysis(deps)
  const bugs = useBugPrediction(deps)
  const specialized = useSpecializedAnalysis(deps)

  // #5365: Previously these three refs were declared as empty
  // `ref<Type[]>([])` and never written — declared + returned + unwritten.
  // CodebaseSecurityPanel therefore showed empty findings on every
  // render regardless of scan results (same bug class as #5277).
  //
  // The live data is produced by `useCodeIntelScores` via POST to
  // `/api/code-intelligence/{security,performance,redis}/analyze` into
  // `securityFindings`, `performanceFindings`, `redisOptimizations` —
  // but those use the `SecurityFindingDetail` shape (fields `line`,
  // `description`, `recommendation`), while the panel prop types use
  // the `SecurityFinding` shape (fields `line_number`, `message`,
  // `remediation`). These computed adapters map between the two
  // without changing the panel contract or consumer bindings.
  const codeIntelSecurityFindings = computed<SecurityFinding[]>(() =>
    (scores.securityFindings.value || []).map((f) => ({
      severity: f.severity as Severity,
      vulnerability_type: f.vulnerability_type,
      file_path: f.file_path,
      line_number: f.line ?? 0,
      code_snippet: f.code_snippet ?? '',
      message: f.description,
      remediation: f.recommendation ?? '',
      owasp_category: f.owasp_category ?? '',
    })),
  )
  const codeIntelPerformanceFindings = computed<PerformanceFinding[]>(() =>
    (scores.performanceFindings.value || []).map((f) => ({
      issue_type: f.issue_type,
      severity: f.severity as Severity,
      file_path: f.file_path,
      line_number: f.line ?? 0,
      message: f.description,
      recommendation: f.recommendation ?? '',
      estimated_impact: '',
    })),
  )
  const codeIntelRedisFindings = computed<RedisOptimizationFinding[]>(() =>
    (scores.redisOptimizations.value || []).map((f) => ({
      optimization_type: f.optimization_type,
      severity: f.severity as Severity,
      file_path: f.file_path,
      line_number: f.line ?? 0,
      message: f.description,
      recommendation: f.recommendation ?? '',
      category: f.category ?? '',
    })),
  )

  return {
    // Code Intelligence (facade-owned)
    codeIntelLoading,
    codeIntelSuggestions,
    codeIntelSecurityFindings,
    codeIntelPerformanceFindings,
    codeIntelRedisFindings,
    codeIntelFindingsLoading,
    codeIntelFindingsFetched,
    codeIntelTotalFindings,
    codeIntelHealthScore,
    codeIntelQualityScore,
    codeIntelAnalysisHistory,
    codeIntelGetHealthScore,
    codeIntelGetQualityScore,
    codeIntelGetAnalysisHistory,
    runCodeIntelligenceAnalysis,
    handleFileScan,
    // Cache (facade-owned)
    clearingCache,
    clearCache,
    // Scores + findings (from useCodeIntelScores)
    ...scores,
    // Code smells (from useCodeSmellAnalysis)
    ...smells,
    // Bug prediction (from useBugPrediction)
    ...bugs,
    // Specialized analysis (from useSpecializedAnalysis)
    ...specialized,
  }
}
