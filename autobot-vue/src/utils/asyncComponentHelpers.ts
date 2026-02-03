import { defineAsyncComponent, defineComponent, h } from 'vue'
import type { AsyncComponentLoader } from 'vue'
import AsyncErrorFallback from '@/components/async/AsyncErrorFallback.vue'
// Issue #156 Fix: Import RumAgent to get complete Window.rum type
import '../utils/RumAgent'
import { createLogger } from '@/utils/debugUtils'

// Create scoped logger for asyncComponentHelpers
const logger = createLogger('AsyncComponent')

// Type declarations for global objects
declare global {
  interface Window {
    // Issue #156 Fix: rum is declared in RumAgent.ts with complete type
    __webpack_require__?: {
      cache: Record<string, any>
    }
  }
}

export interface AsyncComponentOptions {
  /** Display name for the component (used in error messages) */
  name?: string
  /** Custom loading message */
  loadingMessage?: string
  /** Maximum number of retry attempts */
  maxRetries?: number
  /** Delay between retries in milliseconds */
  retryDelay?: number
  /** Loading timeout in milliseconds */
  timeout?: number
  /** Props to pass to the component */
  props?: Record<string, any>
  /** Whether to show detailed loading progress */
  showProgress?: boolean
  /** Custom error handler */
  onError?: (error: Error) => void
  /** Custom retry handler */
  onRetry?: (attempt: number) => void
}

/**
 * Creates a robust async component with error boundaries, loading states, and retry logic
 *
 * @param loader - Function that returns a Promise resolving to the component
 * @param options - Configuration options for error handling and loading
 * @returns A wrapped component with error boundaries and loading states
 */
export function createAsyncComponent(
  loader: AsyncComponentLoader,
  options: AsyncComponentOptions = {}
) {
  const {
    name = 'AsyncComponent',
    loadingMessage = 'Loading component...',
    maxRetries = 3,
    retryDelay = 1000,
    timeout = 10000,
    props = {},
    showProgress: _showProgress = true, // Reserved for future progress indicators
    onError,
    onRetry
  } = options

  // Lazy load the wrapper component to avoid circular dependencies
  const AsyncComponentWrapper = defineAsyncComponent({
    loader: () => import('@/components/async/AsyncComponentWrapper.vue'),
    delay: 200,
    timeout: 10000
  })

  // Create a wrapper component that uses AsyncComponentWrapper
  return defineComponent({
    name: `Async${name}`,
    setup(_, { attrs, slots }) {
      return () => h(AsyncComponentWrapper, {
        componentLoader: loader,
        componentName: name,
        componentProps: { ...props, ...attrs },
        loadingMessage,
        maxRetries,
        retryDelay,
        timeout,
        onError: (error: Error) => {
          logger.error(`Error in ${name}:`, error)
          onError?.(error)
        },
        onRetry: (attempt: number) => {
          onRetry?.(attempt)
        }
      }, slots)
    }
  })
}

/**
 * Enhanced defineAsyncComponent with built-in error handling and retries
 *
 * @param loader - Function that returns a Promise resolving to the component
 * @param options - Configuration options
 * @returns Enhanced async component
 */
