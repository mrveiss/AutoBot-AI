/**
 * Error Handling Composable
 *
 * Centralized error handling to eliminate duplicate try/catch/finally blocks across components.
 * Consolidates 480+ error handling occurrences with consistent patterns.
 *
 * Features:
 * - Async operation wrapper with automatic error handling
 * - Reactive error state management
 * - Loading state automation
 * - Customizable error logging
 * - User notification integration
 * - Rollback/cleanup callbacks
 * - Retry logic with exponential backoff
 * - TypeScript type safety
 * - Auto-cleanup on component unmount
 *
 * Usage:
 * ```typescript
 * import { useAsyncHandler, useErrorState } from '@/composables/useErrorHandler'
 *
 * // Basic async operation wrapper
 * const { execute, loading, error } = useAsyncHandler(async () => {
 *   const response = await apiClient.get('/data')
 *   return response.data
 * })
 *
 * // Execute operation
 * await execute()
 *
 * // With error handling options
 * const { execute } = useAsyncHandler(
 *   async () => apiClient.post('/save', data),
 *   {
 *     onError: (error) => console.error('Save failed:', error),
 *     onSuccess: () => showMessage('Saved!', 'success'),
 *     loadingMessage: 'Saving...',
 *     errorMessage: 'Failed to save'
 *   }
 * )
 * ```
 */

import { ref, computed, onUnmounted, onErrorCaptured, getCurrentInstance, type Ref } from 'vue'
import { createLogger } from '@/utils/debugUtils'

// Create scoped logger for useErrorHandler
const logger = createLogger('useErrorHandler')

// ========================================
// Types & Interfaces
// ========================================

export interface AsyncHandlerOptions<T = unknown> {
  /**
   * Callback when operation succeeds
   */
  onSuccess?: (result: T) => void | Promise<void>

  /**
   * Callback when operation fails
   */
  onError?: (error: Error) => void | Promise<void>

  /**
   * Callback to execute in finally block (cleanup)
   */
  onFinally?: () => void | Promise<void>

  /**
   * Rollback callback when operation fails
   * Use for reverting UI state changes
   */
  onRollback?: () => void | Promise<void>

  /**
   * Enable retry logic on failure
   * Default: false
   */
  retry?: boolean

  /**
   * Maximum number of total attempts (initial attempt + retries)
   * Example: retryAttempts: 3 means 1 initial attempt + up to 2 retries
   * Default: 3
   */
  retryAttempts?: number

  /**
   * Retry delay in milliseconds (with exponential backoff)
   * Default: 1000
   */
  retryDelay?: number

  /**
   * Log errors to console
   * Default: true
   */
  logErrors?: boolean

  /**
   * Custom error log prefix
   * Default: '[Error]'
   */
  errorPrefix?: string

  /**
   * Error message to display to user
   * Used with notification callback if provided
   */
  errorMessage?: string

  /**
   * Success message to display to user
   * Used with notification callback if provided
   */
  successMessage?: string

  /**
   * Loading message to display to user
   */
  loadingMessage?: string

  /**
   * Custom notification function
   * Called with (message, type) where type is 'success' | 'error' | 'info'
   */
  notify?: (message: string, type: 'success' | 'error' | 'info') => void

  /**
   * Throw error after handling
   * Default: false (errors are caught and stored in error state)
   */
  throwOnError?: boolean

  /**
   * Debounce delay in milliseconds
   * Prevents rapid repeated executions
   */
  debounce?: number
}

export interface UseAsyncHandlerReturn<T> {
  /**
   * Execute the async operation
   */
  execute: (...args: any[]) => Promise<T | undefined>

  /**
   * Reactive loading state
   */
  loading: Ref<boolean>

  /**
   * Reactive error state (null if no error)
   */
  error: Ref<Error | null>

  /**
   * Reactive data result (undefined until first success)
   */
  data: Ref<T | undefined>

  /**
   * Clear error state
   */
  clearError: () => void

  /**
   * Reset all state (loading, error, data)
   */
  reset: () => void

