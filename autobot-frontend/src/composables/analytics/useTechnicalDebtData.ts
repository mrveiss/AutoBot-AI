// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
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

import { ref, computed } from 'vue'
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

/** ROI list paging (#12741): /api/debt/roi-priorities takes `limit` up to ROI_MAX and reports `total_available`. */
export const ROI_PAGE = 10
export const ROI_MAX = 100

interface RoiRaw {
  priorities?: DebtItem[]
  /** How many ROI-ranked items exist; `priorities` holds at most the requested `limit` of them. */
  total_available?: number
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

  const roiTotal = ref(0)
  const roiLimit = ref(ROI_PAGE)
  /** The server hands out at most ROI_MAX items; past that there is no more to ask for. */
  const roiAtCap = computed(() => roiLimit.value >= ROI_MAX)
  const roiEndpoint = useFetchEndpoint<RoiRaw, DebtItem[]>(
    {
      path: '/api/debt/roi-priorities',
      pickData: (raw) => {
        roiTotal.value = raw.total_available ?? raw.priorities?.length ?? 0
        return (raw.priorities ?? raw) as DebtItem[]
      },
      onError: (message, err) => {
        roiFailed = true
        logger.error('Failed to load ROI priorities:', err)
      },
      label: 'ROI priorities',
    },
  )

  /** The last list the server returned; a failed or empty reload keeps it instead of blanking the panel. */
  let roiItems: DebtItem[] = []
  let roiFailed = false

  async function fetchRoiPriorities(limit = ROI_PAGE): Promise<DebtItem[]> {
    isLoading.value = true
    error.value = null
    roiFailed = false
    try {
      await roiEndpoint.load({ limit: String(limit) })
      const items = roiEndpoint.data.value
      if (roiFailed || !items) return roiItems
      // #12741: the page size moves only once the server answered, so a failed "show more" retries the same page.
      roiLimit.value = limit
      roiItems = items
      return items
    } finally {
      isLoading.value = false
    }
  }

  /** "Show more": ask the server for the next page (`limit` grows by ROI_PAGE, capped at ROI_MAX). */
  const loadMoreRoi = () => fetchRoiPriorities(Math.min(roiLimit.value + ROI_PAGE, ROI_MAX))

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
    roiTotal,
    roiAtCap,
    loadMoreRoi,
    fetchDebtItems,
    fetchTrends,
    fetchReportBlob,
  }
}
