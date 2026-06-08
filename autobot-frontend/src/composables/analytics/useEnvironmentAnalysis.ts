// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * Composable: useEnvironmentAnalysis
 *
 * Environment variable scanning with optional AI-powered filtering.
 * Extracted from useSpecializedAnalysis (Issue #2372).
 *
 * Migrated from raw fetchWithAuth to useFetchEndpoint (#6022) for
 * AbortController, race protection, and consistent error handling.
 */

import { ref } from 'vue'
import { useFetchEndpoint } from '@/composables/api/useFetchEndpoint'
import { getConfig } from '@/config/ssot-config'
import { createLogger } from '@/utils/debugUtils'
import type {
  UseCodeIntelAnalysisDeps,
  EnvironmentAnalysisResult,
} from './codeIntelTypes'

const logger = createLogger('useEnvironmentAnalysis')

interface EnvAnalysisRaw {
  status: string
  total_hardcoded_values?: number
  high_priority_count?: number
  recommendations_count?: number
  categories?: Record<string, number>
  analysis_time_seconds?: number
  hardcoded_values?: unknown[]
  recommendations?: unknown[]
  llm_filtering?: {
    enabled: boolean
    model: string
    original_count: number
    filtered_count: number
    reduction_percent: number
    filter_priority: string | null
  }
}

export function useEnvironmentAnalysis(
  deps: UseCodeIntelAnalysisDeps,
) {
  const { rootPath, withSourceId } = deps

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

  const endpoint = useFetchEndpoint<EnvAnalysisRaw, EnvironmentAnalysisResult>(
    {
      path: '/api/analytics/codebase/env-analysis',
      scopeToSource: true,
      pickData: (raw) => {
        if (raw.status === 'no_data') {
          logger.debug(
            'No environment analysis data - run indexing first',
          )
          return null
        }
        if (raw.status !== 'success') return null
        return {
          total_hardcoded_values: raw.total_hardcoded_values ?? 0,
          high_priority_count: raw.high_priority_count ?? 0,
          recommendations_count: raw.recommendations_count ?? 0,
          categories: raw.categories ?? {},
          analysis_time_seconds: raw.analysis_time_seconds ?? 0,
          hardcoded_values: (raw.hardcoded_values ?? []) as EnvironmentAnalysisResult['hardcoded_values'],
          recommendations: (raw.recommendations ?? []) as EnvironmentAnalysisResult['recommendations'],
        }
      },
      onSuccess: (_data, raw) => {
        if (raw.llm_filtering) {
          llmFilteringResult.value = raw.llm_filtering
          logger.info('LLM filtering applied:', raw.llm_filtering)
        }
      },
      onError: (message, err) => {
        logger.error('Failed to load environment analysis:', err)
        // error surface is handled by endpoint.error
      },
      label: 'Environment analysis',
    },
    { withSourceId },
  )

  const loadEnvironmentAnalysis = async () => {
    if (!rootPath.value) return
    llmFilteringResult.value = null

    const queryExtras: Record<string, string> = {
      path: rootPath.value,
    }
    if (useAiFiltering.value) {
      queryExtras['use_llm_filter'] = 'true'
      queryExtras['llm_model'] = aiFilteringModel.value
      queryExtras['filter_priority'] = aiFilteringPriority.value
    }

    await endpoint.load(queryExtras)
  }

  return {
    environmentAnalysis: endpoint.data,
    loadingEnvAnalysis: endpoint.loading,
    envAnalysisError: endpoint.error,
    useAiFiltering,
    aiFilteringModel,
    aiFilteringPriority,
    llmFilteringResult,
    loadEnvironmentAnalysis,
  }
}
