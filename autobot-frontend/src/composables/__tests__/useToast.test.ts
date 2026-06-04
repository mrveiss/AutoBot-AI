/**
 * useToast Composable Tests
 *
 * Covers acceptance criteria from issue #3283 and MVA-347:
 * - Global availability via provide/inject
 * - success / error / warning / info variants
 * - Auto-dismiss after configurable timeout (default 4s for success, persistent for errors)
 * - Maximum 3 toasts stacked; oldest Tier A/B evicted (Miller's Law)
 * - Tier C (persistent error) toasts never auto-evicted; excess queued
 * - Manual dismiss promotes queued toasts
 *
 * @author mrveiss
 * @copyright 2025 mrveiss
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { defineComponent, nextTick } from 'vue'
import { mount } from '@vue/test-utils'
import {
  useToast,
  provideToast,
  TOAST_INJECT_KEY,
  TOAST_DURATIONS,
  MAX_TOASTS,
  type ToastType,
} from '../useToast'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Mount a minimal component and call setup(); returns whatever setup returns. */
function withSetup<T>(setup: () => T): T {
  let result!: T
  const Wrapper = defineComponent({
    setup() {
      result = setup()
      return {}
    },
    template: '<div />',
  })
  mount(Wrapper, {
    global: { stubs: { Teleport: true } },
  })
  return result
}

