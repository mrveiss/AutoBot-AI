/**
 * Global Error Handler Plugin
 * Provides comprehensive error handling for the Vue application
 */

import type { App } from 'vue'
import rumAgent from '../utils/RumAgent'
import { createLogger } from '@/utils/debugUtils'

// Create scoped logger for errorHandler
const logger = createLogger('errorHandler')

interface ErrorNotification {
  id: string
  message: string
  type: 'error' | 'warning' | 'info'
  timestamp: number
  stack?: string
  dismissible: boolean
}

class GlobalErrorHandler {
  private notifications: ErrorNotification[] = []
  private listeners: Set<(notifications: ErrorNotification[]) => void> = new Set()
  private maxNotifications = 5

  constructor() {
    this.setupGlobalHandlers()
  }

  private setupGlobalHandlers() {
    // Catch unhandled promise rejections
    window.addEventListener('unhandledrejection', (event) => {
      logger.error('Unhandled promise rejection:', event.reason)

      this.addNotification({
        message: this.getUnhandledRejectionMessage(event.reason),
        type: 'error',
        dismissible: true,
        stack: event.reason?.stack
      })

      // Track with RUM
      rumAgent.trackError('unhandled_promise_rejection', {
        message: event.reason?.message || 'Unknown promise rejection',
        stack: event.reason?.stack,
        source: 'global_error_handler'
      })

      // Prevent the default browser error logging
      event.preventDefault()
    })

    // Catch JavaScript errors
    window.addEventListener('error', (event) => {
      logger.error('Global JavaScript error:', event.error)

      this.addNotification({
        message: this.getJavaScriptErrorMessage(event.error, event.filename, event.lineno),
        type: 'error',
        dismissible: true,
        stack: event.error?.stack
      })

      // Track with RUM
      rumAgent.trackError('javascript_error', {
        message: event.message,
        filename: event.filename,
        lineno: event.lineno,
        colno: event.colno,
        stack: event.error?.stack,
        source: 'global_error_handler'
      })
    })

    // Catch network errors (fetch failures)
    this.interceptFetch()
  }

  private interceptFetch() {
    const originalFetch = window.fetch

    window.fetch = async (...args) => {
      try {
        const response = await originalFetch(...args)

        if (!response.ok) {
          const requestUrl = typeof args[0] === 'string'
            ? args[0]
            : args[0] instanceof URL
              ? args[0].href
              : (args[0] as Request)?.url

          // Track HTTP errors
          rumAgent.trackError('http_error', {
            status: response.status,
            statusText: response.statusText,
            url: requestUrl,
            source: 'fetch_interceptor'
          })

          // Log HTTP errors to console for debugging (especially 404s)
          if (response.status === 404) {
            logger.error(`[HTTP 404] Resource not found: ${requestUrl}`)
          } else if (response.status >= 400 && response.status < 500) {
            logger.warn(`[HTTP ${response.status}] Client error: ${requestUrl} - ${response.statusText}`)
          } else if (response.status >= 500) {
            logger.error(`[HTTP ${response.status}] Server error: ${requestUrl} - ${response.statusText}`)
          }

          if (response.status >= 500) {
            this.addNotification({
              message: `Server error (${response.status}). Please try again later.`,
              type: 'error',
              dismissible: true
            })
          } else if (response.status === 401) {
            this.addNotification({
              message: 'Authentication required. Please log in again.',
              type: 'warning',
              dismissible: true
            })
          } else if (response.status === 403) {
            this.addNotification({
              message: 'Access denied. You may not have permission for this action.',
              type: 'warning',
              dismissible: true
            })
          } else if (response.status === 404) {
            this.addNotification({
              message: 'Requested resource not found.',
              type: 'warning',
              dismissible: true
            })
          }
        }

        return response
      } catch (error) {
        // Don't log expected health check failures
        const isHealthCheck = typeof args[0] === 'string' && args[0].includes('/health')
        if (!isHealthCheck) {
          logger.error('Fetch error:', error)
        }

        // Track network errors
        const requestUrl = typeof args[0] === 'string'
          ? args[0]
          : args[0] instanceof URL
            ? args[0].href
            : (args[0] as Request)?.url

        rumAgent.trackError('network_error', {
          message: (error as Error).message,
          stack: (error as Error).stack,
          url: requestUrl,
          source: 'fetch_interceptor'
        })

        // Only show notification for non-health check failures
        if (!isHealthCheck) {
          this.addNotification({
            message: 'Network connection failed. Please check your internet connection.',
            type: 'error',
            dismissible: true,
            stack: (error as Error).stack
          })
        }

        throw error
      }
    }
  }

