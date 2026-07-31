// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * Performance Monitoring Composable for SLM Admin
 *
 * Provides access to performance tracing, SLO management, and alert rules
 * from the SLM backend API.
 * Issue #752 - Comprehensive performance monitoring.
 */

import { ref, onMounted, onUnmounted } from 'vue'
import { createLogger } from '@/utils/debugUtils'
import { slmApiClient } from '@/utils/ApiClient'

const logger = createLogger('usePerformanceMonitoring')

// ===== Type Definitions =====

export interface PerformanceOverview {
  avg_latency_ms: number
  p95_latency_ms: number
  p99_latency_ms: number
  throughput_rpm: number
  error_rate_percent: number
  total_traces: number
  active_slos: number
  slo_compliance_percent: number
  top_slow_traces: TraceItem[]
}

export interface TraceItem {
  trace_id: string
  name: string
  source_node_id: string | null
  status: string
  duration_ms: number
  span_count: number
  created_at: string
}

export interface TraceDetail {
  trace_id: string
  name: string
  status: string
  duration_ms: number
  spans: TraceSpan[]
}

export interface TraceSpan {
  span_id: string
  parent_span_id: string | null
  name: string
  service_name: string
  node_id: string | null
  status: string
  duration_ms: number
  start_time: string
  end_time: string
}

export interface SLODefinition {
  slo_id: string
  name: string
  description: string | null
  target_percent: number
  metric_type: string
  threshold_value: number
  threshold_unit: string
  window_days: number
  node_id: string | null
  enabled: boolean
  current_compliance?: number
}

export interface AlertRule {
  rule_id: string
  name: string
  description: string | null
  metric_type: string
  condition: string
  threshold: number
  duration_seconds: number
  severity: string
  node_id: string | null
  enabled: boolean
  last_triggered: string | null
}

export interface TraceQueryParams {
  hours?: number
  status?: string
  node_id?: string
  page?: number
  per_page?: number
}

// ===== Composable Implementation =====

