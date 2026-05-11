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
 *   // apiClient.get() returns parsed JSON directly — no .data envelope
 *   return await apiClient.get<any>('/data')
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

import { ref, computed, onUnmounted, onErrorCaptured, getCurrentInstance, type Ref, type ComponentPublicInstance } from 'vue'
import { createLogger } from '@/utils/debugUtils'

// Create scoped logger for useErrorHandler
const logger = createLogger('useErrorHandler')

// ========================================
// Types & Interfaces
// ========================================

export interface AsyncHandlerOptions<T = unknown> {
  onSuccess?: (result: T) => void | Promise<void>
  onError?: (error: Error) => void | Promise<void>
  onFinally?: () => void | Promise<void>
  onRollback?: () => void | Promise<void>
  retry?: boolean
  retryAttempts?: number
  retryDelay?: number
  logErrors?: boolean
  errorPrefix?: string
  errorMessage?: string
  successMessage?: string
  loadingMessage?: string
  notify?: (message: string, type: 'success' | 'error' | 'info') => void
  throwOnError?: boolean
  debounce?: number
}

export interface UseAsyncHandlerReturn<T> {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any -- generic pass-through args
  execute: (...args: any[]) => Promise<T | undefined>
  loading: Ref<boolean>
  error: Ref<Error | null>
  data: Ref<T | undefined>
  clearError: () => void
  reset: () => void
  isSuccess: Ref<boolean>
}

export interface UseErrorStateOptions {
  autoClear?: number
  onError?: (error: Error | null) => void
}

// ========================================
// Error State Management
// ========================================

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

 
export function useAsyncHandler<T = unknown>(
  // eslint-disable-next-line @typescript-eslint/no-explicit-any -- generic pass-through args
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

  const executeWithRetry = async (args: unknown[], attempt = 0): Promise<T> => {
    try {
      const result = await operation(...args)
      return result
    } catch (err) {
      if (retry && attempt < retryAttempts - 1) {
        const delay = retryDelay * Math.pow(2, attempt)

        if (logErrors) {
          logger.warn(
            `${errorPrefix} Attempt ${attempt + 1}/${retryAttempts} failed. Retrying in ${delay}ms...`,
            err
          )
        }

        return new Promise<T>((resolve, reject) => {
          setTimeout(() => {
            executeWithRetry(args, attempt + 1)
              .then(resolve)
              .catch(reject)
          }, delay)
        })
      }

      throw err
    }
  }

  const executeOperation = async (args: unknown[]): Promise<T | undefined> => {
    error.value = null
    loading.value = true

    if (loadingMessage && notify) {
      notify(loadingMessage, 'info')
    }

    try {
      const result = await executeWithRetry(args)
      data.value = result
      isSuccess.value = true

      if (successMessage && notify) {
        notify(successMessage, 'success')
      }

      if (onSuccess) {
        await onSuccess(result)
      }

      return result
    } catch (err) {
      const errorObj = err instanceof Error ? err : new Error(String(err))
      error.value = errorObj

      if (logErrors) {
        logger.error(errorPrefix, errorObj)
      }

      if (errorMessage && notify) {
        notify(errorMessage, 'error')
      }

      if (onError) {
        await onError(errorObj)
      }

      if (onRollback) {
        await onRollback()
      }

      if (throwOnError) {
        throw errorObj
      }

      return undefined
    } finally {
      loading.value = false

      if (onFinally) {
        await onFinally()
      }
    }
  }

  // eslint-disable-next-line @typescript-eslint/no-explicit-any -- generic pass-through args
  const execute = async (...args: any[]): Promise<T | undefined> => {
    if (debounce) {
      if (debounceTimer) {
        clearTimeout(debounceTimer)
      }

      return new Promise((resolve) => {
        pendingResolvers.push(resolve)

        debounceTimer = setTimeout(() => {
          debounceTimer = null

          const resolvers = [...pendingResolvers]
          pendingResolvers = []

          executeOperation(args).then((result) => {
            resolvers.forEach(r => r(result))
          })
        }, debounce)
      })
    }

    return executeOperation(args)
  }

  const clearError = () => {
    error.value = null
  }

  const reset = () => {
    loading.value = false
    error.value = null
    data.value = undefined
    isSuccess.value = false
  }

  const instance = getCurrentInstance()
  if (instance) {
    onUnmounted(() => {
      if (debounceTimer) {
        clearTimeout(debounceTimer)
      }
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
// Retry Utility
// ========================================

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
        const delay = initialDelay * Math.pow(2, attempt)
        await new Promise((resolve) => setTimeout(resolve, delay))
      }
    }
  }

  throw lastError || new Error('Operation failed after all retries')
}

// ========================================
// Error Boundary Helper
// ========================================

export function useErrorBoundary(onError: (error: Error, instance: ComponentPublicInstance | null) => boolean | void) {
  const hasError = ref(false)
  const lastError = ref<Error | null>(null)

  const instance = getCurrentInstance()

  if (instance) {
    onErrorCaptured((err: Error, vm: ComponentPublicInstance | null, info: string) => {
      hasError.value = true
      lastError.value = err
      logger.error(`[useErrorBoundary] Caught error in child component (${info}):`, err)
      const result = onError(err, vm)
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