export function defineRobustAsyncComponent(
  loader: AsyncComponentLoader,
  options: AsyncComponentOptions = {}
) {
  const {
    name = 'RobustAsyncComponent',
    maxRetries = 3,
    retryDelay = 1000,
    timeout = 10000,
    onError,
    onRetry
  } = options

  let retryCount = 0

  const enhancedLoader = async () => {
    try {
      const startTime = Date.now()

      const component = await loader()

      const _loadTime = Date.now() - startTime // For future metrics logging

      // Reset retry count on success
      retryCount = 0

      return component
    } catch (error: unknown) {
      logger.error(`Failed to load ${name}:`, error)

      // Issue #156 Fix: Type guard for error message property
      const errorMessage = (error as any)?.message || String(error)

      // Check if this is a chunk loading error
      const isChunkError = errorMessage.includes('Loading chunk') ||
                           errorMessage.includes('ChunkLoadError') ||
                           errorMessage.includes('Loading CSS chunk')

      if (isChunkError) {
        logger.warn(`Chunk loading error detected for ${name}, using cache management...`)

        // Use cache management system for chunk errors
        try {
          const { handleChunkLoadingError } = await import('./cacheManagement')
          await handleChunkLoadingError(error as Error, name)
          return // Cache management will handle the reload
        } catch (cacheError) {
          logger.error(`Cache management failed for ${name}:`, cacheError)
          // Fallback to standard retry logic
        }
      }

      if (retryCount < maxRetries) {
        retryCount++

        onRetry?.(retryCount)

        // Exponential backoff delay
        const delay = Math.min(retryDelay * Math.pow(2, retryCount - 1), 5000)
        await new Promise(resolve => setTimeout(resolve, delay))

        // Recursive retry
        return enhancedLoader()
      }

      // Max retries reached, call error handler and rethrow
      onError?.(error as Error)
      throw error
    }
  }

  return defineAsyncComponent({
    loader: enhancedLoader,
    errorComponent: AsyncErrorFallback,
    delay: 200,
    timeout,
    suspensible: true
  })
}

/**
 * Utility to wrap route components with async error boundaries
 *
 * @param loader - Component loader function
 * @param routeName - Name of the route (for debugging)
 * @returns Wrapped component ready for router use
 */
export function createRouteComponent(
  loader: AsyncComponentLoader,
  routeName: string
) {
  return createAsyncComponent(loader, {
    name: routeName,
    loadingMessage: `Loading ${routeName.replace(/([A-Z])/g, ' $1').trim()}...`,
    maxRetries: 3,
    retryDelay: 1000,
    timeout: 15000, // Longer timeout for route components
    onError: (error) => {
      // Track route loading errors
      logger.error(`Failed to load route: ${routeName}`, error)

      // Report to RUM if available
      if (window.rum) {
        window.rum.trackError('route_component_load_failed', {
          route: routeName,
          message: error.message,
          stack: error.stack
        })
      }
    },
    onRetry: (attempt) => {

      // Track retry attempts
      if (window.rum) {
        window.rum.trackUserInteraction('route_component_retry', null, {
          route: routeName,
          attempt
        })
      }
    }
  })
}

/**
 * Creates a lazy-loaded component with chunk loading error handling
 *
 * @param importFn - Dynamic import function
 * @param componentName - Display name for the component
 * @returns Component with chunk loading error boundaries
 */
export function createLazyComponent(
  importFn: () => Promise<any>,
  componentName: string
) {
  return defineRobustAsyncComponent(
    async () => {
      try {
        const module = await importFn()
        return module.default || module
      } catch (error: any) {
        // Handle specific chunk loading errors
        if (error?.message?.includes('Loading chunk') ||
            error?.message?.includes('ChunkLoadError') ||
            error?.message?.includes('Loading CSS chunk')) {

          logger.warn(`Chunk loading failed for ${componentName}, attempting cache bust...`)

          // Attempt to clear module cache and retry once
          if (typeof window !== 'undefined' && (window as any).__webpack_require__) {
            // Clear webpack module cache if possible
            const webpackRequire = (window as any).__webpack_require__
            if (webpackRequire.cache) {
              Object.keys(webpackRequire.cache).forEach(key => {
                if (key.includes(componentName.toLowerCase())) {
                  delete webpackRequire.cache[key]
                }
              })
            }
          }

          // Use cache management system for chunk errors
          try {
            const { handleChunkLoadingError } = await import('./cacheManagement')
            await handleChunkLoadingError(error, componentName)
            return // Cache management will handle the reload
          } catch (cacheError) {
            logger.error(`Cache management failed for ${componentName}:`, cacheError)
            throw new Error(`Chunk loading failed for ${componentName}. Page refresh may be required.`)
          }
        }

        throw error
      }
    },
    {
      name: componentName,
      maxRetries: 2, // Fewer retries for chunk errors
      retryDelay: 500,
      timeout: 10000,
      onError: (error) => {
        logger.error(`Error loading ${componentName}:`, error)

        // Special handling for chunk errors
        if (error.message?.includes('chunk') || error.message?.includes('Chunk')) {
          // Show user-friendly message about app updates
          if (window.rum) {
            window.rum.trackError('chunk_load_error', {
              component: componentName,
              message: error.message,
              userAgent: navigator.userAgent,
              timestamp: new Date().toISOString()
            })
          }
        }
      }
    }
  )
}

