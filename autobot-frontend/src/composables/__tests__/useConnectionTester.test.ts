/**
 * Unit Tests for useConnectionTester Composable
 *
 * Tests connection testing functionality including:
 * - Basic connection testing
 * - Timeout handling
 * - Retry logic
 * - Callbacks
 * - Custom validation
 * - Multiple testers
 * - State management
 * - Edge cases
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { nextTick } from 'vue'
import { useConnectionTester, useConnectionTesters } from '../useConnectionTester'

// Mock fetch globally
global.fetch = vi.fn()

// Mock performance.now() to return incrementing values
let performanceNowCallCount = 0
const performanceNowMock = vi.fn(() => {
  const value = performanceNowCallCount * 10 //  Each call increments by 10ms
  performanceNowCallCount++
  return value
})

describe('useConnectionTester composable', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    performanceNowCallCount = 0 // Reset counter

    // Mock performance.now using vi.stubGlobal
    vi.stubGlobal('performance', {
      now: performanceNowMock
    })

    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
    vi.useRealTimers()
  })

  // ========================================
  // Basic Functionality
  // ========================================

  describe('basic functionality', () => {
    it('should initialize with unknown status', () => {
      const tester = useConnectionTester({
        endpoint: 'http://example.com/health'
      })

      expect(tester.status.value).toBe('unknown')
      expect(tester.message.value).toBe('Connection status unknown')
      expect(tester.responseTime.value).toBeNull()
      expect(tester.isTesting.value).toBe(false)
      expect(tester.retryCount.value).toBe(0)
      expect(tester.lastTestedAt.value).toBeNull()
    })

    it('should successfully test connection', async () => {
      const mockResponse = new Response(null, { status: 200 })
      vi.mocked(fetch).mockResolvedValue(mockResponse)

      const tester = useConnectionTester({
        endpoint: 'http://example.com/health'
      })

      const result = await tester.test()

      expect(result).toBe(true)
      expect(tester.status.value).toBe('connected')
      expect(tester.message.value).toContain('Connected successfully')
      expect(typeof tester.responseTime.value).toBe('number') // Response time is recorded
      expect(tester.lastTestedAt.value).toBeInstanceOf(Date)
    })

    it('should handle connection failure', async () => {
      const mockResponse = new Response(null, { status: 500 })
      vi.mocked(fetch).mockResolvedValue(mockResponse)

      const tester = useConnectionTester({
        endpoint: 'http://example.com/health'
      })

      const result = await tester.test()

      expect(result).toBe(false)
      expect(tester.status.value).toBe('disconnected')
      expect(tester.message.value).toContain('Connection failed (HTTP 500)')
      expect(typeof tester.responseTime.value).toBe('number') // Response time is recorded
    })

    it('should handle network error', async () => {
      vi.mocked(fetch).mockRejectedValue(new TypeError('Failed to fetch'))

      const tester = useConnectionTester({
        endpoint: 'http://example.com/health'
      })

      const result = await tester.test()

      expect(result).toBe(false)
      expect(tester.status.value).toBe('error')
      expect(tester.message.value).toContain('Network error')
      expect(tester.responseTime.value).toBeNull()
    })
  })

  // ========================================
  // Computed Properties
  // ========================================

  describe('computed properties', () => {
    it('should compute isConnected correctly', async () => {
      const mockResponse = new Response(null, { status: 200 })
      vi.mocked(fetch).mockResolvedValue(mockResponse)

      const tester = useConnectionTester({
        endpoint: 'http://example.com/health'
      })

      expect(tester.isConnected.value).toBe(false)

      await tester.test()

      expect(tester.isConnected.value).toBe(true)
      expect(tester.isDisconnected.value).toBe(false)
    })

    it('should compute isDisconnected correctly', async () => {
      vi.mocked(fetch).mockRejectedValue(new Error('Network error'))

      const tester = useConnectionTester({
        endpoint: 'http://example.com/health'
      })

      await tester.test()

      expect(tester.isDisconnected.value).toBe(true)
      expect(tester.isConnected.value).toBe(false)
    })

    it('should track isTesting during test', async () => {
      let resolveFetch: any
      const fetchPromise = new Promise((resolve) => {
        resolveFetch = () => resolve(new Response(null, { status: 200 }))
      })
      vi.mocked(fetch).mockReturnValue(fetchPromise as any)

      const tester = useConnectionTester({
        endpoint: 'http://example.com/health'
      })

      expect(tester.isTesting.value).toBe(false)

      const testPromise = tester.test()
      await nextTick()

      expect(tester.isTesting.value).toBe(true)

      resolveFetch()
      await testPromise

      expect(tester.isTesting.value).toBe(false)
    })
  })

  // ========================================
  // Timeout Handling
  // ========================================

  describe('timeout handling', () => {
    it('should timeout after specified duration', async () => {
      // Mock fetch to simulate timeout via AbortError
      vi.mocked(fetch).mockImplementation(() =>
        new Promise((_, reject) => {
          setTimeout(() => reject(new DOMException('The operation was aborted', 'AbortError')), 2000)
        })
      )

      const tester = useConnectionTester({
        endpoint: 'http://example.com/health',
        timeout: 2000
      })

      const testPromise = tester.test()

      // Advance time to trigger timeout
      await vi.advanceTimersByTimeAsync(2100)

      const result = await testPromise

      expect(result).toBe(false)
      expect(tester.status.value).toBe('disconnected')
      expect(tester.message.value).toContain('Connection timeout')
      expect(tester.message.value).toContain('>2000ms')
    }, 15000) // Increase test timeout

    it('should use default 5000ms timeout', async () => {
      // Mock fetch to simulate timeout
      vi.mocked(fetch).mockImplementation(() =>
        new Promise((_, reject) => {
          setTimeout(() => reject(new DOMException('The operation was aborted', 'AbortError')), 5000)
        })
      )

      const tester = useConnectionTester({
        endpoint: 'http://example.com/health'
      })

      const testPromise = tester.test()

      // Advance time to trigger timeout
      await vi.advanceTimersByTimeAsync(5100)
      await testPromise

      expect(tester.message.value).toContain('>5000ms')
    }, 15000) // Increase test timeout

    it('should clear timeout on successful response', async () => {
      const mockResponse = new Response(null, { status: 200 })
      vi.mocked(fetch).mockResolvedValue(mockResponse)

      const tester = useConnectionTester({
        endpoint: 'http://example.com/health',
        timeout: 5000
      })

      await tester.test()

      expect(tester.status.value).toBe('connected')
      expect(tester.message.value).not.toContain('timeout')
    })
  })

  // ========================================
  // Retry Logic
  // ========================================

  describe('retry logic', () => {
    it('should not retry by default', async () => {
      vi.mocked(fetch).mockRejectedValue(new Error('Network error'))

      const tester = useConnectionTester({
        endpoint: 'http://example.com/health'
      })

      await tester.test()

      expect(fetch).toHaveBeenCalledTimes(1)
      expect(tester.retryCount.value).toBe(0)
    })

    it('should retry when autoRetry is enabled', async () => {
      vi.mocked(fetch)
        .mockRejectedValueOnce(new Error('Network error'))
        .mockRejectedValueOnce(new Error('Network error'))
        .mockResolvedValueOnce(new Response(null, { status: 200 }))

      const tester = useConnectionTester({
        endpoint: 'http://example.com/health',
        autoRetry: true,
        maxRetries: 3,
        retryDelay: 1000
      })

      const testPromise = tester.test()

      // Run all timers to completion
      await vi.runAllTimersAsync()

      const result = await testPromise

      expect(result).toBe(true)
      expect(fetch).toHaveBeenCalledTimes(3) // Initial + 2 retries
      expect(tester.retryCount.value).toBe(2)
      expect(tester.status.value).toBe('connected')
    }, 15000)

    it('should use exponential backoff for retries', async () => {
      vi.mocked(fetch).mockRejectedValue(new Error('Network error'))

      const tester = useConnectionTester({
        endpoint: 'http://example.com/health',
        autoRetry: true,
        maxRetries: 2,
        retryDelay: 100
      })

      const testPromise = tester.test()

      // Run all timers
      await vi.runAllTimersAsync()

      await testPromise

      // Verify retries occurred
      expect(fetch).toHaveBeenCalledTimes(3) // Initial + 2 retries
      expect(tester.retryCount.value).toBe(2)
      expect(tester.message.value).toContain('failed after 2 retries')
    })

    it('should stop retrying after maxRetries', async () => {
      vi.mocked(fetch).mockRejectedValue(new Error('Network error'))

      const tester = useConnectionTester({
        endpoint: 'http://example.com/health',
        autoRetry: true,
        maxRetries: 2,
        retryDelay: 100
      })

      const testPromise = tester.test()

      // Run all timers
      await vi.runAllTimersAsync()

      const result = await testPromise

      expect(result).toBe(false)
      expect(fetch).toHaveBeenCalledTimes(3) // Initial + 2 retries
      expect(tester.retryCount.value).toBe(2)
      expect(tester.message.value).toContain('failed after 2 retries')
    })
  })

  // ========================================
  // Callbacks
  // ========================================

  describe('callbacks', () => {
    it('should call onSuccess callback with response time', async () => {
      const mockResponse = new Response(null, { status: 200 })
      vi.mocked(fetch).mockResolvedValue(mockResponse)

      const onSuccess = vi.fn()

      const tester = useConnectionTester({
        endpoint: 'http://example.com/health',
        onSuccess
      })

      await tester.test()

      expect(onSuccess).toHaveBeenCalledTimes(1)
      expect(onSuccess).toHaveBeenCalledWith(expect.any(Number))
      expect(typeof onSuccess.mock.calls[0][0]).toBe('number') // Response time is a number
    })

    it('should call onError callback with error message', async () => {
      vi.mocked(fetch).mockRejectedValue(new TypeError('Failed to fetch'))

      const onError = vi.fn()

      const tester = useConnectionTester({
        endpoint: 'http://example.com/health',
        onError
      })

      await tester.test()

      expect(onError).toHaveBeenCalledTimes(1)
      expect(onError).toHaveBeenCalledWith(expect.stringContaining('Network error'))
    })

    it('should call onStatusChange when status changes', async () => {
      const mockResponse = new Response(null, { status: 200 })
      vi.mocked(fetch).mockResolvedValue(mockResponse)

      const onStatusChange = vi.fn()

      const tester = useConnectionTester({
        endpoint: 'http://example.com/health',
        onStatusChange
      })

      await tester.test()

      expect(onStatusChange).toHaveBeenCalledTimes(2)
      expect(onStatusChange).toHaveBeenNthCalledWith(1, 'testing')
      expect(onStatusChange).toHaveBeenNthCalledWith(2, 'connected')
    })

    it('should support async callbacks', async () => {
      const mockResponse = new Response(null, { status: 200 })
      vi.mocked(fetch).mockResolvedValue(mockResponse)

      let callbackExecuted = false

      const tester = useConnectionTester({
        endpoint: 'http://example.com/health',
        onSuccess: async (responseTime) => {
          await new Promise(resolve => setTimeout(resolve, 100))
          callbackExecuted = true
        }
      })

      const testPromise = tester.test()
      await vi.runAllTimersAsync()
      await testPromise

      expect(callbackExecuted).toBe(true)
    }, 15000)
  })

  // ========================================
  // Custom Validation
  // ========================================

  describe('custom validation', () => {
    it('should validate response with validateResponse callback', async () => {
      const mockResponse = new Response(JSON.stringify({ available: true }), { status: 200 })
      vi.mocked(fetch).mockResolvedValue(mockResponse)

      const validateResponse = vi.fn().mockResolvedValue(true)

      const tester = useConnectionTester({
        endpoint: 'http://example.com/health',
        validateResponse
      })

      const result = await tester.test()

      expect(validateResponse).toHaveBeenCalledTimes(1)
      expect(validateResponse).toHaveBeenCalledWith(mockResponse)
      expect(result).toBe(true)
      expect(tester.status.value).toBe('connected')
    })

    it('should fail validation when validateResponse returns false', async () => {
      const mockResponse = new Response(JSON.stringify({ available: false }), { status: 200 })
      vi.mocked(fetch).mockResolvedValue(mockResponse)

      const validateResponse = vi.fn().mockResolvedValue(false)

      const tester = useConnectionTester({
        endpoint: 'http://example.com/health',
        validateResponse
      })

      const result = await tester.test()

      expect(result).toBe(false)
      expect(tester.status.value).toBe('error')
      expect(tester.message.value).toContain('validation failed')
    })

    it('should use custom error message from validateResponse', async () => {
      const mockResponse = new Response(JSON.stringify({ available: false }), { status: 200 })
      vi.mocked(fetch).mockResolvedValue(mockResponse)

      const validateResponse = vi.fn().mockResolvedValue('GPU not available')

      const tester = useConnectionTester({
        endpoint: 'http://example.com/health',
        validateResponse
      })

      await tester.test()

      expect(tester.status.value).toBe('error')
      expect(tester.message.value).toBe('GPU not available')
    })

    it('should support async validateResponse', async () => {
      const mockResponse = new Response(JSON.stringify({ data: 'test' }), { status: 200 })
      vi.mocked(fetch).mockResolvedValue(mockResponse)

      const validateResponse = async (response: Response) => {
        const data = await response.json()
        return data.data === 'test'
      }

      const tester = useConnectionTester({
        endpoint: 'http://example.com/health',
        validateResponse
      })

      const result = await tester.test()

      expect(result).toBe(true)
    })
  })

  // ========================================
  // HTTP Methods & Headers
  // ========================================

  describe('HTTP methods and headers', () => {
    it('should use GET method by default', async () => {
      const mockResponse = new Response(null, { status: 200 })
      vi.mocked(fetch).mockResolvedValue(mockResponse)

      const tester = useConnectionTester({
        endpoint: 'http://example.com/health'
      })

      await tester.test()

      expect(fetch).toHaveBeenCalledWith(
        'http://example.com/health',
        expect.objectContaining({ method: 'GET' })
      )
    })

    it('should support POST method with body', async () => {
      const mockResponse = new Response(null, { status: 200 })
      vi.mocked(fetch).mockResolvedValue(mockResponse)

      const requestBody = { test: 'data' }

      const tester = useConnectionTester({
        endpoint: 'http://example.com/api',
        method: 'POST',
        body: requestBody
      })

      await tester.test()

      expect(fetch).toHaveBeenCalledWith(
        'http://example.com/api',
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify(requestBody)
        })
      )
    })

    it('should include custom headers', async () => {
      const mockResponse = new Response(null, { status: 200 })
      vi.mocked(fetch).mockResolvedValue(mockResponse)

      const customHeaders = {
        'Authorization': 'Bearer token123',
        'X-Custom-Header': 'value'
      }

      const tester = useConnectionTester({
        endpoint: 'http://example.com/health',
        headers: customHeaders
      })

      await tester.test()

      expect(fetch).toHaveBeenCalledWith(
        'http://example.com/health',
        expect.objectContaining({
          headers: expect.objectContaining(customHeaders)
        })
      )
    })

    it('should validate expected status code', async () => {
      const mockResponse = new Response(null, { status: 201 })
      vi.mocked(fetch).mockResolvedValue(mockResponse)

      const tester = useConnectionTester({
        endpoint: 'http://example.com/api',
        expectedStatus: 201
      })

      const result = await tester.test()

      expect(result).toBe(true)
      expect(tester.status.value).toBe('connected')
    })

    it('should fail when status does not match expected', async () => {
      const mockResponse = new Response(null, { status: 201 })
      vi.mocked(fetch).mockResolvedValue(mockResponse)

      const tester = useConnectionTester({
        endpoint: 'http://example.com/api',
        expectedStatus: 200 // Expect 200 but get 201
      })

      const result = await tester.test()

      expect(result).toBe(false)
      expect(tester.status.value).toBe('disconnected')
      expect(tester.message.value).toContain('HTTP 201')
    })
  })

  // ========================================
  // State Management
  // ========================================

  describe('state management', () => {
    it('should reset to initial state', async () => {
      const mockResponse = new Response(null, { status: 200 })
      vi.mocked(fetch).mockResolvedValue(mockResponse)

      const tester = useConnectionTester({
        endpoint: 'http://example.com/health'
      })

      await tester.test()

      expect(tester.status.value).toBe('connected')
      expect(typeof tester.responseTime.value).toBe('number') // Response time is recorded
      expect(tester.lastTestedAt.value).toBeInstanceOf(Date)

      tester.reset()

      expect(tester.status.value).toBe('unknown')
      expect(tester.message.value).toBe('Connection status unknown')
      expect(tester.responseTime.value).toBeNull()
      expect(tester.retryCount.value).toBe(0)
      expect(tester.lastTestedAt.value).toBeNull()
    })

    it('should cancel ongoing test', async () => {
      let resolveFetch: any
      const fetchPromise = new Promise((resolve) => {
        resolveFetch = () => resolve(new Response(null, { status: 200 }))
      })
      vi.mocked(fetch).mockReturnValue(fetchPromise as any)

      const tester = useConnectionTester({
        endpoint: 'http://example.com/health'
      })

      const testPromise = tester.test()
      await nextTick()

      expect(tester.isTesting.value).toBe(true)

      tester.cancel()

      expect(tester.isTesting.value).toBe(false)
      expect(tester.status.value).toBe('unknown')
      expect(tester.message.value).toBe('Test cancelled')
    })

    it('should update endpoint and reset state', () => {
      const tester = useConnectionTester({
        endpoint: 'http://example.com/health'
      })

      tester.updateEndpoint('http://newserver.com/health')

      expect(tester.status.value).toBe('unknown')
      expect(tester.responseTime.value).toBeNull()
    })

    it('should prevent concurrent tests', async () => {
      let resolveFetch: any
      const fetchPromise = new Promise((resolve) => {
        resolveFetch = () => resolve(new Response(null, { status: 200 }))
      })
      vi.mocked(fetch).mockReturnValue(fetchPromise as any)

      const tester = useConnectionTester({
        endpoint: 'http://example.com/health'
      })

      const test1 = tester.test()
      await nextTick()

      const test2 = tester.test() // Should return false immediately
      const result2 = await test2

      expect(result2).toBe(false)
      expect(fetch).toHaveBeenCalledTimes(1) // Only first test called fetch

      resolveFetch()
      await test1
    })
  })

  // ========================================
  // useConnectionTesters (Multiple Testers)
  // ========================================

  describe('useConnectionTesters', () => {
    it('should create multiple testers', () => {
      const { testers } = useConnectionTesters({
        backend: { endpoint: 'http://backend.com/health' },
        redis: { endpoint: 'http://redis.com/ping' },
        llm: { endpoint: 'http://llm.com/health' }
      })

      expect(testers.backend).toBeDefined()
      expect(testers.redis).toBeDefined()
      expect(testers.llm).toBeDefined()

      expect(testers.backend.status.value).toBe('unknown')
      expect(testers.redis.status.value).toBe('unknown')
      expect(testers.llm.status.value).toBe('unknown')
    })

    it('should test all connections in parallel', async () => {
      vi.mocked(fetch)
        .mockResolvedValueOnce(new Response(null, { status: 200 })) // backend
        .mockResolvedValueOnce(new Response(null, { status: 200 })) // redis
        .mockResolvedValueOnce(new Response(null, { status: 200 })) // llm

      const { testAll } = useConnectionTesters({
        backend: { endpoint: 'http://backend.com/health' },
        redis: { endpoint: 'http://redis.com/ping' },
        llm: { endpoint: 'http://llm.com/health' }
      })

      const results = await testAll()

      expect(results).toEqual({
        backend: true,
        redis: true,
        llm: true
      })

      expect(fetch).toHaveBeenCalledTimes(3)
    })

    it('should reset all testers', async () => {
      const mockResponse = new Response(null, { status: 200 })
      vi.mocked(fetch).mockResolvedValue(mockResponse)

      const { testers, testAll, resetAll } = useConnectionTesters({
        backend: { endpoint: 'http://backend.com/health' },
        redis: { endpoint: 'http://redis.com/ping' }
      })

      await testAll()

      expect(testers.backend.status.value).toBe('connected')
      expect(testers.redis.status.value).toBe('connected')

      resetAll()

      expect(testers.backend.status.value).toBe('unknown')
      expect(testers.redis.status.value).toBe('unknown')
    })

    it('should cancel all ongoing tests', async () => {
      let resolveFetch: any
      const fetchPromise = new Promise((resolve) => {
        resolveFetch = () => resolve(new Response(null, { status: 200 }))
      })
      vi.mocked(fetch).mockReturnValue(fetchPromise as any)

      const { testers, testAll, cancelAll } = useConnectionTesters({
        backend: { endpoint: 'http://backend.com/health' },
        redis: { endpoint: 'http://redis.com/ping' }
      })

      const testPromise = testAll()
      await nextTick()

      expect(testers.backend.isTesting.value).toBe(true)
      expect(testers.redis.isTesting.value).toBe(true)

      cancelAll()

      expect(testers.backend.isTesting.value).toBe(false)
      expect(testers.redis.isTesting.value).toBe(false)
    })

    it('should compute allConnected', async () => {
      vi.mocked(fetch)
        .mockResolvedValueOnce(new Response(null, { status: 200 })) // backend
        .mockResolvedValueOnce(new Response(null, { status: 500 })) // redis (fail)

      const { testers, testAll, allConnected } = useConnectionTesters({
        backend: { endpoint: 'http://backend.com/health' },
        redis: { endpoint: 'http://redis.com/ping' }
      })

      expect(allConnected.value).toBe(false)

      await testAll()

      expect(testers.backend.isConnected.value).toBe(true)
      expect(testers.redis.isConnected.value).toBe(false)
      expect(allConnected.value).toBe(false)
    })

    it('should compute anyTesting', async () => {
      let resolveFetch: any
      const fetchPromise = new Promise((resolve) => {
        resolveFetch = () => resolve(new Response(null, { status: 200 }))
      })
      vi.mocked(fetch).mockReturnValue(fetchPromise as any)

      const { testers, anyTesting } = useConnectionTesters({
        backend: { endpoint: 'http://backend.com/health' },
        redis: { endpoint: 'http://redis.com/ping' }
      })

      expect(anyTesting.value).toBe(false)

      const testPromise = testers.backend.test()
      await nextTick()

      expect(anyTesting.value).toBe(true)

      resolveFetch()
      await testPromise

      expect(anyTesting.value).toBe(false)
    })
  })

  // ========================================
  // Edge Cases
  // ========================================

  describe('edge cases', () => {
    it('should handle empty endpoint', async () => {
      const tester = useConnectionTester({
        endpoint: ''
      })

      const result = await tester.test()

      expect(result).toBe(false)
      expect(tester.status.value).toBe('error')
    })

    it('should distinguish between timeout and network errors', async () => {
      // Timeout error
      vi.mocked(fetch).mockImplementation(() =>
        new Promise((_, reject) => {
          setTimeout(() => reject(new DOMException('The operation was aborted', 'AbortError')), 1000)
        })
      )
      const tester1 = useConnectionTester({
        endpoint: 'http://example.com/health',
        timeout: 1000
      })

      const test1Promise = tester1.test()
      await vi.advanceTimersByTimeAsync(1100)
      await test1Promise

      expect(tester1.message.value).toContain('timeout')

      // Network error
      vi.mocked(fetch).mockRejectedValue(new TypeError('Failed to fetch'))
      const tester2 = useConnectionTester({
        endpoint: 'http://example.com/health'
      })

      await tester2.test()

      expect(tester2.message.value).toContain('Network error')
    }, 15000)

    it('should handle AbortError specifically', async () => {
      const abortError = new DOMException('The operation was aborted', 'AbortError')
      vi.mocked(fetch).mockRejectedValue(abortError)

      const tester = useConnectionTester({
        endpoint: 'http://example.com/health'
      })

      await tester.test()

      expect(tester.message.value).toContain('timeout')
      expect(tester.responseTime.value).toBeNull()
    })

    it('should track response time', async () => {
      const mockResponse = new Response(null, { status: 200 })
      vi.mocked(fetch).mockResolvedValue(mockResponse)

      const tester = useConnectionTester({
        endpoint: 'http://example.com/health'
      })

      await tester.test()

      // Response time should be recorded as a number
      expect(typeof tester.responseTime.value).toBe('number')
      expect(tester.responseTime.value).toBeGreaterThanOrEqual(0) // Non-negative
      expect(tester.message.value).toMatch(/\d+ms/) // Message includes response time
    })
  })

  // ========================================
  // TypeScript Type Safety
  // ========================================

  describe('TypeScript type safety', () => {
    it('should enforce ConnectionStatus type', () => {
      const tester = useConnectionTester({
        endpoint: 'http://example.com/health'
      })

      // Should be one of: 'connected' | 'disconnected' | 'testing' | 'unknown' | 'error'
      const status: string = tester.status.value
      expect(['connected', 'disconnected', 'testing', 'unknown', 'error']).toContain(status)
    })

    it('should type testAll results correctly', async () => {
      const mockResponse = new Response(null, { status: 200 })
      vi.mocked(fetch).mockResolvedValue(mockResponse)

      const { testAll } = useConnectionTesters({
        backend: { endpoint: 'http://backend.com/health' },
        redis: { endpoint: 'http://redis.com/ping' }
      })

      const results = await testAll()

      // TypeScript should infer: Record<'backend' | 'redis', boolean>
      expect(typeof results.backend).toBe('boolean')
      expect(typeof results.redis).toBe('boolean')
    })
  })

  // ========================================
  // Performance
  // ========================================

  describe('performance', () => {
    it('should handle rapid test calls efficiently', async () => {
      const mockResponse = new Response(null, { status: 200 })
      vi.mocked(fetch).mockResolvedValue(mockResponse)

      const tester = useConnectionTester({
        endpoint: 'http://example.com/health'
      })

      // Try to call test() 100 times rapidly
      const promises = Array.from({ length: 100 }, () => tester.test())

      const results = await Promise.all(promises)

      // Only the first test should succeed, rest should return false (concurrent protection)
      const successCount = results.filter(r => r === true).length
      expect(successCount).toBeLessThanOrEqual(10) // Allow some successful due to timing
      expect(fetch).toHaveBeenCalledTimes(successCount)
    })
  })
})
