// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * Error Monitoring Composable
 *
 * Wires the backend /api/errors/* endpoints (api/error_monitoring.py, mounted at
 * /errors prefix via monitoring_routers.py) into a reusable Vue composable.
 *
 * Consumed endpoints (live):
 *   GET  /api/errors/statistics            — system-wide error stats
 *   GET  /api/errors/recent?limit=N        — recent error list
 *   GET  /api/errors/categories            — breakdown by category + percentages
 *   GET  /api/errors/components            — breakdown by component (sorted)
 *
 * NOTE: /metrics/summary, /metrics/timeline, /metrics/top-errors, /metrics/resolve
 * are DEPRECATED NO-OP stubs (Phase 5, Issue #348). They are intentionally excluded.
 * A follow-up backend issue owns the real /metrics/* reimplementation.
 *
 * Issue #9891
 */

import { ref, computed, onMounted, getCurrentInstance } from 'vue'
import type { Ref, ComputedRef } from 'vue'
import { useApiClient } from '@/plugins/api'
import { createLogger } from '@/utils/debugUtils'
import { getApiBase } from '@/config/ssot-config'
import { useLoadingState } from '@/composables/useLoadingState'
import { usePollingJob } from '@/composables/usePollingJob'

const logger = createLogger('ErrorMonitoring')

// ─── Types matching backend Pydantic models ───────────────────────────────────

export interface ErrorStatistics {
  total_errors: number
  categories: Record<string, number>
  components: Record<string, number>
  severities: Record<string, number>
  [key: string]: unknown
}

/** Matches boundary_manager.py:303-313 — the exact keys stored to Redis. */
export interface RecentError {
  error_id: string
  error_type: string
  message: string
  severity: string
  category: string
  component: string
  function: string
  timestamp: number | string
  stack_trace?: string
}

export interface CategoryStats {
  count: number
  percentage: number
}

export interface CategoryBreakdown {
  categories: Record<string, CategoryStats>
  total_errors: number
}

export interface ComponentBreakdown {
  components: Record<string, number>
  most_problematic: [string, number][]
}

// Wrapper matching backend ErrorMonitoringDataResponse
interface DataResponse<T> {
  status: string
  data: T
}

// ─── Options ──────────────────────────────────────────────────────────────────

export interface UseErrorMonitoringOptions {
  /** Auto-fetch on mount (default: true) */
  autoFetch?: boolean
  /** Polling interval in ms; 0 = no polling (default: 60_000) */
  pollInterval?: number
  /** Default limit for recent errors (default: 20) */
  recentLimit?: number
}

// ─── Return type ─────────────────────────────────────────────────────────────

export interface UseErrorMonitoringReturn {
  // State
  statistics: Ref<ErrorStatistics | null>
  recentErrors: Ref<RecentError[]>
  categories: Ref<CategoryBreakdown | null>
  components: Ref<ComponentBreakdown | null>
  isLoading: Ref<boolean>
  error: Ref<string | null>
  lastUpdate: Ref<Date | null>
  // Filters
  categoryFilter: Ref<string>
  componentFilter: Ref<string>
  // Computed
  totalErrors: ComputedRef<number>
  // Client-side thresholds mirror api/error_monitoring.py:192-204
  healthStatus: ComputedRef<'excellent' | 'healthy' | 'warning' | 'degraded' | 'critical' | 'unknown'>
  filteredRecentErrors: ComputedRef<RecentError[]>
  // Actions
  fetchStatistics: () => Promise<void>
  fetchRecentErrors: (limit?: number) => Promise<void>
  fetchCategories: () => Promise<void>
  fetchComponents: () => Promise<void>
  fetchAll: () => Promise<void>
  refresh: () => Promise<void>
  startPolling: () => void
  stopPolling: () => void
}

// ─── Composable ───────────────────────────────────────────────────────────────