/** Reset the module-level singleton between tests (must run inside setup context). */
function resetSingleton() {
  withSetup(() => {
    const { clearAllToasts } = useToast()
    clearAllToasts()
  })
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('useToast — acceptance criteria #3283', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    resetSingleton()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  // -------------------------------------------------------------------------
  // 1. Singleton state is shared across calls
  // -------------------------------------------------------------------------
  describe('module-level singleton', () => {
    it('returns the same toasts ref from two independent useToast() calls', () => {
      const a = withSetup(() => useToast())
      const b = withSetup(() => useToast())
      a.showToast('hello', 'info', 0)
      expect(b.toasts.value).toHaveLength(1)
      expect(b.toasts.value[0].message).toBe('hello')
    })
  })

  // -------------------------------------------------------------------------
  // 2. provide / inject
  // -------------------------------------------------------------------------
  describe('provide/inject', () => {
    it('useToast() inside a child component receives the provided instance', () => {
      let childApi: ReturnType<typeof useToast> | undefined

      const Child = defineComponent({
        setup() {
          childApi = useToast()
          return {}
        },
        template: '<span />',
      })

      const Parent = defineComponent({
        setup() {
          provideToast()
          return {}
        },
        components: { Child },
        template: '<Child />',
      })

      mount(Parent, { global: { stubs: { Teleport: true } } })

      const parentApi = withSetup(() => useToast())
      parentApi.showToast('via inject', 'success', 0)

      expect(childApi).toBeDefined()
      expect(childApi!.toasts.value.some((t) => t.message === 'via inject')).toBe(true)
    })

    it('TOAST_INJECT_KEY is a Symbol', () => {
      expect(typeof TOAST_INJECT_KEY).toBe('symbol')
    })
  })

  // -------------------------------------------------------------------------
  // 3. Toast variants
  // -------------------------------------------------------------------------
  describe('toast variants', () => {
    const types: ToastType[] = ['success', 'error', 'warning', 'info']

    types.forEach((type) => {
      it(`showToast stores type="${type}"`, () => {
        const { showToast, toasts } = withSetup(() => useToast())
        showToast(`${type} message`, type, 0)
        const last = toasts.value[toasts.value.length - 1]
        expect(last.type).toBe(type)
        expect(last.message).toBe(`${type} message`)
      })
    })
  })

  // -------------------------------------------------------------------------
  // 4. Default durations
  // -------------------------------------------------------------------------
  describe('default durations', () => {
    it('success default duration is 4000 ms', () => {
      expect(TOAST_DURATIONS.success).toBe(4000)
    })

    it('info default duration is 4000 ms', () => {
      expect(TOAST_DURATIONS.info).toBe(4000)
    })

    it('warning default duration is 6000 ms', () => {
      expect(TOAST_DURATIONS.warning).toBe(6000)
    })

    it('error default duration is 0 (persistent)', () => {
      expect(TOAST_DURATIONS.error).toBe(0)
    })

    it('success toast auto-dismisses after 4 seconds', async () => {
      const { showToast, toasts } = withSetup(() => useToast())
      showToast('auto-dismiss me', 'success')
      expect(toasts.value.some((t) => t.message === 'auto-dismiss me')).toBe(true)
      vi.advanceTimersByTime(4000)
      await nextTick()
      expect(toasts.value.some((t) => t.message === 'auto-dismiss me')).toBe(false)
    })

    it('error toast does NOT auto-dismiss', async () => {
      const { showToast, toasts } = withSetup(() => useToast())
      showToast('persistent error', 'error')
      vi.advanceTimersByTime(30000)
      await nextTick()
      expect(toasts.value.some((t) => t.message === 'persistent error')).toBe(true)
    })
  })

  // -------------------------------------------------------------------------
  // 5. Maximum 3 toasts stacked with Tier C eviction protection (MVA-347)
  // -------------------------------------------------------------------------
  describe('maximum stack size and Tier C eviction protection', () => {
    it('MAX_TOASTS constant is 3', () => {
      expect(MAX_TOASTS).toBe(3)
    })

    it('does not exceed 3 toasts; oldest Tier A/B is evicted when a 4th is added', () => {
      const { showToast, toasts } = withSetup(() => useToast())
      showToast('toast 1', 'info', 0)
      showToast('toast 2', 'success', 0)
      showToast('toast 3', 'warning', 0)
      expect(toasts.value).toHaveLength(3)
      expect(toasts.value[0].message).toBe('toast 1')

      // Add a 4th — toast 1 (oldest, Tier A/B) should be evicted
      showToast('toast 4', 'info', 0)
      expect(toasts.value).toHaveLength(3)
      expect(toasts.value.some((t) => t.message === 'toast 1')).toBe(false)
      expect(toasts.value[toasts.value.length - 1].message).toBe('toast 4')
    })

    it('evicts oldest non-Tier-C when stack has mixed Tier A/B and Tier C toasts', () => {
      const { showToast, toasts } = withSetup(() => useToast())
      // Tier C (persistent error) first
      showToast('error 1', 'error')
      // Then two Tier A/B
      showToast('info 1', 'info', 0)
      showToast('info 2', 'info', 0)
      expect(toasts.value).toHaveLength(3)

      // 4th toast — should evict 'info 1' (oldest non-Tier-C), NOT 'error 1'
      showToast('warning 1', 'warning', 0)
      expect(toasts.value).toHaveLength(3)
      expect(toasts.value.some((t) => t.message === 'error 1')).toBe(true)
      expect(toasts.value.some((t) => t.message === 'info 1')).toBe(false)
      expect(toasts.value.some((t) => t.message === 'warning 1')).toBe(true)
    })

    it('queues a new toast (not shown) when all 3 visible slots are Tier C', () => {
      const { showToast, toasts } = withSetup(() => useToast())
      showToast('error 1', 'error')
      showToast('error 2', 'error')
      showToast('error 3', 'error')
      expect(toasts.value).toHaveLength(3)

      // 4th toast cannot evict any Tier C — should be queued, not visible
      showToast('info queued', 'info', 0)
      expect(toasts.value).toHaveLength(3)
      expect(toasts.value.some((t) => t.message === 'info queued')).toBe(false)
    })

    it('promotes queued toast when user dismisses a Tier C', async () => {
      const { showToast, removeToast, toasts } = withSetup(() => useToast())
      const id1 = showToast('error 1', 'error')
      showToast('error 2', 'error')
      showToast('error 3', 'error')

      // Queue a non-Tier-C toast
      showToast('info queued', 'info', 0)
      expect(toasts.value.some((t) => t.message === 'info queued')).toBe(false)

      // Dismiss one Tier C — queued toast should become visible
      removeToast(id1)
      await nextTick()
      expect(toasts.value).toHaveLength(3)
      expect(toasts.value.some((t) => t.message === 'info queued')).toBe(true)
    })

    it('clearAllToasts also clears the pending queue', async () => {
      const { showToast, clearAllToasts, removeToast, toasts } = withSetup(() => useToast())
      const id1 = showToast('error 1', 'error')
      showToast('error 2', 'error')
      showToast('error 3', 'error')

      // Queue a toast
      showToast('queued info', 'info', 0)

      // Clear everything — pending queue must also be cleared
      clearAllToasts()
      expect(toasts.value).toHaveLength(0)

      // Simulate dismissing (no-op after clear) — queued toast must NOT reappear
      removeToast(id1)
      await nextTick()
      expect(toasts.value).toHaveLength(0)
    })

    it('error toast with non-zero duration is NOT Tier C and can be evicted', () => {
      const { showToast, toasts } = withSetup(() => useToast())
      // Custom-duration error (Tier A/B, not Tier C)
      showToast('timed error', 'error', 2000)
      showToast('info 1', 'info', 0)
      showToast('info 2', 'info', 0)
      expect(toasts.value).toHaveLength(3)

      // 4th toast: 'timed error' is the oldest and NOT Tier C — evict it
      showToast('info 3', 'info', 0)
      expect(toasts.value).toHaveLength(3)
      expect(toasts.value.some((t) => t.message === 'timed error')).toBe(false)
      expect(toasts.value.some((t) => t.message === 'info 3')).toBe(true)
    })
  })

  // -------------------------------------------------------------------------
  // 6. Manual dismiss
  // -------------------------------------------------------------------------
  describe('manual dismiss', () => {
    it('removeToast removes a toast by id', () => {
      const { showToast, removeToast, toasts } = withSetup(() => useToast())
      const id = showToast('remove me', 'warning', 0)
      expect(toasts.value.some((t) => t.id === id)).toBe(true)
      removeToast(id)
      expect(toasts.value.some((t) => t.id === id)).toBe(false)
    })

    it('removeToast with unknown id is a no-op', () => {
      const { showToast, removeToast, toasts } = withSetup(() => useToast())
      showToast('keep me', 'info', 0)
      const before = toasts.value.length
      removeToast(999999)
      expect(toasts.value.length).toBe(before)
    })

    it('clearAllToasts removes every toast', () => {
      const { showToast, clearAllToasts, toasts } = withSetup(() => useToast())
      showToast('a', 'info', 0)
      showToast('b', 'success', 0)
      clearAllToasts()
      expect(toasts.value).toHaveLength(0)
    })
  })

  // -------------------------------------------------------------------------
  // 7. Custom duration override
  // -------------------------------------------------------------------------
  describe('custom duration', () => {
    it('accepts a custom duration that overrides the default', async () => {
      const { showToast, toasts } = withSetup(() => useToast())
      showToast('custom', 'error', 2000)  // override persistent default
      vi.advanceTimersByTime(2000)
      await nextTick()
      expect(toasts.value.some((t) => t.message === 'custom')).toBe(false)
    })

    it('duration 0 keeps toast alive indefinitely', async () => {
      const { showToast, toasts } = withSetup(() => useToast())
      showToast('forever', 'success', 0)
      vi.advanceTimersByTime(60000)
      await nextTick()
      expect(toasts.value.some((t) => t.message === 'forever')).toBe(true)
    })
  })

  // -------------------------------------------------------------------------
  // 8. showToast return value
  // -------------------------------------------------------------------------
  describe('showToast return value', () => {
    it('returns an incrementing numeric id', () => {
      const { showToast } = withSetup(() => useToast())
      const id1 = showToast('first', 'info', 0)
      const id2 = showToast('second', 'info', 0)
      expect(typeof id1).toBe('number')
      expect(id2).toBeGreaterThan(id1)
    })
  })
})
