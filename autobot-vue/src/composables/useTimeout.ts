/**
 * Timeout & Debounce Composable
 *
 * Centralized timeout, interval, debounce, and throttle utilities to eliminate duplicate
 * timing logic across components. Provides automatic cleanup to prevent memory leaks.
 *
 * Features:
 * - Debounced function execution with automatic cleanup
 * - Throttled function execution
 * - Managed setTimeout with auto-cleanup
 * - Managed setInterval with auto-cleanup
 * - Promise-based sleep/delay utilities
 * - TypeScript type safety
 * - Automatic cleanup on component unmount
 *
 * Usage:
 * ```typescript
 * import { useDebounce, useThrottle, useTimeout, useSleep } from '@/composables/useTimeout'
 *
 * // Debounce search input
 * const debouncedSearch = useDebounce((query: string) => {
 *   performSearch(query)
 * }, 500)
 *
 * // Throttle scroll handler
 * const throttledScroll = useThrottle(() => {
 *   handleScroll()
 * }, 200)
 *
 * // Auto-cleanup timeout
 * const { start, stop, isActive } = useTimeout(() => {
 *   console.log('Executed after delay')
 * }, 1000)
 *
 * // Promise-based delay
 * await useSleep(2000) // Sleep for 2 seconds
 * ```
 */

import { ref, onUnmounted, type Ref } from 'vue'
import { createLogger } from '@/utils/debugUtils'

// Create scoped logger for useTimeout
const logger = createLogger('useTimeout')

// ========================================
// Types & Interfaces
// ========================================

export interface UseTimeoutReturn {
  /**
   * Start the timeout
   */
  start: () => void

  /**
   * Stop/cancel the timeout
   */
  stop: () => void

  /**
   * Whether timeout is currently active (pending)
   */
  isActive: Readonly<Ref<boolean>>

  /**
   * Restart the timeout (stop + start)
   */
  restart: () => void
}

export interface UseIntervalReturn {
  /**
   * Start the interval
   */
  start: () => void

  /**
   * Stop/cancel the interval
   */
  stop: () => void

  /**
   * Whether interval is currently active (running)
   */
  isActive: Readonly<Ref<boolean>>

  /**
   * Restart the interval (stop + start)
   */
  restart: () => void

  /**
   * Pause the interval (can be resumed with start)
   */
  pause: () => void

  /**
   * Resume the interval
   */
  resume: () => void
}

export interface DebouncedFunction<T extends (...args: any[]) => any> {
  /**
   * The debounced function
   */
  (...args: Parameters<T>): void

  /**
   * Cancel any pending execution
   */
  cancel: () => void

  /**
   * Execute immediately and cancel any pending execution
   */
  flush: () => void
}

export interface ThrottledFunction<T extends (...args: any[]) => any> {
  /**
   * The throttled function
   */
  (...args: Parameters<T>): void

  /**
   * Cancel any pending execution
   */
  cancel: () => void
}

// ========================================
// Debounce
// ========================================

/**
 * Create a debounced function that delays execution until after wait milliseconds
 * have elapsed since the last time it was invoked.
 *
 * @param fn - Function to debounce
 * @param delay - Delay in milliseconds (default: 300)
 * @param options - Configuration options
 * @returns Debounced function with cancel and flush methods
 *
 * @example Debounce search input
 * ```typescript
 * const debouncedSearch = useDebounce((query: string) => {
 *   api.search(query)
 * }, 500)
 *
 * // In template
 * <input @input="debouncedSearch($event.target.value)" />
 * ```
 *
 * @example With immediate execution
 * ```typescript
 * const debouncedSave = useDebounce(saveData, 1000, { leading: true })
 * // Executes immediately on first call, then debounces subsequent calls
 * ```
 *
 * @example Cancel pending execution
 * ```typescript
 * const debounced = useDebounce(fn, 500)
 * debounced() // Schedule execution
 * debounced.cancel() // Cancel scheduled execution
 * ```
 */
