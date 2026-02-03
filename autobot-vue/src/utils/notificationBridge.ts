/**
 * Notification Bridge for ErrorHandler Integration
 *
 * Connects the vanilla JavaScript ErrorHandler class with Vue's useToast composable.
 * This bridge allows non-Vue code to trigger toast notifications.
 *
 * Features:
 * - Rate limiting to prevent notification spam
 * - Message deduplication with configurable window
 * - Severity-based duration configuration
 * - Critical error persistence
 * - Queue management for rapid notifications
 *
 * @author mrveiss
 * @copyright 2025 mrveiss
 */

import { useToast, type ToastType } from '@/composables/useToast'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('NotificationBridge')

// ========================================
// Types & Configuration
// ========================================

export type NotificationType = 'error' | 'warning' | 'info' | 'success'

interface NotificationConfig {
  /** Default duration for each notification type (ms) */
  durations: Record<NotificationType, number>
  /** Rate limit: max notifications per time window */
  rateLimit: {
    maxNotifications: number
    windowMs: number
  }
  /** Deduplication: ignore duplicate messages within this window (ms) */
  deduplicationWindowMs: number
  /** Critical errors stay visible until dismissed */
  criticalErrorPersistent: boolean
}

interface QueuedNotification {
  message: string
  type: NotificationType
  timestamp: number
  isCritical: boolean
}

// Default configuration
const DEFAULT_CONFIG: NotificationConfig = {
  durations: {
    error: 8000,     // Errors stay longer
    warning: 5000,   // Warnings moderate duration
    info: 3000,      // Info brief
    success: 3000    // Success brief
  },
  rateLimit: {
    maxNotifications: 5,  // Max 5 notifications
    windowMs: 10000       // Per 10 seconds
  },
  deduplicationWindowMs: 3000,  // Ignore duplicate messages within 3 seconds
  criticalErrorPersistent: true  // Critical errors don't auto-dismiss
}

// ========================================
// NotificationBridge Class
// ========================================

class NotificationBridge {
  private config: NotificationConfig
  private recentNotifications: QueuedNotification[] = []
  private isInitialized = false
  private showToast: ((message: string, type?: ToastType, duration?: number) => number) | null = null

  constructor(config: Partial<NotificationConfig> = {}) {
    this.config = { ...DEFAULT_CONFIG, ...config }
  }

  /**
   * Initialize the bridge with the Vue toast system.
   * Call this once when the Vue app mounts (in App.vue setup).
   */
  initialize(): void {
    if (this.isInitialized) {
      logger.debug('NotificationBridge already initialized')
      return
    }

    try {
      const { showToast } = useToast()
      this.showToast = showToast
      this.isInitialized = true
      logger.debug('NotificationBridge initialized successfully')
    } catch (error) {
      logger.error('Failed to initialize NotificationBridge:', error)
    }
  }

  /**
   * Check if the bridge is ready to send notifications
   */
  isReady(): boolean {
    return this.isInitialized && this.showToast !== null
  }

  /**
   * Send a notification through the toast system.
   * Handles rate limiting and deduplication automatically.
   *
   * @param message - Message to display
   * @param type - Notification type
   * @param isCritical - If true, notification won't auto-dismiss (for errors)
   * @returns Toast ID if shown, -1 if rate limited or deduplicated
   */
  notify(message: string, type: NotificationType = 'info', isCritical = false): number {
    if (!this.isReady()) {
      // Fallback to console if not initialized
      logger.warn('NotificationBridge not ready, falling back to console:', message)
      this.logFallback(message, type)
      return -1
    }

    // Check for duplicate messages
    if (this.isDuplicate(message)) {
      logger.debug('Duplicate notification suppressed:', message.substring(0, 50))
      return -1
    }

    // Check rate limit
    if (this.isRateLimited()) {
      logger.debug('Notification rate limited:', message.substring(0, 50))
      return -1
    }

    // Record this notification
    this.recordNotification({ message, type, timestamp: Date.now(), isCritical })

    // Calculate duration
    const duration = isCritical && type === 'error'
      ? 0  // 0 = persistent (no auto-dismiss)
      : this.config.durations[type]

    // Map notification type to toast type
    const toastType = this.mapToToastType(type)

    // Show the toast
    const toastId = this.showToast!(message, toastType, duration)

    logger.debug(`Notification shown [${type}]: ${message.substring(0, 50)}...`)

    return toastId
  }

  /**
   * Show an error notification
   */
  error(message: string, isCritical = false): number {
    return this.notify(message, 'error', isCritical)
  }

  /**
   * Show a warning notification
   */
  warning(message: string): number {
    return this.notify(message, 'warning', false)
  }

  /**
   * Show an info notification
   */
  info(message: string): number {
    return this.notify(message, 'info', false)
  }

  /**
   * Show a success notification
   */
  success(message: string): number {
    return this.notify(message, 'success', false)
  }

  /**
   * Update configuration at runtime
   */
  updateConfig(config: Partial<NotificationConfig>): void {
    this.config = { ...this.config, ...config }
    logger.debug('NotificationBridge config updated')
  }

  /**
   * Clear notification history (useful for testing or reset)
   */
  clearHistory(): void {
    this.recentNotifications = []
  }

  // ========================================
  // Private Helper Methods
  // ========================================

  /**
   * Check if a message is a duplicate of a recent notification
   */
  private isDuplicate(message: string): boolean {
    const now = Date.now()
    const cutoff = now - this.config.deduplicationWindowMs

    // Clean up old entries
    this.recentNotifications = this.recentNotifications.filter(n => n.timestamp > cutoff)

    // Check for exact duplicate
    return this.recentNotifications.some(n => n.message === message)
  }

  /**
   * Check if we've exceeded the rate limit
   */
  private isRateLimited(): boolean {
    const now = Date.now()
    const cutoff = now - this.config.rateLimit.windowMs

    // Count notifications in the window
    const recentCount = this.recentNotifications.filter(n => n.timestamp > cutoff).length

    return recentCount >= this.config.rateLimit.maxNotifications
  }

  /**
   * Record a notification for rate limiting and deduplication
   */
  private recordNotification(notification: QueuedNotification): void {
    this.recentNotifications.push(notification)

    // Limit history size to prevent memory growth
    if (this.recentNotifications.length > 100) {
      this.recentNotifications = this.recentNotifications.slice(-50)
    }
  }

  /**
   * Map our notification types to toast types
   */
  private mapToToastType(type: NotificationType): ToastType {
    // Direct mapping since our types match
    return type as ToastType
  }

  /**
   * Fallback logging when toast system not available
   */
  private logFallback(message: string, type: NotificationType): void {
    switch (type) {
      case 'error':
        logger.error(`[NOTIFICATION] ${message}`)
        break
      case 'warning':
        logger.warn(`[NOTIFICATION] ${message}`)
        break
      case 'success':
        logger.info(`[NOTIFICATION] ✓ ${message}`)
        break
      default:
        logger.info(`[NOTIFICATION] ${message}`)
    }
  }
}

// ========================================
// Singleton Instance Export
// ========================================

/**
 * Global notification bridge instance.
 * Initialize in App.vue setup, then use from ErrorHandler or anywhere.
 */
export const notificationBridge = new NotificationBridge()

/**
 * Initialize the notification bridge (call from App.vue setup)
 */
export function initializeNotificationBridge(): void {
  notificationBridge.initialize()
}

/**
 * Convenience export for the notify function
 */
export function showNotification(
  message: string,
  type: NotificationType = 'info',
  isCritical = false
): number {
  return notificationBridge.notify(message, type, isCritical)
}

export default notificationBridge
