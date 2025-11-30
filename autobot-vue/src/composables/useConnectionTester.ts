/**
 * Connection Tester Composable
 *
 * Centralized connection testing to eliminate duplicate test logic across components.
 * Supports health checks, timeout handling, response time tracking, and status management.
 *
 * Features:
 * - Connection status tracking (connected/disconnected/testing/unknown/error)
 * - Response time measurement with performance metrics
 * - Configurable timeout handling
 * - Automatic retry logic with exponential backoff
 * - Success/failure callbacks
 * - Multiple connection tester management
 * - TypeScript type safety
 *
 * Usage:
 * ```typescript
 * import { useConnectionTester } from '@/composables/useConnectionTester'
 * import { NetworkConstants } from '@/constants/network'
 *
 * const backendTest = useConnectionTester({
 *   endpoint: `${NetworkConstants.getBackendUrl()}/api/health`,
 *   timeout: 5000,
 *   onSuccess: (responseTime) => console.log(`Connected in ${responseTime}ms`),
 *   onError: (error) => console.error('Connection failed:', error)
 * })
 *
 * // In template or methods
 * await backendTest.test()
 * console.log(backendTest.status.value) // 'connected' | 'disconnected' | 'testing'
 * console.log(backendTest.responseTime.value) // 245 (ms)
 * ```
 */

import { ref, computed, type Ref, type ComputedRef } from 'vue'
import { createLogger } from '@/utils/debugUtils'

// Create scoped logger for useConnectionTester
const logger = createLogger('useConnectionTester')

// ========================================
// Types & Interfaces
// ========================================

export type ConnectionStatus = 'connected' | 'disconnected' | 'testing' | 'unknown' | 'error'

export interface ConnectionTestOptions {
  /**
   * Health check endpoint URL
   */
  endpoint: string

  /**
   * HTTP method (default: 'GET')
   */
  method?: 'GET' | 'POST' | 'HEAD'

  /**
   * Request timeout in milliseconds (default: 5000)
   */
  timeout?: number

  /**
   * Custom headers for the request
   */
  headers?: Record<string, string>

  /**
   * Request body (for POST requests)
   */
  body?: any

  /**
   * Expected response status code (default: 200)
   */
  expectedStatus?: number

  /**
   * Callback on successful connection
   * @param responseTime - Response time in milliseconds
   */
  onSuccess?: (responseTime: number) => void | Promise<void>

  /**
   * Callback on connection failure
   * @param error - Error message or object
   */
  onError?: (error: string | Error) => void | Promise<void>

  /**
   * Callback when test status changes
   * @param status - New connection status
   */
  onStatusChange?: (status: ConnectionStatus) => void | Promise<void>

  /**
   * Enable automatic retry on failure (default: false)
   */
  autoRetry?: boolean

  /**
   * Number of retry attempts (default: 3)
   */
  maxRetries?: number

  /**
   * Retry delay in milliseconds (default: 1000)
   * Uses exponential backoff: delay * (2 ^ attempt)
   */
  retryDelay?: number

  /**
   * Custom validation function for response
   * @param response - Fetch Response object
   * @returns true if valid, false or error message if invalid
   */
  validateResponse?: (response: Response) => boolean | string | Promise<boolean | string>
}

export interface UseConnectionTesterReturn {
  /**
   * Current connection status
   */
  status: Ref<ConnectionStatus>

  /**
   * Status message (human-readable)
   */
  message: Ref<string>

  /**
   * Response time in milliseconds (null if not tested or failed)
   */
  responseTime: Ref<number | null>

  /**
   * Is currently testing
   */
  isTesting: Readonly<Ref<boolean>>

  /**
   * Is connected (status === 'connected')
   */
  isConnected: ComputedRef<boolean>

  /**
   * Is disconnected (status === 'disconnected' || status === 'error')
   */
  isDisconnected: ComputedRef<boolean>

  /**
   * Number of retry attempts made (when autoRetry enabled)
   */
  retryCount: Readonly<Ref<number>>

  /**
   * Last test timestamp
   */
  lastTestedAt: Readonly<Ref<Date | null>>

  /**
   * Test the connection
   */
  test: () => Promise<boolean>

  /**
   * Reset to initial state
   */
  reset: () => void

  /**
   * Cancel ongoing test
   */
  cancel: () => void

  /**
   * Update endpoint URL
   */
  updateEndpoint: (newEndpoint: string) => void
}

// ========================================
// Main Composable
// ========================================

