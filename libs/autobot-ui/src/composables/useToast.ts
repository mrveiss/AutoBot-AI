// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * @autobot/ui — Toast Notification Composable (#14907)
 *
 * Consolidation of `autobot-frontend/src/composables/useToast.ts` (184 lines)
 * and `autobot-slm-frontend/src/composables/useToast.ts` (93 lines) — same
 * public contract (`ToastType`, `Toast`, `UseToastReturn`, `MAX_TOASTS`,
 * `TOAST_DURATIONS`, `TOAST_INJECT_KEY`, `provideToast`, `useToast`), two
 * independently-drifted implementations. This is the union of both:
 *
 *   - `MAX_TOASTS` / stacking behavior — taken from the main app's version.
 *     The SLM's version (MAX_TOASTS=5) simply truncated the oldest toast —
 *     including an unread persistent error — whenever the stack overflowed.
 *     The main app's version distinguishes Tier C (persistent error) toasts,
 *     never evicts one, and queues overflow toasts FIFO until a visible slot
 *     opens. Dropping that to match the SLM's simpler truncation would have
 *     silently discarded an in-flight error notification — a regression
 *     wearing a refactor's clothes. `MAX_TOASTS` is set to 3 (the main app's
 *     documented, tested value — Miller's Law, MVA-347); neither app's call
 *     sites read the constant directly, so this is a safe pick, not a guess.
 *   - Everything else (types, durations, provide/inject wiring, singleton
 *     fallback) was already identical between the two.
 *
 * Usage (direct import):
 * ```typescript
 * import { useToast } from '@autobot/ui'
 *
 * const { showToast } = useToast()
 * showToast('Operation successful', 'success')
 * showToast('Something went wrong', 'error')   // persistent — no auto-dismiss
 * showToast('Please wait...', 'info')
 * showToast('Proceed with caution', 'warning')
 * ```
 *
 * Usage (provide/inject — register once in App.vue):
 * ```typescript
 * import { provideToast } from '@autobot/ui'
 * provideToast()
 *
 * // In any child component:
 * import { useToast } from '@autobot/ui'
 * const { showToast } = useToast()
 * ```
 */

import { ref, inject, provide, type Ref, type InjectionKey } from 'vue'

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

/**
 * Maximum number of toasts displayed simultaneously (Miller's Law — MVA-347).
 * Oldest Tier A/B toast is evicted when the stack is full.
 * Tier C (persistent error) toasts are never auto-evicted.
 */
export const MAX_TOASTS = 3

/**
 * Default auto-dismiss durations per toast type (ms).
 * 0 = persistent (no auto-dismiss).
 */
export const TOAST_DURATIONS: Record<ToastType, number> = {
  success: 4000,
  info: 4000,
  warning: 6000, // canonical: extra reading time for warnings
  error: 0, // errors are persistent until manually dismissed
}

/** Injection key for provide/inject usage. */
export const TOAST_INJECT_KEY: InjectionKey<UseToastReturn> = Symbol('useToast')

/**
 * Returns true for Tier C toasts: persistent errors that must never be
 * auto-evicted to make room for lower-priority notifications.
 */
const isTierC = (t: Toast): boolean => t.type === 'error' && t.duration === 0

// ============================================================
// Module-level singleton state (shared across all instances
// that do NOT use the provide/inject path).
// ============================================================
const _toasts = ref<Toast[]>([])
let _nextId = 1

function _buildApi(toasts: Ref<Toast[]>, idCounter: { value: number }): UseToastReturn {
  // Toasts waiting for a visible slot; shown in FIFO order when a slot opens.
  const pendingQueue: Toast[] = []

  const removeToast = (id: number): void => {
    // Remove from visible stack.
    const index = toasts.value.findIndex((t) => t.id === id)
    if (index > -1) {
      toasts.value.splice(index, 1)
      // Promote next queued toast now that a slot opened.
      if (pendingQueue.length > 0) {
        const next = pendingQueue.shift()!
        toasts.value.push(next)
        if (next.duration > 0) {
          setTimeout(() => removeToast(next.id), next.duration)
        }
      }
      return
    }
    // Also handle removal of a still-queued toast.
    const queueIndex = pendingQueue.findIndex((t) => t.id === id)
    if (queueIndex > -1) {
      pendingQueue.splice(queueIndex, 1)
    }
  }

  const showToast = (
    message: string,
    type: ToastType = 'info',
    duration?: number,
  ): number => {
    const resolvedDuration = duration !== undefined ? duration : TOAST_DURATIONS[type]
    const id = idCounter.value++
    const toast: Toast = { id, message, type, duration: resolvedDuration }

    if (toasts.value.length >= MAX_TOASTS) {
      // Evict the oldest non-Tier-C toast to make room.
      const evictIndex = toasts.value.findIndex((t) => !isTierC(t))
      if (evictIndex !== -1) {
        toasts.value.splice(evictIndex, 1)
      } else {
        // All visible slots are Tier C — queue until the user dismisses one.
        pendingQueue.push(toast)
        return id
      }
    }

    toasts.value.push(toast)

    if (resolvedDuration > 0) {
      setTimeout(() => {
        removeToast(id)
      }, resolvedDuration)
    }

    return id
  }

  const clearAllToasts = (): void => {
    toasts.value.splice(0)
    pendingQueue.splice(0)
  }

  return { toasts, showToast, removeToast, clearAllToasts }
}

// Singleton counter object (mutable reference so _buildApi closure can mutate it).
const _idCounter = { value: _nextId }
const _singletonApi = _buildApi(_toasts, _idCounter)

// Keep module-level nextId in sync (for backward compat if any code read it).
Object.defineProperty(_idCounter, 'value', {
  get: () => _nextId,
  set: (v: number) => { _nextId = v },
})

/**
 * Register the toast API with the current Vue component tree via provide().
 * Call once in the root App component's setup().
 * Child components calling useToast() will receive the same instance.
 */
export function provideToast(): UseToastReturn {
  provide(TOAST_INJECT_KEY, _singletonApi)
  return _singletonApi
}

/**
 * Toast notification composable.
 *
 * When called inside a component that has a provideToast() ancestor, the
 * injected instance is returned (same state). Otherwise falls back to the
 * module-level singleton, which is the same underlying state.
 *
 * @returns Toast notification utilities
 */
export function useToast(): UseToastReturn {
  const injected = inject(TOAST_INJECT_KEY, null)
  return injected ?? _singletonApi
}
