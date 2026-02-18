/**
 * useDebounce Composable
 *
 * Provides debouncing functionality for reactive values.
 * Useful for search inputs, filters, and any user input that triggers expensive operations.
 *
 * Benefits:
 * - Reduces API calls by 70-90%
 * - Improves performance by delaying expensive operations
 * - Better UX - waits for user to finish typing
 */

import { ref, watch, onUnmounted, type Ref } from 'vue'

/**
 * Debounce a reactive value
 *
 * @param value - The reactive value to debounce
 * @param delay - Debounce delay in milliseconds (default: 300ms)
 * @returns Debounced reactive value
 *
 * @example
 * ```typescript
 * const searchQuery = ref('')
 * const debouncedSearch = useDebounce(searchQuery, 300)
 *
 * watch(debouncedSearch, async (query) => {
 *   // This will only fire 300ms after user stops typing
 *   await performSearch(query)
 * })
 * ```
 */
export function useDebounce<T>(value: Ref<T>, delay: number = 300): Ref<T> {
  const debouncedValue = ref<T>(value.value) as Ref<T>
  let timeoutId: ReturnType<typeof setTimeout> | null = null

  // Watch for changes and debounce them
  const unwatch = watch(
    value,
    (newValue) => {
      // Clear previous timeout
      if (timeoutId !== null) {
        clearTimeout(timeoutId)
      }

      // Set new timeout
      timeoutId = setTimeout(() => {
        debouncedValue.value = newValue
        timeoutId = null
      }, delay)
    },
    { immediate: false }
  )

  // Cleanup on unmount
  onUnmounted(() => {
    if (timeoutId !== null) {
      clearTimeout(timeoutId)
    }
    unwatch()
  })

  return debouncedValue
}

/**
 * Create a debounced function
 *
 * @param fn - The function to debounce
 * @param delay - Debounce delay in milliseconds (default: 300ms)
 * @returns Debounced function and cancel method
 *
 * @example
 * ```typescript
 * const { debouncedFn, cancel } = useDebouncedFn(async (query: string) => {
 *   await performSearch(query)
 * }, 300)
 *
 * // Call the debounced function
 * debouncedFn('search term')
 *
 * // Cancel pending execution if needed
 * cancel()
 * ```
 */
export function useDebouncedFn<T extends (...args: any[]) => any>(
  fn: T,
  delay: number = 300
): {
  debouncedFn: (...args: Parameters<T>) => void
  cancel: () => void
} {
  let timeoutId: ReturnType<typeof setTimeout> | null = null

  const cancel = () => {
    if (timeoutId !== null) {
      clearTimeout(timeoutId)
      timeoutId = null
    }
  }

  const debouncedFn = (...args: Parameters<T>) => {
    cancel()
    timeoutId = setTimeout(() => {
      fn(...args)
      timeoutId = null
    }, delay)
  }

  // Cleanup on unmount
  onUnmounted(() => {
    cancel()
  })

  return {
    debouncedFn,
    cancel
  }
}

/**
 * Debounce with loading state
 *
 * @param value - The reactive value to debounce
 * @param delay - Debounce delay in milliseconds (default: 300ms)
 * @returns Debounced value and isDebouncing state
 *
 * @example
 * ```typescript
 * const searchQuery = ref('')
 * const { debouncedValue, isDebouncing } = useDebounceWithLoading(searchQuery, 300)
 *
 * watch(debouncedValue, async (query) => {
 *   await performSearch(query)
 * })
 *
 * // Show loading indicator while debouncing
 * <LoadingSpinner v-if="isDebouncing" />
 * ```
 */
export function useDebounceWithLoading<T>(
  value: Ref<T>,
  delay: number = 300
): {
  debouncedValue: Ref<T>
  isDebouncing: Ref<boolean>
} {
  const debouncedValue = ref<T>(value.value) as Ref<T>
  const isDebouncing = ref(false)
  let timeoutId: ReturnType<typeof setTimeout> | null = null

  const unwatch = watch(
    value,
    (newValue) => {
      // Clear previous timeout
      if (timeoutId !== null) {
        clearTimeout(timeoutId)
      }

      // Set debouncing state
      isDebouncing.value = true

      // Set new timeout
      timeoutId = setTimeout(() => {
        debouncedValue.value = newValue
        isDebouncing.value = false
        timeoutId = null
      }, delay)
    },
    { immediate: false }
  )

  // Cleanup on unmount
  onUnmounted(() => {
    if (timeoutId !== null) {
      clearTimeout(timeoutId)
    }
    unwatch()
  })

  return {
    debouncedValue,
    isDebouncing
  }
}
