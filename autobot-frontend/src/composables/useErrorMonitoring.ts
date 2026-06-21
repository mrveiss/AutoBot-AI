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
 *   GET  /api/errors/statistics                       — system-wide error stats
 *   GET  /api/errors/recent?limit=N                   — recent error list (annotated `resolved`)
 *   GET  /api/errors/categories                       — breakdown by category + percentages
 *   GET  /api/errors/components                        — breakdown by component (sorted)
 *   GET  /api/errors/metrics/summary                  — totals + breakdowns + prometheus_available
 *   GET  /api/errors/metrics/timeline?hours=N&...     — error-count timeline points
 *   GET  /api/errors/metrics/top-errors?limit=N       — most frequent {component,error_code,count}
 *   POST /api/errors/metrics/resolve/{trace_id}       — mark an error resolved (trace_id == error_id)
 *
 * The /metrics/* endpoints were reimplemented Prometheus-backed (timeline/top-errors/
 * summary) + Redis-backed resolution in #9983, restoring this UI surface (trimmed by
 * #9891/#9973 while they were no-op stubs).
 *
 * Issues #9891, #9983
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

/** Matches boundary_manager.py:303-313 — the exact keys stored to Redis.
 *  `resolved` is annotated by GET /recent (#9983), keyed on `error_id` (== trace_id). */
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
  resolved?: boolean
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

// ─── Metrics shapes (#9983 — reimplemented Prometheus/Redis metrics endpoints) ──

/** GET /metrics/summary → data */
export interface MetricsSummary {
  total_errors: number
  unique_error_types: number
  category_breakdown: Record<string, number>
  component_breakdown: Record<string, number>
  alert_thresholds_configured: number
  prometheus_available: boolean
}

/** A single timeline point from GET /metrics/timeline. */
export interface TimelinePoint {
  timestamp: string
  value: number
}

/** GET /metrics/timeline → data */
export interface TimelineData {
  timeline: TimelinePoint[]
  hours: number
  component: string | null
}

/** A row from GET /metrics/top-errors. */
export interface TopError {
  component: string
  error_code: string
  count: number
}

/** GET /metrics/top-errors → data */
export interface TopErrorsData {
  top_errors: TopError[]
}

/** POST /metrics/resolve/{trace_id} response (no `data` envelope). */
export interface ResolveResult {
  status: 'success' | 'not_found' | string
  message: string
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
  /** Default timeline window in hours (default: 24) */
  timelineHours?: number
  /** Default limit for top-errors (default: 10) */
  topErrorsLimit?: number
}

// ─── Return type ─────────────────────────────────────────────────────────────

export interface UseErrorMonitoringReturn {
  // State
  statistics: Ref<ErrorStatistics | null>
  recentErrors: Ref<RecentError[]>
  categories: Ref<CategoryBreakdown | null>
  components: Ref<ComponentBreakdown | null>
  summary: Ref<MetricsSummary | null>
  timeline: Ref<TimelinePoint[]>
  topErrors: Ref<TopError[]>
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
  prometheusAvailable: ComputedRef<boolean>
  // Actions
  fetchStatistics: () => Promise<void>
  fetchRecentErrors: (limit?: number) => Promise<void>
  fetchCategories: () => Promise<void>
  fetchComponents: () => Promise<void>
  fetchSummary: () => Promise<void>
  fetchTimeline: (hours?: number, component?: string) => Promise<void>
  fetchTopErrors: (limit?: number) => Promise<void>
  resolveError: (errorId: string) => Promise<boolean>
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
    timelineHours: defaultTimelineHours = 24,
    topErrorsLimit: defaultTopErrorsLimit = 10,
  } = options

  const api = useApiClient()
  const base = `${getApiBase()}/errors`

  // ── State ──────────────────────────────────────────────────────────────────
  const statistics = ref<ErrorStatistics | null>(null)
  const recentErrors = ref<RecentError[]>([])
  const categories = ref<CategoryBreakdown | null>(null)
  const components = ref<ComponentBreakdown | null>(null)
  const summary = ref<MetricsSummary | null>(null)
  const timeline = ref<TimelinePoint[]>([])
  const topErrors = ref<TopError[]>([])
  const error = ref<string | null>(null)
  const lastUpdate = ref<Date | null>(null)

  // Filters (reactive, used by filteredRecentErrors)
  const categoryFilter = ref('')
  const componentFilter = ref('')

  const { isLoading, wrap } = useLoadingState()

  // ── Computed ───────────────────────────────────────────────────────────────

  const totalErrors = computed(() => statistics.value?.total_errors ?? 0)

  const prometheusAvailable = computed(() => summary.value?.prometheus_available ?? false)

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

  // ── Metrics fetch methods (#9983) ────────────────────────────────────────────

  async function fetchSummary(): Promise<void> {
    try {
      const res = await api.get<DataResponse<MetricsSummary>>(`${base}/metrics/summary`)
      summary.value = res.data ?? null
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Failed to fetch error metrics summary'
      logger.error('fetchSummary failed:', err)
      error.value = msg
    }
  }

  async function fetchTimeline(hours = defaultTimelineHours, component?: string): Promise<void> {
    try {
      const params = new URLSearchParams({ hours: String(hours) })
      if (component) params.set('component', component)
      const res = await api.get<DataResponse<TimelineData>>(`${base}/metrics/timeline?${params.toString()}`)
      timeline.value = res.data?.timeline ?? []
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Failed to fetch error timeline'
      logger.error('fetchTimeline failed:', err)
      error.value = msg
    }
  }

  async function fetchTopErrors(limit = defaultTopErrorsLimit): Promise<void> {
    try {
      const res = await api.get<DataResponse<TopErrorsData>>(`${base}/metrics/top-errors?limit=${limit}`)
      topErrors.value = res.data?.top_errors ?? []
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Failed to fetch top errors'
      logger.error('fetchTopErrors failed:', err)
      error.value = msg
    }
  }

  /**
   * Mark an error resolved. `errorId` is the recent-error `error_id` (== backend trace_id).
   * Returns true on success; on success the local recentErrors entry is flagged resolved
   * so the UI updates without a full refetch.
   */
  async function resolveError(errorId: string): Promise<boolean> {
    try {
      const res = await api.post<ResolveResult>(`${base}/metrics/resolve/${encodeURIComponent(errorId)}`)
      if (res.status === 'success') {
        recentErrors.value = recentErrors.value.map((e: RecentError) =>
          e.error_id === errorId ? { ...e, resolved: true } : e,
        )
        return true
      }
      logger.warn('resolveError: error not found', { errorId, status: res.status })
      return false
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Failed to resolve error'
      logger.error('resolveError failed:', err)
      error.value = msg
      return false
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
        fetchSummary(),
        fetchTimeline(),
        fetchTopErrors(),
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
    summary,
    timeline,
    topErrors,
    isLoading,
    error,
    lastUpdate,
    categoryFilter,
    componentFilter,
    totalErrors,
    healthStatus,
    filteredRecentErrors,
    prometheusAvailable,
    fetchStatistics,
    fetchRecentErrors,
    fetchCategories,
    fetchComponents,
    fetchSummary,
    fetchTimeline,
    fetchTopErrors,
    resolveError,
    fetchAll,
    refresh,
    startPolling,
    stopPolling,
  }
}

export default useErrorMonitoring