  /**
   * Check if operation has completed successfully at least once
   */
  isSuccess: Ref<boolean>
}

export interface UseErrorStateOptions {
  /**
   * Auto-clear error after delay (milliseconds)
   * Set to 0 to disable auto-clear
   * Default: 0 (disabled)
   */
  autoClear?: number

  /**
   * Callback when error changes
   */
  onError?: (error: Error | null) => void
}

// ========================================
// Error State Management
// ========================================

/**
 * Reactive error state with auto-clear support
 *
 * @param options - Configuration options
 * @returns Error state management utilities
 *
 * @example
 * ```typescript
 * const { error, setError, clearError, hasError } = useErrorState({
 *   autoClear: 5000 // Clear after 5 seconds
 * })
 *
 * setError(new Error('Something failed'))
 * // Error automatically clears after 5 seconds
 * ```
 */
export function useErrorState(options: UseErrorStateOptions = {}) {
  const { autoClear = 0, onError } = options

  const error = ref<Error | null>(null)
  const hasError = computed(() => error.value !== null)

  let clearTimer: ReturnType<typeof setTimeout> | null = null

  const setError = (err: Error | null) => {
    error.value = err

    // Clear existing timer
    if (clearTimer) {
      clearTimeout(clearTimer)
      clearTimer = null
    }

    // Auto-clear if enabled and error is set
    if (autoClear > 0 && err !== null) {
      clearTimer = setTimeout(() => {
        error.value = null
        clearTimer = null
      }, autoClear)
    }

    // Call onError callback
    if (onError) {
      onError(err)
    }
  }

  const clearError = () => {
    if (clearTimer) {
      clearTimeout(clearTimer)
      clearTimer = null
    }
    error.value = null
  }

  // Cleanup on unmount
  const instance = getCurrentInstance()
  if (instance) {
    onUnmounted(() => {
      if (clearTimer) {
        clearTimeout(clearTimer)
      }
    })
  }

  return {
    error,
    setError,
    clearError,
    hasError
  }
}

// ========================================
// Async Operation Wrapper
// ========================================

/**
 * Wraps async operation with automatic error handling, loading state, and retry logic
 *
 * @param operation - Async function to execute
 * @param options - Configuration options
 * @returns Async handler utilities
 *
 * @example Basic usage
 * ```typescript
 * const { execute, loading, error } = useAsyncHandler(async () => {
 *   const response = await fetch('/api/data')
 *   return response.json()
 * })
 *
 * await execute() // Auto-handles errors, loading state
 * ```
 *
 * @example With all options
 * ```typescript
 * const { execute, loading, error, data } = useAsyncHandler(
 *   async (id: number) => apiClient.get(`/users/${id}`),
 *   {
 *     onSuccess: (user) => console.log('Loaded:', user),
 *     onError: (error) => console.error('Failed:', error),
 *     onRollback: () => (selectedUser.value = null),
 *     retry: true,
 *     retryAttempts: 3,
 *     errorMessage: 'Failed to load user',
 *     notify: showMessage
 *   }
 * )
 *
 * await execute(123) // Automatically retries on failure
 * ```
 */
