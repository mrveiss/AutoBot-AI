/**
 * Health Monitoring Composable
 * Extracted from App.vue for better maintainability
 */

import { ref, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAppStore } from '@/stores/useAppStore'
import { optimizedHealthMonitor } from '@/utils/OptimizedHealthMonitor.js'
import { smartMonitoringController, getAdaptiveInterval } from '@/config/OptimizedPerformance.js'
import { clearAllSystemNotifications, resetHealthMonitor } from '@/utils/ClearNotifications.js'
import { cacheBuster } from '@/utils/CacheBuster.js'

export function useHealthMonitoring() {
  const router = useRouter()
  const appStore = useAppStore()

  let systemHealthCheck = null
  let notificationCleanup = null

  // OPTIMIZED: Intelligent system health monitoring
  const startOptimizedHealthCheck = () => {
    console.log('[App] Starting optimized health monitoring system...')

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

    console.log('[App] Optimized health monitoring initialized')
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
        console.log('[App] Cleaning up excessive notifications:', appStore.systemNotifications.length)
        // Keep only the last 5 notifications
        const recentNotifications = appStore.systemNotifications.slice(-5)
        appStore.systemNotifications.splice(0, appStore.systemNotifications.length, ...recentNotifications)
      }
    }, cleanupInterval)

    console.log(`[App] Notification cleanup scheduled every ${Math.round(cleanupInterval/60000)} minutes`)
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
    router.afterEach((to, from) => {
      console.log(`[App] Navigation: ${from.path} → ${to.path}`)

      // Update user activity in smart monitoring controller
      smartMonitoringController.userActivity.lastActivity = Date.now()
      smartMonitoringController.userActivity.isActive = true
    })

    // Monitor router errors
    router.onError((error) => {
      console.error('[App] Router error:', error)
      // Note: handleGlobalError should be passed in or accessed via a store
    })
  }

  const initializeHealthMonitoring = async () => {
    console.log('[App] Initializing optimized AutoBot health monitoring...')

    // CRITICAL FIX: Clear any stuck system notifications on startup
    console.log('[App] Clearing stuck system notifications on startup...')
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

      console.log('[App] Optimized monitoring systems initialized successfully')

    } catch (error) {
      console.error('[App] Error initializing optimized systems:', error)
    }

    // OPTIMIZED: Start adaptive notification cleanup
    startOptimizedNotificationCleanup()

    // Set loading to false once initialization is complete
    if (appStore && typeof appStore.setLoading === 'function') {
      appStore.setLoading(false)
    }

    console.log('[App] ✅ Optimized AutoBot initialized - monitoring restored with <50ms performance budget')
  }

  const cleanupHealthMonitoring = () => {
    console.log('[App] Cleaning up optimized monitoring systems...')

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