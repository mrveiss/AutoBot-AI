// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * Composable: useCodeQualityData
 *
 * Encapsulates all fetchWithAuth calls for the Code Quality Dashboard.
 * Extracted from CodeQualityDashboard.vue (Issue #6055).
 *
 * Endpoints (all under /api/quality/*):
 *   GET  /quality/health-score
 *   GET  /quality/metrics
 *   GET  /quality/patterns
 *   GET  /quality/complexity?top_n=5
 *   GET  /quality/trends?period=<period>
 *   GET  /quality/snapshot
 *   GET  /quality/drill-down/<category>
 *   GET  /quality/export?format=<format>
 */

import { ref } from 'vue'
import { fetchWithAuth } from '@/utils/fetchWithAuth'
import { getApiBase } from '@/config/ssot-config'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('useCodeQualityData')

export interface QualityHealthScore {
  overall: number
  grade: string
  trend: number
  breakdown: Record<string, number>
  components: Record<string, number>
  recommendations: string[]
}

export interface QualityMetric {
  name: string
  category: string
  value: number
  grade: string
  trend: number
  weight: number
}

export interface QualityPattern {
  type: string
  display_name: string
  count: number
  percentage: number
  severity: string
}

export interface QualityComplexity {
  averages: { cyclomatic: number; cognitive: number }
  maximums: { cyclomatic: number; cognitive: number }
  hotspots: Array<{ file: string; complexity: number; lines: number }>
}

export interface QualityDrillDown {
  total_files: number
  total_issues: number
  average_score: number
  files: Array<{ path: string; issues: number; score: number; top_issue: string }>
}

export interface QualityExportResult {
  format: string
  content?: string
  [key: string]: unknown
}

export function useCodeQualityData(withSourceId: (url: string) => string) {
  const isLoading = ref(false)
  const error = ref<string | null>(null)

  async function fetchHealthScore(): Promise<QualityHealthScore | null> {
    error.value = null
    try {
      // Issue #552: backend uses /api/quality/* not /api/analytics/quality/*
      // Issue #3436: scope to project when sourceId is present
      const response = await fetchWithAuth(withSourceId(`${getApiBase()}/quality/health-score`))
      if (!response.ok) {
        logger.warn('Failed to load health score: HTTP', response.status)
        return null
      }
      const data = await response.json()
      return {
        overall: data.overall ?? 0,
        grade: data.grade || 'C',
        trend: data.trend ?? 0,
        breakdown: data.breakdown || {},
        components: data.components || { code_quality: 0, security: 0, performance: 0 },
        recommendations: data.recommendations || [],
      }
    } catch (e) {
      logger.error('Failed to load health score:', e)
      error.value = e instanceof Error ? e.message : 'Unknown error'
      return null
    }
  }

  async function fetchMetrics(): Promise<QualityMetric[]> {
    error.value = null
    try {
      // Issue #552 / #3436
      const response = await fetchWithAuth(withSourceId(`${getApiBase()}/quality/metrics`))
      if (!response.ok) {
        logger.warn('Failed to load metrics: HTTP', response.status)
        return []
      }
      const data = await response.json()
      return Array.isArray(data) ? data : (data.metrics || [])
    } catch (e) {
      logger.error('Failed to load metrics:', e)
      error.value = e instanceof Error ? e.message : 'Unknown error'
      return []
    }
  }

  async function fetchPatterns(): Promise<QualityPattern[]> {
    error.value = null
    try {
      // Issue #552 / #3436
      const response = await fetchWithAuth(withSourceId(`${getApiBase()}/quality/patterns`))
      if (!response.ok) {
        logger.warn('Failed to load patterns: HTTP', response.status)
        return []
      }
      const data = await response.json()
      return Array.isArray(data) ? data : (data.patterns || [])
    } catch (e) {
      logger.error('Failed to load patterns:', e)
      error.value = e instanceof Error ? e.message : 'Unknown error'
      return []
    }
  }

  async function fetchComplexity(): Promise<QualityComplexity | null> {
    error.value = null
    try {
      // Issue #552 / #3436
      const response = await fetchWithAuth(withSourceId(`${getApiBase()}/quality/complexity?top_n=5`))
      if (!response.ok) {
        logger.warn('Failed to load complexity: HTTP', response.status)
        return null
      }
      const data = await response.json()
      return {
        averages: data.averages || { cyclomatic: 0, cognitive: 0 },
        maximums: data.maximums || { cyclomatic: 0, cognitive: 0 },
        hotspots: data.hotspots || [],
      }
    } catch (e) {
      logger.error('Failed to load complexity:', e)
      error.value = e instanceof Error ? e.message : 'Unknown error'
      return null
    }
  }

  async function fetchTrends(period: string): Promise<Array<{ date: string; score: number }>> {
    error.value = null
    try {
      // Issue #552 / #3436
      const response = await fetchWithAuth(withSourceId(`${getApiBase()}/quality/trends?period=${period}`))
      if (!response.ok) {
        logger.warn('Failed to load trends: HTTP', response.status)
        return []
      }
      const data = await response.json()
      return data.data_points || []
    } catch (e) {
      logger.error('Failed to load trends:', e)
      error.value = e instanceof Error ? e.message : 'Unknown error'
      return []
    }
  }

  async function fetchSnapshot(): Promise<{ files: number; lines: number; issues: number } | null> {
    error.value = null
    try {
      // Issue #552 / #3436
      const response = await fetchWithAuth(withSourceId(`${getApiBase()}/quality/snapshot`))
      if (!response.ok) {
        logger.warn('Failed to load snapshot: HTTP', response.status)
        return null
      }
      const data = await response.json()
      return data.codebase_stats || { files: 0, lines: 0, issues: 0 }
    } catch (e) {
      logger.error('Failed to load snapshot:', e)
      error.value = e instanceof Error ? e.message : 'Unknown error'
      return null
    }
  }

  async function fetchDrillDown(category: string): Promise<QualityDrillDown | null> {
    error.value = null
    try {
      // Issue #552 / #3436
      const response = await fetchWithAuth(withSourceId(`${getApiBase()}/quality/drill-down/${category}`))
      if (!response.ok) {
        logger.warn('Failed to load drill-down data: HTTP', response.status)
        return null
      }
      return await response.json()
    } catch (e) {
      logger.error('Failed to load drill-down data:', e)
      error.value = e instanceof Error ? e.message : 'Unknown error'
      return null
    }
  }

  async function fetchExport(format: string): Promise<QualityExportResult | null> {
    error.value = null
    try {
      // Issue #552: no source scoping for export
      const response = await fetchWithAuth(`${getApiBase()}/quality/export?format=${format}`)
      if (!response.ok) {
        logger.warn('Failed to export report: HTTP', response.status)
        return null
      }
      return await response.json()
    } catch (e) {
      logger.error('Failed to export report:', e)
      error.value = e instanceof Error ? e.message : 'Unknown error'
      return null
    }
  }

  return {
    isLoading,
    error,
    fetchHealthScore,
    fetchMetrics,
    fetchPatterns,
    fetchComplexity,
    fetchTrends,
    fetchSnapshot,
    fetchDrillDown,
    fetchExport,
  }
}
