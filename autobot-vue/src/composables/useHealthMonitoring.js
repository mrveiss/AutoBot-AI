/**
 * Health Monitoring Composable
 * Extracted from App.vue for better maintainability
 */

import { onMounted, onUnmounted } from 'vue'
import { createLogger } from '@/utils/debugUtils'
import { useRouter } from 'vue-router'

// Create scoped logger for useHealthMonitoring
const logger = createLogger('useHealthMonitoring')
import { useAppStore } from '@/stores/useAppStore'
import { optimizedHealthMonitor } from '@/utils/OptimizedHealthMonitor.js'
import { smartMonitoringController, getAdaptiveInterval } from '@/config/OptimizedPerformance.js'
import { clearAllSystemNotifications, resetHealthMonitor } from '@/utils/ClearNotifications.js'
import { cacheBuster } from '@/utils/CacheBuster.js'

export function useHealthMonitoring() {
  const router = useRouter()
  const appStore = useAppStore()

  let _systemHealthCheck = null // Reserved for future health check expansion
  let notificationCleanup = null

  // OPTIMIZED: Intelligent system health monitoring
  const startOptimizedHealthCheck = () => {

    // Listen for health changes from optimized monitor
    optimizedHealthMonitor.onHealthChange((healthData) => {
      // Update app store with health status
      if (appStore && typeof appStore.setBackendStatus === 'function') {
        const backendStatus = healthData.status.backend
        appStore.setBackendStatus({
          text: backendStatus === 'healthy' ? 'Connected' :
                backendStatus === 'degraded' ? 'Degraded' : 'Disconnected',
          class: backendStatus === 'healthy' ? 'success' :
                 backendStatus === 'degraded' ? 'warning' : 'error'
        })
      }

      // Update smart monitoring controller
      smartMonitoringController.setSystemHealth(healthData.status.overall)
    })

  }

  // OPTIMIZED: Smart notification cleanup with adaptive intervals
  const startOptimizedNotificationCleanup = () => {
    if (notificationCleanup) {
      clearInterval(notificationCleanup)
    }

    // Use adaptive interval based on system state
    const cleanupInterval = getAdaptiveInterval('NOTIFICATION_CLEANUP', 'healthy', false)

    notificationCleanup = setInterval(() => {
      if (appStore && appStore.systemNotifications && appStore.systemNotifications.length > 5) {
        // Keep only the last 5 notifications
        const recentNotifications = appStore.systemNotifications.slice(-5)
        appStore.systemNotifications.splice(0, appStore.systemNotifications.length, ...recentNotifications)
      }
    }, cleanupInterval)

  }

  const stopOptimizedNotificationCleanup = () => {
    if (notificationCleanup) {
      clearInterval(notificationCleanup)
      notificationCleanup = null
    }
  }

  // Router event monitoring - OPTIMIZED: Event-driven instead of polling
  const setupRouterMonitoring = () => {
    // Monitor router navigation events
    router.afterEach((_to, _from) => {

      // Update user activity in smart monitoring controller
      smartMonitoringController.userActivity.lastActivity = Date.now()
      smartMonitoringController.userActivity.isActive = true
    })

    // Monitor router errors
    router.onError((error) => {
      logger.error('[App] Router error:', error)
      // Note: handleGlobalError should be passed in or accessed via a store
    })
  }

  const initializeHealthMonitoring = async () => {

    // CRITICAL FIX: Clear any stuck system notifications on startup
    clearAllSystemNotifications()
    resetHealthMonitor()

    // OPTIMIZED: Initialize new performance-aware systems
    try {
      // Initialize cache buster
      if (cacheBuster && typeof cacheBuster.initialize === 'function') {
        cacheBuster.initialize()
      }

      // OPTIMIZED: Start optimized health monitoring
      startOptimizedHealthCheck()

      // OPTIMIZED: Setup router monitoring (event-driven)
      setupRouterMonitoring()


    } catch (error) {
      logger.error('[App] Error initializing optimized systems:', error)
    }

    // OPTIMIZED: Start adaptive notification cleanup
    startOptimizedNotificationCleanup()

    // Set loading to false once initialization is complete
    if (appStore && typeof appStore.setLoading === 'function') {
      appStore.setLoading(false)
    }

  }

  const cleanupHealthMonitoring = () => {

    stopOptimizedNotificationCleanup()

    // Destroy optimized health monitor
    if (optimizedHealthMonitor && typeof optimizedHealthMonitor.destroy === 'function') {
      optimizedHealthMonitor.destroy()
    }
  }

  onMounted(async () => {
    await initializeHealthMonitoring()
  })

  onUnmounted(() => {
    cleanupHealthMonitoring()
  })

  return {
    // Methods
    initializeHealthMonitoring,
    cleanupHealthMonitoring,
    startOptimizedHealthCheck,
    startOptimizedNotificationCleanup,
    stopOptimizedNotificationCleanup
  }
}