export function useErrorMonitoring(options: UseErrorMonitoringOptions = {}): UseErrorMonitoringReturn {
  const {
    autoFetch = true,
    pollInterval = 60_000,
    recentLimit: defaultRecentLimit = 20,
  } = options

  const api = useApiClient()
  const base = `${getApiBase()}/errors`

  // ── State ──────────────────────────────────────────────────────────────────
  const statistics = ref<ErrorStatistics | null>(null)
  const recentErrors = ref<RecentError[]>([])
  const categories = ref<CategoryBreakdown | null>(null)
  const components = ref<ComponentBreakdown | null>(null)
  const error = ref<string | null>(null)
  const lastUpdate = ref<Date | null>(null)

  // Filters (reactive, used by filteredRecentErrors)
  const categoryFilter = ref('')
  const componentFilter = ref('')

  const { isLoading, wrap } = useLoadingState()

  // ── Computed ───────────────────────────────────────────────────────────────

  const totalErrors = computed(() => statistics.value?.total_errors ?? 0)

  // Client-side thresholds mirror api/error_monitoring.py:192-204
  const healthStatus = computed<'excellent' | 'healthy' | 'warning' | 'degraded' | 'critical' | 'unknown'>(() => {
    if (!statistics.value) return 'unknown'
    const sev = statistics.value.severities ?? {}
    const critical = (sev['critical'] as number) ?? 0
    const high = (sev['high'] as number) ?? 0
    const total = statistics.value.total_errors ?? 0
    if (critical > 0) return 'critical'
    if (high > 5) return 'degraded'
    if (total > 20) return 'warning'
    if (total > 0) return 'healthy'
    return 'excellent'
  })

  const filteredRecentErrors = computed(() => {
    let list = recentErrors.value
    if (categoryFilter.value) {
      list = list.filter((e: RecentError) => e.category === categoryFilter.value)
    }
    if (componentFilter.value) {
      list = list.filter((e: RecentError) => e.component === componentFilter.value)
    }
    return list
  })

  // ── Fetch methods ──────────────────────────────────────────────────────────

  async function fetchStatistics(): Promise<void> {
    try {
      const res = await api.get<DataResponse<ErrorStatistics>>(`${base}/statistics`)
      statistics.value = res.data ?? null
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Failed to fetch error statistics'
      logger.error('fetchStatistics failed:', err)
      error.value = msg
    }
  }

  async function fetchRecentErrors(limit = defaultRecentLimit): Promise<void> {
    try {
      const res = await api.get<DataResponse<{ errors: RecentError[]; total_count: number }>>(
        `${base}/recent?limit=${limit}`,
      )
      recentErrors.value = res.data?.errors ?? []
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Failed to fetch recent errors'
      logger.error('fetchRecentErrors failed:', err)
      error.value = msg
    }
  }

  async function fetchCategories(): Promise<void> {
    try {
      const res = await api.get<DataResponse<CategoryBreakdown>>(`${base}/categories`)
      categories.value = res.data ?? null
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Failed to fetch error categories'
      logger.error('fetchCategories failed:', err)
      error.value = msg
    }
  }

  async function fetchComponents(): Promise<void> {
    try {
      const res = await api.get<DataResponse<ComponentBreakdown>>(`${base}/components`)
      components.value = res.data ?? null
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Failed to fetch component errors'
      logger.error('fetchComponents failed:', err)
      error.value = msg
    }
  }

  async function fetchAll(): Promise<void> {
    return wrap(async () => {
      error.value = null
      await Promise.all([
        fetchStatistics(),
        fetchRecentErrors(),
        fetchCategories(),
        fetchComponents(),
      ])
      lastUpdate.value = new Date()
    })
  }

  async function refresh(): Promise<void> {
    await fetchAll()
  }

  // ── Polling ────────────────────────────────────────────────────────────────

  const { start: _startPoller, stop: stopPolling } = usePollingJob<void>(
    async () => { await fetchAll() },
    { intervalMs: pollInterval },
  )

  function startPolling(): void {
    // usePollingJob.start() fires immediately — no separate fetchAll() needed
    if (pollInterval > 0) _startPoller('')
  }

  // ── Lifecycle ──────────────────────────────────────────────────────────────

  if (getCurrentInstance()) {
    onMounted(() => {
      if (autoFetch) {
        if (pollInterval > 0) {
          startPolling()
        } else {
          void fetchAll()
        }
      }
    })
  }

  return {
    statistics,
    recentErrors,
    categories,
    components,
    isLoading,
    error,
    lastUpdate,
    categoryFilter,
    componentFilter,
    totalErrors,
    healthStatus,
    filteredRecentErrors,
    fetchStatistics,
    fetchRecentErrors,
    fetchCategories,
    fetchComponents,
    fetchAll,
    refresh,
    startPolling,
    stopPolling,
  }
}

export default useErrorMonitoring
