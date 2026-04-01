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
import { fetchWithAuth } from '@/utils/fetchWithAuth'
import appConfig from '@/config/AppConfig.js'
import { useCodeIntelligence } from '@/composables/useCodeIntelligence'
import { createLogger } from '@/utils/debugUtils'
import type {
  SecurityFinding,
  PerformanceFinding,
  RedisOptimizationFinding,
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
  const codeIntelSecurityFindings = ref<SecurityFinding[]>([])
  const codeIntelPerformanceFindings = ref<PerformanceFinding[]>([])
  const codeIntelRedisFindings = ref<RedisOptimizationFinding[]>([])
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

  const clearCache = async (
    withSourceIdFn: (url: string) => string,
    localStateResetFn: () => void,
  ) => {
    clearingCache.value = true
    try {
      const backendUrl = await appConfig.getServiceUrl('backend')
      const response = await fetchWithAuth(
        withSourceIdFn(
          `${backendUrl}/api/analytics/codebase/cache`,
        ),
        {
          method: 'DELETE',
          headers: { 'Content-Type': 'application/json' },
        },
      )
      if (!response.ok) {
        const errorText = await response.text()
        throw new Error(`Status ${response.status}: ${errorText}`)
      }
      const result = await response.json()
      localStateResetFn()
      notify(
        t('analytics.codebase.notify.cacheCleared', {
          count: result.deleted_keys || 0,
        }),
        'success',
      )
    } catch (error: unknown) {
      const errorMessage =
        error instanceof Error ? error.message : String(error)
      logger.error('Cache clear failed:', error)
      notify(
        t('analytics.codebase.notify.cacheClearFailed', {
          error: errorMessage,
        }),
        'error',
      )
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
      await codeIntelAnalyzeCode({ code: rootPath.value })
      await codeIntelGetSuggestions(rootPath.value)
      codeIntelFindingsFetched.value = {
        security: true,
        performance: true,
        redis: true,
      }
      notify(
        t('analytics.codebase.notify.codeIntelComplete', {
          count: codeIntelTotalFindings.value,
        }),
        'success',
      )
    } catch (e) {
      logger.error('Code Intelligence analysis failed:', e)
      notify(
        t('analytics.codebase.notify.codeIntelFailed'),
        'error',
      )
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