export function useDebounce<T extends (...args: any[]) => any>(
  fn: T,
  delay: number = 300,
  options: {
    /**
     * Execute on the leading edge (first call) instead of trailing edge
     * Default: false
     */
    leading?: boolean
    /**
     * Maximum time fn is allowed to be delayed before it's invoked
     * Useful for ensuring function executes at least once per maxWait period
     */
    maxWait?: number
  } = {}
): DebouncedFunction<T> {
  // Validate delay
  if (delay < 0 || !isFinite(delay)) {
    throw new Error(`[useDebounce] Invalid delay: ${delay}. Delay must be a non-negative finite number.`)
  }

  const { leading = false, maxWait } = options

  // Validate maxWait if provided
  if (maxWait !== undefined && (maxWait < 0 || !isFinite(maxWait))) {
    throw new Error(`[useDebounce] Invalid maxWait: ${maxWait}. MaxWait must be a non-negative finite number.`)
  }

  let timeoutId: ReturnType<typeof setTimeout> | null = null
  let maxWaitTimeoutId: ReturnType<typeof setTimeout> | null = null
  let lastCallTime: number | null = null
  let lastArgs: Parameters<T> | null = null
  let lastThis: any = null

  const cancel = (): void => {
    if (timeoutId) {
      clearTimeout(timeoutId)
      timeoutId = null
    }
    if (maxWaitTimeoutId) {
      clearTimeout(maxWaitTimeoutId)
      maxWaitTimeoutId = null
    }
    lastCallTime = null
    lastArgs = null
    lastThis = null
  }

  const invokeFunction = (): void => {
    if (lastArgs) {
      try {
        fn.apply(lastThis, lastArgs)
      } catch (error) {
        logger.error('Callback error:', error)
        throw error // Re-throw to preserve error behavior
      } finally {
        lastArgs = null
        lastCallTime = null
        lastThis = null
      }
    }
  }

  const flush = (): void => {
    // Invoke before canceling to preserve lastArgs
    invokeFunction()
    cancel()
  }

  const debounced = function (this: any, ...args: Parameters<T>): void {
    const now = Date.now()
    const isFirstCall = lastCallTime === null

    // Always update lastCallTime
    lastCallTime = now

    // Leading edge execution
    if (isFirstCall && leading) {
      try {
        fn.apply(this, args)
      } catch (error) {
        logger.error('Leading edge callback error:', error)
        throw error
      }
      // Don't save args/this - no trailing edge in leading-only mode
    } else if (!leading) {
      // Only save args for trailing edge execution (not in leading mode)
      lastArgs = args
      lastThis = this
    }

    // Cancel previous timeout
    if (timeoutId) {
      clearTimeout(timeoutId)
    }

    // Schedule timeout based on mode
    if (leading) {
      // Leading mode: Just reset state after delay (no execution)
      timeoutId = setTimeout(() => {
        cancel()
      }, delay)
    } else {
      // Trailing mode: Execute on trailing edge
      timeoutId = setTimeout(() => {
        invokeFunction()
        cancel()
      }, delay)
    }

    // MaxWait timeout - start from first call
    if (maxWait !== undefined && !maxWaitTimeoutId) {
      if (leading) {
        // Leading mode: maxWait just resets state (no execution)
        maxWaitTimeoutId = setTimeout(() => {
          cancel()
        }, maxWait)
      } else {
        // Trailing mode: maxWait triggers execution
        maxWaitTimeoutId = setTimeout(() => {
          invokeFunction()
          cancel()
        }, maxWait)
      }
    }
  } as DebouncedFunction<T>

  debounced.cancel = cancel
  debounced.flush = flush

  // Auto-cleanup on unmount
  onUnmounted(() => {
    cancel()
  })

  return debounced
}

// ========================================
// Throttle
// ========================================

/**
 * Create a throttled function that only invokes fn at most once per every wait milliseconds.
 *
 * @param fn - Function to throttle
 * @param delay - Delay in milliseconds (default: 300)
 * @param options - Configuration options
 * @returns Throttled function with cancel method
 *
 * @example Throttle scroll handler
 * ```typescript
 * const throttledScroll = useThrottle(() => {
 *   console.log('Scroll position:', window.scrollY)
 * }, 200)
 *
 * window.addEventListener('scroll', throttledScroll)
 * ```
 *
 * @example Throttle API calls
 * ```typescript
 * const throttledUpdate = useThrottle((data) => {
 *   api.update(data)
 * }, 1000, { trailing: false }) // Only leading edge
 * ```
 */
