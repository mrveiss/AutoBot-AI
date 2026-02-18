// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss
/**
 * Workflow Components Utilities
 * Reusable functions and types for workflow UI components
 */

// ============================================================================
// Types and Interfaces
// ============================================================================

/**
 * Notification types for workflow events
 */
export type NotificationType =
  | 'info'
  | 'success'
  | 'warning'
  | 'error'
  | 'approval'
  | 'progress'

/**
 * Workflow notification object
 */
export interface WorkflowNotification {
  id: string | number
  type: NotificationType
  title: string
  message: string
  timestamp: number
  actionRequired?: boolean
  actionText?: string
  workflowId?: string
  stepId?: string
}

/**
 * Workflow progress data
 */
export interface WorkflowProgress {
  current: number
  total: number
  percentage: number
  status: string
}

// ============================================================================
// Icon Utilities
// ============================================================================

/**
 * Get FontAwesome icon class for notification type
 *
 * @param type - Notification type
 * @returns FontAwesome icon class string
 *
 * @example
 * ```ts
 * const icon = getNotificationIcon('success') // 'fas fa-check-circle'
 * ```
 */
export function getNotificationIcon(type: NotificationType): string {
  const icons: Record<NotificationType, string> = {
    'info': 'fas fa-info-circle',
    'success': 'fas fa-check-circle',
    'warning': 'fas fa-exclamation-triangle',
    'error': 'fas fa-times-circle',
    'approval': 'fas fa-user-check',
    'progress': 'fas fa-sync fa-spin'
  }
  return icons[type] || 'fas fa-bell'
}

/**
 * Get color for notification type
 *
 * @param type - Notification type
 * @returns CSS color value
 */
export function getNotificationColor(type: NotificationType): string {
  const colors: Record<NotificationType, string> = {
    'info': '#17a2b8',
    'success': '#28a745',
    'warning': '#ffc107',
    'error': '#dc3545',
    'approval': '#fd7e14',
    'progress': '#6f42c1'
  }
  return colors[type] || '#6c757d'
}

// ============================================================================
// Time Utilities
// ============================================================================

/**
 * Format timestamp to locale time string
 *
 * @param timestamp - Unix timestamp in milliseconds
 * @returns Formatted time string (e.g., "2:30:45 PM")
 *
 * @example
 * ```ts
 * const time = formatTimestamp(Date.now()) // "2:30:45 PM"
 * ```
 */
export function formatTimestamp(timestamp: number): string {
  return new Date(timestamp).toLocaleTimeString()
}

/**
 * Format timestamp to relative time (e.g., "2 minutes ago")
 *
 * @param timestamp - Unix timestamp in milliseconds
 * @returns Relative time string
 */
export function formatRelativeTime(timestamp: number): string {
  const now = Date.now()
  const diff = now - timestamp
  const seconds = Math.floor(diff / 1000)
  const minutes = Math.floor(seconds / 60)
  const hours = Math.floor(minutes / 60)
  const days = Math.floor(hours / 24)

  if (seconds < 60) return 'just now'
  if (minutes < 60) return `${minutes} minute${minutes > 1 ? 's' : ''} ago`
  if (hours < 24) return `${hours} hour${hours > 1 ? 's' : ''} ago`
  return `${days} day${days > 1 ? 's' : ''} ago`
}

// ============================================================================
// Progress Utilities
// ============================================================================

/**
 * Calculate progress percentage
 *
 * @param current - Current step/value
 * @param total - Total steps/value
 * @returns Progress percentage (0-100)
 *
 * @example
 * ```ts
 * const progress = calculateProgress(3, 10) // 30
 * ```
 */
export function calculateProgress(current: number, total: number): number {
  if (total === 0) return 0
  return Math.min(100, Math.max(0, (current / total) * 100))
}

/**
 * Get progress bar color based on percentage
 *
 * @param percentage - Progress percentage (0-100)
 * @returns CSS color value
 */
export function getProgressColor(percentage: number): string {
  if (percentage >= 100) return '#28a745' // Green - Complete
  if (percentage >= 75) return '#17a2b8'  // Blue - Nearly done
  if (percentage >= 50) return '#007bff'  // Primary blue
  if (percentage >= 25) return '#ffc107'  // Yellow - In progress
  return '#6c757d' // Gray - Just started
}

/**
 * Format progress as text
 *
 * @param current - Current step
 * @param total - Total steps
 * @param status - Optional status text
 * @returns Formatted progress text
 *
 * @example
 * ```ts
 * const text = formatProgressText(3, 10, 'running') // "3/10 - running"
 * ```
 */
export function formatProgressText(
  current: number,
  total: number,
  status?: string
): string {
  const base = `${current}/${total}`
  return status ? `${base} - ${status}` : base
}

// ============================================================================
// Notification Utilities
// ============================================================================

/**
 * Create a notification object with defaults
 *
 * @param type - Notification type
 * @param title - Notification title
 * @param message - Notification message
 * @param options - Additional options
 * @returns WorkflowNotification object
 *
 * @example
 * ```ts
 * const notification = createNotification(
 *   'success',
 *   'Task Complete',
 *   'The workflow has finished successfully'
 * )
 * ```
 */
export function createNotification(
  type: NotificationType,
  title: string,
  message: string,
  options: Partial<WorkflowNotification> = {}
): WorkflowNotification {
  return {
    id: Date.now() + Math.random(),
    type,
    title,
    message,
    timestamp: Date.now(),
    ...options
  }
}

/**
 * Get auto-dismiss timeout for notification type
 *
 * @param type - Notification type
 * @returns Timeout in milliseconds (0 = no auto-dismiss)
 */
export function getNotificationTimeout(type: NotificationType): number {
  const timeouts: Record<NotificationType, number> = {
    'info': 10000,      // 10 seconds
    'success': 5000,    // 5 seconds
    'warning': 0,       // No auto-dismiss
    'error': 0,         // No auto-dismiss
    'approval': 0,      // No auto-dismiss
    'progress': 0       // No auto-dismiss
  }
  return timeouts[type]
}

// ============================================================================
// Workflow Status Utilities
// ============================================================================

/**
 * Get CSS class for workflow classification
 *
 * @param classification - Workflow classification
 * @returns CSS class string
 */
export function getClassificationClass(classification: string): string {
  const classes: Record<string, string> = {
    'simple': 'classification-simple',
    'research': 'classification-research',
    'install': 'classification-install',
    'complex': 'classification-complex'
  }
  return classes[classification.toLowerCase()] || 'classification-default'
}

/**
 * Get color for workflow classification
 *
 * @param classification - Workflow classification
 * @returns CSS color value
 */
export function getClassificationColor(classification: string): string {
  const colors: Record<string, string> = {
    'simple': '#28a745',
    'research': '#17a2b8',
    'install': '#ffc107',
    'complex': '#dc3545'
  }
  return colors[classification.toLowerCase()] || '#6c757d'
}

// ============================================================================
// Export All
// ============================================================================

export default {
  // Types (re-export for convenience)
  // Icon utilities
  getNotificationIcon,
  getNotificationColor,
  // Time utilities
  formatTimestamp,
  formatRelativeTime,
  // Progress utilities
  calculateProgress,
  getProgressColor,
  formatProgressText,
  // Notification utilities
  createNotification,
  getNotificationTimeout,
  // Status utilities
  getClassificationClass,
  getClassificationColor
}
