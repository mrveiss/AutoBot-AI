import { ref } from 'vue'
import { fetchWithAuth } from '@/utils/fetchWithAuth'
import { getApiBase } from '@/config/ssot-config'
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

export function useLLMPatternData() {
  const isLoading = ref(false)
  const error = ref<string | null>(null)

  async function fetchStats(days = 7): Promise<LLMPatternStats | null> {
    isLoading.value = true
    error.value = null
    try {
      const response = await fetchWithAuth(`${getApiBase()}/llm-patterns/stats?days=${days}`)
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      return await response.json() as LLMPatternStats
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Unknown error'
      logger.error('Failed to fetch stats:', e)
      return null
    } finally {
      isLoading.value = false
    }
  }

  async function fetchRecommendations(): Promise<LLMPatternRecommendation[]> {
    isLoading.value = true
    error.value = null
    try {
      const response = await fetchWithAuth(`${getApiBase()}/llm-patterns/recommendations`)
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      const data = await response.json() as { recommendations?: LLMPatternRecommendation[] }
      return data.recommendations ?? []
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Unknown error'
      logger.error('Failed to fetch recommendations:', e)
      return []
    } finally {
      isLoading.value = false
    }
  }

  async function fetchModelComparison(): Promise<LLMPatternModelData[]> {
    isLoading.value = true
    error.value = null
    try {
      const response = await fetchWithAuth(`${getApiBase()}/llm-patterns/model-comparison`)
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      const data = await response.json() as { models?: LLMPatternModelData[] }
      return data.models ?? []
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Unknown error'
      logger.error('Failed to fetch model comparison:', e)
      return []
    } finally {
      isLoading.value = false
    }
  }

  async function fetchCategoryDistribution(): Promise<LLMPatternCategoryData | null> {
    isLoading.value = true
    error.value = null
    try {
      const response = await fetchWithAuth(`${getApiBase()}/llm-patterns/category-distribution`)
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      return await response.json() as LLMPatternCategoryData
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Unknown error'
      logger.error('Failed to fetch category distribution:', e)
      return null
    } finally {
      isLoading.value = false
    }
  }

  async function fetchCacheOpportunities(): Promise<LLMPatternCacheOpportunity[]> {
    isLoading.value = true
    error.value = null
    try {
      const response = await fetchWithAuth(`${getApiBase()}/llm-patterns/cache-opportunities`)
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      const data = await response.json() as { opportunities?: LLMPatternCacheOpportunity[] }
      return data.opportunities ?? []
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Unknown error'
      logger.error('Failed to fetch cache opportunities:', e)
      return []
    } finally {
      isLoading.value = false
    }
  }

  async function analyzePrompt(
    prompt: string,
    model: string | null
  ): Promise<LLMPatternAnalysisResult | null> {
    isLoading.value = true
    error.value = null
    try {
      const response = await fetchWithAuth(`${getApiBase()}/llm-patterns/analyze`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt, model })
      })
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      return await response.json() as LLMPatternAnalysisResult
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Unknown error'
      logger.error('Failed to analyze prompt:', e)
      return null
    } finally {
      isLoading.value = false
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
    analyzePrompt
  }
}