export function usePerformanceMonitoring(options: {
  autoFetch?: boolean
  pollInterval?: number
} = {}) {
  const { autoFetch = false, pollInterval = 30000 } = options

  // State
  const overview = ref<PerformanceOverview | null>(null)
  const traces = ref<TraceItem[]>([])
  const traceTotal = ref(0)
  const slos = ref<SLODefinition[]>([])
  const alertRules = ref<AlertRule[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)

  let pollingInterval: ReturnType<typeof setInterval> | null = null

  /**
   * Perform one authenticated SLM request and return parsed JSON.
   *
   * Helper for all fetch functions (Issue #752), routed through the canonical
   * client in #13140. It calls `slmApiClient.rawRequest` and NOT the client's
   * `get`/`post`/... helpers, deliberately: rawRequest is the single seam that
   * contributes the `getSlmApiBase()` origin, the bearer token (read from
   * storage per request rather than from a reactive ref that may never have
   * been hydrated), the request timeout and the 401 handler — while leaving
   * this function's two behaviours that callers depend on intact:
   *
   *   * the `HTTP <n>: <raw body text>` error message, which every catch block
   *     below surfaces to the user verbatim (the helpers re-shape it from the
   *     parsed JSON, changing what the UI shows);
   *   * single-shot dispatch. `get()` would retry a 5xx three times with
   *     exponential backoff, and `startPolling()` re-issues `fetchOverview`
   *     every `pollInterval` — a retried tick would overlap the next one.
   *
   * `endpoint` is relative to the API base, e.g. '/performance/slos'.
   */
  async function apiRequest<T>(
    endpoint: string,
    options: { method?: string; body?: unknown } = {}
  ): Promise<T> {
    const response = await slmApiClient.rawRequest(endpoint, options)
    if (!response.ok) {
      const body = await response.text().catch(() => '')
      throw new Error(`HTTP ${response.status}: ${body || response.statusText}`)
    }
    if (response.status === 204) {
      return undefined as unknown as T
    }
    return response.json()
  }

  // ===== Fetch Functions =====

  async function fetchOverview(): Promise<void> {
    loading.value = true
    error.value = null
    try {
      const data = await apiRequest<PerformanceOverview>('/performance/overview')
      overview.value = data
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to fetch overview'
      logger.error('Failed to fetch performance overview:', err)
      error.value = message
    } finally {
      loading.value = false
    }
  }

  async function fetchTraces(params: TraceQueryParams = {}): Promise<void> {
    loading.value = true
    error.value = null
    try {
      const query = new URLSearchParams()
      if (params.hours !== undefined) query.set('hours', String(params.hours))
      if (params.status) query.set('status', params.status)
      if (params.node_id) query.set('node_id', params.node_id)
      if (params.page !== undefined) query.set('page', String(params.page))
      if (params.per_page !== undefined) query.set('per_page', String(params.per_page))

      const queryStr = query.toString()
      const url = `/performance/traces${queryStr ? `?${queryStr}` : ''}`
      const data = await apiRequest<{ traces: TraceItem[]; total: number }>(url)
      traces.value = data.traces ?? []
      traceTotal.value = data.total ?? 0
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to fetch traces'
      logger.error('Failed to fetch traces:', err)
      error.value = message
    } finally {
      loading.value = false
    }
  }

  async function fetchTraceDetail(traceId: string): Promise<TraceDetail | null> {
    try {
      return await apiRequest<TraceDetail>(`/performance/traces/${traceId}`)
    } catch (err) {
      logger.error(`Failed to fetch trace ${traceId}:`, err)
      error.value = err instanceof Error ? err.message : 'Failed to fetch trace detail'
      return null
    }
  }

  async function fetchSLOs(): Promise<void> {
    loading.value = true
    error.value = null
    try {
      const data = await apiRequest<{ slos: SLODefinition[] }>('/performance/slos')
      slos.value = data.slos ?? []
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to fetch SLOs'
      logger.error('Failed to fetch SLOs:', err)
      error.value = message
    } finally {
      loading.value = false
    }
  }

  async function createSLO(
    slo: Omit<SLODefinition, 'slo_id' | 'current_compliance'>
  ): Promise<SLODefinition | null> {
    try {
      // `body` is handed over unserialised: rawRequest JSON-stringifies it
      // (and would double-encode a pre-stringified string).
      const created = await apiRequest<SLODefinition>('/performance/slos', {
        method: 'POST',
        body: slo,
      })
      await fetchSLOs()
      return created
    } catch (err) {
      logger.error('Failed to create SLO:', err)
      error.value = err instanceof Error ? err.message : 'Failed to create SLO'
      return null
    }
  }

  async function deleteSLO(sloId: string): Promise<boolean> {
    try {
      await apiRequest<void>(`/performance/slos/${sloId}`, { method: 'DELETE' })
      await fetchSLOs()
      return true
    } catch (err) {
      logger.error(`Failed to delete SLO ${sloId}:`, err)
      error.value = err instanceof Error ? err.message : 'Failed to delete SLO'
      return false
    }
  }

  async function fetchAlertRules(): Promise<void> {
    loading.value = true
    error.value = null
    try {
      const data = await apiRequest<{ rules: AlertRule[] }>('/performance/alerts/rules')
      alertRules.value = data.rules ?? []
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to fetch alert rules'
      logger.error('Failed to fetch alert rules:', err)
      error.value = message
    } finally {
      loading.value = false
    }
  }

  async function createAlertRule(
    rule: Omit<AlertRule, 'rule_id' | 'last_triggered'>
  ): Promise<AlertRule | null> {
    try {
      const created = await apiRequest<AlertRule>('/performance/alerts/rules', {
        method: 'POST',
        body: rule,
      })
      await fetchAlertRules()
      return created
    } catch (err) {
      logger.error('Failed to create alert rule:', err)
      error.value = err instanceof Error ? err.message : 'Failed to create alert rule'
      return null
    }
  }

  async function updateAlertRule(
    ruleId: string,
    updates: Partial<AlertRule>
  ): Promise<AlertRule | null> {
    try {
      const updated = await apiRequest<AlertRule>(`/performance/alerts/rules/${ruleId}`, {
        method: 'PUT',
        body: updates,
      })
      await fetchAlertRules()
      return updated
    } catch (err) {
      logger.error(`Failed to update alert rule ${ruleId}:`, err)
      error.value = err instanceof Error ? err.message : 'Failed to update alert rule'
      return null
    }
  }

  async function deleteAlertRule(ruleId: string): Promise<boolean> {
    try {
      await apiRequest<void>(`/performance/alerts/rules/${ruleId}`, { method: 'DELETE' })
      await fetchAlertRules()
      return true
    } catch (err) {
      logger.error(`Failed to delete alert rule ${ruleId}:`, err)
      error.value = err instanceof Error ? err.message : 'Failed to delete alert rule'
      return false
    }
  }

  // ===== Polling =====

  function startPolling(): void {
    if (pollingInterval) return
    logger.debug(`Starting performance polling: ${pollInterval}ms`)
    pollingInterval = setInterval(fetchOverview, pollInterval)
  }

  function stopPolling(): void {
    if (pollingInterval) {
      clearInterval(pollingInterval)
      pollingInterval = null
      logger.debug('Performance polling stopped')
    }
  }

  // ===== Lifecycle =====

  onMounted(() => {
    if (autoFetch) {
      fetchOverview()
    }
    if (autoFetch && pollInterval > 0) {
      startPolling()
    }
  })

  onUnmounted(() => {
    stopPolling()
  })

  return {
    // State
    overview,
    traces,
    traceTotal,
    slos,
    alertRules,
    loading,
    error,

    // Methods
    fetchOverview,
    fetchTraces,
    fetchTraceDetail,
    fetchSLOs,
    createSLO,
    deleteSLO,
    fetchAlertRules,
    createAlertRule,
    updateAlertRule,
    deleteAlertRule,
    startPolling,
    stopPolling,
  }
}

export default usePerformanceMonitoring
