// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * Composable: useCodeEvolutionData
 *
 * Encapsulates all fetchWithAuth calls for the Code Evolution Timeline.
 * Extracted from CodeEvolutionTimeline.vue (Issue #6072).
 *
 * Endpoints (all under /api/evolution/*):
 *   GET  /evolution/timeline?start_date=<d>&end_date=<d>&granularity=<g>&metrics=<m>
 *   GET  /evolution/trends?days=<n>
 *   GET  /evolution/patterns
 *   GET  /evolution/export?format=csv&start_date=<d>&end_date=<d>
 */

import { ref } from 'vue'
import { fetchWithAuth } from '@/utils/fetchWithAuth'
import apiClient from '@/utils/ApiClient'
import { getApiBase } from '@/config/ssot-config'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('useCodeEvolutionData')

export interface TimelinePoint {
  timestamp: string
  overall_score?: number
  maintainability?: number
  testability?: number
  documentation?: number
  complexity?: number
  security?: number
  performance?: number
  total_files?: number
  total_lines?: number
}

export interface TrendData {
  first_value: number
  last_value: number
  change: number
  percent_change: number
  direction: 'improving' | 'declining' | 'stable'
  data_points: number
}

export interface PatternPoint {
  timestamp: string
  count: number
  pattern_type: string
}

export interface TimelineResult {
  timeline: TimelinePoint[]
  status?: string
}

export interface TrendsResult {
  trends: Record<string, TrendData>
}

export interface PatternsResult {
  patterns: Record<string, PatternPoint[]>
}

export function useCodeEvolutionData() {
  const isLoading = ref(false)
  const error = ref<string | null>(null)

  async function fetchTimeline(
    startDate: string,
    endDate: string,
    granularity: string,
    metrics: string[]
  ): Promise<TimelineResult | null> {
    error.value = null
    try {
      const params = new URLSearchParams({
        start_date: startDate,
        end_date: endDate,
        granularity,
        metrics: metrics.join(','),
      })
      // Issue #552: backend uses /api/evolution/* not /api/analytics/evolution/*
      return await apiClient.get<TimelineResult>(`${getApiBase()}/evolution/timeline?${params}`)
    } catch (e) {
      logger.error('Failed to load evolution timeline:', e)
      error.value = e instanceof Error ? e.message : 'Unknown error'
      return null
    }
  }

  async function fetchTrends(days: string): Promise<TrendsResult | null> {
    error.value = null
    try {
      // Issue #552: backend uses /api/evolution/* not /api/analytics/evolution/*
      return await apiClient.get<TrendsResult>(`${getApiBase()}/evolution/trends?days=${days}`)
    } catch (e) {
      logger.error('Failed to load evolution trends:', e)
      error.value = e instanceof Error ? e.message : 'Unknown error'
      return null
    }
  }

  async function fetchPatterns(): Promise<PatternsResult | null> {
    error.value = null
    try {
      // Issue #552: backend uses /api/evolution/* not /api/analytics/evolution/*
      return await apiClient.get<PatternsResult>(`${getApiBase()}/evolution/patterns`)
    } catch (e) {
      logger.error('Failed to load evolution patterns:', e)
      error.value = e instanceof Error ? e.message : 'Unknown error'
      return null
    }
  }

  async function fetchExport(startDate: string, endDate: string): Promise<Blob | null> {
    error.value = null
    try {
      // Issue #552: backend uses /api/evolution/* not /api/analytics/evolution/*
      const response = await fetchWithAuth( // fetchWithAuth retained: binary blob response — exempt from Wave 5 (#6224)
        `${getApiBase()}/evolution/export?format=csv&start_date=${startDate}&end_date=${endDate}`
      )
      if (!response.ok) {
        logger.warn('Failed to export evolution data: HTTP', response.status)
        return null
      }
      return await response.blob()
    } catch (e) {
      logger.error('Failed to export evolution data:', e)
      error.value = e instanceof Error ? e.message : 'Unknown error'
      return null
    }
  }

  return {
    isLoading,
    error,
    fetchTimeline,
    fetchTrends,
    fetchPatterns,
    fetchExport,
  }
}
