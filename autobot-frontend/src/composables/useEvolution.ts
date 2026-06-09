// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * Code Evolution Composable (Issue #243 - Phase 2, #247 - Timeline Visualization)
 *
 * Provides reactive state and methods for code evolution mining and analysis.
 */

import { ref, computed, isRef, type ComputedRef } from 'vue'
import ApiClient from '@/utils/ApiClient'
import { useLoadingState } from '@/composables/useLoadingState'
import { createLogger } from '@/utils/debugUtils'
import { extractApiErrorMessage } from '@/utils/errorExtract'
import { getApiBase } from '@/config/ssot-config'

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
  [key: string]: string | number | undefined
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

export function useEvolution(sourceId?: string | ComputedRef<string | undefined>) {
  const { isLoading: loading, wrap } = useLoadingState()
  const error = ref<string | null>(null)

  const analysisResult = ref<EvolutionAnalysisResponse | null>(null)
  const timelineData = ref<TimelineData[]>([])
  const patternData = ref<PatternEvolutionData>({})
  const trendsData = ref<TrendsData>({})
  const summary = ref<EvolutionSummary | null>(null)

  /**
   * Merge source_id into params when sourceId is provided (Issue #3436).
   * Accepts a plain string or ComputedRef so callers pass a reactive route
   * param without freezing the value at setup time.
   */
  function withSourceId(params: Record<string, string> = {}): Record<string, string> {
    const id = isRef(sourceId) ? sourceId.value : sourceId
    if (!id) return params
    return { ...params, source_id: id }
  }

  /**
   * Trigger code evolution analysis
   */
  async function analyzeEvolution(request: EvolutionAnalysisRequest): Promise<boolean> {
    error.value = null
    try {
      const data = await wrap(() =>
        ApiClient.post<EvolutionAnalysisResponse>(
          `${getApiBase()}/evolution/analyze`,
          request,
          { timeout: 120000 }
        )
      )
      analysisResult.value = data

      // After analysis, fetch timeline and pattern data
      await fetchTimeline()
      await fetchPatternEvolution()

      logger.info('Evolution analysis complete', data)
      return true
    } catch (e: unknown) {
      error.value = extractApiErrorMessage(e, 'Analysis failed')
      logger.error('Evolution analysis failed:', e)
      return false
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
    error.value = null
    try {
      const params: Record<string, string> = { granularity, metrics }
      if (start_date) params.start_date = start_date
      if (end_date) params.end_date = end_date

      // Issue #3436: scope to project when sourceId is provided
      const qs = new URLSearchParams(withSourceId(params)).toString()
      const data = await wrap(() =>
        ApiClient.get<{ timeline: TimelineData[] }>(
          `${getApiBase()}/evolution/timeline?${qs}`,
          { timeout: 120000 }
        )
      )

      if (data.timeline) {
        timelineData.value = data.timeline
      }

      logger.info('Timeline data fetched', { count: timelineData.value.length })
    } catch (e: unknown) {
      error.value = extractApiErrorMessage(e, 'Failed to fetch timeline')
      logger.error('Failed to fetch timeline:', e)
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
    error.value = null
    try {
      const params: Record<string, string> = {}
      if (pattern_type) params.pattern_type = pattern_type
      if (start_date) params.start_date = start_date
      if (end_date) params.end_date = end_date

      // Issue #3436: scope to project when sourceId is provided
      const qs = new URLSearchParams(withSourceId(params)).toString()
      const data = await wrap(() =>
        ApiClient.get<{ patterns: PatternEvolutionData }>(
          `${getApiBase()}/evolution/patterns?${qs}`,
          { timeout: 120000 }
        )
      )

      if (data.patterns) {
        patternData.value = data.patterns
      }

      logger.info('Pattern evolution data fetched', { count: Object.keys(patternData.value).length })
    } catch (e: unknown) {
      error.value = extractApiErrorMessage(e, 'Failed to fetch pattern data')
      logger.error('Failed to fetch pattern evolution:', e)
    }
  }

  /**
   * Fetch quality trend analysis (Issue #247)
   */
  async function fetchTrends(days: number = 30): Promise<void> {
    try {
      // Issue #3436: scope to project when sourceId is provided
      const qs = new URLSearchParams(withSourceId({ days: String(days) })).toString()
      const data = await ApiClient.get<{ trends: TrendsData }>(
        `${getApiBase()}/evolution/trends?${qs}`
      )
      if (data.trends) {
        trendsData.value = data.trends
      }
      logger.info('Trends data fetched', { count: Object.keys(trendsData.value).length })
    } catch (e: unknown) {
      logger.error('Failed to fetch trends:', e)
    }
  }

  /**
   * Fetch evolution summary stats (Issue #247)
   */
  async function fetchSummary(): Promise<void> {
    try {
      // Issue #3436: scope to project when sourceId is provided
      const params = withSourceId()
      const qs = new URLSearchParams(params).toString()
      const url = `${getApiBase()}/evolution/summary${qs ? `?${qs}` : ''}`
      const data = await ApiClient.get<{ summary: EvolutionSummary }>(url)
      if (data.summary) {
        summary.value = data.summary
      }
      logger.info('Evolution summary fetched')
    } catch (e: unknown) {
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
      const params: Record<string, string> = { format }
      if (start_date) params.start_date = start_date
      if (end_date) params.end_date = end_date

      const qs = new URLSearchParams(params).toString()
      const response = await ApiClient.rawRequest(
        `${getApiBase()}/evolution/export?${qs}`
      )

      let blob: Blob
      if (format === 'csv') {
        blob = await response.blob()
      } else {
        const data = await response.json()
        blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
      }
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `evolution_data_${new Date().toISOString().slice(0, 10)}.${format}`
      a.click()
      URL.revokeObjectURL(url)
      logger.info('Evolution data exported as', format)
    } catch (e: unknown) {
      error.value = extractApiErrorMessage(e, 'Export failed')
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
