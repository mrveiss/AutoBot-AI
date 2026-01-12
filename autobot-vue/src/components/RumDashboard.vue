<template>
  <div v-if="isDev" class="rum-dashboard relative">
    <!-- Toggle Button -->
    <button
      @click="toggleVisibility"
      :class="{
        'bg-red-500 hover:bg-red-600': hasIssues,
        'bg-green-500 hover:bg-green-600': !hasIssues,
        'animate-pulse': hasIssues
      }"
      class="fixed top-4 right-20 z-50 px-3 py-1 rounded-full text-white text-sm font-medium shadow-lg transition-all duration-300 flex items-center space-x-2"
      :title="hasIssues ? `${criticalIssues.length} critical issues detected` : 'System monitoring healthy'"
    >
      <div
        :class="{
          'bg-white': hasIssues,
          'bg-green-200': !hasIssues
        }"
        class="w-2 h-2 rounded-full"
      ></div>
      <span>{{ hasIssues ? criticalIssues.length : '✓' }}</span>
      <!-- PERFORMANCE: Show reduced monitoring indicator -->
      <span v-if="isPerformanceModeEnabled" class="text-xs opacity-75">[PM]</span>
    </button>

    <!-- Dashboard Panel -->
    <Transition
      enter-active-class="transition duration-300 ease-out"
      enter-from-class="transform translate-x-full opacity-0"
      enter-to-class="transform translate-x-0 opacity-100"
      leave-active-class="transition duration-200 ease-in"
      leave-from-class="transform translate-x-0 opacity-100"
      leave-to-class="transform translate-x-full opacity-0"
    >
      <div
        v-if="isVisible"
        class="fixed top-16 right-4 w-80 bg-white rounded-lg shadow-xl border z-40 max-h-96 overflow-y-auto"
      >
        <div class="sticky top-0 bg-white border-b px-4 py-3">
          <div class="flex items-center justify-between">
            <h3 class="text-lg font-semibold text-gray-900">System Monitor</h3>
            <div class="flex items-center space-x-2">
              <!-- PERFORMANCE: Show performance mode status -->
              <span v-if="isPerformanceModeEnabled" class="text-xs text-orange-600 font-medium">
                Performance Mode
              </span>
              <button
                @click="refreshData"
                :disabled="isLoading"
                class="p-1 rounded-full hover:bg-gray-100 transition-colors duration-200"
                title="Refresh data"
              >
                <svg
                  :class="{ 'animate-spin': isLoading }"
                  class="w-4 h-4 text-gray-600"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    stroke-linecap="round"
                    stroke-linejoin="round"
                    stroke-width="2"
                    d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
                  ></path>
                </svg>
              </button>
              <button
                @click="isVisible = false"
                class="p-1 rounded-full hover:bg-gray-100 transition-colors duration-200"
              >
                <svg class="w-4 h-4 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path>
                </svg>
              </button>
            </div>
          </div>
        </div>

        <div class="p-4 space-y-4">
          <!-- Performance Mode Warning -->
          <div v-if="isPerformanceModeEnabled" class="bg-orange-50 border border-orange-200 rounded-lg p-3">
            <div class="flex items-center space-x-2">
              <svg class="w-4 h-4 text-orange-500" fill="currentColor" viewBox="0 0 20 20">
                <path fill-rule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clip-rule="evenodd"></path>
              </svg>
              <span class="text-sm text-orange-700 font-medium">
                Performance Mode Active
              </span>
            </div>
            <p class="text-xs text-orange-600 mt-1">
              Monitoring reduced to {{ Math.round(refreshInterval / 60000) }} minutes intervals for better performance.
            </p>
          </div>

          <!-- System Status -->
          <div class="space-y-2">
            <h4 class="text-sm font-medium text-gray-700">System Status</h4>
            <div class="grid grid-cols-2 gap-2 text-sm">
              <div class="bg-gray-50 rounded p-2">
                <div class="text-gray-500">Uptime</div>
                <div class="font-medium">{{ formatUptime(systemData.uptime) }}</div>
              </div>
              <div class="bg-gray-50 rounded p-2">
                <div class="text-gray-500">Memory</div>
                <div class="font-medium">{{ systemData.memoryUsage }}%</div>
              </div>
            </div>
          </div>

          <!-- Critical Issues -->
          <div v-if="criticalIssues.length > 0" class="space-y-2">
            <h4 class="text-sm font-medium text-red-700">Critical Issues ({{ criticalIssues.length }})</h4>
            <div class="space-y-1">
              <div
                v-for="issue in criticalIssues.slice(0, 5)"
                :key="issue.id"
                class="bg-red-50 border border-red-200 rounded p-2 text-sm"
              >
                <div class="font-medium text-red-800">{{ issue.type }}</div>
                <div class="text-red-600 text-xs">{{ issue.message }}</div>
                <div class="text-red-500 text-xs">{{ formatTimeAgo(issue.timestamp) }}</div>
              </div>
            </div>
          </div>

          <!-- Recent Events -->
          <div v-if="recentEvents.length > 0" class="space-y-2">
            <h4 class="text-sm font-medium text-gray-700">Recent Events</h4>
            <div class="space-y-1">
              <div
                v-for="event in recentEvents.slice(0, 5)"
                :key="event.id"
                class="bg-gray-50 rounded p-2 text-sm"
              >
                <div class="font-medium text-gray-800">{{ event.type }}</div>
                <div class="text-gray-600 text-xs">{{ event.message }}</div>
                <div class="text-gray-500 text-xs">{{ formatTimeAgo(event.timestamp) }}</div>
              </div>
            </div>
          </div>

          <!-- Performance Metrics -->
          <div class="space-y-2">
            <h4 class="text-sm font-medium text-gray-700">Performance</h4>
            <div class="space-y-1 text-sm">
              <div class="flex justify-between">
                <span class="text-gray-500">Page Load:</span>
                <span class="font-medium">{{ performanceData.pageLoadTime }}ms</span>
              </div>
              <div class="flex justify-between">
                <span class="text-gray-500">API Response:</span>
                <span class="font-medium">{{ performanceData.apiResponseTime }}ms</span>
              </div>
              <div class="flex justify-between">
                <span class="text-gray-500">Render Time:</span>
                <span class="font-medium">{{ performanceData.renderTime }}ms</span>
              </div>
            </div>
          </div>

          <!-- Last Updated -->
          <div class="border-t pt-2 text-xs text-gray-500 text-center">
            Last updated: {{ formatTimeAgo(lastUpdated) }}
            <br>
            <span v-if="isPerformanceModeEnabled" class="text-orange-600">
              Next update in ~{{ Math.round(refreshInterval / 60000) }}m
            </span>
          </div>
        </div>
      </div>
    </Transition>
  </div>
