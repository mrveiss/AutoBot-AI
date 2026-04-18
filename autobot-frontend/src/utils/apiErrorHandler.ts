/**
 * API Error Handler Utility
 *
 * Provides standardized error handling for all API calls across the application.
 * Features:
 * - Consistent error message extraction
 * - Toast notifications for user feedback
 * - Retry logic for transient failures
 * - Loading state management helpers
 *
 * @module apiErrorHandler
 */

import { ref, type Ref } from 'vue'
import { createLogger } from '@/utils/debugUtils'
import { useUnifiedLoading } from '@/composables/useUnifiedLoading'

// Create scoped logger for apiErrorHandler
const logger = createLogger('apiErrorHandler')

/**
 * Standard API error structure
 */
export interface ApiError {
  message: string
  code?: string
  status?: number
  details?: Record<string, unknown>
  isNetworkError: boolean
  isTimeout: boolean
  isServerError: boolean
  isClientError: boolean
  retryable: boolean
}

/**
 * Options for error handling
 */
export interface ErrorHandlerOptions {
  /** Show toast notification on error (default: true) */
  showToast?: boolean
  /** Custom error message to display instead of API error */
  customMessage?: string
  /** Whether to log error to console (default: true) */
  logError?: boolean
  /** Component name for error context */
  componentName?: string
  /** Number of retry attempts for transient failures (default: 0) */
  retryCount?: number
  /** Delay between retries in ms (default: 1000) */
  retryDelay?: number
  /** Callback function on error */
  onError?: (error: ApiError) => void
}

/**
 * Result type for API calls with error handling
 */
export interface ApiResult<T> {
  success: boolean
  data?: T
  error?: ApiError
}

/**
 * Default error handler options
 */
const DEFAULT_OPTIONS: ErrorHandlerOptions = {
  showToast: true,
  logError: true,
  retryCount: 0,
  retryDelay: 1000
}

/**
 * Parse error from various sources into standardized ApiError
 */
export function parseError(error: unknown): ApiError {
  const apiError: ApiError = {
    message: 'An unexpected error occurred',
    isNetworkError: false,
    isTimeout: false,
    isServerError: false,
    isClientError: false,
    retryable: false
  }

  if (error instanceof Error) {
    apiError.message = error.message

    // Check for network errors
    if (error.message.includes('Failed to fetch') ||
        error.message.includes('Network request failed') ||
        error.message.includes('NetworkError')) {
      apiError.isNetworkError = true
      apiError.retryable = true
      apiError.message = 'Network connection failed. Please check your connection.'
    }

    // Check for timeout errors
    if (error.message.includes('timeout') ||
        error.message.includes('AbortError') ||
        error.name === 'AbortError') {
      apiError.isTimeout = true
      apiError.retryable = true
      apiError.message = 'Request timed out. Please try again.'
    }
  }

  // Handle Response objects
  if (typeof error === 'object' && error !== null) {
    const errObj = error as Record<string, unknown>

    if ('status' in errObj && typeof errObj.status === 'number') {
      apiError.status = errObj.status

      // Categorize by status code
      if (errObj.status >= 500) {
        apiError.isServerError = true
        apiError.retryable = true
        apiError.message = 'Server error. Please try again later.'
      } else if (errObj.status >= 400) {
        apiError.isClientError = true
        apiError.retryable = false
      }
    }

    // Extract message from various formats
    if ('message' in errObj && typeof errObj.message === 'string') {
      apiError.message = errObj.message
    } else if ('error' in errObj && typeof errObj.error === 'string') {
      apiError.message = errObj.error
    } else if ('detail' in errObj && typeof errObj.detail === 'string') {
      apiError.message = errObj.detail
    }

    // Extract error code
    if ('code' in errObj && typeof errObj.code === 'string') {
      apiError.code = errObj.code
    }

    // Extract details
    if ('details' in errObj && typeof errObj.details === 'object') {
      apiError.details = errObj.details as Record<string, unknown>
    }
  }

  return apiError
}

/**
 * Display toast notification for error
 * Uses native browser alert as fallback if no toast library is available
 */
