// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss
/**
 * Code Evolution Composable (Issue #243 - Phase 2, #247 - Timeline Visualization)
 *
 * Provides reactive state and methods for code evolution mining and analysis.
 */

import { ref, computed } from 'vue'
import axios from 'axios'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('useEvolution')

export interface EvolutionAnalysisRequest {
  repo_path: string
  start_date?: string
  end_date?: string
  commit_limit?: number
}

export interface PatternData {
  pattern_type: string
  count: number
  trend: string
  first_seen: string
  last_seen: string
}

export interface EvolutionAnalysisResponse {
  status: string
  message: string
  commits_analyzed: number
  emerging_patterns: PatternData[]
  declining_patterns: PatternData[]
  refactorings_detected: number
  analysis_duration_seconds: number
}

export interface TimelineData {
  timestamp: string
  overall_score?: number
  maintainability?: number
  testability?: number
  complexity?: number
  security?: number
  performance?: number
  [key: string]: any
}

export interface PatternEvolutionData {
  [patternType: string]: Array<{
    timestamp: string
    count: number
    pattern_type: string
  }>
}

export interface TrendEntry {
  first_value: number
  last_value: number
  change: number
  percent_change: number
  direction: 'improving' | 'declining' | 'stable'
  data_points: number
}

export interface TrendsData {
  [metric: string]: TrendEntry
}

export interface EvolutionSummary {
  total_snapshots: number
  date_range: { first: string | null; last: string | null }
  latest_scores: { overall_score?: number; maintainability?: number; complexity?: number }
  trend_direction: string
  pattern_counts: Record<string, number>
}

