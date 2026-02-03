<template>
  <div v-if="isDev" class="optimized-rum-dashboard relative">
    <!-- Smart Toggle Button with Health Indicator -->
    <button
      @click="toggleVisibility"
      :class="{
        'bg-red-500 hover:bg-red-600': hasIssues,
        'bg-green-500 hover:bg-green-600': !hasIssues && isHealthy,
        'bg-yellow-500 hover:bg-yellow-600': !hasIssues && !isHealthy,
        'animate-pulse': hasIssues
      }"
      class="fixed top-4 right-20 z-50 px-3 py-1 rounded-full text-white text-sm font-medium shadow-lg transition-all duration-300 flex items-center space-x-2"
      :title="getStatusTooltip()"
    >
      <div
        :class="{
          'bg-white': hasIssues,
          'bg-green-200': isHealthy,
          'bg-yellow-200': !isHealthy && !hasIssues
        }"
        class="w-2 h-2 rounded-full"
      ></div>
      <span>{{ getStatusText() }}</span>
      <span v-if="isLiveMode" class="text-xs opacity-75 animate-pulse">●</span>
    </button>

    <!-- Optimized Dashboard Panel -->
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
        <!-- Header with Controls -->
        <div class="sticky top-0 bg-white border-b px-4 py-3">
          <div class="flex items-center justify-between">
            <h3 class="text-lg font-semibold text-gray-900">System Monitor</h3>
            <div class="flex items-center space-x-2">
              <!-- Live Mode Toggle -->
              <button
                @click="toggleLiveMode"
                :class="{
                  'bg-green-500 text-white': isLiveMode,
                  'bg-gray-200 text-gray-700': !isLiveMode
                }"
                class="px-2 py-1 rounded text-xs font-medium transition-colors duration-200"
                :title="isLiveMode ? 'Live mode: Auto-refresh enabled' : 'Static mode: Manual refresh only'"
              >
                {{ isLiveMode ? 'LIVE' : 'STATIC' }}
              </button>

              <!-- Refresh Control -->
              <div class="relative">
                <button
                  @click="showRefreshOptions = !showRefreshOptions"
                  class="p-1 rounded-full hover:bg-gray-100 transition-colors duration-200 text-xs"
                  :title="`Refresh every ${formatInterval(currentRefreshInterval)}`"
                >
                  ⏱{{ formatInterval(currentRefreshInterval) }}
                </button>

                <!-- Refresh Options Dropdown -->
                <div
                  v-if="showRefreshOptions"
                  class="absolute right-0 top-full mt-1 bg-white border rounded-lg shadow-lg z-50 min-w-32"
                  @click.stop
                >
                  <div class="p-2 text-xs text-gray-500 border-b">Update Interval</div>
                  <button
                    v-for="interval in refreshIntervals"
                    :key="interval.value"
                    @click="setRefreshInterval(interval.value)"
                    :class="{
                      'bg-blue-50 text-blue-700': currentRefreshInterval === interval.value,
                      'hover:bg-gray-50': currentRefreshInterval !== interval.value
                    }"
                    class="w-full text-left px-3 py-2 text-sm transition-colors duration-200"
                  >
                    {{ interval.label }}
                  </button>
                  <div class="border-t">
                    <button
                      @click="performManualRefresh"
                      class="w-full text-left px-3 py-2 text-sm text-blue-600 hover:bg-blue-50 transition-colors duration-200"
                    >
                      Manual Refresh
                    </button>
                  </div>
                </div>
              </div>

              <!-- Manual Refresh Button -->
              <button
                @click="performManualRefresh"
                :disabled="isLoading"
                class="p-1 rounded-full hover:bg-gray-100 transition-colors duration-200"
                title="Manual refresh"
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

              <!-- Close Button -->
              <button
                @click="closePanel"
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
          <!-- Performance Impact Warning -->
          <div v-if="isLiveMode && currentRefreshInterval < 30000" class="bg-amber-50 border border-amber-200 rounded-lg p-3">
            <div class="flex items-center space-x-2">
              <svg class="w-4 h-4 text-amber-500" fill="currentColor" viewBox="0 0 20 20">
                <path fill-rule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clip-rule="evenodd"></path>
              </svg>
              <span class="text-sm text-amber-700 font-medium">
                Fast Refresh Active
              </span>
            </div>
            <p class="text-xs text-amber-600 mt-1">
              High refresh rate may impact performance. Consider using 30s+ intervals.
            </p>
          </div>

          <!-- System Health Overview -->
          <div class="space-y-2">
            <h4 class="text-sm font-medium text-gray-700">System Health</h4>
            <div class="grid grid-cols-2 gap-2 text-sm">
              <div
                v-for="(status, service) in healthStatus"
                :key="service"
                :class="{
                  'bg-green-50 border-green-200': status === 'healthy',
                  'bg-yellow-50 border-yellow-200': status === 'degraded',
                  'bg-red-50 border-red-200': status === 'critical',
                  'bg-gray-50 border-gray-200': status === 'unknown'
                }"
                class="border rounded p-2"
              >
                <div class="text-gray-500 capitalize">{{ service }}</div>
                <div
                  :class="{
                    'text-green-700 font-medium': status === 'healthy',
                    'text-yellow-700 font-medium': status === 'degraded',
                    'text-red-700 font-medium': status === 'critical',
                    'text-gray-500': status === 'unknown'
                  }"
                  class="capitalize"
                >
                  {{ status }}
                </div>
              </div>
            </div>
          </div>

          <!-- Performance Metrics -->
          <div class="space-y-2">
            <h4 class="text-sm font-medium text-gray-700">Performance</h4>
            <div class="space-y-1 text-sm">
              <div class="flex justify-between">
                <span class="text-gray-500">Monitoring Overhead:</span>
                <span :class="{
                  'font-medium text-green-600': performanceData.monitoringOverhead < 25,
                  'font-medium text-yellow-600': performanceData.monitoringOverhead >= 25 && performanceData.monitoringOverhead < 40,
                  'font-medium text-red-600': performanceData.monitoringOverhead >= 40
                }">
                  {{ performanceData.monitoringOverhead.toFixed(1) }}ms/min
                </span>
              </div>
              <div class="flex justify-between">
                <span class="text-gray-500">Health Checks:</span>
                <span class="font-medium">{{ performanceData.checksPerformed }}</span>
              </div>
              <div class="flex justify-between">
                <span class="text-gray-500">Avg Check Time:</span>
                <span class="font-medium">{{ performanceData.averageCheckTime.toFixed(1) }}ms</span>
              </div>
              <div class="flex justify-between">
                <span class="text-gray-500">Memory Usage:</span>
                <span class="font-medium">{{ formatMemoryUsage() }}</span>
              </div>
            </div>
          </div>

          <!-- Active Issues -->
          <div v-if="activeIssues.length > 0" class="space-y-2">
            <h4 class="text-sm font-medium text-red-700">Active Issues ({{ activeIssues.length }})</h4>
            <div class="space-y-1">
              <div
                v-for="issue in activeIssues.slice(0, 3)"
                :key="issue.id"
                class="bg-red-50 border border-red-200 rounded p-2 text-sm"
              >
                <div class="font-medium text-red-800">{{ issue.type }}</div>
                <div class="text-red-600 text-xs">{{ issue.message }}</div>
                <div class="text-red-500 text-xs">{{ formatTimeAgo(issue.timestamp) }}</div>
              </div>
            </div>
          </div>

          <!-- Monitoring Statistics -->
          <div class="space-y-2">
            <h4 class="text-sm font-medium text-gray-700">Monitoring Stats</h4>
            <div class="text-xs text-gray-500 space-y-1">
              <div>Mode: {{ isLiveMode ? 'Live Updates' : 'Manual Only' }}</div>
              <div>Interval: {{ formatInterval(currentRefreshInterval) }}</div>
              <div>Last Update: {{ formatTimeAgo(lastUpdated) }}</div>
              <div v-if="isLiveMode">Next Update: {{ formatTimeAgo(nextUpdate) }}</div>
            </div>
          </div>

          <!-- Action Buttons -->
          <div class="border-t pt-3 space-y-2">
            <button
              @click="clearAllIssues"
              v-if="activeIssues.length > 0"
              class="w-full bg-red-500 text-white px-3 py-2 rounded text-sm hover:bg-red-600 transition-colors duration-200"
            >
              Clear All Issues
            </button>

            <button
              @click="resetPerformanceStats"
              class="w-full bg-gray-500 text-white px-3 py-2 rounded text-sm hover:bg-gray-600 transition-colors duration-200"
            >
              Reset Performance Stats
            </button>
          </div>
        </div>
      </div>
    </Transition>

    <!-- Click overlay to close options -->
    <div
      v-if="showRefreshOptions"
      @click="showRefreshOptions = false"
      class="fixed inset-0 z-30"
    ></div>
  </div>
