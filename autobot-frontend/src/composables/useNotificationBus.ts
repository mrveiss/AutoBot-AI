// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * Canonical notification bus composable.
 *
 * Provides typed convenience methods for component-level notifications.
 * All components should import this instead of useToast directly.
 * The underlying transport is useToast; notificationBridge wraps this for
 * non-Vue (class/utility) callers.
 *
 * Usage:
 * ```typescript
 * const { success, error, warning, info, showToast } = useNotificationBus()
 * success('Saved')
 * error('Upload failed')
 * showToast('Custom duration', 'info', 2000)
 * ```
 */

import { useToast } from '@/composables/useToast'
export type { ToastType } from '@/composables/useToast'

export function useNotificationBus() {
  const { showToast } = useToast()

  return {
    showToast,
    success: (message: string, duration?: number) => showToast(message, 'success', duration),
    error: (message: string, duration?: number) => showToast(message, 'error', duration),
    warning: (message: string, duration?: number) => showToast(message, 'warning', duration),
    info: (message: string, duration?: number) => showToast(message, 'info', duration),
  }
}