export function useEvolution() {
  const loading = ref(false)
  const error = ref<string | null>(null)

  const analysisResult = ref<EvolutionAnalysisResponse | null>(null)
  const timelineData = ref<TimelineData[]>([])
  const patternData = ref<PatternEvolutionData>({})
  const trendsData = ref<TrendsData>({})
  const summary = ref<EvolutionSummary | null>(null)

  // API client with auth token
  const api = axios.create({
    baseURL: '/api/analytics/evolution',
    timeout: 120000, // 2 minutes for long-running analysis
    headers: {
      'Content-Type': 'application/json',
    },
  })

  // Add auth token to requests
  api.interceptors.request.use((config) => {
    const token = localStorage.getItem('access_token')
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  })

  /**
   * Trigger code evolution analysis
   */
  async function analyzeEvolution(request: EvolutionAnalysisRequest): Promise<boolean> {
    loading.value = true
    error.value = null

    try {
      const response = await api.post<EvolutionAnalysisResponse>('/analyze', request)
      analysisResult.value = response.data

      // After analysis, fetch timeline and pattern data
      await fetchTimeline()
      await fetchPatternEvolution()

      logger.info('Evolution analysis complete', response.data)
      return true
    } catch (e: any) {
      const errorMsg = e.response?.data?.message || e.message || 'Analysis failed'
      error.value = errorMsg
      logger.error('Evolution analysis failed:', e)
      return false
    } finally {
      loading.value = false
    }
  }

  /**
   * Fetch evolution timeline data
   */
  async function fetchTimeline(
    start_date?: string,
    end_date?: string,
    granularity: string = 'daily',
    metrics: string = 'overall_score,complexity,maintainability'
  ): Promise<void> {
    loading.value = true
    error.value = null

    try {
      const params: any = { granularity, metrics }
      if (start_date) params.start_date = start_date
      if (end_date) params.end_date = end_date

      const response = await api.get<{ timeline: TimelineData[] }>('/timeline', { params })

      if (response.data.timeline) {
        timelineData.value = response.data.timeline
      }

      logger.info('Timeline data fetched', timelineData.value.length, 'points')
    } catch (e: any) {
      const errorMsg = e.response?.data?.message || e.message || 'Failed to fetch timeline'
      error.value = errorMsg
      logger.error('Failed to fetch timeline:', e)
    } finally {
      loading.value = false
    }
  }

  /**
   * Fetch pattern evolution data
   */
  async function fetchPatternEvolution(
    pattern_type?: string,
    start_date?: string,
    end_date?: string
  ): Promise<void> {
    loading.value = true
    error.value = null

    try {
      const params: any = {}
      if (pattern_type) params.pattern_type = pattern_type
      if (start_date) params.start_date = start_date
      if (end_date) params.end_date = end_date

      const response = await api.get<{ patterns: PatternEvolutionData }>('/patterns', { params })

      if (response.data.patterns) {
        patternData.value = response.data.patterns
      }

      logger.info('Pattern evolution data fetched', Object.keys(patternData.value).length, 'types')
    } catch (e: any) {
      const errorMsg = e.response?.data?.message || e.message || 'Failed to fetch pattern data'
      error.value = errorMsg
      logger.error('Failed to fetch pattern evolution:', e)
    } finally {
      loading.value = false
    }
  }

  /**
   * Fetch quality trend analysis (Issue #247)
   */
  async function fetchTrends(days: number = 30): Promise<void> {
    try {
      const response = await api.get<{ trends: TrendsData }>('/trends', { params: { days } })
      if (response.data.trends) {
        trendsData.value = response.data.trends
      }
      logger.info('Trends data fetched', Object.keys(trendsData.value).length, 'metrics')
    } catch (e: any) {
      logger.error('Failed to fetch trends:', e)
    }
  }

  /**
   * Fetch evolution summary stats (Issue #247)
   */
  async function fetchSummary(): Promise<void> {
    try {
      const response = await api.get<{ summary: EvolutionSummary }>('/summary')
      if (response.data.summary) {
        summary.value = response.data.summary
      }
      logger.info('Evolution summary fetched')
    } catch (e: any) {
      logger.error('Failed to fetch summary:', e)
    }
  }

  /**
   * Export evolution data as JSON or CSV (Issue #247)
   */
  async function exportData(
    format: 'json' | 'csv' = 'json',
    start_date?: string,
    end_date?: string
  ): Promise<void> {
    try {
      const params: any = { format }
      if (start_date) params.start_date = start_date
      if (end_date) params.end_date = end_date

      const response = await api.get('/export', {
        params,
        responseType: format === 'csv' ? 'blob' : 'json',
      })

      if (format === 'csv') {
        const blob = new Blob([response.data], { type: 'text/csv' })
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = `evolution_data_${new Date().toISOString().slice(0, 10)}.csv`
        a.click()
        URL.revokeObjectURL(url)
      } else {
        const blob = new Blob([JSON.stringify(response.data, null, 2)], {
          type: 'application/json',
        })
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = `evolution_data_${new Date().toISOString().slice(0, 10)}.json`
        a.click()
        URL.revokeObjectURL(url)
      }
      logger.info('Evolution data exported as', format)
    } catch (e: any) {
      const errorMsg = e.response?.data?.message || e.message || 'Export failed'
      error.value = errorMsg
      logger.error('Export failed:', e)
    }
  }

  /**
   * Clear all data
   */
  function clearData(): void {
    analysisResult.value = null
    timelineData.value = []
    patternData.value = {}
    trendsData.value = {}
    summary.value = null
    error.value = null
  }

  // Computed properties
  const hasTimelineData = computed(() => timelineData.value.length > 0)
  const hasPatternData = computed(() => Object.keys(patternData.value).length > 0)
  const hasAnalysisResult = computed(() => analysisResult.value !== null)
  const hasTrendsData = computed(() => Object.keys(trendsData.value).length > 0)

  return {
    // State
    loading,
    error,
    analysisResult,
    timelineData,
    patternData,
    trendsData,
    summary,

    // Computed
    hasTimelineData,
    hasPatternData,
    hasAnalysisResult,
    hasTrendsData,

    // Methods
    analyzeEvolution,
    fetchTimeline,
    fetchPatternEvolution,
    fetchTrends,
    fetchSummary,
    exportData,
    clearData,
  }
}
