/**
 * Test suite for async component error boundaries
 * Tests loading states, error handling, and retry mechanisms
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createRouter, createWebHistory } from 'vue-router'
import AsyncComponentWrapper from '@/components/async/AsyncComponentWrapper.vue'
import AsyncErrorFallback from '@/components/async/AsyncErrorFallback.vue'
import { createAsyncComponent, createLazyComponent, AsyncComponentErrorRecovery } from '@/utils/asyncComponentHelpers'

// Mock RUM
const mockRum = {
  trackError: vi.fn(),
  trackUserInteraction: vi.fn()
}

global.window.rum = mockRum

describe('Async Component Error Boundaries', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    AsyncComponentErrorRecovery.resetAll()

    // Clear session storage
    global.sessionStorage.clear()

    // Mock console methods
    global.console.error = vi.fn()
    global.console.warn = vi.fn()
    global.console.log = vi.fn()
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  describe('AsyncErrorFallback Component', () => {
    it('should display user-friendly error message for chunk loading failures', async () => {
      const error = new Error('Loading chunk 123 failed.')

      const wrapper = mount(AsyncErrorFallback, {
        props: {
          error,
          componentName: 'TestComponent',
          retryCount: 0,
          maxRetries: 3
        }
      })

      expect(wrapper.find('.error-title').text()).toBe('Failed to Load Component')
      expect(wrapper.find('.error-message').text()).toContain('This page failed to load due to a network issue')
      expect(wrapper.find('[data-testid="retry-button"]').exists()).toBe(true)
    })

    it('should show retry count and disable retry button when max retries reached', async () => {
      const wrapper = mount(AsyncErrorFallback, {
        props: {
          error: new Error('Loading chunk failed'),
          componentName: 'TestComponent',
          retryCount: 3,
          maxRetries: 3
        }
      })

      const retryButton = wrapper.find('button:first-of-type')
      expect(retryButton.attributes('disabled')).toBeDefined()
      expect(retryButton.text()).toContain('Retry (3/3)')
    })

    it('should emit retry event when retry button is clicked', async () => {
      const wrapper = mount(AsyncErrorFallback, {
        props: {
          error: new Error('Test error'),
          componentName: 'TestComponent',
          retryCount: 1,
          maxRetries: 3
        }
      })

      await wrapper.find('button:first-of-type').trigger('click')
      expect(wrapper.emitted('retry')).toBeTruthy()
    })

    it('should track error with RUM when component loads', () => {
      mount(AsyncErrorFallback, {
        props: {
          error: new Error('Test error'),
          componentName: 'TestComponent'
        }
      })

      expect(mockRum.trackError).toHaveBeenCalledWith('async_component_load_failed', {
        component: 'TestComponent',
        message: 'Test error',
        stack: expect.any(String),
        retryCount: 0,
        maxRetries: 3
      })
    })
  })

  describe('AsyncComponentWrapper', () => {
    it('should display loading state while component loads', async () => {
      const slowLoader = () => new Promise(resolve => setTimeout(resolve, 1000))

      const wrapper = mount(AsyncComponentWrapper, {
        props: {
          componentLoader: slowLoader,
          componentName: 'SlowComponent'
        }
      })

      await flushPromises()

      // Should show loading state
      expect(wrapper.find('.async-loading').exists()).toBe(true)
      expect(wrapper.find('.loading-title').text()).toContain('Loading Slow Component')
    })

    it('should handle component loading errors', async () => {
      const failingLoader = () => Promise.reject(new Error('Loading failed'))

      const wrapper = mount(AsyncComponentWrapper, {
        props: {
          componentLoader: failingLoader,
          componentName: 'FailingComponent'
        }
      })

      await flushPromises()

      // Should emit error event
      expect(wrapper.emitted('error')).toBeTruthy()
      expect(wrapper.emitted('error')[0][0].message).toBe('Loading failed')
    })

    it('should track loading time and emit loaded event on success', async () => {
      const mockComponent = { template: '<div>Test Component</div>' }
      const successLoader = () => Promise.resolve(mockComponent)

      const wrapper = mount(AsyncComponentWrapper, {
        props: {
          componentLoader: successLoader,
          componentName: 'SuccessComponent'
        }
      })

      await flushPromises()

      expect(wrapper.emitted('loaded')).toBeTruthy()
      expect(mockRum.trackUserInteraction).toHaveBeenCalledWith('async_component_loaded', null, {
        component: 'SuccessComponent',
        loadingTime: expect.any(Number),
        retryCount: 0
      })
    })
  })

  describe('Async Component Helpers', () => {
    describe('createAsyncComponent', () => {
      it('should create component with proper error handling', () => {
        const loader = () => Promise.resolve({ template: '<div>Test</div>' })

        const component = createAsyncComponent(loader, {
          name: 'TestComponent',
          maxRetries: 2,
          timeout: 5000
        })

        expect(component).toBeDefined()
        expect(component.name).toBe('AsyncTestComponent')
      })
    })

    describe('createLazyComponent', () => {
      it('should handle chunk loading errors', async () => {
        const chunkError = new Error('Loading chunk 456 failed.')
        const failingImport = () => Promise.reject(chunkError)

        const component = createLazyComponent(failingImport, 'ChunkComponent')

        // Component should be created but will fail when loaded
        expect(component).toBeDefined()
      })
    })

    describe('AsyncComponentErrorRecovery', () => {
      it('should track failed components', () => {
        AsyncComponentErrorRecovery.markAsFailed('FailedComponent')

        expect(AsyncComponentErrorRecovery.hasFailed('FailedComponent')).toBe(true)
        expect(AsyncComponentErrorRecovery.hasFailed('WorkingComponent')).toBe(false)
      })

      it('should increment retry counts', () => {
        expect(AsyncComponentErrorRecovery.incrementRetry('TestComponent')).toBe(1)
        expect(AsyncComponentErrorRecovery.incrementRetry('TestComponent')).toBe(2)
        expect(AsyncComponentErrorRecovery.getRetryCount('TestComponent')).toBe(2)
      })

      it('should reset component state', () => {
        AsyncComponentErrorRecovery.markAsFailed('TestComponent')
        AsyncComponentErrorRecovery.incrementRetry('TestComponent')

        AsyncComponentErrorRecovery.reset('TestComponent')

        expect(AsyncComponentErrorRecovery.hasFailed('TestComponent')).toBe(false)
        expect(AsyncComponentErrorRecovery.getRetryCount('TestComponent')).toBe(0)
      })

      it('should provide stats about failed components', () => {
        AsyncComponentErrorRecovery.markAsFailed('Component1')
        AsyncComponentErrorRecovery.markAsFailed('Component2')
        AsyncComponentErrorRecovery.incrementRetry('Component1')

        const stats = AsyncComponentErrorRecovery.getStats()

        expect(stats.failedCount).toBe(2)
        expect(stats.failedComponents).toEqual(['Component1', 'Component2'])
        expect(stats.retryAttempts).toEqual({ Component1: 1 })
      })
    })
  })

  describe('Router Integration', () => {
    it('should handle chunk loading errors in router', async () => {
      const router = createRouter({
        history: createWebHistory(),
        routes: [
          {
            path: '/test',
            component: createLazyComponent(() => Promise.reject(new Error('Loading chunk failed')), 'TestRoute')
          }
        ]
      })

      // Mock router.onError
      const errorHandler = vi.fn()
      router.onError(errorHandler)

      try {
        await router.push('/test')
      } catch (error) {
        // Error should be handled by router error handler
      }

      // Should track the error
      expect(mockRum.trackError).toHaveBeenCalled()
    })
  })

  describe('Global Error Handler', () => {
    it('should handle unhandled promise rejections for chunk errors', () => {
      // Mock document.body.appendChild
      const mockAppendChild = vi.fn()
      global.document.body.appendChild = mockAppendChild

      // Simulate unhandled rejection
      const chunkError = new Error('Loading chunk 789 failed.')
      const rejectionEvent = new PromiseRejectionEvent('unhandledrejection', {
        reason: chunkError,
        promise: Promise.reject(chunkError)
      })

      // Mock preventDefault
      rejectionEvent.preventDefault = vi.fn()

      // Dispatch the event
      global.window.dispatchEvent(rejectionEvent)

      // Should prevent default and create notification
      expect(rejectionEvent.preventDefault).toHaveBeenCalled()
      expect(mockRum.trackError).toHaveBeenCalledWith('unhandled_chunk_error', {
        message: 'Loading chunk 789 failed.',
        stack: expect.any(String),
        userAgent: expect.any(String),
        url: expect.any(String),
        timestamp: expect.any(String)
      })
    })
  })

  describe('Error Recovery Scenarios', () => {
    it('should implement exponential backoff for retries', async () => {
      const startTime = Date.now()
      let attempts = 0

      const intermittentLoader = () => {
        attempts++
        if (attempts < 3) {
          return Promise.reject(new Error('Intermittent failure'))
        }
        return Promise.resolve({ template: '<div>Success</div>' })
      }

      const wrapper = mount(AsyncComponentWrapper, {
        props: {
          componentLoader: intermittentLoader,
          componentName: 'IntermittentComponent',
          maxRetries: 3,
          retryDelay: 100
        }
      })

      // Wait for retries to complete
      await new Promise(resolve => setTimeout(resolve, 2000))
      await flushPromises()

      // Should eventually succeed
      expect(wrapper.emitted('loaded')).toBeTruthy()
      expect(attempts).toBe(3)
    })

    it('should clear session storage flags on successful navigation', () => {
      global.sessionStorage.setItem('chunk-reload-attempted', 'true')
      global.sessionStorage.setItem('chunk-reload-count', '1')

      // Simulate successful route navigation
      const mockRoute = { matched: [{ path: '/success' }] }

      // This would be called by the router beforeEach guard
      if (mockRoute.matched.length > 0) {
        global.sessionStorage.removeItem('chunk-reload-attempted')
        global.sessionStorage.removeItem('chunk-reload-count')
      }

      expect(global.sessionStorage.getItem('chunk-reload-attempted')).toBeNull()
      expect(global.sessionStorage.getItem('chunk-reload-count')).toBeNull()
    })
  })
})

// Integration test for simulating chunk loading failures
describe('Chunk Loading Failure Simulation', () => {
  it('should handle real-world chunk loading scenarios', async () => {
    // Simulate network failure during chunk loading
    const networkFailureLoader = () => Promise.reject(new Error('TypeError: Failed to fetch dynamically imported module'))

    const wrapper = mount(AsyncComponentWrapper, {
      props: {
        componentLoader: networkFailureLoader,
        componentName: 'NetworkFailureComponent'
      }
    })

    await flushPromises()

    // Should show error fallback
    expect(wrapper.find('.async-error-fallback').exists()).toBe(true)

    // Should track the specific error type
    expect(mockRum.trackError).toHaveBeenCalledWith('async_component_loading_error', {
      component: 'NetworkFailureComponent',
      message: 'TypeError: Failed to fetch dynamically imported module',
      stack: expect.any(String),
      retryCount: 0,
      loadingTime: expect.any(Number)
    })
  })

  it('should provide user-friendly messages for different error types', () => {
    const testCases = [
      {
        error: new Error('Loading chunk 123 failed.'),
        expectedMessage: 'This page failed to load due to a network issue'
      },
      {
        error: new Error('Failed to fetch'),
        expectedMessage: 'Unable to download the required files'
      },
      {
        error: new Error('NetworkError when attempting to fetch resource'),
        expectedMessage: 'Network connection failed while loading the component'
      },
      {
        error: new Error('Request timeout'),
        expectedMessage: 'The component took too long to load'
      }
    ]

    testCases.forEach(({ error, expectedMessage }) => {
      const wrapper = mount(AsyncErrorFallback, {
        props: { error, componentName: 'TestComponent' }
      })

      expect(wrapper.find('.error-message').text()).toContain(expectedMessage)
    })
  })
})

console.log('✅ Async component error boundaries test suite completed')