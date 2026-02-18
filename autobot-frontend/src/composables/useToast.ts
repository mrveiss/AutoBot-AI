/**
 * Toast Notification Composable
 *
 * Provides a global toast notification system for user feedback.
 *
 * Usage:
 * ```typescript
 * import { useToast } from '@/composables/useToast'
 *
 * const { showToast } = useToast()
 *
 * // Show different types of toasts
 * showToast('Operation successful', 'success')
 * showToast('Something went wrong', 'error', 5000)
 * showToast('Please wait...', 'info')
 * showToast('Proceed with caution', 'warning')
 * ```
 */

import { ref, type Ref } from 'vue'

export type ToastType = 'info' | 'success' | 'warning' | 'error'

export interface Toast {
  id: number
  message: string
  type: ToastType
  duration: number
}

export interface UseToastReturn {
  toasts: Ref<Toast[]>
  showToast: (message: string, type?: ToastType, duration?: number) => number
  removeToast: (id: number) => void
  clearAllToasts: () => void
}

// Global toast state (shared across all component instances)
const toasts = ref<Toast[]>([])
let nextId = 1

/**
 * Toast notification composable
 *
 * @returns Toast notification utilities
 */
export function useToast(): UseToastReturn {
  /**
   * Show a toast notification
   *
   * @param message - Message to display
   * @param type - Toast type: 'info', 'success', 'warning', 'error'
   * @param duration - Duration in milliseconds (0 = no auto-remove)
   * @returns Toast ID for manual removal
   */
  const showToast = (
    message: string,
    type: ToastType = 'info',
    duration = 3000
  ): number => {
    const id = nextId++
    const toast: Toast = {
      id,
      message,
      type,
      duration
    }

    toasts.value.push(toast)

    // Auto-remove after duration
    if (duration > 0) {
      setTimeout(() => {
        removeToast(id)
      }, duration)
    }

    return id
  }

  /**
   * Remove a toast by ID
   *
   * @param id - Toast ID to remove
   */
  const removeToast = (id: number): void => {
    const index = toasts.value.findIndex((toast) => toast.id === id)
    if (index > -1) {
      toasts.value.splice(index, 1)
    }
  }

  /**
   * Clear all toasts
   */
  const clearAllToasts = (): void => {
    toasts.value.splice(0)
  }

  return {
    toasts,
    showToast,
    removeToast,
    clearAllToasts
  }
}
