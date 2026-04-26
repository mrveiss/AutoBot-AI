// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * Composable: useTechnicalDebtData
 *
 * Encapsulates all fetchWithAuth API calls for the TechnicalDebtDashboard:
 * summary, category breakdown, ROI priorities, debt items, trends, and
 * the markdown report export.
 *
 * Issue #6058: Extracted from TechnicalDebtDashboard.vue.
 */

import { ref } from 'vue'
import { fetchWithAuth } from '@/utils/fetchWithAuth'
import { createLogger } from '@/utils/debugUtils'
import { getApiBase } from '@/config/ssot-config'

const logger = createLogger('useTechnicalDebtData')

export interface DebtItem {
  id: string
  file_path: string
  line_number?: number
  category: string
  severity: string
  description: string
  estimated_hours: number
  impact_score: number
  roi_score: number
  suggested_fix?: string
  created_at: string
}

export interface CategoryBreakdown {
  category: string
  count: number
  total_hours: number
  avg_severity: string
}

export interface TrendPoint {
  date: string
  total_items: number
  total_hours: number
  by_category: Record<string, number>
}

export interface DebtSummary {
  total_items: number
  total_hours: number
  estimated_cost: number
  critical_count: number
  health_score: number
  trend: number
}

export function useTechnicalDebtData() {
  const isLoading = ref(false)
  const error = ref<string | null>(null)

  async function fetchSummary(): Promise<{ summary: DebtSummary; rawResult: Record<string, unknown> }> {
    isLoading.value = true
    error.value = null
    try {
      // Issue #552: Fixed path - backend uses /api/debt/* not /api/analytics/debt/*
      const response = await fetchWithAuth(`${getApiBase()}/debt/summary`)
      if (!response.ok) {
        const msg = `Failed to load summary (HTTP ${response.status})`
        logger.warn('Failed to load summary: HTTP', response.status)
        error.value = msg
        throw new Error(msg)
      }
      const result = await response.json() as Record<string, unknown>
      error.value = null
      return { summary: (result.summary ?? result) as DebtSummary, rawResult: result }
    } catch (e) {
      const msg = e instanceof Error ? e.message : 'Failed to connect to analytics API'
      error.value = msg
      logger.error('Failed to load summary:', e)
      throw e
    } finally {
      isLoading.value = false
    }
  }

  async function fetchCategoryBreakdown(): Promise<CategoryBreakdown[]> {
    isLoading.value = true
    error.value = null
    try {
      // Issue #552: Fixed - backend returns summary.by_category from /debt/summary
      const response = await fetchWithAuth(`${getApiBase()}/debt/summary`)
      if (!response.ok) {
        logger.warn('Failed to load category breakdown: HTTP', response.status)
        return []
      }
      const result = await response.json() as Record<string, unknown>
      const nested = result.summary as Record<string, unknown> | undefined
      return ((nested?.by_category ?? (result.by_category ?? [])) as CategoryBreakdown[])
    } catch (e) {
      logger.error('Failed to load category breakdown:', e)
      return []
    } finally {
      isLoading.value = false
    }
  }

  async function fetchRoiPriorities(limit = 10): Promise<DebtItem[]> {
    isLoading.value = true
    error.value = null
    try {
      // Issue #552: Fixed path - backend returns {status, priorities: [...], total_available: N}
      const response = await fetchWithAuth(`${getApiBase()}/debt/roi-priorities?limit=${limit}`)
      if (!response.ok) {
        logger.warn('Failed to load ROI priorities: HTTP', response.status)
        return []
      }
      const result = await response.json() as Record<string, unknown>
      return ((result.priorities ?? result) as DebtItem[])
    } catch (e) {
      logger.error('Failed to load ROI priorities:', e)
      return []
    } finally {
      isLoading.value = false
    }
  }

  async function fetchDebtItems(): Promise<DebtItem[]> {
    isLoading.value = true
    error.value = null
    try {
      // Issue #552: Fixed - backend uses POST for /api/debt/calculate
      // Backend returns {status, data: {items, summary, ...}} structure
      const response = await fetchWithAuth(`${getApiBase()}/debt/calculate`, { method: 'POST' })
      if (!response.ok) {
        logger.warn('Failed to load debt items: HTTP', response.status)
        return []
      }
      const result = await response.json() as Record<string, unknown>
      const data = result.data as Record<string, unknown> | undefined
      return ((data?.items ?? (result.items ?? [])) as DebtItem[])
    } catch (e) {
      logger.error('Failed to load debt items:', e)
      return []
    } finally {
      isLoading.value = false
    }
  }

  async function fetchTrends(period: string): Promise<TrendPoint[]> {
    isLoading.value = true
    error.value = null
    try {
      // Issue #552: Fixed path - backend returns {status, trends: [...], ...}
      const response = await fetchWithAuth(`${getApiBase()}/debt/trends?period=${period}`)
      if (!response.ok) {
        logger.warn('Failed to load trends: HTTP', response.status)
        return []
      }
      const result = await response.json() as Record<string, unknown>
      return ((result.trends ?? result) as TrendPoint[])
    } catch (e) {
      logger.error('Failed to load trends:', e)
      return []
    } finally {
      isLoading.value = false
    }
  }

  async function fetchReportBlob(): Promise<string> {
    isLoading.value = true
    error.value = null
    try {
      // Issue #552: Fixed path - backend returns {status, format, report: "markdown content"}
      const response = await fetchWithAuth(`${getApiBase()}/debt/report?format=markdown`)
      if (!response.ok) {
        const msg = `Failed to fetch report (HTTP ${response.status})`
        error.value = msg
        throw new Error(msg)
      }
      const result = await response.json() as Record<string, unknown>
      return (result.report as string) ?? ''
    } catch (e) {
      logger.error('Failed to export report:', e)
      throw e
    } finally {
      isLoading.value = false
    }
  }

  return {
    isLoading,
    error,
    fetchSummary,
    fetchCategoryBreakdown,
    fetchRoiPriorities,
    fetchDebtItems,
    fetchTrends,
    fetchReportBlob,
  }
}
