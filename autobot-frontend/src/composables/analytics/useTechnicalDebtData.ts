// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * Composable: useTechnicalDebtData
 *
 * Encapsulates all API calls for the TechnicalDebtDashboard:
 * summary, category breakdown, ROI priorities, debt items, trends, and
 * the markdown report export.
 *
 * Issue #6058: Extracted from TechnicalDebtDashboard.vue.
 * Migrated from bare fetchWithAuth to useFetchEndpoint (#6152) for GET calls,
 * useApi for the POST /debt/calculate mutation.
 */

import { ref } from 'vue'
import { useFetchEndpoint } from '@/composables/api/useFetchEndpoint'
import { useApiClient } from '@/plugins/api'
import { createLogger } from '@/utils/debugUtils'

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

interface SummaryRaw {
  summary?: DebtSummary
  by_category?: CategoryBreakdown[]
  [key: string]: unknown
}

interface RoiRaw {
  priorities?: DebtItem[]
  [key: string]: unknown
}

interface TrendsRaw {
  trends?: TrendPoint[]
  [key: string]: unknown
}

interface ReportRaw {
  report?: string
  [key: string]: unknown
}

export function useTechnicalDebtData() {
  const isLoading = ref(false)
  const error = ref<string | null>(null)
  const api = useApiClient()

  // ---- Summary ------------------------------------------------------------
  // Issue #552: Fixed path - backend uses /api/debt/* not /api/analytics/debt/*

  const summaryEndpoint = useFetchEndpoint<SummaryRaw, { summary: DebtSummary; rawResult: SummaryRaw }>(
    {
      path: '/api/debt/summary',
      pickData: (raw) => ({ summary: (raw.summary ?? raw) as DebtSummary, rawResult: raw }),
      onError: (message, err) => {
        logger.error('Failed to load summary:', err)
        error.value = message
      },
      label: 'Debt summary',
    },
  )

  async function fetchSummary(): Promise<{ summary: DebtSummary; rawResult: Record<string, unknown> }> {
    isLoading.value = true
    error.value = null
    try {
      await summaryEndpoint.load()
      if (summaryEndpoint.error.value) {
        const msg = summaryEndpoint.error.value
        error.value = msg
        throw new Error(msg)
      }
      error.value = null
      return summaryEndpoint.data.value!
    } finally {
      isLoading.value = false
    }
  }

  // ---- Category breakdown -------------------------------------------------
  // Issue #552: Fixed - backend returns summary.by_category from /debt/summary

  const categoryEndpoint = useFetchEndpoint<SummaryRaw, CategoryBreakdown[]>(
    {
      path: '/api/debt/summary',
      pickData: (raw) => {
        const nested = raw.summary as Record<string, unknown> | undefined
        return (nested?.by_category ?? raw.by_category ?? []) as CategoryBreakdown[]
      },
      onError: (message, err) => {
        logger.error('Failed to load category breakdown:', err)
      },
      fallbackData: () => [],
      label: 'Category breakdown',
    },
  )

  async function fetchCategoryBreakdown(): Promise<CategoryBreakdown[]> {
    isLoading.value = true
    error.value = null
    try {
      await categoryEndpoint.load()
      return categoryEndpoint.data.value ?? []
    } finally {
      isLoading.value = false
    }
  }

  // ---- ROI priorities -----------------------------------------------------
  // Issue #552: Fixed path - backend returns {status, priorities: [...], total_available: N}

  const roiEndpoint = useFetchEndpoint<RoiRaw, DebtItem[]>(
    {
      path: '/api/debt/roi-priorities',
      pickData: (raw) => (raw.priorities ?? raw) as DebtItem[],
      onError: (message, err) => {
        logger.error('Failed to load ROI priorities:', err)
      },
      fallbackData: () => [],
      label: 'ROI priorities',
    },
  )

  async function fetchRoiPriorities(limit = 10): Promise<DebtItem[]> {
    isLoading.value = true
    error.value = null
    try {
      await roiEndpoint.load({ limit: String(limit) })
      return roiEndpoint.data.value ?? []
    } finally {
      isLoading.value = false
    }
  }

  // ---- Debt items (POST /debt/calculate via useApi) -----------------------
  // Issue #552: Fixed - backend uses POST for /api/debt/calculate
  // Backend returns {status, data: {items, summary, ...}} structure

  async function fetchDebtItems(): Promise<DebtItem[]> {
    isLoading.value = true
    error.value = null
    try {
      const result = await api.post<Record<string, unknown>>('/api/debt/calculate')
      const data = result.data as Record<string, unknown> | undefined
      return ((data?.items ?? (result.items ?? [])) as DebtItem[])
    } catch (e) {
      logger.error('Failed to load debt items:', e)
      return []
    } finally {
      isLoading.value = false
    }
  }

  // ---- Trends -------------------------------------------------------------
  // Issue #552: Fixed path - backend returns {status, trends: [...], ...}

  const trendsEndpoint = useFetchEndpoint<TrendsRaw, TrendPoint[]>(
    {
      path: '/api/debt/trends',
      pickData: (raw) => (raw.trends ?? raw) as TrendPoint[],
      onError: (message, err) => {
        logger.error('Failed to load trends:', err)
      },
      fallbackData: () => [],
      label: 'Debt trends',
    },
  )

  async function fetchTrends(period: string): Promise<TrendPoint[]> {
    isLoading.value = true
    error.value = null
    try {
      await trendsEndpoint.load({ period })
      return trendsEndpoint.data.value ?? []
    } finally {
      isLoading.value = false
    }
  }

  // ---- Report blob --------------------------------------------------------
  // Issue #552: Fixed path - backend returns {status, format, report: "markdown content"}

  const reportEndpoint = useFetchEndpoint<ReportRaw, string>(
    {
      path: '/api/debt/report',
      pickData: (raw) => (raw.report as string) ?? '',
      onError: (message, err) => {
        logger.error('Failed to export report:', err)
        error.value = message
      },
      label: 'Debt report',
    },
  )

  async function fetchReportBlob(): Promise<string> {
    isLoading.value = true
    error.value = null
    try {
      await reportEndpoint.load({ format: 'markdown' })
      if (reportEndpoint.error.value) {
        const msg = reportEndpoint.error.value
        error.value = msg
        throw new Error(msg)
      }
      return reportEndpoint.data.value ?? ''
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