/**
 * Create connection tester
 *
 * @param options - Connection test configuration
 * @returns Connection tester state and methods
 *
 * @example
 * ```typescript
 * import { NetworkConstants } from '@/constants/network'
 *
 * const backendTest = useConnectionTester({
 *   endpoint: `${NetworkConstants.getBackendUrl()}/api/health`,
 *   timeout: 5000,
 *   onSuccess: (time) => console.log(`Connected in ${time}ms`)
 * })
 *
 * await backendTest.test()
 * ```
 */
export function useConnectionTester(
  options: ConnectionTestOptions
): UseConnectionTesterReturn {
  const {
    endpoint: initialEndpoint,
    method = 'GET',
    timeout = 5000,
    headers = {},
    body = null,
    expectedStatus = 200,
    onSuccess,
    onError,
    onStatusChange,
    autoRetry = false,
    maxRetries = 3,
    retryDelay = 1000,
    validateResponse
  } = options

  // State
  const endpoint = ref<string>(initialEndpoint)
  const status = ref<ConnectionStatus>('unknown')
  const message = ref<string>('Connection status unknown')
  const responseTime = ref<number | null>(null)
  const isTesting = ref<boolean>(false)
  const retryCount = ref<number>(0)
  const lastTestedAt = ref<Date | null>(null)

  // Abort controller for cancellation
  let abortController: AbortController | null = null

  // Computed properties
  const isConnected = computed(() => status.value === 'connected')
  const isDisconnected = computed(() =>
    status.value === 'disconnected' || status.value === 'error'
  )

  /**
   * Update status and trigger callback
   */
  const updateStatus = async (newStatus: ConnectionStatus, newMessage: string): Promise<void> => {
    status.value = newStatus
    message.value = newMessage

    if (onStatusChange) {
      await onStatusChange(newStatus)
    }
  }

  /**
   * Perform connection test with timeout
   */
  const performTest = async (): Promise<boolean> => {
    // Create abort controller for timeout
    abortController = new AbortController()
    const timeoutId = setTimeout(() => abortController?.abort(), timeout)

    try {
      const startTime = performance.now()

      // Prepare request options
      const requestOptions: RequestInit = {
        method,
        headers: {
          'Content-Type': 'application/json',
          ...headers
        },
        signal: abortController.signal
      }

      if (body && method !== 'GET' && method !== 'HEAD') {
        requestOptions.body = typeof body === 'string' ? body : JSON.stringify(body)
      }

      // Make request
      const response = await fetch(endpoint.value, requestOptions)

      clearTimeout(timeoutId)
      const endTime = performance.now()
      const measuredResponseTime = Math.round(endTime - startTime)
      responseTime.value = measuredResponseTime

      // Validate response status
      if (response.status !== expectedStatus) {
        await updateStatus('disconnected', `Connection failed (HTTP ${response.status})`)
        if (onError) {
          await onError(`HTTP ${response.status}: ${response.statusText}`)
        }
        return false
      }

      // Custom response validation
      if (validateResponse) {
        const validationResult = await validateResponse(response)
        if (validationResult !== true) {
          const errorMsg = typeof validationResult === 'string'
            ? validationResult
            : 'Response validation failed'
          await updateStatus('error', errorMsg)
          if (onError) {
            await onError(errorMsg)
          }
          return false
        }
      }

      // Success
      await updateStatus('connected', `Connected successfully (${measuredResponseTime}ms)`)
      lastTestedAt.value = new Date()

      if (onSuccess) {
        await onSuccess(measuredResponseTime)
      }

      return true

    } catch (error: any) {
      clearTimeout(timeoutId)

      // Handle different error types
      let errorMessage: string

      if (error.name === 'AbortError') {
        errorMessage = `Connection timeout (>${timeout}ms)`
        await updateStatus('disconnected', errorMessage)
      } else if (error instanceof TypeError) {
        errorMessage = `Network error: ${error.message}`
        await updateStatus('error', errorMessage)
      } else {
        errorMessage = error.message || 'Unknown connection error'
        await updateStatus('error', errorMessage)
      }

      responseTime.value = null

      if (onError) {
        await onError(errorMessage)
      }

      return false

    } finally {
      abortController = null
    }
  }

  /**
   * Test connection with optional retry logic
   */
  const test = async (): Promise<boolean> => {
    // Prevent concurrent tests
    if (isTesting.value) {
      logger.warn('Test already in progress')
      return false
    }

    isTesting.value = true
    retryCount.value = 0
    await updateStatus('testing', 'Testing connection...')

    try {
      let attempt = 0
      let success = false

      while (attempt <= (autoRetry ? maxRetries : 0)) {
        if (attempt > 0) {
          // Exponential backoff: delay * (2 ^ attempt)
          const delay = retryDelay * Math.pow(2, attempt - 1)
          await updateStatus('testing', `Retrying... (attempt ${attempt}/${maxRetries})`)
          await new Promise(resolve => setTimeout(resolve, delay))
          retryCount.value = attempt
        }

        success = await performTest()

        if (success) {
          return true
        }

        attempt++

        // Don't retry if autoRetry is disabled
        if (!autoRetry) {
          break
        }
      }

      // All attempts failed
      if (autoRetry && retryCount.value > 0) {
        await updateStatus('disconnected', `Connection failed after ${retryCount.value} retries`)
      }

      return false

    } finally {
      isTesting.value = false
    }
  }

  /**
   * Reset to initial state
   */
  const reset = (): void => {
    status.value = 'unknown'
    message.value = 'Connection status unknown'
    responseTime.value = null
    retryCount.value = 0
    lastTestedAt.value = null

    if (abortController) {
      abortController.abort()
      abortController = null
    }
  }

  /**
   * Cancel ongoing test
   */
  const cancel = (): void => {
    if (isTesting.value && abortController) {
      abortController.abort()
      abortController = null
      isTesting.value = false
      updateStatus('unknown', 'Test cancelled')
    }
  }

  /**
   * Update endpoint URL
   */
  const updateEndpoint = (newEndpoint: string): void => {
    endpoint.value = newEndpoint
    reset()
  }

  return {
    status,
    message,
    responseTime,
    isTesting: computed(() => isTesting.value),
    isConnected,
    isDisconnected,
    retryCount: computed(() => retryCount.value),
    lastTestedAt: computed(() => lastTestedAt.value),
    test,
    reset,
    cancel,
    updateEndpoint
  }
}

