// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
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

export async function resetHealthMonitor() {
  try {
    // Issue #11640: reset the canonical health monitor via its own seam.
    // (Previously poked window.frontendHealthMonitor — an orphaned monitor
    // that was never imported, so this function silently no-oped.)
    const { healthMonitor } = await import('@/utils/HealthMonitor.js')
    healthMonitor.resetFailures()

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
