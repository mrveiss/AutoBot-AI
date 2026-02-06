/**
 * Async Operation Composable
 *
 * Foundation composable for managing async operations with automatic loading/error state management.
 * This composable eliminates duplicate loading/error patterns found across 40+ components.
 *
 * @module useAsyncOperation
 * @category Composables
 *
 * @example
 * // Basic usage
 * const { loading, error, execute, data } = useAsyncOperation()
 * const loadData = () => execute(() => apiClient.get('/api/data'))
 *
 * @example
 * // With callbacks
 * const { loading, error, execute } = useAsyncOperation({
 *   onSuccess: (data) => console.log('Success:', data),
 *   onError: (err) => console.error('Failed:', err),
 *   errorMessage: 'Failed to load data'
 * })
 *
 * @example
 * // Multiple operations in single component
 * const tree = useAsyncOperation({ errorMessage: 'Failed to load tree' })
 * const content = useAsyncOperation({ errorMessage: 'Failed to load content' })
 * const pagination = useAsyncOperation()
 *
 * const loadTree = () => tree.execute(() => api.getTree())
 * const loadContent = () => content.execute(() => api.getContent(id))
 */

import { ref, computed, type Ref, type ComputedRef } from 'vue'

/**
 * Configuration options for async operations
 */
export interface AsyncOperationOptions<T> {
  /**
   * Callback executed when operation succeeds
   * @param data - The resolved data from the async operation
   */
  onSuccess?: (data: T) => void

  /**
   * Callback executed when operation fails
   * @param error - The error thrown by the async operation
   */
  onError?: (error: Error) => void

  /**
   * Initial loading state (default: false)
   */
  initialLoading?: boolean

  /**
   * Custom error message prefix for error handling
   * If not provided, uses the error's message directly
   */
  errorMessage?: string
}

/**
 * Return type for useAsyncOperation composable
 */
export interface AsyncOperationReturn<T> {
  /**
   * Reactive loading state - true during async operation execution
   */
  loading: Ref<boolean>

  /**
   * Reactive error state - contains Error object if operation failed, null otherwise
   */
  error: Ref<Error | null>

  /**
   * Reactive data state - contains resolved data from successful operation, null otherwise
   */
  data: Ref<T | null>

  /**
   * Execute an async operation with automatic state management
   * @param fn - Async function to execute
   * @returns Promise resolving to the function's return value
   * @throws Re-throws the error after storing it in error ref
   */
  execute: (fn: () => Promise<T>) => Promise<T>

  /**
   * Reset all states to initial values
   */
  reset: () => void

  /**
   * Computed property - true if data exists and no error
   */
  isSuccess: ComputedRef<boolean>

  /**
   * Computed property - true if error exists
   */
  isError: ComputedRef<boolean>
}

/**
 * Composable for managing async operations with automatic loading/error state handling
 *
 * This composable provides a standardized way to handle async operations across the AutoBot
 * frontend. It automatically manages loading states, error handling, and success/error callbacks.
 *
 * **Concurrent Call Handling**:
 * - Latest call wins - if multiple calls are made, all execute but state reflects the last completed call
 * - For sequential execution, use `await execute()` before calling again
 * - For cancellation, implement AbortController in your async function
 *
 * **Error Handling**:
 * - Errors are caught and stored in `error` ref
 * - Error object or string are normalized to Error type
 * - Optional `onError` callback for custom error handling
 * - Errors are re-thrown after handling, allowing upstream catch blocks
 *
 * @template T - Type of data returned by the async operation
 * @param options - Configuration options
 * @returns Object with reactive states and execute function
 */
export function useAsyncOperation<T = any>(
  options: AsyncOperationOptions<T> = {}
): AsyncOperationReturn<T> {
  const { onSuccess, onError, initialLoading = false, errorMessage } = options

  // Reactive state
  const loading = ref<boolean>(initialLoading)
  const error = ref<Error | null>(null)
  const data = ref<T | null>(null)

  // Computed helpers
  const isSuccess = computed(() => data.value !== null && error.value === null)
  const isError = computed(() => error.value !== null)

  /**
   * Execute an async operation with automatic state management
   *
   * **State Management**:
   * 1. Sets loading=true and clears error
   * 2. Executes the async function
   * 3. On success: stores data, calls onSuccess callback
   * 4. On error: stores error, calls onError callback
   * 5. Finally: sets loading=false
   *
   * **Concurrent Calls**:
   * Multiple calls will execute in parallel. State (loading, error, data) reflects
   * the most recently completed operation. If you need sequential execution, use:
   * `await execute(fn1); await execute(fn2)`
   *
   * @param fn - Async function to execute
   * @returns Promise resolving to the function's return value
   * @throws Re-throws the error after handling (allows upstream error handling)
   */
  const execute = async (fn: () => Promise<T>): Promise<T> => {
    // Set loading state and clear error
    loading.value = true
    error.value = null

    try {
      // Execute async operation
      const result = await fn()

      // Store successful result
      data.value = result

      // Call success callback if provided
      if (onSuccess) {
        onSuccess(result)
      }

      return result
    } catch (err) {
      // Normalize error to Error object
      const normalizedError =
        err instanceof Error ? err : new Error(String(err))

      // Apply custom error message prefix if provided
      if (errorMessage) {
        normalizedError.message = `${errorMessage}: ${normalizedError.message}`
      }

      // Store error
      error.value = normalizedError

      // Call error callback if provided
      if (onError) {
        onError(normalizedError)
      }

      // Re-throw to allow upstream error handling
      throw normalizedError
    } finally {
      // Always reset loading state
      loading.value = false
    }
  }

  /**
   * Reset all states to initial values
   *
   * Clears loading, error, and data states. Useful when:
   * - Unmounting component
   * - Resetting form after submission
   * - Clearing previous operation results
   */
  const reset = () => {
    loading.value = initialLoading
    error.value = null
    data.value = null
  }

  return {
    loading,
    error,
    data: data as Ref<T | null>, // Type assertion for Vue 3 ref() inference
    execute,
    reset,
    isSuccess,
    isError
  }
}

/**
 * Type guard to check if value is an Error object
 * @param value - Value to check
 * @returns True if value is an Error instance
 */
export function isError(value: unknown): value is Error {
  return value instanceof Error
}

/**
 * Utility to create multiple async operations with shared configuration
 *
 * @example
 * const operations = createAsyncOperations({
 *   tree: { errorMessage: 'Failed to load tree' },
 *   content: { errorMessage: 'Failed to load content' },
 *   metadata: { onSuccess: (data) => console.log(data) }
 * })
 *
 * // Use: operations.tree.execute(() => api.getTree())
 */
export function createAsyncOperations<
  T extends Record<string, AsyncOperationOptions<any>>
>(
  configs: T
): {
  [K in keyof T]: AsyncOperationReturn<any>
} {
  const operations: any = {}

  for (const [key, config] of Object.entries(configs)) {
    operations[key] = useAsyncOperation(config)
  }

  return operations
}