export function useAsyncHandler<T = unknown>(
  operation: (...args: any[]) => Promise<T>,
  options: AsyncHandlerOptions<T> = {}
): UseAsyncHandlerReturn<T> {
  const {
    onSuccess,
    onError,
    onFinally,
    onRollback,
    retry = false,
    retryAttempts = 3,
    retryDelay = 1000,
    logErrors = true,
    errorPrefix = '[Error]',
    errorMessage,
    successMessage,
    loadingMessage,
    notify,
    throwOnError = false,
    debounce
  } = options

  const loading = ref(false)
  const error = ref<Error | null>(null)
  const data = ref<T | undefined>(undefined) as Ref<T | undefined>
  const isSuccess = ref(false)

  let debounceTimer: ReturnType<typeof setTimeout> | null = null
  let pendingResolvers: Array<(value: T | undefined) => void> = []

  /**
   * Execute operation with retry logic
   * Uses callback-based timing for fake timer compatibility
   */
  const executeWithRetry = async (args: any[], attempt = 0): Promise<T> => {
    try {
      const result = await operation(...args)
      return result
    } catch (err) {
      // If retry enabled and attempts remaining
      // attempt < retryAttempts - 1 because attempt starts at 0 (initial try)
      if (retry && attempt < retryAttempts - 1) {
        // Exponential backoff: delay * 2^attempt
        const delay = retryDelay * Math.pow(2, attempt)

        if (logErrors) {
          logger.warn(
            `${errorPrefix} Attempt ${attempt + 1}/${retryAttempts} failed. Retrying in ${delay}ms...`,
            err
          )
        }

        // Use Promise with setTimeout for fake timer compatibility
        // Avoid async callback - use promise chaining for better fake timer support
        return new Promise<T>((resolve, reject) => {
          setTimeout(() => {
            executeWithRetry(args, attempt + 1)
              .then(resolve)
              .catch(reject)
          }, delay)
        })
      }

      // No more retries or retry disabled - throw error
      throw err
    }
  }

  /**
   * Core execution logic (internal)
   * Separated from execute() to avoid recursion issues with debounce
   */
  const executeOperation = async (args: any[]): Promise<T | undefined> => {
    // Clear previous error
    error.value = null

    // Set loading state
    loading.value = true

    // Show loading message if provided
    if (loadingMessage && notify) {
      notify(loadingMessage, 'info')
    }

    try {
      // Execute operation with retry logic
      const result = await executeWithRetry(args)

      // Store result
      data.value = result
      isSuccess.value = true

      // Show success message if provided
      if (successMessage && notify) {
        notify(successMessage, 'success')
      }

      // Call success callback
      if (onSuccess) {
        await onSuccess(result)
      }

      return result
    } catch (err) {
      const errorObj = err instanceof Error ? err : new Error(String(err))
      error.value = errorObj

      // Log error if enabled
      if (logErrors) {
        logger.error(errorPrefix, errorObj)
      }

      // Show error message if provided
      if (errorMessage && notify) {
        notify(errorMessage, 'error')
      }

      // Call error callback
      if (onError) {
        await onError(errorObj)
      }

      // Call rollback callback
      if (onRollback) {
        await onRollback()
      }

      // Throw if configured to do so
      if (throwOnError) {
        throw errorObj
      }

      return undefined
    } finally {
      // Reset loading state
      loading.value = false

      // Call finally callback
      if (onFinally) {
        await onFinally()
      }
    }
  }

  /**
   * Main execute function with debounce support
   *
   * Debouncing Strategy:
   * - Multiple rapid calls reset the timer and collect their promise resolvers
   * - Only the last call's timer executes the operation
   * - All collected resolvers receive the same result
   * - This ensures all callers get their promises resolved even if execution is debounced
   */
  const execute = async (...args: any[]): Promise<T | undefined> => {
    // Handle debouncing - collect all pending promises and resolve them together
    if (debounce) {
      // Cancel previous timer if exists (debounce behavior)
      if (debounceTimer) {
        clearTimeout(debounceTimer)
      }

      return new Promise((resolve) => {
        // Collect this call's resolver - will be resolved when timer fires
        pendingResolvers.push(resolve)

        // Start new debounce timer
        debounceTimer = setTimeout(() => {
          debounceTimer = null

          // Capture all pending resolvers and clear list for next batch
          const resolvers = [...pendingResolvers]
          pendingResolvers = []

          // Execute once, resolve all pending promises with same result
          executeOperation(args).then((result) => {
            resolvers.forEach(r => r(result))
          })
        }, debounce)
      })
    }

    // Non-debounced execution - direct pass-through
    return executeOperation(args)
  }

  /**
   * Clear error state
   */
  const clearError = () => {
    error.value = null
  }

  /**
   * Reset all state
   */
  const reset = () => {
    loading.value = false
    error.value = null
    data.value = undefined
    isSuccess.value = false
  }

  // Cleanup on unmount
  const instance = getCurrentInstance()
  if (instance) {
    onUnmounted(() => {
      if (debounceTimer) {
        clearTimeout(debounceTimer)
      }
      // Clear pending resolvers to prevent memory leaks
      pendingResolvers = []
    })
  }

  return {
    execute,
    loading,
    error,
    data,
    clearError,
    reset,
    isSuccess
  }
}