export function showErrorToast(error: ApiError, options: ErrorHandlerOptions = {}): void {
  const message = options.customMessage || error.message

  // Try to use Vue notification system if available
  if (typeof window !== 'undefined') {
    // Check for common toast libraries using unknown intermediate cast
    const windowAny = window as unknown as Record<string, unknown>

    // Element Plus toast
    if (windowAny.$toast && typeof (windowAny.$toast as Record<string, unknown>).error === 'function') {
      (windowAny.$toast as { error: (msg: string) => void }).error(message)
      return
    }

    // Element Plus message
    if (windowAny.ElMessage && typeof (windowAny.ElMessage as Record<string, unknown>).error === 'function') {
      (windowAny.ElMessage as { error: (msg: string) => void }).error(message)
      return
    }

    // Dispatch custom event for app-level error handling
    window.dispatchEvent(new CustomEvent('api-error', {
      detail: { error, message, options }
    }))
  }

  // Console warning as final fallback
  logger.warn(`[API Error] ${message}`)
}

/**
 * Log error with context
 */
export function logApiError(error: ApiError, options: ErrorHandlerOptions = {}): void {
  const context = options.componentName ? `[${options.componentName}]` : '[API]'
  logger.error(`${context} API Error:`, {
    message: error.message,
    code: error.code,
    status: error.status,
    isNetworkError: error.isNetworkError,
    isTimeout: error.isTimeout,
    isServerError: error.isServerError,
    retryable: error.retryable
  })
}

/**
 * Sleep utility for retry delays
 */
function sleep(ms: number): Promise<void> {
  return new Promise(resolve => setTimeout(resolve, ms))
}

/**
 * Wrap an async API call with error handling
 *
 * @param apiCall - The async function to execute
 * @param options - Error handling options
 * @returns ApiResult with success status and data or error
 *
 * @example
 * ```typescript
 * const result = await handleApiCall(
 *   () => apiClient.get('/api/users'),
 *   { componentName: 'UserList', showToast: true }
 * )
 *
 * if (result.success) {
 *   users.value = result.data
 * }
 * ```
 */
export async function handleApiCall<T>(
  apiCall: () => Promise<T>,
  options: ErrorHandlerOptions = {}
): Promise<ApiResult<T>> {
  const opts = { ...DEFAULT_OPTIONS, ...options }
  let lastError: ApiError | null = null
  let attempts = 0
  const maxAttempts = (opts.retryCount || 0) + 1

  while (attempts < maxAttempts) {
    attempts++

    try {
      const data = await apiCall()
      return { success: true, data }
    } catch (error) {
      lastError = parseError(error)

      // Log error
      if (opts.logError) {
        logApiError(lastError, opts)
      }

      // Check if we should retry
      const shouldRetry = lastError.retryable && attempts < maxAttempts
      if (shouldRetry) {
        logger.info(`[API] Retrying request (attempt ${attempts + 1}/${maxAttempts})...`)
        await sleep(opts.retryDelay || 1000)
        continue
      }

      // No more retries - handle the error
      if (opts.showToast) {
        showErrorToast(lastError, opts)
      }

      if (opts.onError) {
        opts.onError(lastError)
      }

      return { success: false, error: lastError }
    }
  }

  // Should not reach here, but return error just in case
  return { success: false, error: lastError || parseError(new Error('Unknown error')) }
}

/**
 * Create a composable that wraps API calls with loading state
 *
 * Loading-state tracking is delegated to the canonical `useUnifiedLoading`
 * composable. The structured `ApiError` shape is preserved — callers of
 * `useApiRequest` see the same `{ loading, error, execute }` surface, with
 * `error` typed as `ApiError | null` (not a plain string).
 *
 * @param componentKey Optional key for scoping the shared loading state
 *                     registry; defaults to a unique per-instance key.
 * @returns API call wrapper with built-in loading state
 *
 * @example
 * ```typescript
 * const { loading, error, execute } = useApiRequest('UserList')
 *
 * const result = await execute(
 *   () => apiClient.get('/api/users'),
 *   { componentName: 'UserList' }
 * )
 * ```
 */
export function useApiRequest<T = unknown>(componentKey?: string) {
  const unified = useUnifiedLoading(componentKey)
  const error: Ref<ApiError | null> = ref(null)

  async function execute(
    apiCall: () => Promise<T>,
    options: ErrorHandlerOptions = {}
  ): Promise<ApiResult<T>> {
    error.value = null
    unified.setLoading(true)

    const result = await handleApiCall(apiCall, options)

    if (!result.success && result.error) {
      error.value = result.error
    }

    unified.setLoading(false)
    return result
  }

  return {
    loading: unified.isLoading,
    error,
    execute
  }
}

// Export default options for customization
export { DEFAULT_OPTIONS }
