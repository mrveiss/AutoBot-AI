// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * Canonical notification routing composable.
 *
 * ## Why this exists
 *
 * The frontend had three independent notification surfaces with no shared
 * routing bus (GH#7448):
 *
 *   1. Toast (`useToast`) — transient pop-up messages, auto-dismissed
 *   2. Inline alert (`<div role="alert">`) — persistent, co-located with the
 *      triggering control
 *   3. Error boundary — full fallback UI for unrecoverable errors
 *
 * Components were choosing ad-hoc, leading to inconsistent UX. This composable
 * is the single canonical routing surface: callers say **what** happened (with
 * metadata), and the bus routes the notification to the **right** surface.
 *
 * ## Routing rules
 *
 * | error type            | route               | auto-dismiss? |
 * |-----------------------|---------------------|---------------|
 * | transient (retryable) | toast warning       | yes (4 s)     |
 * | user-recoverable      | toast error         | no (sticky)   |
 * | background / silent   | console only        | n/a           |
 * | success               | toast success       | yes (4 s)     |
 * | informational         | toast info          | yes (4 s)     |
 *
 * For inline errors (form validation, per-field messages), the caller owns
 * the display — `useNotificationBus` returns `lastError` for binding.
 *
 * ## Usage
 *
 * ```typescript
 * import { useNotificationBus } from '@/composables/useNotificationBus'
 *
 * const bus = useNotificationBus()
 *
 * // Route an API error (auto-selects toast vs sticky based on type)
 * await bus.notifyApiError(err, { context: 'Loading users' })
 *
 * // Explicit convenience helpers
 * bus.notifySuccess('Settings saved')
 * bus.notifyWarning('Session expiring soon')
 * bus.notifyInfo('New version available — refresh to update')
 *
 * // Legacy short-form aliases (GH#7741 components — backward compatible)
 * bus.success('Settings saved')
 * bus.error('Something failed')
 *
 * // Last error reactive ref (for inline display)
 * <p v-if="bus.lastError.value">{{ bus.lastError.value.message }}</p>
 * ```
 *
 * ## Migration from raw `useToast`
 *
 * Before:
 * ```typescript
 * const { showToast } = useToast()
 * showToast('Something failed', 'error')
 * ```
 *
 * After:
 * ```typescript
 * const bus = useNotificationBus()
 * bus.notifyError('Something failed')   // routing is handled automatically
 * ```
 *
 * Companion issues: GH#7447 (error handler consolidation), GH#7448 (toast unification)
 */

import { ref, type Ref } from 'vue'
import { useToast, type ToastType } from '@/composables/useToast'
import { createLogger } from '@/utils/debugUtils'
import { extractApiErrorMessage } from '@/utils/errorExtract'

export type { ToastType } from '@/composables/useToast'

const logger = createLogger('useNotificationBus')

// ============================================================
// Types
// ============================================================

export interface ApiErrorContext {
  /** Human-readable context label, e.g. "Loading users" */
  context?: string
  /** When true, treat as transient — use toast warning instead of sticky error */
  retryable?: boolean
  /** Suppress the toast entirely (errors still written to lastError) */
  silent?: boolean
}

export interface UseNotificationBusReturn {
  /** Last error set via notifyApiError/notifyError, or null */
  lastError: Ref<Error | null>

  /**
   * Route an API/async error to the correct surface.
   * Reads error type to choose toast variant and persistence.
   */
  notifyApiError(err: unknown, ctx?: ApiErrorContext): void

  /** Show a sticky error toast (no auto-dismiss). */
  notifyError(message: string): void

  /** Show an auto-dismissing warning toast (4 s). */
  notifyWarning(message: string): void

  /** Show an auto-dismissing success toast (4 s). */
  notifySuccess(message: string): void

  /** Show an auto-dismissing info toast (4 s). */
  notifyInfo(message: string): void

  /** Clear the lastError ref (for inline dismissal). */
  clearError(): void

  // Backward-compatible aliases for components wired in GH#7741
  success(message: string, duration?: number): void
  error(message: string, duration?: number): void
  warning(message: string, duration?: number): void
  info(message: string, duration?: number): void
  showToast(message: string, type: ToastType, duration?: number): void
}

// ============================================================
// Implementation
// ============================================================

/**
 * Canonical notification routing composable.
 * Prefer this over calling `useToast()` directly in components.
 */
export function useNotificationBus(): UseNotificationBusReturn {
  const { showToast } = useToast()
  const lastError = ref<Error | null>(null)

  function _toast(message: string, type: ToastType, duration?: number): void {
    showToast(message, type, duration)
  }

  function notifyApiError(err: unknown, ctx: ApiErrorContext = {}): void {
    const fallback = ctx.context ? `${ctx.context} failed` : 'An error occurred'
    const message = extractApiErrorMessage(err, fallback)
    const error = err instanceof Error ? err : new Error(message)

    lastError.value = error

    if (ctx.silent) {
      logger.error(`[silent] ${fallback}:`, err)
      return
    }

    logger.error(`${fallback}:`, err)

    if (ctx.retryable) {
      _toast(message, 'warning')
    } else {
      _toast(message, 'error', 0)
    }
  }

  function notifyError(message: string): void {
    lastError.value = new Error(message)
    logger.error(message)
    _toast(message, 'error', 0)
  }

  function notifyWarning(message: string): void {
    logger.warn(message)
    _toast(message, 'warning')
  }

  function notifySuccess(message: string): void {
    _toast(message, 'success')
  }

  function notifyInfo(message: string): void {
    _toast(message, 'info')
  }

  function clearError(): void {
    lastError.value = null
  }

  return {
    lastError,
    notifyApiError,
    notifyError,
    notifyWarning,
    notifySuccess,
    notifyInfo,
    clearError,
    // Backward-compatible aliases (GH#7741 components use these short forms)
    success: (message, duration) => _toast(message, 'success', duration),
    error: (message, duration) => _toast(message, 'error', duration),
    warning: (message, duration) => _toast(message, 'warning', duration),
    info: (message, duration) => _toast(message, 'info', duration),
    showToast: _toast,
  }
}
