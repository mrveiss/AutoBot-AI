/**
 * Utility to clear stuck system notifications
 * This addresses the issue where system error notifications with overlay level
 * are covering the entire UI due to accumulated consecutive failures
 */

import { useAppStore } from '@/stores/useAppStore'

export function clearAllSystemNotifications() {
  try {
    const appStore = useAppStore()

    console.log('[ClearNotifications] Current notifications:', appStore.systemNotifications?.length || 0)

    // Clear all notifications
    if (appStore && typeof appStore.clearAllNotifications === 'function') {
      appStore.clearAllNotifications()
      console.log('[ClearNotifications] All system notifications cleared')
    }

    // Reset backend status to healthy to prevent recreation
    if (appStore && typeof appStore.setBackendStatus === 'function') {
      appStore.setBackendStatus({
        text: 'Connected',
        class: 'success'
      })
      console.log('[ClearNotifications] Backend status reset to healthy')
    }

    return true
  } catch (error) {
    console.error('[ClearNotifications] Error clearing notifications:', error)
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
        console.log('[ClearNotifications] Health monitor consecutive failures reset')
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
        console.log('[ClearNotifications] Health monitor status reset to healthy')
      }
    }

    return true
  } catch (error) {
    console.error('[ClearNotifications] Error resetting health monitor:', error)
    return false
  }
}

// Make functions available globally for console access
if (typeof window !== 'undefined') {
  window.clearAllSystemNotifications = clearAllSystemNotifications
  window.resetHealthMonitor = resetHealthMonitor

  // Auto-execute on import in development
  if (import.meta.env.DEV) {
    console.log('[ClearNotifications] Notification clearing utilities loaded')
    console.log('Available commands:')
    console.log('- window.clearAllSystemNotifications()')
    console.log('- window.resetHealthMonitor()')
  }
}

export default {
  clearAllSystemNotifications,
  resetHealthMonitor
}