// ========================================
// Loading State Helper
// ========================================

/**
 * Simple loading state management
 *
 * @param initialState - Initial loading state
 * @returns Loading state utilities
 *
 * @example
 * ```typescript
 * const { loading, startLoading, stopLoading, withLoading } = useLoadingState()
 *
 * // Manual control
 * startLoading()
 * await doSomething()
 * stopLoading()
 *
 * // Auto-wrapped
 * await withLoading(async () => {
 *   await doSomething() // Loading state automatic
 * })
 * ```
 */
export function useLoadingState(initialState = false) {
  const loading = ref(initialState)

  const startLoading = () => {
    loading.value = true
  }

  const stopLoading = () => {
    loading.value = false
  }

  const withLoading = async <T>(operation: () => Promise<T>): Promise<T> => {
    try {
      loading.value = true
      return await operation()
    } finally {
      loading.value = false
    }
  }

  return {
    loading,
    startLoading,
    stopLoading,
    withLoading
  }
}

// ========================================
// Retry Utility
// ========================================

/**
 * Retry an operation with exponential backoff
 *
 * @param operation - Operation to retry
 * @param maxAttempts - Maximum number of total attempts (including initial attempt)
 * @param initialDelay - Initial delay in milliseconds
 * @returns Operation result
 *
 * @example
 * ```typescript
 * const data = await retryOperation(
 *   async () => fetchData(),
 *   3,  // 3 total attempts (initial + 2 retries)
 *   1000  // 1 second initial delay
 * )
 * ```
 */
export async function retryOperation<T>(
  operation: () => Promise<T>,
  maxAttempts = 3,
  initialDelay = 1000
): Promise<T> {
  let lastError: Error | undefined

  for (let attempt = 0; attempt < maxAttempts; attempt++) {
    try {
      return await operation()
    } catch (err) {
      lastError = err instanceof Error ? err : new Error(String(err))

      if (attempt < maxAttempts - 1) {
        // Exponential backoff
        const delay = initialDelay * Math.pow(2, attempt)
        await new Promise((resolve) => setTimeout(resolve, delay))
      }
    }
  }

  // All attempts failed
  throw lastError || new Error('Operation failed after all retries')
}

// ========================================
// Error Boundary Helper
// ========================================

/**
 * Create error boundary for catching Vue errors from child components.
 * Uses Vue 3's onErrorCaptured lifecycle hook for component-level error handling.
 *
 * @param onError - Error handler callback. Return false to prevent propagation.
 *
 * @example
 * ```typescript
 * const { hasError, lastError, clearError } = useErrorBoundary((error, instance) => {
 *   console.error('Child component error:', error)
 *   showErrorNotification(error.message)
 * })
 * ```
 */
export function useErrorBoundary(onError: (error: Error, instance: any) => boolean | void) {
  const hasError = ref(false)
  const lastError = ref<Error | null>(null)

  const instance = getCurrentInstance()

  if (instance) {
    // Issue #820: Use Vue 3's onErrorCaptured for actual error boundary behavior
    onErrorCaptured((err: Error, vm: any, info: string) => {
      hasError.value = true
      lastError.value = err
      logger.error(`[useErrorBoundary] Caught error in child component (${info}):`, err)
      const result = onError(err, vm)
      // Return false to stop error propagation, otherwise let it bubble
      return result === false ? false : undefined
    })
  } else {
    logger.warn('[useErrorBoundary] Must be called inside setup()')
  }

  const clearError = () => {
    hasError.value = false
    lastError.value = null
  }

  return {
    onError,
    hasError,
    lastError,
    clearError
  }
}