// ========================================
// Multi-Connection Tester Helper
// ========================================

/**
 * Create multiple connection testers
 *
 * @param configs - Object mapping names to connection test options
 * @returns Object mapping names to connection testers
 *
 * @example
 * ```typescript
 * import { NetworkConstants } from '@/constants/network'
 *
 * const { testers, testAll, resetAll } = useConnectionTesters({
 *   backend: { endpoint: `${NetworkConstants.getBackendUrl()}/api/health` },
 *   redis: { endpoint: `http://${NetworkConstants.REDIS_VM_IP}:${NetworkConstants.REDIS_PORT}/ping` },
 *   llm: { endpoint: `http://${NetworkConstants.AI_STACK_VM_IP}:${NetworkConstants.OLLAMA_PORT}/api/tags` }
 * })
 *
 * await testAll() // Test all connections in parallel
 * ```
 */
export function useConnectionTesters<T extends string>(
  configs: Record<T, ConnectionTestOptions>
): {
  testers: Record<T, UseConnectionTesterReturn>
  testAll: () => Promise<Record<T, boolean>>
  resetAll: () => void
  cancelAll: () => void
  allConnected: ComputedRef<boolean>
  anyTesting: ComputedRef<boolean>
} {
  const testers = {} as Record<T, UseConnectionTesterReturn>

  // Create tester for each config
  for (const [name, config] of Object.entries(configs) as [T, ConnectionTestOptions][]) {
    testers[name] = useConnectionTester(config)
  }

  /**
   * Test all connections in parallel
   */
  const testAll = async (): Promise<Record<T, boolean>> => {
    const results = await Promise.all(
      Object.entries(testers).map(async ([name, tester]) => {
        const success = await (tester as UseConnectionTesterReturn).test()
        return [name, success] as [T, boolean]
      })
    )

    return Object.fromEntries(results) as Record<T, boolean>
  }

  /**
   * Reset all testers
   */
  const resetAll = (): void => {
    for (const tester of Object.values(testers)) {
      (tester as UseConnectionTesterReturn).reset()
    }
  }

  /**
   * Cancel all ongoing tests
   */
  const cancelAll = (): void => {
    for (const tester of Object.values(testers)) {
      (tester as UseConnectionTesterReturn).cancel()
    }
  }

  /**
   * Are all connections connected
   */
  const allConnected = computed(() => {
    return Object.values(testers).every(
      tester => (tester as UseConnectionTesterReturn).isConnected.value
    )
  })

  /**
   * Is any connection currently testing
   */
  const anyTesting = computed(() => {
    return Object.values(testers).some(
      tester => (tester as UseConnectionTesterReturn).isTesting.value
    )
  })

  return {
    testers,
    testAll,
    resetAll,
    cancelAll,
    allConnected,
    anyTesting
  }
}