</template>

<script>
import { ref, computed, onMounted, onUnmounted, nextTick } from 'vue'
import { createLogger } from '@/utils/debugUtils'
import { optimizedHealthMonitor } from '@/utils/OptimizedHealthMonitor.js'
import { useAsyncOperation } from '@/composables/useAsyncOperation'

const logger = createLogger('OptimizedRumDashboard')

export default {
  name: 'OptimizedRumDashboard',
  setup() {
    // Reactive state
    const isVisible = ref(false)
    const isLiveMode = ref(false)
    const showRefreshOptions = ref(false)
    const lastUpdated = ref(Date.now())
    const nextUpdate = ref(Date.now())

    // Refresh configuration
    const refreshIntervals = [
      { label: 'Manual Only', value: 0 },
      { label: '10 seconds', value: 10000 },
      { label: '30 seconds', value: 30000 },
      { label: '1 minute', value: 60000 },
      { label: '2 minutes', value: 120000 },
      { label: '5 minutes', value: 300000 }
    ]
    const currentRefreshInterval = ref(60000) // Default 1 minute
    let refreshTimer = null

    // Data state
    const healthStatus = ref({
      overall: 'unknown',
      backend: 'unknown',
      frontend: 'healthy',
      websocket: 'unknown'
    })

    const performanceData = ref({
      monitoringOverhead: 0,
      checksPerformed: 0,
      averageCheckTime: 0,
      memoryUsage: 0
    })

    const activeIssues = ref([])

    // Environment detection
    const isDev = process.env.NODE_ENV === 'development' || window.location.hostname === 'localhost'

    // Computed properties
    const hasIssues = computed(() => activeIssues.value.length > 0)
    const isHealthy = computed(() =>
      healthStatus.value.overall === 'healthy' ||
      (healthStatus.value.backend === 'healthy' && healthStatus.value.frontend === 'healthy')
    )

    // Methods
    const toggleVisibility = () => {
      isVisible.value = !isVisible.value

      if (isVisible.value) {
        // Notify health monitor that user is viewing
        optimizedHealthMonitor.setUserViewing(true)
        // Perform immediate refresh when opening
        performManualRefresh()
      } else {
        // Notify health monitor that user stopped viewing
        optimizedHealthMonitor.setUserViewing(false)
      }
    }

    const closePanel = () => {
      isVisible.value = false
      showRefreshOptions.value = false
      optimizedHealthMonitor.setUserViewing(false)
    }

    const toggleLiveMode = () => {
      isLiveMode.value = !isLiveMode.value

      if (isLiveMode.value) {
        startAutoRefresh()
      } else {
        stopAutoRefresh()
      }

    }

    const setRefreshInterval = (interval) => {
      currentRefreshInterval.value = interval
      showRefreshOptions.value = false

      if (interval === 0) {
        isLiveMode.value = false
        stopAutoRefresh()
      } else if (isLiveMode.value) {
        startAutoRefresh()
      }
    }

    const startAutoRefresh = () => {
      stopAutoRefresh()

      if (currentRefreshInterval.value > 0) {

        const refresh = () => {
          if (isLiveMode.value && isVisible.value) {
            performManualRefresh()
            nextUpdate.value = Date.now() + currentRefreshInterval.value
            refreshTimer = setTimeout(refresh, currentRefreshInterval.value)
          }
        }

        refreshTimer = setTimeout(refresh, currentRefreshInterval.value)
        nextUpdate.value = Date.now() + currentRefreshInterval.value
      }
    }

    const stopAutoRefresh = () => {
      if (refreshTimer) {
        clearTimeout(refreshTimer)
        refreshTimer = null
      }
    }

    // Use composable for async data fetching
    const { execute: performManualRefresh, loading: isLoading } = useAsyncOperation(async () => {
      // Get health status from optimized monitor
      const healthData = optimizedHealthMonitor.getHealthStatus()

      // Update health status
      healthStatus.value = { ...healthData }

      // Update performance data
      performanceData.value = {
        monitoringOverhead: optimizedHealthMonitor.performanceBudget.currentOverhead,
        checksPerformed: healthData.performanceMetrics?.checksPerformed || 0,
        averageCheckTime: healthData.performanceMetrics?.averageCheckTime || 0,
        memoryUsage: getMemoryUsage()
      }

      // Update active issues based on health status
      updateActiveIssues(healthData)

      lastUpdated.value = Date.now()
    }, {
      onError: (error) => {
        logger.error('Error refreshing data:', error)

        // Add error as active issue
        activeIssues.value.unshift({
          id: Date.now(),
          type: 'Dashboard Error',
          message: error.message,
          timestamp: Date.now()
        })
      }
    })

    const updateActiveIssues = (healthData) => {
      const issues = []

      // Check for health issues
      Object.entries(healthData).forEach(([service, status]) => {
        if (status === 'critical' || status === 'degraded') {
          issues.push({
            id: `health-${service}`,
            type: `${service.charAt(0).toUpperCase() + service.slice(1)} Issue`,
            message: `${service} is ${status}`,
            timestamp: Date.now()
          })
        }
      })

      // Check for performance issues
      if (performanceData.value.monitoringOverhead > 40) {
        issues.push({
          id: 'performance-overhead',
          type: 'Performance Issue',
          message: `High monitoring overhead: ${performanceData.value.monitoringOverhead.toFixed(1)}ms/min`,
          timestamp: Date.now()
        })
      }

      // Check for consecutive failures
      if (healthData.consecutiveFailures) {
        Object.entries(healthData.consecutiveFailures).forEach(([service, count]) => {
          if (count >= 3) {
            issues.push({
              id: `failures-${service}`,
              type: 'Connection Failures',
              message: `${count} consecutive failures for ${service}`,
              timestamp: Date.now()
            })
          }
        })
      }

      activeIssues.value = issues
    }

    const getMemoryUsage = () => {
      if (performance.memory) {
        return Math.round((performance.memory.usedJSHeapSize / performance.memory.totalJSHeapSize) * 100)
      }
      return 0
    }

    const clearAllIssues = () => {
      activeIssues.value = []
    }

    const resetPerformanceStats = () => {
      // Reset performance metrics in the health monitor
      if (optimizedHealthMonitor.performanceMetrics) {
        optimizedHealthMonitor.performanceMetrics.checksPerformed = 0
        optimizedHealthMonitor.performanceMetrics.totalCheckTime = 0
        optimizedHealthMonitor.performanceMetrics.averageCheckTime = 0
      }

      performManualRefresh()
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

    const formatInterval = (interval) => {
      if (interval === 0) return 'Manual'
      if (interval < 60000) return `${interval / 1000}s`
      return `${interval / 60000}m`
    }

    const formatMemoryUsage = () => {
      return `${performanceData.value.memoryUsage}%`
    }

    const getStatusText = () => {
      if (hasIssues.value) return activeIssues.value.length
      if (isHealthy.value) return '✓'
      return '?'
    }

    const getStatusTooltip = () => {
      if (hasIssues.value) {
        return `${activeIssues.value.length} active issues detected`
      }
      if (isHealthy.value) {
        return 'System monitoring - all services healthy'
      }
      return 'System monitoring - status unknown'
    }

    // Lifecycle
    onMounted(() => {
      if (isDev) {

        // Listen for health changes from the optimized monitor
        optimizedHealthMonitor.onHealthChange((healthData) => {
          if (isVisible.value) {
            // Update data when health changes and dashboard is visible
            healthStatus.value = healthData.status
            updateActiveIssues(healthData)
            lastUpdated.value = Date.now()
          }
        })

        // Show dashboard if there are critical issues
        nextTick(() => {
          const currentHealth = optimizedHealthMonitor.getHealthStatus()
          if (currentHealth.overall === 'critical') {
            isVisible.value = true
          }
        })
      }
    })

    onUnmounted(() => {
      stopAutoRefresh()
      optimizedHealthMonitor.setUserViewing(false)
    })

    return {
      // Reactive state
      isVisible,
      isLoading,
      isLiveMode,
      showRefreshOptions,
      lastUpdated,
      nextUpdate,
      currentRefreshInterval,
      refreshIntervals,
      healthStatus,
      performanceData,
      activeIssues,

      // Computed
      hasIssues,
      isHealthy,
      isDev,

      // Methods
      toggleVisibility,
      closePanel,
      toggleLiveMode,
      setRefreshInterval,
      performManualRefresh,
      clearAllIssues,
      resetPerformanceStats,
      formatTimeAgo,
      formatInterval,
      formatMemoryUsage,
      getStatusText,
      getStatusTooltip
    }
  }
}
</script>

<style scoped>
/* Issue #704: Migrated to CSS design tokens */
.optimized-rum-dashboard {
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

/* Smooth transitions */
.transition-colors {
  transition-property: background-color, border-color, color, fill, stroke;
  transition-timing-function: cubic-bezier(0.4, 0, 0.2, 1);
  transition-duration: 200ms;
}
</style>