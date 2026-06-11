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
 * Consumed endpoints:
 *   GET  /api/errors/statistics            — system-wide error stats
 *   GET  /api/errors/recent?limit=N        — recent error list
 *   GET  /api/errors/categories            — breakdown by category + percentages
 *   GET  /api/errors/components            — breakdown by component (sorted)
 *   GET  /api/errors/metrics/summary       — aggregated metrics (rates, retries)
 *   GET  /api/errors/metrics/timeline?hours=N&component=X — hourly timeline
 *   GET  /api/errors/metrics/top-errors?limit=N — top-N most frequent errors
 *   POST /api/errors/metrics/resolve/{trace_id}  — mark an error resolved
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

export interface RecentError {
  trace_id?: string
  timestamp?: number | string
  message?: string
  category?: string
  component?: string
  severity?: string
  resolved?: boolean
  [key: string]: unknown
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

export interface MetricsSummary {
  [key: string]: unknown
}

export interface TimelineEntry {
  hour: string | number
  error_count: number
  errors: unknown[]
}

export interface ErrorTimeline {
  timeline: TimelineEntry[]
  hours: number
  component: string | null
}

export interface TopError {
  error_code?: string
  component?: string
  count?: number
  first_seen?: number | string
  last_seen?: number | string
  resolved?: boolean
  [key: string]: unknown
}

export interface TopErrors {
  top_errors: TopError[]
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
  /** Default hours for timeline (default: 24) */
  timelineHours?: number
}

// ─── Return type ─────────────────────────────────────────────────────────────

export interface UseErrorMonitoringReturn {
  // State
  statistics: Ref<ErrorStatistics | null>
  recentErrors: Ref<RecentError[]>
  categories: Ref<CategoryBreakdown | null>
  components: Ref<ComponentBreakdown | null>
  metricsSummary: Ref<MetricsSummary | null>
  timeline: Ref<ErrorTimeline | null>
  topErrors: Ref<TopError[]>
  isLoading: Ref<boolean>
  error: Ref<string | null>
  lastUpdate: Ref<Date | null>
  // Filters
  categoryFilter: Ref<string>
  componentFilter: Ref<string>
  timelineHours: Ref<number>
  // Computed
  totalErrors: ComputedRef<number>
  healthStatus: ComputedRef<'excellent' | 'healthy' | 'warning' | 'degraded' | 'critical' | 'unknown'>
  filteredRecentErrors: ComputedRef<RecentError[]>
  // Actions
  fetchStatistics: () => Promise<void>
  fetchRecentErrors: (limit?: number) => Promise<void>
  fetchCategories: () => Promise<void>
  fetchComponents: () => Promise<void>
  fetchMetricsSummary: () => Promise<void>
  fetchTimeline: (hours?: number, component?: string | null) => Promise<void>
  fetchTopErrors: (limit?: number) => Promise<void>
  fetchAll: () => Promise<void>
  resolveError: (traceId: string) => Promise<boolean>
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
  } = options

  const api = useApiClient()
  const base = `${getApiBase()}/errors`

  // ── State ──────────────────────────────────────────────────────────────────
  const statistics = ref<ErrorStatistics | null>(null)
  const recentErrors = ref<RecentError[]>([])
  const categories = ref<CategoryBreakdown | null>(null)
  const components = ref<ComponentBreakdown | null>(null)
  const metricsSummary = ref<MetricsSummary | null>(null)
  const timeline = ref<ErrorTimeline | null>(null)
  const topErrors = ref<TopError[]>([])
  const error = ref<string | null>(null)
  const lastUpdate = ref<Date | null>(null)

  // Filters (reactive, used by filteredRecentErrors + fetchTimeline)
  const categoryFilter = ref('')
  const componentFilter = ref('')
  const timelineHoursRef = ref(defaultTimelineHours)

  const { isLoading, wrap } = useLoadingState()

  // ── Computed ───────────────────────────────────────────────────────────────

  const totalErrors = computed(() => statistics.value?.total_errors ?? 0)

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
      error.value = null
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
      error.value = null
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
      error.value = null
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
      error.value = null
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Failed to fetch component errors'
      logger.error('fetchComponents failed:', err)
      error.value = msg
    }
  }

  async function fetchMetricsSummary(): Promise<void> {
    try {
      const res = await api.get<DataResponse<MetricsSummary>>(`${base}/metrics/summary`)
      metricsSummary.value = res.data ?? null
      error.value = null
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Failed to fetch metrics summary'
      logger.error('fetchMetricsSummary failed:', err)
      error.value = msg
    }
  }

  async function fetchTimeline(hours = timelineHoursRef.value, component: string | null = null): Promise<void> {
    try {
      let url = `${base}/metrics/timeline?hours=${hours}`
      if (component) url += `&component=${encodeURIComponent(component)}`
      const res = await api.get<DataResponse<ErrorTimeline>>(url)
      timeline.value = res.data ?? null
      error.value = null
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Failed to fetch error timeline'
      logger.error('fetchTimeline failed:', err)
      error.value = msg
    }
  }

  async function fetchTopErrors(limit = 10): Promise<void> {
    try {
      const res = await api.get<DataResponse<TopErrors>>(`${base}/metrics/top-errors?limit=${limit}`)
      topErrors.value = res.data?.top_errors ?? []
      error.value = null
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Failed to fetch top errors'
      logger.error('fetchTopErrors failed:', err)
      error.value = msg
    }
  }

  async function fetchAll(): Promise<void> {
    return wrap(async () => {
      await Promise.all([
        fetchStatistics(),
        fetchRecentErrors(),
        fetchCategories(),
        fetchComponents(),
        fetchMetricsSummary(),
        fetchTimeline(),
        fetchTopErrors(),
      ])
      lastUpdate.value = new Date()
    })
  }

  async function resolveError(traceId: string): Promise<boolean> {
    try {
      const res = await api.post<{ status: string; message: string }>(
        `${base}/metrics/resolve/${encodeURIComponent(traceId)}`,
        {},
      )
      if (res.status === 'success') {
        logger.info('Resolved error trace:', traceId)
        // Optimistically remove from recent list
        recentErrors.value = recentErrors.value.filter((e: RecentError) => e.trace_id !== traceId)
        topErrors.value = topErrors.value.map((e: TopError) =>
          e.trace_id === traceId ? { ...e, resolved: true } : e,
        )
        return true
      }
      return false
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Failed to resolve error'
      logger.error('resolveError failed:', err)
      error.value = msg
      return false
    }
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
    if (pollInterval > 0) _startPoller('')
  }

  // ── Lifecycle ──────────────────────────────────────────────────────────────

  if (getCurrentInstance()) {
    onMounted(() => {
      if (autoFetch) fetchAll()
      if (pollInterval > 0) startPolling()
    })
  }

  return {
    statistics,
    recentErrors,
    categories,
    components,
    metricsSummary,
    timeline,
    topErrors,
    isLoading,
    error,
    lastUpdate,
    categoryFilter,
    componentFilter,
    timelineHours: timelineHoursRef,
    totalErrors,
    healthStatus,
    filteredRecentErrors,
    fetchStatistics,
    fetchRecentErrors,
    fetchCategories,
    fetchComponents,
    fetchMetricsSummary,
    fetchTimeline,
    fetchTopErrors,
    fetchAll,
    resolveError,
    refresh,
    startPolling,
    stopPolling,
  }
}

export default useErrorMonitoring