/**
 * Error recovery utility for failed async components
 */
export class AsyncComponentErrorRecovery {
  private static failedComponents = new Set<string>()
  private static retryAttempts = new Map<string, number>()

  static markAsFailed(componentName: string) {
    this.failedComponents.add(componentName)
  }

  static hasFailed(componentName: string): boolean {
    return this.failedComponents.has(componentName)
  }

  static incrementRetry(componentName: string): number {
    const current = this.retryAttempts.get(componentName) || 0
    const newCount = current + 1
    this.retryAttempts.set(componentName, newCount)
    return newCount
  }

  static getRetryCount(componentName: string): number {
    return this.retryAttempts.get(componentName) || 0
  }

  static reset(componentName: string) {
    this.failedComponents.delete(componentName)
    this.retryAttempts.delete(componentName)
  }

  static resetAll() {
    this.failedComponents.clear()
    this.retryAttempts.clear()
  }

  static getFailedComponents(): string[] {
    return Array.from(this.failedComponents)
  }

  static getStats() {
    return {
      failedCount: this.failedComponents.size,
      failedComponents: Array.from(this.failedComponents),
      retryAttempts: Object.fromEntries(this.retryAttempts)
    }
  }
}

/**
 * Global error handler for async component failures (legacy support)
 * Note: This is now mainly handled by the cache management system
 */
export function setupAsyncComponentErrorHandler() {
  if (typeof window === 'undefined') return

  // Listen for unhandled promise rejections (chunk loading failures)
  window.addEventListener('unhandledrejection', async (event) => {
    const error = event.reason

    if (error?.message?.includes('Loading chunk') ||
        error?.message?.includes('ChunkLoadError') ||
        error?.message?.includes('Loading CSS chunk')) {

      logger.warn('Detected chunk loading failure:', error)

      // Track chunk loading failures
      if (window.rum) {
        window.rum.trackError('unhandled_chunk_error', {
          message: error.message,
          stack: error.stack,
          userAgent: navigator.userAgent,
          url: window.location.href,
          timestamp: new Date().toISOString()
        })
      }

      // Prevent default error handling for chunk errors
      event.preventDefault()

      // Use cache management system
      try {
        const { handleChunkLoadingError } = await import('./cacheManagement')
        await handleChunkLoadingError(error)
      } catch (cacheError) {
        logger.error('Cache management failed:', cacheError)

        // Fallback to legacy notification system
        const notification = document.createElement('div')
        notification.style.cssText = `
          position: fixed;
          top: 20px;
          right: 20px;
          background: #fff3cd;
          border: 1px solid #ffeaa7;
          color: #856404;
          padding: 1rem;
          border-radius: 8px;
          box-shadow: 0 4px 12px rgba(0,0,0,0.15);
          z-index: 10000;
          max-width: 300px;
          font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
        `
        notification.innerHTML = `
          <strong>App Update Available</strong><br>
          Please refresh the page to get the latest version.
          <button onclick="window.location.reload()" style="
            margin-top: 8px;
            padding: 4px 8px;
            background: #007bff;
            color: white;
            border: none;
            border-radius: 4px;
            cursor: pointer;
          ">Refresh</button>
        `

        document.body.appendChild(notification)

        // Auto-remove notification after 10 seconds
        setTimeout(() => {
          if (notification.parentNode) {
            notification.parentNode.removeChild(notification)
          }
        }, 10000)
      }
    }
  })

}