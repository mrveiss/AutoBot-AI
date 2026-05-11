// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * Composable: useLLMPatternData
 *
 * Migrated from raw fetchWithAuth to useFetchEndpoint / useApi (#6152) for
 * AbortController, race protection, and consistent error handling.
 */

import { computed } from 'vue'
import { useFetchEndpoint } from '@/composables/api/useFetchEndpoint'
import { useApiClient } from '@/plugins/api'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('useLLMPatternData')

export interface LLMPatternStats {
  total_requests: number
  total_cost: number
  avg_cost_per_request: number
  success_rate: number
  by_date: Array<{ date: string; requests: number; cost: number; success_rate: number }>
  by_model: Record<string, number>
}

export interface LLMPatternRecommendation {
  type: string
  title: string
  description: string
  potential_savings: number
  priority: number
  affected_prompts: number
  implementation_steps: string[]
}

export interface LLMPatternModelData {
  model: string
  request_count: number
  total_tokens: number
  total_cost: number
  avg_cost_per_request: number
  avg_response_time: number
  success_rate: number
}

export interface LLMPatternCategoryData {
  categories: Array<{
    category: string
    count: number
    percentage: number
    cost: number
    cost_percentage: number
  }>
  total_count: number
  total_cost: number
}

export interface LLMPatternCacheOpportunity {
  prompt_hash: string
  prompt_preview: string
  occurrence_count: number
  total_cost: number
  potential_savings: number
}

export interface LLMPatternAnalysisResult {
  prompt_hash: string
  category: string
  estimated_tokens: number
  estimated_cost: number
  issues: Array<{ type: string; message: string; severity: string }>
  recommendations: string[]
  cache_potential: boolean
}

interface StatsRaw {
  total_requests: number
  total_cost: number
  avg_cost_per_request: number
  success_rate: number
  by_date: Array<{ date: string; requests: number; cost: number; success_rate: number }>
  by_model: Record<string, number>
}

interface RecommendationsRaw {
  recommendations?: LLMPatternRecommendation[]
}

interface ModelComparisonRaw {
  models?: LLMPatternModelData[]
}

interface CacheOpportunitiesRaw {
  opportunities?: LLMPatternCacheOpportunity[]
}

export function useLLMPatternData() {
  const api = useApiClient()

  const statsEndpoint = useFetchEndpoint<StatsRaw, LLMPatternStats>(
    {
      path: '/api/llm-patterns/stats',
      pickData: (raw) => raw as LLMPatternStats,
      onError: (_message, e) => { logger.error('Failed to fetch stats:', e) },
      label: 'LLM pattern stats',
    },
  )

  const recommendationsEndpoint = useFetchEndpoint<RecommendationsRaw, LLMPatternRecommendation[]>(
    {
      path: '/api/llm-patterns/recommendations',
      pickData: (raw) => raw.recommendations ?? [],
      onError: (_message, e) => { logger.error('Failed to fetch recommendations:', e) },
      label: 'LLM pattern recommendations',
    },
  )

  const modelComparisonEndpoint = useFetchEndpoint<ModelComparisonRaw, LLMPatternModelData[]>(
    {
      path: '/api/llm-patterns/model-comparison',
      pickData: (raw) => raw.models ?? [],
      onError: (_message, e) => { logger.error('Failed to fetch model comparison:', e) },
      label: 'LLM pattern model comparison',
    },
  )

  const categoryDistributionEndpoint = useFetchEndpoint<LLMPatternCategoryData, LLMPatternCategoryData>(
    {
      path: '/api/llm-patterns/category-distribution',
      pickData: (raw) => raw,
      onError: (_message, e) => { logger.error('Failed to fetch category distribution:', e) },
      label: 'LLM pattern category distribution',
    },
  )

  const cacheOpportunitiesEndpoint = useFetchEndpoint<CacheOpportunitiesRaw, LLMPatternCacheOpportunity[]>(
    {
      path: '/api/llm-patterns/cache-opportunities',
      pickData: (raw) => raw.opportunities ?? [],
      onError: (_message, e) => { logger.error('Failed to fetch cache opportunities:', e) },
      label: 'LLM pattern cache opportunities',
    },
  )

  // Combined loading/error for backward-compatible public API
  const allEndpoints = [
    statsEndpoint,
    recommendationsEndpoint,
    modelComparisonEndpoint,
    categoryDistributionEndpoint,
    cacheOpportunitiesEndpoint,
  ]
  const isLoading = computed(() => allEndpoints.some((ep) => ep.loading.value))
  const error = computed(() =>
    allEndpoints.map((ep) => ep.error.value).find((e) => e !== '') ?? null
  )

  async function fetchStats(days = 7): Promise<LLMPatternStats | null> {
    await statsEndpoint.load({ days: String(days) })
    return statsEndpoint.data.value
  }

  async function fetchRecommendations(): Promise<LLMPatternRecommendation[]> {
    await recommendationsEndpoint.load()
    return recommendationsEndpoint.data.value ?? []
  }

  async function fetchModelComparison(): Promise<LLMPatternModelData[]> {
    await modelComparisonEndpoint.load()
    return modelComparisonEndpoint.data.value ?? []
  }

  async function fetchCategoryDistribution(): Promise<LLMPatternCategoryData | null> {
    await categoryDistributionEndpoint.load()
    return categoryDistributionEndpoint.data.value
  }

  async function fetchCacheOpportunities(): Promise<LLMPatternCacheOpportunity[]> {
    await cacheOpportunitiesEndpoint.load()
    return cacheOpportunitiesEndpoint.data.value ?? []
  }

  async function analyzePrompt(
    prompt: string,
    model: string | null,
  ): Promise<LLMPatternAnalysisResult | null> {
    try {
      return await api.post<LLMPatternAnalysisResult>('/api/llm-patterns/analyze', { prompt, model })
    } catch (e) {
      logger.error('Failed to analyze prompt:', e)
      return null
    }
  }

  return {
    isLoading,
    error,
    fetchStats,
    fetchRecommendations,
    fetchModelComparison,
    fetchCategoryDistribution,
    fetchCacheOpportunities,
    analyzePrompt,
  }
}