  private getUnhandledRejectionMessage(reason: any): string {
    if (reason?.message) {
      if (reason.message.includes('Failed to fetch')) {
        return 'Connection failed. Please check your internet connection and try again.'
      }
      if (reason.message.includes('NetworkError')) {
        return 'Network error occurred. Please try again.'
      }
      if (reason.message.includes('ChunkLoadError')) {
        return 'Application update detected. Please reload the page.'
      }
    }

    return 'An unexpected error occurred. Please try refreshing the page.'
  }

  private getJavaScriptErrorMessage(error: Error, _filename?: string, _lineno?: number): string {
    if (error?.message) {
      if (error.message.includes('ChunkLoadError')) {
        return 'Application files failed to load. Please reload the page.'
      }
      if (error.message.includes('ResizeObserver loop limit exceeded')) {
        return 'Display refresh needed. This is usually harmless.'
      }
      if (error.message.includes('Cannot read properties')) {
        return 'Data loading issue. Please try refreshing the page.'
      }
    }

    return 'A JavaScript error occurred. Please try refreshing the page.'
  }

  private addNotification(notification: Omit<ErrorNotification, 'id' | 'timestamp'>) {
    // Defensive programming: ensure notifications array is initialized
    if (!Array.isArray(this.notifications)) {
      this.notifications = []
    }

    const id = `error_${Date.now()}_${Math.random().toString(36).substring(2, 11)}`
    const fullNotification: ErrorNotification = {
      ...notification,
      id,
      timestamp: Date.now()
    }

    // Prevent duplicate notifications
    const isDuplicate = this.notifications.some(n =>
      n.message === notification.message &&
      Date.now() - n.timestamp < 5000 // Within 5 seconds
    )

    if (!isDuplicate) {
      this.notifications.unshift(fullNotification)

      // Keep only the most recent notifications
      if (this.notifications.length > this.maxNotifications) {
        this.notifications = this.notifications.slice(0, this.maxNotifications)
      }

      this.notifyListeners()

      // Auto-dismiss info notifications after 5 seconds
      if (notification.type === 'info') {
        setTimeout(() => {
          this.dismissNotification(id)
        }, 5000)
      }
    }
  }

  public dismissNotification(id: string) {
    this.notifications = this.notifications.filter(n => n.id !== id)
    this.notifyListeners()
  }

  public clearAllNotifications() {
    this.notifications = []
    this.notifyListeners()
  }

  public subscribe(listener: (notifications: ErrorNotification[]) => void) {
    this.listeners.add(listener)
    // Immediately call with current notifications
    listener([...this.notifications])

    return () => {
      this.listeners.delete(listener)
    }
  }

  private notifyListeners() {
    this.listeners.forEach(listener => {
      listener([...this.notifications])
    })
  }

  public getNotifications(): ErrorNotification[] {
    return [...this.notifications]
  }

  public addManualNotification(message: string, type: ErrorNotification['type'] = 'info', dismissible = true) {
    this.addNotification({ message, type, dismissible })
  }
}

const globalErrorHandler = new GlobalErrorHandler()

// Plugin installation
export default {
  install(app: App) {
    // Enhanced Vue error handler
    const originalErrorHandler = app.config.errorHandler

    app.config.errorHandler = (error, instance, info) => {
      logger.error('Vue Error:', { error, info })

      // Call original handler (RUM plugin)
      if (originalErrorHandler) {
        originalErrorHandler(error, instance, info)
      }

      // Show user-friendly notification
      globalErrorHandler.addManualNotification(
        'Component error occurred. Some features may not work correctly.',
        'error'
      )
    }

    // Add error handler to global properties
    app.config.globalProperties.$errorHandler = globalErrorHandler

    // Provide for composition API
    app.provide('errorHandler', globalErrorHandler)

    // Global Error Handler installed successfully
  }
}

export { globalErrorHandler }
export type { ErrorNotification }