export function useThrottle<T extends (...args: any[]) => any>(
  fn: T,
  delay: number = 300,
  options: {
    /**
     * Execute on the leading edge (first call)
     * Default: true
     */
    leading?: boolean
    /**
     * Execute on the trailing edge (after delay)
     * Default: true
     */
    trailing?: boolean
  } = {}
): ThrottledFunction<T> {
  // Validate delay
  if (delay < 0 || !isFinite(delay)) {
    throw new Error(`[useThrottle] Invalid delay: ${delay}. Delay must be a non-negative finite number.`)
  }

  const { leading = true, trailing = true } = options

  let lastCallTime: number | null = null
  let timeoutId: ReturnType<typeof setTimeout> | null = null
  let lastArgs: Parameters<T> | null = null

  const cancel = (): void => {
    if (timeoutId) {
      clearTimeout(timeoutId)
      timeoutId = null
    }
    lastCallTime = null
    lastArgs = null
  }

  const invokeFunction = (args: Parameters<T>): void => {
    lastCallTime = Date.now()
    try {
      fn(...args)
    } catch (error) {
      logger.error('Throttle callback error:', error)
      throw error
    }
  }

  const throttled = function (this: any, ...args: Parameters<T>): void {
    const now = Date.now()
    const timeSinceLastCall = lastCallTime ? now - lastCallTime : Infinity

    lastArgs = args

    // Leading edge
    if (timeSinceLastCall >= delay) {
      if (leading) {
        invokeFunction(args)
        lastArgs = null
      } else {
        lastCallTime = now
      }

      // Schedule trailing edge if enabled
      if (trailing && !leading) {
        if (timeoutId) clearTimeout(timeoutId)
        timeoutId = setTimeout(() => {
          if (lastArgs) {
            invokeFunction(lastArgs)
            lastArgs = null
          }
          timeoutId = null
        }, delay)
      }
    } else if (trailing) {
      // Still within delay period - schedule trailing edge
      if (timeoutId) clearTimeout(timeoutId)

      const remainingTime = delay - timeSinceLastCall

      timeoutId = setTimeout(() => {
        if (lastArgs) {
          invokeFunction(lastArgs)
          lastArgs = null
        }
        timeoutId = null
      }, remainingTime)
    }
  } as ThrottledFunction<T>

  throttled.cancel = cancel

  // Auto-cleanup on unmount
  onUnmounted(() => {
    cancel()
  })

  return throttled
}

// ========================================
// Timeout
// ========================================

/**
 * Managed setTimeout with automatic cleanup on component unmount
 *
 * @param callback - Function to execute after delay
 * @param delay - Delay in milliseconds
 * @param options - Configuration options
 * @returns Timeout control object
 *
 * @example Auto-hide notification
 * ```typescript
 * const { start, stop, isActive } = useTimeout(() => {
 *   notification.value = null
 * }, 3000)
 *
 * // Show notification and auto-hide
 * notification.value = 'Saved!'
 * start()
 * ```
 *
 * @example Conditional timeout
 * ```typescript
 * const { start, restart } = useTimeout(() => {
 *   checkStatus()
 * }, 5000, { immediate: false })
 *
 * // Start manually when needed
 * if (needsCheck.value) {
 *   start()
 * }
 * ```
 */
export function useTimeout(
  callback: () => void,
  delay: number,
  options: {
    /**
     * Start timeout immediately on creation (default: true)
     */
    immediate?: boolean
  } = {}
): UseTimeoutReturn {
  // Validate delay
  if (delay < 0 || !isFinite(delay)) {
    throw new Error(`[useTimeout] Invalid delay: ${delay}. Delay must be a non-negative finite number.`)
  }

  const { immediate = true } = options

  const isActive = ref<boolean>(false)
  let timeoutId: ReturnType<typeof setTimeout> | null = null

  const stop = (): void => {
    if (timeoutId) {
      clearTimeout(timeoutId)
      timeoutId = null
      isActive.value = false
    }
  }

  const start = (): void => {
    stop() // Clear any existing timeout

    isActive.value = true
    timeoutId = setTimeout(() => {
      try {
        callback()
      } catch (error) {
        logger.error('Timeout callback error:', error)
        throw error
      } finally {
        isActive.value = false
        timeoutId = null
      }
    }, delay)
  }

  const restart = (): void => {
    start()
  }

  // Auto-start if immediate
  if (immediate) {
    start()
  }

  // Auto-cleanup on unmount
  onUnmounted(() => {
    stop()
  })

  return {
    start,
    stop,
    isActive,
    restart
  }
}

// ========================================
// Interval
// ========================================

/**
 * Managed setInterval with automatic cleanup on component unmount
 *
 * @param callback - Function to execute repeatedly
 * @param delay - Delay between executions in milliseconds
 * @param options - Configuration options
 * @returns Interval control object
 *
 * @example Polling API
 * ```typescript
 * const { start, stop, isActive } = useInterval(() => {
 *   fetchStatus()
 * }, 5000)
 *
 * // Start/stop polling based on conditions
 * watch(isMonitoring, (monitoring) => {
 *   if (monitoring) start()
 *   else stop()
 * })
 * ```
 *
 * @example Auto-refresh with pause/resume
 * ```typescript
 * const { pause, resume } = useInterval(() => {
 *   refreshData()
 * }, 10000, { immediate: true })
 *
 * // Pause when tab is hidden
 * document.addEventListener('visibilitychange', () => {
 *   if (document.hidden) pause()
 *   else resume()
 * })
 * ```
 */
