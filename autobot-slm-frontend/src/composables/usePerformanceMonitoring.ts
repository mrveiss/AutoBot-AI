// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
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
import { useAuthStore } from '@/stores/auth'

const logger = createLogger('usePerformanceMonitoring')

// SLM Admin uses the local SLM backend API
const API_BASE = '/api'

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

  const authStore = useAuthStore()

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
   * Build auth headers for API requests.
   */
  function getHeaders(): Record<string, string> {
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
    }
    if (authStore.token) {
      headers.Authorization = `Bearer ${authStore.token}`
    }
    return headers
  }

  /**
   * Perform an authenticated API request and return parsed JSON.
   *
   * Helper for all fetch functions (Issue #752).
   */
  async function apiRequest<T>(
    url: string,
    options: RequestInit = {}
  ): Promise<T> {
    const response = await fetch(url, {
      ...options,
      headers: { ...getHeaders(), ...(options.headers as Record<string, string> || {}) },
    })
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
      const data = await apiRequest<PerformanceOverview>(
        `${API_BASE}/performance/overview`
      )
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
      const url = `${API_BASE}/performance/traces${queryStr ? `?${queryStr}` : ''}`
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
      return await apiRequest<TraceDetail>(
        `${API_BASE}/performance/traces/${traceId}`
      )
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
      const data = await apiRequest<{ slos: SLODefinition[] }>(
        `${API_BASE}/performance/slos`
      )
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
      const created = await apiRequest<SLODefinition>(
        `${API_BASE}/performance/slos`,
        { method: 'POST', body: JSON.stringify(slo) }
      )
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
      await apiRequest<void>(
        `${API_BASE}/performance/slos/${sloId}`,
        { method: 'DELETE' }
      )
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
      const data = await apiRequest<{ rules: AlertRule[] }>(
        `${API_BASE}/performance/alert-rules`
      )
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
      const created = await apiRequest<AlertRule>(
        `${API_BASE}/performance/alert-rules`,
        { method: 'POST', body: JSON.stringify(rule) }
      )
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
      const updated = await apiRequest<AlertRule>(
        `${API_BASE}/performance/alert-rules/${ruleId}`,
        { method: 'PATCH', body: JSON.stringify(updates) }
      )
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
      await apiRequest<void>(
        `${API_BASE}/performance/alert-rules/${ruleId}`,
        { method: 'DELETE' }
      )
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
