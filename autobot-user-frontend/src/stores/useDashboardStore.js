import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import ApiClient from '../utils/ApiClient'
import { createLogger } from '@/utils/debugUtils'

// Create scoped logger for DashboardStore
const logger = createLogger('DashboardStore')

export const useDashboardStore = defineStore('dashboard', () => {
  // State
  const metrics = ref({
    timestamp: null,
    success: false,
    loading: false,
    error: null,

    // Task Metrics
    tasks: {
      active: 0,
      completed: 0,
      failed: 0,
      total: 0,
      success_rate: 0,
      queue_length: 0
    },

    // Performance Metrics
    performance: {
      score: 0,
      response_time_ms: 0,
      cpu_usage: 0,
      memory_usage: 0,
      disk_usage: 0,
    },

    // System Health
    system_health: {
      status: "unknown",
      uptime_hours: 0,
      services_online: 0,
      total_services: 5,
      cpu_temp: null,
      load_average: 0
    },

    // Knowledge Base Stats
    knowledge_base: {
      documents: 0,
      vectors: 0,
      facts: 0,
      last_update: null,
      search_performance_ms: 0
    },

    // Chat Metrics
    chat: {
      active_sessions: 0,
      total_messages: 0,
      sessions_today: 0,
      avg_response_time_ms: 0
    },

    // Meta Information
    meta: {
      collection_time_ms: 0,
      data_sources: [],
      refresh_rate_seconds: 30,
      version: "1.0.0"
    }
  })

  const realTimeMetrics = ref({
    timestamp: null,
    cpu_percent: 0,
    memory_percent: 0,
    disk_percent: 0,
    active_workflows: 0,
    monitoring_active: false,
    system_healthy: false
  })

  // Auto-refresh settings
  const autoRefreshEnabled = ref(true)
  const refreshInterval = ref(30000) // 30 seconds
  const lastRefresh = ref(null)
  let refreshTimer = null

  // Computed properties for dashboard display
  const tasksCompleted = computed(() => metrics.value.tasks.completed)
  const performanceScore = computed(() => Math.round(metrics.value.performance.score))
  const activeSessions = computed(() => Math.max(metrics.value.chat.active_sessions, 1))
  const knowledgeItems = computed(() => metrics.value.knowledge_base.documents)

  // System status computed properties
  const systemHealthStatus = computed(() => {
    const status = metrics.value.system_health.status || 'unknown'
    return {
      text: status.charAt(0).toUpperCase() + status.slice(1),
      class: status === 'healthy' ? 'success' : status === 'degraded' ? 'warning' : 'error',
      message: `System is ${status}`
    }
  })

  const cpuStatus = computed(() => {
    const cpu = metrics.value.performance.cpu_usage
    return {
      text: `${cpu}%`,
      class: cpu > 80 ? 'error' : cpu > 60 ? 'warning' : 'success',
      message: `CPU usage: ${cpu}%`
    }
  })

  const memoryStatus = computed(() => {
    const memory = metrics.value.performance.memory_usage
    return {
      text: `${memory}%`,
      class: memory > 85 ? 'error' : memory > 70 ? 'warning' : 'success',
      message: `Memory usage: ${memory}%`
    }
  })

  const servicesStatus = computed(() => {
    const online = metrics.value.system_health.services_online
    const total = metrics.value.system_health.total_services
    const ratio = total > 0 ? online / total : 0

    return {
      text: `${online}/${total}`,
      class: ratio >= 0.8 ? 'success' : ratio >= 0.6 ? 'warning' : 'error',
      message: `${online} of ${total} services online`
    }
  })

  // Actions
  async function fetchDashboardMetrics() {
    if (metrics.value.loading) return

    try {
      metrics.value.loading = true
      metrics.value.error = null

      // Issue #552: Fixed path - backend uses /api/metrics/dashboard (not /comprehensive)
      logger.debug('Fetching dashboard metrics from /api/metrics/dashboard')

      const response = await ApiClient.get('/api/metrics/dashboard')

      if (response.success !== false) {
        // Update all metrics
        Object.assign(metrics.value, response)
        lastRefresh.value = new Date()

        logger.debug('Dashboard metrics updated successfully:', {
          tasks: response.tasks?.completed || 0,
          performance: response.performance?.score || 0,
          cpu: response.performance?.cpu_usage || 0,
          memory: response.performance?.memory_usage || 0
        })
      } else {
        throw new Error(response.error || 'Failed to fetch dashboard metrics')
      }

    } catch (error) {
      logger.error('Failed to fetch dashboard metrics:', error)
      metrics.value.error = error.message || 'Failed to load dashboard data'

      // Keep existing data on error, don't reset to empty values
      // This provides better UX when there are temporary network issues

    } finally {
      metrics.value.loading = false
    }
  }

  async function fetchRealtimeMetrics() {
    try {
      // Issue #552: Fixed path - backend uses /api/metrics/system/current for realtime
      const response = await ApiClient.get('/api/metrics/system/current')

      if (!response.error) {
        Object.assign(realTimeMetrics.value, response)

        // Update main metrics with real-time data
        metrics.value.performance.cpu_usage = response.cpu_percent || 0
        metrics.value.performance.memory_usage = response.memory_percent || 0
        metrics.value.performance.disk_usage = response.disk_percent || 0
        metrics.value.tasks.active = response.active_workflows || 0
      }
    } catch (error) {
      logger.warn('Failed to fetch real-time metrics:', error.message)
      // Don't throw error for real-time updates
    }
  }

  function startAutoRefresh() {
    if (refreshTimer) return

    autoRefreshEnabled.value = true

    // Initial fetch
    fetchDashboardMetrics()

    // Set up periodic refresh
    refreshTimer = setInterval(() => {
      if (autoRefreshEnabled.value) {
        fetchDashboardMetrics()

        // Also fetch real-time metrics more frequently
        fetchRealtimeMetrics()
      }
    }, refreshInterval.value)

    logger.debug(`Dashboard auto-refresh started (${refreshInterval.value / 1000}s interval)`)
  }

  function stopAutoRefresh() {
    if (refreshTimer) {
      clearInterval(refreshTimer)
      refreshTimer = null
      autoRefreshEnabled.value = false
      logger.debug('Dashboard auto-refresh stopped')
    }
  }

  function setRefreshInterval(intervalMs) {
    refreshInterval.value = intervalMs

    if (refreshTimer) {
      // Restart with new interval
      stopAutoRefresh()
      startAutoRefresh()
    }
  }

  async function refreshNow() {
    logger.debug('Manual dashboard refresh triggered')
    await Promise.all([
      fetchDashboardMetrics(),
      fetchRealtimeMetrics()
    ])
  }

  // Reset metrics to initial state
  function resetMetrics() {
    metrics.value = {
      timestamp: null,
      success: false,
      loading: false,
      error: null,

      tasks: { active: 0, completed: 0, failed: 0, total: 0, success_rate: 0, queue_length: 0 },
      performance: { score: 0, response_time_ms: 0, cpu_usage: 0, memory_usage: 0, disk_usage: 0 },
      system_health: { status: "unknown", uptime_hours: 0, services_online: 0, total_services: 5, cpu_temp: null, load_average: 0 },
      knowledge_base: { documents: 0, vectors: 0, facts: 0, last_update: null, search_performance_ms: 0 },
      chat: { active_sessions: 0, total_messages: 0, sessions_today: 0, avg_response_time_ms: 0 },
      meta: { collection_time_ms: 0, data_sources: [], refresh_rate_seconds: 30, version: "1.0.0" }
    }

    realTimeMetrics.value = {
      timestamp: null,
      cpu_percent: 0,
      memory_percent: 0,
      disk_percent: 0,
      active_workflows: 0,
      monitoring_active: false,
      system_healthy: false
    }
  }

  // Cleanup on store disposal
  function dispose() {
    stopAutoRefresh()
  }

  return {
    // State
    metrics,
    realTimeMetrics,
    autoRefreshEnabled,
    refreshInterval,
    lastRefresh,

    // Computed
    tasksCompleted,
    performanceScore,
    activeSessions,
    knowledgeItems,
    systemHealthStatus,
    cpuStatus,
    memoryStatus,
    servicesStatus,

    // Actions
    fetchDashboardMetrics,
    fetchRealtimeMetrics,
    startAutoRefresh,
    stopAutoRefresh,
    setRefreshInterval,
    refreshNow,
    resetMetrics,
    dispose
  }
}, {
  persist: {
    key: 'autobot-dashboard-metrics',
    storage: localStorage,
    paths: [
      'autoRefreshEnabled',
      'refreshInterval'
    ]
  }
})
