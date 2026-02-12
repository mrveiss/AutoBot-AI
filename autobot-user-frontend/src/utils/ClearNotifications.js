/**
 * Utility to clear stuck system notifications
 * This addresses the issue where system error notifications with overlay level
 * are covering the entire UI due to accumulated consecutive failures
 */

import { createLogger } from '@/utils/debugUtils'

// Create scoped logger for ClearNotifications
const logger = createLogger('ClearNotifications')

export async function clearAllSystemNotifications() {
  try {
    // Lazy-load store to avoid circular dependency during initialization
    const { useAppStore } = await import('@/stores/useAppStore')
    const appStore = useAppStore()


    // Clear all notifications
    if (appStore && typeof appStore.clearAllNotifications === 'function') {
      appStore.clearAllNotifications()
    }

    // Reset backend status to healthy to prevent recreation
    if (appStore && typeof appStore.setBackendStatus === 'function') {
      appStore.setBackendStatus({
        text: 'Connected',
        class: 'success'
      })
    }

    return true
  } catch (error) {
    logger.error('[ClearNotifications] Error clearing notifications:', error)
    return false
  }
}

export function resetHealthMonitor() {
  try {
    // Reset the frontend health monitor consecutive failures
    if (window.frontendHealthMonitor) {
      if (window.frontendHealthMonitor.consecutiveFailures) {
        window.frontendHealthMonitor.consecutiveFailures = {
          backend: 0,
          websocket: 0,
          router: 0
        }
      }

      if (window.frontendHealthMonitor.healthStatus) {
        window.frontendHealthMonitor.healthStatus = {
          overall: 'healthy',
          frontend: 'healthy',
          backend: 'healthy',
          router: 'healthy',
          cache: 'healthy',
          websocket: 'healthy'
        }
      }
    }

    return true
  } catch (error) {
    logger.error('[ClearNotifications] Error resetting health monitor:', error)
    return false
  }
}

// Make functions available globally for console access
if (typeof window !== 'undefined') {
  window.clearAllSystemNotifications = clearAllSystemNotifications
  window.resetHealthMonitor = resetHealthMonitor

  // Auto-execute on import in development
  if (import.meta.env.DEV) {
  }
}

export default {
  clearAllSystemNotifications,
  resetHealthMonitor
}
