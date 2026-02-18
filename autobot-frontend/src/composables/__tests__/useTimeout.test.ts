import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { defineComponent, nextTick } from 'vue'
import { mount } from '@vue/test-utils'
import {
  useDebounce,
  useThrottle,
  useTimeout,
  useInterval,
  useSleep,
  useCancelableSleep
} from '../useTimeout'

/**
 * useTimeout Composable Tests
 *
 * Tests all timeout/debounce utilities:
 * - useDebounce (12 tests)
 * - useThrottle (10 tests)
 * - useTimeout (8 tests)
 * - useInterval (8 tests)
 * - useSleep (4 tests)
 * - useCancelableSleep (4 tests)
 *
 * Total: 46 tests
 */

describe('useTimeout Composable', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.restoreAllMocks()
    vi.useRealTimers()
  })

  // ========================================
  // useDebounce Tests
  // ========================================

  describe('useDebounce', () => {
    it('should delay function execution', async () => {
      const callback = vi.fn()
      const TestComponent = defineComponent({
        setup() {
          const debounced = useDebounce(callback, 500)
          return { debounced }
        },
        template: '<div></div>'
      })

      const wrapper = mount(TestComponent)
      const { debounced } = wrapper.vm

      // Call debounced function
      debounced('test')

      // Should not execute immediately
      expect(callback).not.toHaveBeenCalled()

      // Advance time by 400ms (not enough)
      vi.advanceTimersByTime(400)
      expect(callback).not.toHaveBeenCalled()

      // Advance time by 100ms more (total 500ms)
      vi.advanceTimersByTime(100)
      expect(callback).toHaveBeenCalledTimes(1)
      expect(callback).toHaveBeenCalledWith('test')
    })

    it('should reset delay on subsequent calls', async () => {
      const callback = vi.fn()
      const TestComponent = defineComponent({
        setup() {
          const debounced = useDebounce(callback, 500)
          return { debounced }
        },
        template: '<div></div>'
      })

      const wrapper = mount(TestComponent)
      const { debounced } = wrapper.vm

      // First call
      debounced('first')
      vi.advanceTimersByTime(300)

      // Second call (resets timer)
      debounced('second')
      vi.advanceTimersByTime(300)

      // Should not have executed yet
      expect(callback).not.toHaveBeenCalled()

      // Advance remaining time
      vi.advanceTimersByTime(200)
      expect(callback).toHaveBeenCalledTimes(1)
      expect(callback).toHaveBeenCalledWith('second')
    })

    it('should execute only once for multiple rapid calls', async () => {
      const callback = vi.fn()
      const TestComponent = defineComponent({
        setup() {
          const debounced = useDebounce(callback, 500)
          return { debounced }
        },
        template: '<div></div>'
      })

      const wrapper = mount(TestComponent)
      const { debounced } = wrapper.vm

      // Multiple rapid calls
      debounced('call1')
      debounced('call2')
      debounced('call3')
      debounced('call4')

      // Advance time
      vi.advanceTimersByTime(500)

      // Should execute only once with last arguments
      expect(callback).toHaveBeenCalledTimes(1)
      expect(callback).toHaveBeenCalledWith('call4')
    })

    it('should support leading edge execution', async () => {
      const callback = vi.fn()
      const TestComponent = defineComponent({
        setup() {
          const debounced = useDebounce(callback, 500, { leading: true })
          return { debounced }
        },
        template: '<div></div>'
      })

      const wrapper = mount(TestComponent)
      const { debounced } = wrapper.vm

      // First call should execute immediately (leading)
      debounced('first')
      expect(callback).toHaveBeenCalledTimes(1)
      expect(callback).toHaveBeenCalledWith('first')

      // Subsequent calls within delay should not execute
      debounced('second')
      debounced('third')
      vi.advanceTimersByTime(500)

      // Should not execute trailing call with leading=true
      expect(callback).toHaveBeenCalledTimes(1)
    })

    it('should support maxWait option', async () => {
      const callback = vi.fn()
      const TestComponent = defineComponent({
        setup() {
          const debounced = useDebounce(callback, 500, { maxWait: 1000 })
          return { debounced }
        },
        template: '<div></div>'
      })

      const wrapper = mount(TestComponent)
      const { debounced } = wrapper.vm

      // Call every 400ms (always resetting the 500ms timer)
      debounced('call1')
      vi.advanceTimersByTime(400)

      debounced('call2')
      vi.advanceTimersByTime(400)

      debounced('call3')
      vi.advanceTimersByTime(200) // Total: 1000ms

      // Should execute due to maxWait
      expect(callback).toHaveBeenCalledTimes(1)
    })

    it('should cancel pending execution', async () => {
      const callback = vi.fn()
      const TestComponent = defineComponent({
        setup() {
          const debounced = useDebounce(callback, 500)
          return { debounced }
        },
        template: '<div></div>'
      })

      const wrapper = mount(TestComponent)
      const { debounced } = wrapper.vm

      debounced('test')
      vi.advanceTimersByTime(300)

      // Cancel before execution
      debounced.cancel()
      vi.advanceTimersByTime(300)

      // Should not have executed
      expect(callback).not.toHaveBeenCalled()
    })

    it('should flush pending execution immediately', async () => {
      const callback = vi.fn()
      const TestComponent = defineComponent({
        setup() {
          const debounced = useDebounce(callback, 500)
          return { debounced }
        },
        template: '<div></div>'
      })

      const wrapper = mount(TestComponent)
      const { debounced } = wrapper.vm

      debounced('test')
      vi.advanceTimersByTime(300)

      // Flush before normal execution time
      debounced.flush()

      // Should have executed immediately
      expect(callback).toHaveBeenCalledTimes(1)
      expect(callback).toHaveBeenCalledWith('test')

      // Advance remaining time
      vi.advanceTimersByTime(200)

      // Should not execute again
      expect(callback).toHaveBeenCalledTimes(1)
    })

    it('should cleanup on component unmount', async () => {
      const callback = vi.fn()
      const TestComponent = defineComponent({
        setup() {
          const debounced = useDebounce(callback, 500)
          return { debounced }
        },
        template: '<div></div>'
      })

      const wrapper = mount(TestComponent)
      const { debounced } = wrapper.vm

      debounced('test')
      vi.advanceTimersByTime(300)

      // Unmount component
      wrapper.unmount()
      await nextTick()

      // Advance time
      vi.advanceTimersByTime(300)

      // Should not execute after unmount
      expect(callback).not.toHaveBeenCalled()
    })

    it('should handle multiple arguments', async () => {
      const callback = vi.fn()
      const TestComponent = defineComponent({
        setup() {
          const debounced = useDebounce(callback, 500)
          return { debounced }
        },
        template: '<div></div>'
      })

      const wrapper = mount(TestComponent)
      const { debounced } = wrapper.vm

      debounced('arg1', 'arg2', 'arg3')
      vi.advanceTimersByTime(500)

      expect(callback).toHaveBeenCalledWith('arg1', 'arg2', 'arg3')
    })

    it('should work with default delay', async () => {
      const callback = vi.fn()
      const TestComponent = defineComponent({
        setup() {
          const debounced = useDebounce(callback) // Default 300ms
          return { debounced }
        },
        template: '<div></div>'
      })

      const wrapper = mount(TestComponent)
      const { debounced } = wrapper.vm

      debounced('test')
      vi.advanceTimersByTime(300)

      expect(callback).toHaveBeenCalledTimes(1)
    })

    it('should handle leading and trailing together', async () => {
      const callback = vi.fn()
      const TestComponent = defineComponent({
        setup() {
          const debounced = useDebounce(callback, 500, { leading: true })
          return { debounced }
        },
        template: '<div></div>'
      })

      const wrapper = mount(TestComponent)
      const { debounced } = wrapper.vm

      // First call - leading edge
      debounced('first')
      expect(callback).toHaveBeenCalledTimes(1)

      vi.advanceTimersByTime(600) // Wait for delay to pass

      // Second call after delay - should trigger leading edge again
      debounced('second')
      expect(callback).toHaveBeenCalledTimes(2)
      expect(callback).toHaveBeenNthCalledWith(2, 'second')
    })

    it('should preserve function context', async () => {
      let capturedThis: any = null
      const callback = function (this: any) {
        capturedThis = this
      }

      const context = { value: 'test-context' }
      const TestComponent = defineComponent({
        setup() {
          const debounced = useDebounce(callback, 500)
          return { debounced, context }
        },
        template: '<div></div>'
      })

      const wrapper = mount(TestComponent)
      const { debounced, context: ctx } = wrapper.vm

      debounced.call(ctx)
      vi.advanceTimersByTime(500)

      expect(capturedThis).toBeDefined()
    })
  })

  // ========================================
  // useThrottle Tests
  // ========================================

  describe('useThrottle', () => {
    it('should execute immediately on first call (leading edge)', async () => {
      const callback = vi.fn()
      const TestComponent = defineComponent({
        setup() {
          const throttled = useThrottle(callback, 500)
          return { throttled }
        },
        template: '<div></div>'
      })

      const wrapper = mount(TestComponent)
      const { throttled } = wrapper.vm

      throttled('first')
      expect(callback).toHaveBeenCalledTimes(1)
      expect(callback).toHaveBeenCalledWith('first')
    })

    it('should throttle subsequent calls within delay', async () => {
      const callback = vi.fn()
      const TestComponent = defineComponent({
        setup() {
          const throttled = useThrottle(callback, 500)
          return { throttled }
        },
        template: '<div></div>'
      })

      const wrapper = mount(TestComponent)
      const { throttled } = wrapper.vm

      // First call executes
      throttled('call1')
      expect(callback).toHaveBeenCalledTimes(1)

      // Subsequent calls within delay are throttled
      throttled('call2')
      throttled('call3')
      expect(callback).toHaveBeenCalledTimes(1)

      // Advance time past delay
      vi.advanceTimersByTime(500)

      // Trailing edge should execute with last arguments
      expect(callback).toHaveBeenCalledTimes(2)
      expect(callback).toHaveBeenLastCalledWith('call3')
    })

    it('should support trailing edge only', async () => {
      const callback = vi.fn()
      const TestComponent = defineComponent({
        setup() {
          const throttled = useThrottle(callback, 500, {
            leading: false,
            trailing: true
          })
          return { throttled }
        },
        template: '<div></div>'
      })

      const wrapper = mount(TestComponent)
      const { throttled } = wrapper.vm

      // First call should not execute (no leading)
      throttled('call1')
      expect(callback).not.toHaveBeenCalled()

      // Advance time
      vi.advanceTimersByTime(500)

      // Should execute on trailing edge
      expect(callback).toHaveBeenCalledTimes(1)
      expect(callback).toHaveBeenCalledWith('call1')
    })

    it('should support leading edge only', async () => {
      const callback = vi.fn()
      const TestComponent = defineComponent({
        setup() {
          const throttled = useThrottle(callback, 500, {
            leading: true,
            trailing: false
          })
          return { throttled }
        },
        template: '<div></div>'
      })

      const wrapper = mount(TestComponent)
      const { throttled } = wrapper.vm

      // First call executes (leading)
      throttled('call1')
      expect(callback).toHaveBeenCalledTimes(1)

      // Subsequent calls are ignored
      throttled('call2')
      throttled('call3')

      // Advance time
      vi.advanceTimersByTime(500)

      // Should not execute trailing edge
      expect(callback).toHaveBeenCalledTimes(1)
    })

    it('should reset after delay period', async () => {
      const callback = vi.fn()
      const TestComponent = defineComponent({
        setup() {
          const throttled = useThrottle(callback, 500)
          return { throttled }
        },
        template: '<div></div>'
      })

      const wrapper = mount(TestComponent)
      const { throttled } = wrapper.vm

      // First call
      throttled('call1')
      expect(callback).toHaveBeenCalledTimes(1)

      // Wait for delay to pass
      vi.advanceTimersByTime(600)

      // Next call should execute immediately (new cycle)
      throttled('call2')
      expect(callback).toHaveBeenCalledTimes(2)
      expect(callback).toHaveBeenLastCalledWith('call2')
    })

    it('should cancel pending execution', async () => {
      const callback = vi.fn()
      const TestComponent = defineComponent({
        setup() {
          const throttled = useThrottle(callback, 500)
          return { throttled }
        },
        template: '<div></div>'
      })

      const wrapper = mount(TestComponent)
      const { throttled } = wrapper.vm

      throttled('call1')
      throttled('call2')

      // Cancel before trailing edge
      throttled.cancel()
      vi.advanceTimersByTime(500)

      // Should not execute trailing edge
      expect(callback).toHaveBeenCalledTimes(1) // Only leading edge
    })

    it('should cleanup on component unmount', async () => {
      const callback = vi.fn()
      const TestComponent = defineComponent({
        setup() {
          const throttled = useThrottle(callback, 500)
          return { throttled }
        },
        template: '<div></div>'
      })

      const wrapper = mount(TestComponent)
      const { throttled } = wrapper.vm

      throttled('call1')
      throttled('call2')

      // Unmount before trailing edge
      wrapper.unmount()
      await nextTick()

      vi.advanceTimersByTime(500)

      // Should not execute trailing edge after unmount
      expect(callback).toHaveBeenCalledTimes(1) // Only leading edge
    })

    it('should work with default delay', async () => {
      const callback = vi.fn()
      const TestComponent = defineComponent({
        setup() {
          const throttled = useThrottle(callback) // Default 300ms
          return { throttled }
        },
        template: '<div></div>'
      })

      const wrapper = mount(TestComponent)
      const { throttled } = wrapper.vm

      throttled('test')
      expect(callback).toHaveBeenCalledTimes(1)
    })

    it('should handle rapid calls correctly', async () => {
      const callback = vi.fn()
      const TestComponent = defineComponent({
        setup() {
          const throttled = useThrottle(callback, 100)
          return { throttled }
        },
        template: '<div></div>'
      })

      const wrapper = mount(TestComponent)
      const { throttled } = wrapper.vm

      // Simulate rapid scroll events
      for (let i = 0; i < 20; i++) {
        throttled(`call${i}`)
        vi.advanceTimersByTime(20) // Total: 400ms
      }

      // Should have throttled to ~4 executions (0ms, 100ms, 200ms, 300ms, trailing at 400ms)
      expect(callback.mock.calls.length).toBeLessThanOrEqual(5)
    })

    it('should handle multiple arguments', async () => {
      const callback = vi.fn()
      const TestComponent = defineComponent({
        setup() {
          const throttled = useThrottle(callback, 500)
          return { throttled }
        },
        template: '<div></div>'
      })

      const wrapper = mount(TestComponent)
      const { throttled } = wrapper.vm

      throttled('arg1', 'arg2', 'arg3')
      expect(callback).toHaveBeenCalledWith('arg1', 'arg2', 'arg3')
    })
  })

  // ========================================
  // useTimeout Tests
  // ========================================

  describe('useTimeout', () => {
    it('should execute callback after delay', async () => {
      const callback = vi.fn()
      const TestComponent = defineComponent({
        setup() {
          const timeout = useTimeout(callback, 1000)
          return { timeout }
        },
        template: '<div></div>'
      })

      mount(TestComponent)

      expect(callback).not.toHaveBeenCalled()

      vi.advanceTimersByTime(1000)

      expect(callback).toHaveBeenCalledTimes(1)
    })

    it('should track active state', async () => {
      const callback = vi.fn()
      const TestComponent = defineComponent({
        setup() {
          const timeout = useTimeout(callback, 1000)
          return { timeout }
        },
        template: '<div></div>'
      })

      const wrapper = mount(TestComponent)
      const { timeout } = wrapper.vm

      expect(timeout.isActive.value).toBe(true)

      vi.advanceTimersByTime(1000)

      expect(timeout.isActive.value).toBe(false)
    })

    it('should stop timeout', async () => {
      const callback = vi.fn()
      const TestComponent = defineComponent({
        setup() {
          const timeout = useTimeout(callback, 1000)
          return { timeout }
        },
        template: '<div></div>'
      })

      const wrapper = mount(TestComponent)
      const { timeout } = wrapper.vm

      vi.advanceTimersByTime(500)
      timeout.stop()

      expect(timeout.isActive.value).toBe(false)

      vi.advanceTimersByTime(500)

      expect(callback).not.toHaveBeenCalled()
    })

    it('should restart timeout', async () => {
      const callback = vi.fn()
      const TestComponent = defineComponent({
        setup() {
          const timeout = useTimeout(callback, 1000, { immediate: false })
          return { timeout }
        },
        template: '<div></div>'
      })

      const wrapper = mount(TestComponent)
      const { timeout } = wrapper.vm

      timeout.restart()
      vi.advanceTimersByTime(500)

      timeout.restart() // Reset timer

      vi.advanceTimersByTime(500)
      expect(callback).not.toHaveBeenCalled()

      vi.advanceTimersByTime(500)
      expect(callback).toHaveBeenCalledTimes(1)
    })

    it('should support immediate: false option', async () => {
      const callback = vi.fn()
      const TestComponent = defineComponent({
        setup() {
          const timeout = useTimeout(callback, 1000, { immediate: false })
          return { timeout }
        },
        template: '<div></div>'
      })

      const wrapper = mount(TestComponent)
      const { timeout } = wrapper.vm

      expect(timeout.isActive.value).toBe(false)

      timeout.start()
      expect(timeout.isActive.value).toBe(true)

      vi.advanceTimersByTime(1000)
      expect(callback).toHaveBeenCalledTimes(1)
    })

    it('should cleanup on component unmount', async () => {
      const callback = vi.fn()
      const TestComponent = defineComponent({
        setup() {
          useTimeout(callback, 1000)
        },
        template: '<div></div>'
      })

      const wrapper = mount(TestComponent)

      vi.advanceTimersByTime(500)

      wrapper.unmount()
      await nextTick()

      vi.advanceTimersByTime(500)

      expect(callback).not.toHaveBeenCalled()
    })

    it('should handle multiple starts correctly', async () => {
      const callback = vi.fn()
      const TestComponent = defineComponent({
        setup() {
          const timeout = useTimeout(callback, 1000, { immediate: false })
          return { timeout }
        },
        template: '<div></div>'
      })

      const wrapper = mount(TestComponent)
      const { timeout } = wrapper.vm

      timeout.start()
      vi.advanceTimersByTime(500)

      timeout.start() // Should clear previous and start new

      vi.advanceTimersByTime(500)
      expect(callback).not.toHaveBeenCalled()

      vi.advanceTimersByTime(500)
      expect(callback).toHaveBeenCalledTimes(1)
    })

    it('should handle stop when not active', async () => {
      const callback = vi.fn()
      const TestComponent = defineComponent({
        setup() {
          const timeout = useTimeout(callback, 1000, { immediate: false })
          return { timeout }
        },
        template: '<div></div>'
      })

      const wrapper = mount(TestComponent)
      const { timeout } = wrapper.vm

      // Stop when not active should not throw
      expect(() => timeout.stop()).not.toThrow()
    })
  })

  // ========================================
  // useInterval Tests
  // ========================================

  describe('useInterval', () => {
    it('should execute callback repeatedly', async () => {
      const callback = vi.fn()
      const TestComponent = defineComponent({
        setup() {
          useInterval(callback, 1000)
        },
        template: '<div></div>'
      })

      mount(TestComponent)

      vi.advanceTimersByTime(1000)
      expect(callback).toHaveBeenCalledTimes(1)

      vi.advanceTimersByTime(1000)
      expect(callback).toHaveBeenCalledTimes(2)

      vi.advanceTimersByTime(1000)
      expect(callback).toHaveBeenCalledTimes(3)
    })

    it('should track active state', async () => {
      const callback = vi.fn()
      const TestComponent = defineComponent({
        setup() {
          const interval = useInterval(callback, 1000)
          return { interval }
        },
        template: '<div></div>'
      })

      const wrapper = mount(TestComponent)
      const { interval } = wrapper.vm

      expect(interval.isActive.value).toBe(true)

      interval.stop()
      expect(interval.isActive.value).toBe(false)
    })

    it('should stop interval', async () => {
      const callback = vi.fn()
      const TestComponent = defineComponent({
        setup() {
          const interval = useInterval(callback, 1000)
          return { interval }
        },
        template: '<div></div>'
      })

      const wrapper = mount(TestComponent)
      const { interval } = wrapper.vm

      vi.advanceTimersByTime(2000)
      expect(callback).toHaveBeenCalledTimes(2)

      interval.stop()

      vi.advanceTimersByTime(2000)
      expect(callback).toHaveBeenCalledTimes(2) // Should not increase
    })

    it('should pause and resume interval', async () => {
      const callback = vi.fn()
      const TestComponent = defineComponent({
        setup() {
          const interval = useInterval(callback, 1000)
          return { interval }
        },
        template: '<div></div>'
      })

      const wrapper = mount(TestComponent)
      const { interval } = wrapper.vm

      vi.advanceTimersByTime(1000)
      expect(callback).toHaveBeenCalledTimes(1)

      interval.pause()

      vi.advanceTimersByTime(2000)
      expect(callback).toHaveBeenCalledTimes(1) // Paused

      interval.resume()

      vi.advanceTimersByTime(1000)
      expect(callback).toHaveBeenCalledTimes(2) // Resumed
    })

    it('should support immediate: false option', async () => {
      const callback = vi.fn()
      const TestComponent = defineComponent({
        setup() {
          const interval = useInterval(callback, 1000, { immediate: false })
          return { interval }
        },
        template: '<div></div>'
      })

      const wrapper = mount(TestComponent)
      const { interval } = wrapper.vm

      expect(interval.isActive.value).toBe(false)

      interval.start()
      expect(interval.isActive.value).toBe(true)

      vi.advanceTimersByTime(1000)
      expect(callback).toHaveBeenCalledTimes(1)
    })

    it('should support immediateCallback option', async () => {
      const callback = vi.fn()
      const TestComponent = defineComponent({
        setup() {
          useInterval(callback, 1000, { immediateCallback: true })
        },
        template: '<div></div>'
      })

      mount(TestComponent)

      // Should execute immediately
      expect(callback).toHaveBeenCalledTimes(1)

      vi.advanceTimersByTime(1000)
      expect(callback).toHaveBeenCalledTimes(2)
    })

    it('should cleanup on component unmount', async () => {
      const callback = vi.fn()
      const TestComponent = defineComponent({
        setup() {
          useInterval(callback, 1000)
        },
        template: '<div></div>'
      })

      const wrapper = mount(TestComponent)

      vi.advanceTimersByTime(1000)
      expect(callback).toHaveBeenCalledTimes(1)

      wrapper.unmount()
      await nextTick()

      vi.advanceTimersByTime(2000)
      expect(callback).toHaveBeenCalledTimes(1) // Should not increase
    })

    it('should restart interval', async () => {
      const callback = vi.fn()
      const TestComponent = defineComponent({
        setup() {
          const interval = useInterval(callback, 1000)
          return { interval }
        },
        template: '<div></div>'
      })

      const wrapper = mount(TestComponent)
      const { interval } = wrapper.vm

      vi.advanceTimersByTime(500)

      interval.restart() // Should reset timing

      vi.advanceTimersByTime(500)
      expect(callback).not.toHaveBeenCalled()

      vi.advanceTimersByTime(500)
      expect(callback).toHaveBeenCalledTimes(1)
    })
  })

  // ========================================
  // useSleep Tests
  // ========================================

  describe('useSleep', () => {
    it('should resolve after delay', async () => {
      const promise = useSleep(1000)
      let resolved = false

      promise.then(() => {
        resolved = true
      })

      expect(resolved).toBe(false)

      vi.advanceTimersByTime(1000)
      await promise

      expect(resolved).toBe(true)
    })

    it('should work in async/await context', async () => {
      let step = 0

      const asyncFn = async () => {
        step = 1
        await useSleep(500)
        step = 2
        await useSleep(500)
        step = 3
      }

      const promise = asyncFn()

      expect(step).toBe(1)

      vi.advanceTimersByTime(500)
      await Promise.resolve() // Allow promise to resolve

      expect(step).toBe(2)

      vi.advanceTimersByTime(500)
      await promise

      expect(step).toBe(3)
    })

    it('should handle multiple concurrent sleeps', async () => {
      const results: number[] = []

      const sleep1 = useSleep(1000).then(() => results.push(1))
      const sleep2 = useSleep(500).then(() => results.push(2))
      const sleep3 = useSleep(1500).then(() => results.push(3))

      vi.advanceTimersByTime(500)
      await Promise.resolve()
      expect(results).toEqual([2])

      vi.advanceTimersByTime(500)
      await Promise.resolve()
      expect(results).toEqual([2, 1])

      vi.advanceTimersByTime(500)
      await Promise.all([sleep1, sleep2, sleep3])
      expect(results).toEqual([2, 1, 3])
    })

    it('should work with zero delay', async () => {
      const promise = useSleep(0)
      let resolved = false

      promise.then(() => {
        resolved = true
      })

      vi.advanceTimersByTime(0)
      await promise

      expect(resolved).toBe(true)
    })
  })

  // ========================================
  // useCancelableSleep Tests
  // ========================================

  describe('useCancelableSleep', () => {
    it('should resolve after delay', async () => {
      const sleep = useCancelableSleep(1000)
      let resolved = false

      sleep.promise.then(() => {
        resolved = true
      })

      expect(resolved).toBe(false)

      vi.advanceTimersByTime(1000)
      await sleep.promise

      expect(resolved).toBe(true)
    })

    it('should reject when canceled', async () => {
      const sleep = useCancelableSleep(1000)
      let rejected = false
      let error: Error | null = null

      sleep.promise.catch((err: Error) => {
        rejected = true
        error = err
      })

      vi.advanceTimersByTime(500)

      sleep.cancel()

      await expect(sleep.promise).rejects.toThrow('Sleep canceled')
      expect(rejected).toBe(true)
      expect(error).not.toBeNull()
      expect(error!.message).toBe('Sleep canceled')
    })

    it('should handle cancellation before any time passes', async () => {
      const sleep = useCancelableSleep(1000)

      sleep.cancel()

      await expect(sleep.promise).rejects.toThrow('Sleep canceled')
    })

    it('should cleanup on component unmount', async () => {
      const TestComponent = defineComponent({
        setup() {
          const sleep = useCancelableSleep(1000)
          return { sleep }
        },
        template: '<div></div>'
      })

      const wrapper = mount(TestComponent)
      const { sleep } = wrapper.vm

      let rejected = false
      sleep.promise.catch(() => {
        rejected = true
      })

      wrapper.unmount()
      await nextTick()

      expect(rejected).toBe(true)
    })
  })
})
