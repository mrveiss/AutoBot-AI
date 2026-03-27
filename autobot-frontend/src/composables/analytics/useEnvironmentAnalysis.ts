// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * Composable: useEnvironmentAnalysis
 *
 * Environment variable scanning with optional AI-powered filtering.
 * Extracted from useSpecializedAnalysis (Issue #2372).
 */

import { ref } from 'vue'
import { fetchWithAuth } from '@/utils/fetchWithAuth'
import appConfig from '@/config/AppConfig.js'
import { getConfig } from '@/config/ssot-config'
import { createLogger } from '@/utils/debugUtils'
import type {
  UseCodeIntelAnalysisDeps,
  EnvironmentAnalysisResult,
} from './codeIntelTypes'

const logger = createLogger('useEnvironmentAnalysis')

export function useEnvironmentAnalysis(
  deps: UseCodeIntelAnalysisDeps,
) {
  const { rootPath, withSourceId } = deps

  const environmentAnalysis =
    ref<EnvironmentAnalysisResult | null>(null)
  const loadingEnvAnalysis = ref(false)
  const envAnalysisError = ref('')
  const useAiFiltering = ref(false)
  const aiFilteringModel = ref(getConfig().llm.defaultModel)
  const aiFilteringPriority = ref('high')
  const llmFilteringResult = ref<{
    enabled: boolean
    model: string
    original_count: number
    filtered_count: number
    reduction_percent: number
    filter_priority: string | null
  } | null>(null)

  const loadEnvironmentAnalysis = async () => {
    if (!rootPath.value) return
    loadingEnvAnalysis.value = true
    envAnalysisError.value = ''
    llmFilteringResult.value = null
    try {
      const backendUrl = await appConfig.getServiceUrl('backend')
      let url = `${backendUrl}/api/analytics/codebase/env-analysis?path=${encodeURIComponent(rootPath.value)}`
      if (useAiFiltering.value) {
        url += `&use_llm_filter=true`
        url += `&llm_model=${encodeURIComponent(aiFilteringModel.value)}`
        url += `&filter_priority=${encodeURIComponent(aiFilteringPriority.value)}`
      }
      url = withSourceId(url)
      const response = await fetchWithAuth(url, {
        method: 'GET',
        headers: {
          Accept: 'application/json',
          'Content-Type': 'application/json',
        },
      })
      if (!response.ok) {
        throw new Error(
          `Environment analysis endpoint returned ${response.status}`,
        )
      }
      const data = await response.json()
      if (data.status === 'success') {
        environmentAnalysis.value = {
          total_hardcoded_values:
            data.total_hardcoded_values || 0,
          high_priority_count: data.high_priority_count || 0,
          recommendations_count:
            data.recommendations_count || 0,
          categories: data.categories || {},
          analysis_time_seconds:
            data.analysis_time_seconds || 0,
          hardcoded_values: data.hardcoded_values || [],
          recommendations: data.recommendations || [],
        }
        if (data.llm_filtering) {
          llmFilteringResult.value = data.llm_filtering
          logger.info(
            'LLM filtering applied:',
            data.llm_filtering,
          )
        }
      } else if (data.status === 'no_data') {
        environmentAnalysis.value = null
        logger.debug(
          'No environment analysis data - run indexing first',
        )
      }
    } catch (error: unknown) {
      const errorMessage =
        error instanceof Error ? error.message : String(error)
      logger.error(
        'Failed to load environment analysis:',
        error,
      )
      envAnalysisError.value = errorMessage
    } finally {
      loadingEnvAnalysis.value = false
    }
  }

  return {
    environmentAnalysis,
    loadingEnvAnalysis,
    envAnalysisError,
    useAiFiltering,
    aiFilteringModel,
    aiFilteringPriority,
    llmFilteringResult,
    loadEnvironmentAnalysis,
  }
}