export function useInterval(
  callback: () => void,
  delay: number,
  options: {
    /**
     * Start interval immediately on creation (default: true)
     */
    immediate?: boolean
    /**
     * Execute callback immediately before starting interval (default: false)
     */
    immediateCallback?: boolean
  } = {}
): UseIntervalReturn {
  // Validate delay
  if (delay < 0 || !isFinite(delay)) {
    throw new Error(`[useInterval] Invalid delay: ${delay}. Delay must be a non-negative finite number.`)
  }

  const { immediate = true, immediateCallback = false } = options

  const isActive = ref<boolean>(false)
  let intervalId: ReturnType<typeof setInterval> | null = null

  // Wrap callback with error handling
  const safeCallback = (): void => {
    try {
      callback()
    } catch (error) {
      logger.error('Interval callback error:', error)
      // Don't throw - let interval continue running
    }
  }

  const stop = (): void => {
    if (intervalId) {
      clearInterval(intervalId)
      intervalId = null
      isActive.value = false
    }
  }

  const start = (): void => {
    stop() // Clear any existing interval

    // Execute immediately if requested
    if (immediateCallback) {
      safeCallback()
    }

    isActive.value = true
    intervalId = setInterval(safeCallback, delay)
  }

  const restart = (): void => {
    start()
  }

  const pause = (): void => {
    stop()
  }

  const resume = (): void => {
    if (!isActive.value) {
      start()
    }
  }

  // Auto-start if immediate
  if (immediate) {
    start()
  }

  // Auto-cleanup on unmount
  onUnmounted(() => {
    stop()
  })

  return {
    start,
    stop,
    isActive,
    restart,
    pause,
    resume
  }
}

// ========================================
// Sleep/Delay
// ========================================

/**
 * Promise-based sleep/delay utility for use in async functions
 *
 * @param ms - Milliseconds to sleep
 * @returns Promise that resolves after the delay
 *
 * @example Delay between operations
 * ```typescript
 * async function saveWithDelay() {
 *   await saveData()
 *   await useSleep(2000) // Wait 2 seconds
 *   showSuccessMessage()
 * }
 * ```
 *
 * @example Retry with backoff
 * ```typescript
 * async function fetchWithRetry(url: string, retries = 3) {
 *   for (let i = 0; i < retries; i++) {
 *     try {
 *       return await fetch(url)
 *     } catch (error) {
 *       if (i < retries - 1) {
 *         await useSleep(1000 * Math.pow(2, i)) // Exponential backoff
 *       }
 *     }
 *   }
 *   throw new Error('Max retries exceeded')
 * }
 * ```
 */
export function useSleep(ms: number): Promise<void> {
  // Validate delay
  if (ms < 0 || !isFinite(ms)) {
    return Promise.reject(new Error(`[useSleep] Invalid delay: ${ms}. Delay must be a non-negative finite number.`))
  }

  return new Promise((resolve) => setTimeout(resolve, ms))
}

// ========================================
// Cancelable Sleep
// ========================================

export interface CancelableSleep {
  /**
   * Promise that resolves after delay
   */
  promise: Promise<void>

  /**
   * Cancel the sleep (rejects the promise)
   */
  cancel: () => void
}

/**
 * Cancelable promise-based sleep utility
 *
 * @param ms - Milliseconds to sleep
 * @returns Object with promise and cancel function
 *
 * @example Cancelable delay
 * ```typescript
 * const sleep = useCancelableSleep(5000)
 *
 * try {
 *   await sleep.promise
 *   console.log('Delay completed')
 * } catch (error) {
 *   console.log('Delay canceled')
 * }
 *
 * // Cancel from elsewhere
 * sleep.cancel()
 * ```
 *
 * @note If canceled, the promise will reject with an error.
 * Always use try/catch when awaiting cancelable sleep.
 */
export function useCancelableSleep(ms: number): CancelableSleep {
  // Validate delay
  if (ms < 0 || !isFinite(ms)) {
    throw new Error(`[useCancelableSleep] Invalid delay: ${ms}. Delay must be a non-negative finite number.`)
  }

  let timeoutId: ReturnType<typeof setTimeout> | null = null
  let rejectFn: ((reason?: any) => void) | null = null

  const promise = new Promise<void>((resolve, reject) => {
    rejectFn = reject
    timeoutId = setTimeout(resolve, ms)
  })

  const cancel = (): void => {
    if (timeoutId) {
      clearTimeout(timeoutId)
      timeoutId = null
    }
    if (rejectFn) {
      rejectFn(new Error('Sleep canceled'))
      rejectFn = null
    }
  }

  // Auto-cleanup on unmount
  onUnmounted(() => {
    cancel()
  })

  return {
    promise,
    cancel
  }
}