</template>

<script>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { isPerformanceModeEnabled, getPerformanceInterval, logPerformanceIssue } from '@/config/performance.js'
import { useAsyncOperation } from '@/composables/useAsyncOperation'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('RumDashboard')

export default {
  name: 'RumDashboard',
  setup() {
    // Reactive state
    const isVisible = ref(false)
    const lastUpdated = ref(Date.now())

    // System data
    const systemData = ref({
      uptime: 0,
      memoryUsage: 0,
      cpuUsage: 0
    })

    // Performance data
    const performanceData = ref({
      pageLoadTime: 0,
      apiResponseTime: 0,
      renderTime: 0
    })

    // Events and issues
    const criticalIssues = ref([])
    const recentEvents = ref([])

    // PERFORMANCE: Use performance-aware refresh interval
    const refreshInterval = getPerformanceInterval('RUM_DASHBOARD_REFRESH', 5000) // Default 5s, but performance mode uses 5 minutes
    let refreshIntervalId = null

    // Environment detection
    const isDev = process.env.NODE_ENV === 'development' || window.location.hostname === 'localhost'

    // Computed properties
    const hasIssues = computed(() => criticalIssues.value.length > 0)

    // Methods
    const toggleVisibility = () => {
      isVisible.value = !isVisible.value
    }

    // Use composable for async data fetching
    const { execute, loading: isLoading } = useAsyncOperation({
      onError: (error) => {
        logger.error('Error refreshing data:', error)
        logPerformanceIssue('RumDashboard', 'Data refresh failed', { error: error.message })
      }
    })

    // Wrapper function to execute the data refresh operation
    const refreshData = () => execute(async () => {
      // PERFORMANCE: Only fetch essential data in performance mode
      if (isPerformanceModeEnabled()) {
        // Lightweight data collection
        await Promise.all([
          fetchSystemDataLightweight(),
          fetchCriticalIssuesOnly()
        ])
      } else {
        // Full data collection
        await Promise.all([
          fetchSystemData(),
          fetchPerformanceData(),
          fetchCriticalIssues(),
          fetchRecentEvents()
        ])
      }

      lastUpdated.value = Date.now()
    })

    const fetchSystemDataLightweight = async () => {
      // PERFORMANCE: Basic system info only
      systemData.value = {
        uptime: performance.now(),
        memoryUsage: performance.memory ? Math.round((performance.memory.usedJSHeapSize / performance.memory.totalJSHeapSize) * 100) : 0,
        cpuUsage: 0 // Skip CPU measurement for performance
      }
    }

    const fetchSystemData = async () => {
      try {
        // Get basic performance metrics
        if (performance.memory) {
          systemData.value.memoryUsage = Math.round((performance.memory.usedJSHeapSize / performance.memory.totalJSHeapSize) * 100)
        }
        systemData.value.uptime = performance.now()
      } catch (error) {
        logger.error('Error fetching system data:', error)
      }
    }

    const fetchPerformanceData = async () => {
      try {
        const entries = performance.getEntriesByType('navigation')
        if (entries.length > 0) {
          const entry = entries[0]
          performanceData.value = {
            pageLoadTime: Math.round(entry.loadEventEnd - entry.loadEventStart),
            apiResponseTime: Math.round(entry.responseEnd - entry.requestStart),
            renderTime: Math.round(entry.domContentLoadedEventEnd - entry.domContentLoadedEventStart)
          }
        }
      } catch (error) {
        logger.error('Error fetching performance data:', error)
      }
    }

    const fetchCriticalIssuesOnly = async () => {
      // PERFORMANCE: Only get stored critical issues, don't scan for new ones
      try {
        const stored = localStorage.getItem('rum_critical_issues')
        criticalIssues.value = stored ? JSON.parse(stored) : []
      } catch (error) {
        criticalIssues.value = []
      }
    }

    const fetchCriticalIssues = async () => {
      try {
        // Get stored issues
        const stored = localStorage.getItem('rum_critical_issues')
        const issues = stored ? JSON.parse(stored) : []

        // Add current performance issues if any
        if (systemData.value.memoryUsage > 90) {
          issues.push({
            id: Date.now(),
            type: 'High Memory Usage',
            message: `Memory usage at ${systemData.value.memoryUsage}%`,
            timestamp: Date.now()
          })
        }

        // Keep only recent issues (last 24 hours)
        const oneDayAgo = Date.now() - (24 * 60 * 60 * 1000)
        criticalIssues.value = issues.filter(issue => issue.timestamp > oneDayAgo)

        // Store back
        localStorage.setItem('rum_critical_issues', JSON.stringify(criticalIssues.value))

      } catch (error) {
        logger.error('Error fetching critical issues:', error)
      }
    }

    const fetchRecentEvents = async () => {
      try {
        // Get stored events
        const stored = localStorage.getItem('rum_recent_events')
        const events = stored ? JSON.parse(stored) : []

        // Keep only recent events (last hour)
        const oneHourAgo = Date.now() - (60 * 60 * 1000)
        recentEvents.value = events.filter(event => event.timestamp > oneHourAgo)

      } catch (error) {
        logger.error('Error fetching recent events:', error)
      }
    }

    // Utility functions
    const formatTimeAgo = (timestamp) => {
      const seconds = Math.floor((Date.now() - timestamp) / 1000)
      const minutes = Math.floor(seconds / 60)
      const hours = Math.floor(minutes / 60)

      if (hours > 0) return `${hours}h ago`
      if (minutes > 0) return `${minutes}m ago`
      return `${seconds}s ago`
    }

    const formatUptime = (milliseconds) => {
      const seconds = Math.floor(milliseconds / 1000)
      const minutes = Math.floor(seconds / 60)
      const hours = Math.floor(minutes / 60)

      if (hours > 0) return `${hours}h ${minutes % 60}m`
      if (minutes > 0) return `${minutes}m ${seconds % 60}s`
      return `${seconds}s`
    }

    // Lifecycle
    onMounted(() => {
      if (isDev) {
        // Initial data load
        refreshData()

        // PERFORMANCE: Use performance-aware refresh interval
        if (isPerformanceModeEnabled()) {
        } else {
        }

        refreshIntervalId = setInterval(refreshData, refreshInterval)

        // Show dashboard if there are critical issues
        const issues = JSON.parse(localStorage.getItem('rum_critical_issues') || '[]')
        if (issues.length > 0) {
          isVisible.value = true
        }
      }
    })

    onUnmounted(() => {
      if (refreshIntervalId) {
        clearInterval(refreshIntervalId)
      }
    })

    return {
      // Reactive state
      isVisible,
      lastUpdated,
      systemData,
      performanceData,
      criticalIssues,
      recentEvents,

      // Computed
      hasIssues,
      isDev,
      isPerformanceModeEnabled: isPerformanceModeEnabled(),
      refreshInterval,
      isLoading,

      // Methods
      toggleVisibility,
      refreshData,
      formatTimeAgo,
      formatUptime
    }
  }
}
</script>

<style scoped>
/* Issue #704: Migrated to CSS design tokens */
.rum-dashboard {
  font-family: var(--font-sans, 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif);
}

/* Custom scrollbar */
.overflow-y-auto::-webkit-scrollbar {
  width: 6px;
}

.overflow-y-auto::-webkit-scrollbar-track {
  background: var(--scrollbar-track, #f1f1f1);
  border-radius: var(--radius-sm);
}

.overflow-y-auto::-webkit-scrollbar-thumb {
  background: var(--scrollbar-thumb, #c1c1c1);
  border-radius: var(--radius-sm);
}

.overflow-y-auto::-webkit-scrollbar-thumb:hover {
  background: var(--scrollbar-thumb-hover, #a1a1a1);
}
</style>