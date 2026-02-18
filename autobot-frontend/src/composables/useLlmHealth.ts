// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * LLM Health Monitoring Composable
 * Issue #897 - LLM Configuration Panel
 */

import { ref, onMounted, onUnmounted } from 'vue'
import ApiClient from '@/utils/ApiClient'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('useLlmHealth')

// ===== Type Definitions =====

export interface LLMHealthMetrics {
  provider: string
  status: 'healthy' | 'degraded' | 'unhealthy'
  response_time_ms: number
  success_rate: number
  error_rate: number
  total_requests: number
  failed_requests: number
  last_check: string
  uptime_percentage: number
}

export interface LLMProviderHealth {
  provider: string
  is_available: boolean
  latency_ms: number
  last_successful_request: string | null
  error_count: number
  health_score: number
}

export interface LLMHealthSummary {
  overall_status: 'healthy' | 'degraded' | 'critical'
  total_providers: number
  healthy_providers: number
  degraded_providers: number
  unhealthy_providers: number
  providers: LLMProviderHealth[]
  timestamp: string
}

export interface LLMUsageStats {
  provider: string
  model: string
  total_tokens: number
  input_tokens: number
  output_tokens: number
  total_requests: number
  avg_response_time_ms: number
  cost_usd: number
  period_start: string
  period_end: string
}

export interface UseLlmHealthOptions {
  autoFetch?: boolean
  pollInterval?: number
}

// ===== Composable Implementation =====

export function useLlmHealth(options: UseLlmHealthOptions = {}) {
  const { autoFetch = true, pollInterval = 60000 } = options

  // State
  const healthMetrics = ref<LLMHealthMetrics[]>([])
  const healthSummary = ref<LLMHealthSummary | null>(null)
  const usageStats = ref<LLMUsageStats[]>([])
  const isLoading = ref(false)
  const error = ref<string | null>(null)
  const lastUpdate = ref<Date | null>(null)

  let pollingInterval: ReturnType<typeof setInterval> | null = null

  // ===== API Methods =====

  async function fetchHealthMetrics(): Promise<void> {
    isLoading.value = true
    error.value = null
    try {
      const data = await ApiClient.get('/api/llm/health/metrics')
      healthMetrics.value = data.metrics || []
      lastUpdate.value = new Date()
      logger.debug('Fetched health metrics:', healthMetrics.value)
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to fetch health metrics'
      logger.error('Failed to fetch health metrics:', err)
      error.value = message
    } finally {
      isLoading.value = false
    }
  }

  async function fetchHealthSummary(): Promise<void> {
    isLoading.value = true
    error.value = null
    try {
      const data = await ApiClient.get('/api/llm/health/summary')
      healthSummary.value = data
      lastUpdate.value = new Date()
      logger.debug('Fetched health summary:', healthSummary.value)
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to fetch health summary'
      logger.error('Failed to fetch health summary:', err)
      error.value = message
    } finally {
      isLoading.value = false
    }
  }

  async function fetchUsageStats(startDate?: string, endDate?: string): Promise<void> {
    isLoading.value = true
    error.value = null
    try {
      let url = '/api/llm/usage/stats'
      const params = new URLSearchParams()
      if (startDate) params.append('start_date', startDate)
      if (endDate) params.append('end_date', endDate)
      if (params.toString()) url += `?${params.toString()}`

      const data = await ApiClient.get(url)
      usageStats.value = data.stats || []
      logger.debug('Fetched usage stats:', usageStats.value)
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to fetch usage stats'
      logger.error('Failed to fetch usage stats:', err)
      error.value = message
    } finally {
      isLoading.value = false
    }
  }

  async function checkProviderHealth(provider: string): Promise<LLMProviderHealth | null> {
    isLoading.value = true
    error.value = null
    try {
      const data = await ApiClient.get(`/api/llm/health/provider/${provider}`)
      logger.debug('Checked provider health:', data)
      return data
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to check provider health'
      logger.error('Failed to check provider health:', err)
      error.value = message
      return null
    } finally {
      isLoading.value = false
    }
  }

  async function refreshAll(): Promise<void> {
    isLoading.value = true
    try {
      await Promise.all([
        fetchHealthMetrics(),
        fetchHealthSummary(),
        fetchUsageStats(),
      ])
    } finally {
      isLoading.value = false
    }
  }

  // ===== Polling Methods =====

  function startPolling(): void {
    if (pollingInterval) return
    logger.debug(`Starting health polling with interval: ${pollInterval}ms`)
    pollingInterval = setInterval(refreshAll, pollInterval)
  }

  function stopPolling(): void {
    if (pollingInterval) {
      clearInterval(pollingInterval)
      pollingInterval = null
      logger.debug('Health polling stopped')
    }
  }

  // ===== Lifecycle =====

  onMounted(() => {
    if (autoFetch) {
      refreshAll()
    }
    if (pollInterval > 0) {
      startPolling()
    }
  })

  onUnmounted(() => {
    stopPolling()
  })

  return {
    // State
    healthMetrics,
    healthSummary,
    usageStats,
    isLoading,
    error,
    lastUpdate,

    // Methods
    fetchHealthMetrics,
    fetchHealthSummary,
    fetchUsageStats,
    checkProviderHealth,
    refreshAll,
    startPolling,
    stopPolling,
  }
}

export default useLlmHealth
