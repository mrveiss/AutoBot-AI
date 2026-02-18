/**
 * Centralized Error Handling Utility for AutoBot Frontend
 * Provides consistent error handling, logging, and user feedback
 *
 * @author mrveiss
 * @copyright 2025 mrveiss
 */

import { createLogger } from '@/utils/debugUtils';
import { notificationBridge } from '@/utils/notificationBridge';

// Create scoped logger for ErrorHandler
const logger = createLogger('ErrorHandler');

class ErrorHandler {
  constructor() {
    this.isProduction = import.meta.env.PROD;
    this.errorLog = [];
    this.maxLogSize = 100;
  }

  /**
   * Handle API errors with user-friendly messages
   * @param {Error} error - The error object
   * @param {string} context - Context where error occurred
   * @param {boolean} showToUser - Whether to show error to user
   * @returns {object} Formatted error response
   */
  handleApiError(error, context = '', showToUser = true) {
    const errorInfo = {
      timestamp: new Date().toISOString(),
      context,
      originalError: error,
      userMessage: this.generateUserMessage(error),
      technicalMessage: error.message || 'Unknown error',
      stack: error.stack,
      isCritical: this.isCriticalError(error),
    };

    // Log error internally
    this.logError(errorInfo);

    // Send to monitoring if available
    this.sendToMonitoring(errorInfo);

    // Show user notification if requested
    if (showToUser) {
      this.showUserNotification(errorInfo.userMessage, 'error', errorInfo.isCritical);
    }

    return {
      success: false,
      error: errorInfo.userMessage,
      technical: this.isProduction ? undefined : errorInfo.technicalMessage,
      timestamp: errorInfo.timestamp,
      isCritical: errorInfo.isCritical,
    };
  }

  /**
   * Determine if an error is critical (requires user acknowledgment)
   * Critical errors include server errors, authentication failures, etc.
   * @param {Error} error - The error object
   * @returns {boolean} True if error is critical
   */
  isCriticalError(error) {
    const message = error.message || '';

    // Server errors (5xx) are critical
    if (message.includes('HTTP 500') || message.includes('HTTP 502') ||
        message.includes('HTTP 503') || message.includes('HTTP 504')) {
      return true;
    }

    // Authentication errors are critical
    if (message.includes('HTTP 401') || message.includes('HTTP 403')) {
      return true;
    }

    // Network connection failures are critical
    if (message.includes('Cannot connect to backend') ||
        message.includes('Failed to fetch') && !message.includes('timeout')) {
      return true;
    }

    return false;
  }

  /**
   * Generate user-friendly error messages
   * @param {Error} error - The error object
   * @returns {string} User-friendly message
   */
  generateUserMessage(error) {
    const message = error.message || '';

    // ENHANCED: Handle new ApiClient error messages first

    // Network errors (new format from ApiClient)
    if (message.includes('Network error: Cannot connect to backend')) {
      return 'Cannot connect to the backend service. Please ensure the server is running and try refreshing the page.';
    }

    // Timeout errors (enhanced from ApiClient)
    if (message.includes('Request timeout') && message.includes('took longer than')) {
      const endpointMatch = message.match(/GET|POST|PUT|DELETE [^\s]+/);
      const endpoint = endpointMatch ? endpointMatch[0] : 'API endpoint';

      if (message.includes('/api/prompts/')) {
        return 'Loading prompts is taking longer than expected. This may be due to many files. Please wait or try refreshing.';
      } else if (message.includes('/api/settings/')) {
        return 'Loading settings is taking longer than expected. Please wait or check your connection.';
      } else {
        return `The ${endpoint} request is taking longer than expected. This may indicate the server is busy.`;
      }
    }

    // Request cancelled (enhanced from ApiClient)
    if (message.includes('Request was cancelled') && message.includes('navigation or component unmounting')) {
      return 'Request was cancelled. This usually happens when navigating to another page.';
    }

    // Legacy error formats (keep for compatibility)

    // Network errors
    if (message.includes('Failed to fetch') || message.includes('NetworkError')) {
      return 'Connection failed. Please check your internet connection and try again.';
    }

    // Timeout errors (legacy AbortError)
    if (message.includes('timeout') || message.includes('AbortError') || message.includes('signal is aborted without reason')) {
      return 'Request timed out. The server may be busy, please try again.';
    }

    // HTTP status codes (enhanced with more specific messages)
    if (message.includes('HTTP 400')) {
      return 'Invalid request. Please check your input and try again.';
    }
    if (message.includes('HTTP 401')) {
      return 'Authentication required. Please log in and try again.';
    }
    if (message.includes('HTTP 403')) {
      return 'Access denied. You may not have permission for this action.';
    }
    if (message.includes('HTTP 404')) {
      if (message.includes('Endpoint not found')) {
        return 'API endpoint not found. This may indicate a server configuration issue.';
      }
      return 'Requested resource not found. Please refresh the page.';
    }
    if (message.includes('HTTP 429')) {
      return 'Too many requests. Please wait a moment and try again.';
    }
    if (message.includes('HTTP 500') || message.includes('HTTP 502') || message.includes('HTTP 503')) {
      return 'Server error. Please try again later or contact support.';
    }
    if (message.includes('HTTP 504')) {
      return 'Server timeout. The operation took too long to complete. Please try again.';
    }

    // WebSocket errors
    if (message.includes('WebSocket') || message.includes('socket')) {
      return 'Connection interrupted. The page will attempt to reconnect automatically.';
    }

    // Validation errors
    if (message.includes('validation') || message.includes('invalid')) {
      return 'Please check your input and try again.';
    }

    // File/prompt specific errors
    if (message.includes('prompts') && message.includes('timed out')) {
      return 'Loading prompts took too long. The system has many prompt files. Please try again.';
    }

    // Default message
    return 'An unexpected error occurred. Please try again or contact support if the problem persists.';
  }

  /**
   * Log error to internal storage and console
   * @param {object} errorInfo - Error information object
   */
  logError(errorInfo) {
    // Add to internal log
    this.errorLog.unshift(errorInfo);

    // Keep log size manageable
    if (this.errorLog.length > this.maxLogSize) {
      this.errorLog = this.errorLog.slice(0, this.maxLogSize);
    }

    // Console logging based on environment
    if (!this.isProduction) {
      logger.error(`Error in ${errorInfo.context || 'Unknown Context'}:`, {
        userMessage: errorInfo.userMessage,
        technical: errorInfo.technicalMessage,
        originalError: errorInfo.originalError,
        stack: errorInfo.stack
      });
    } else {
      // Production: minimal logging
      logger.error(`Error [${errorInfo.context}]:`, errorInfo.userMessage);
    }
  }

  /**
   * Handle non-critical warnings
   * @param {string} message - Warning message
   * @param {string} context - Context where warning occurred
   */
  handleWarning(message, context = '') {
    const warningInfo = {
      timestamp: new Date().toISOString(),
      context,
      message,
      type: 'warning'
    };

    if (!this.isProduction) {
      logger.warn(`Warning [${context}]:`, message);
    }

    // Could send to monitoring for production warnings
    this.sendToMonitoring(warningInfo);
  }

  /**
   * Handle informational messages (development only)
   * @param {string} message - Info message
   * @param {string} context - Context
   */
  handleInfo(message, context = '') {
    if (!this.isProduction) {
      logger.info(`Info [${context}]:`, message);
    }
  }

  /**
   * Send error to monitoring system
   * @param {object} errorInfo - Error information
   */
  sendToMonitoring(errorInfo) {
    try {
      // Send to RUM monitoring if available
      if (window.rum && typeof window.rum.trackError === 'function') {
        window.rum.trackError(errorInfo);
      }

      // Send to backend error tracking if available
      if (window.apiClient && typeof window.apiClient.reportError === 'function') {
        window.apiClient.reportError(errorInfo).catch(() => {
          // Fail silently for error reporting errors
        });
      }
    } catch (_e) {
      // Fail silently - don't let error reporting break the app
    }
  }

  /**
   * Show user notification via toast system
   * Integrates with notificationBridge for rate-limited, deduplicated notifications.
   *
   * @param {string} message - Message to show
   * @param {string} type - Type: 'error', 'warning', 'info', 'success'
   * @param {boolean} isCritical - If true, error notifications won't auto-dismiss
   */
  showUserNotification(message, type = 'info', isCritical = false) {
    // Use notification bridge if available (Issue #502)
    if (notificationBridge.isReady()) {
      notificationBridge.notify(message, type, isCritical);
    } else {
      // Fallback: log to console if bridge not yet initialized
      // This can happen during early app startup
      if (type === 'error') {
        logger.error('User Error:', message);
      } else if (type === 'warning') {
        logger.warn('User Warning:', message);
      } else {
        logger.info('User Notification:', message);
      }
    }
  }

  /**
   * Show a success notification to the user
   * @param {string} message - Success message to show
   */
  showSuccess(message) {
    this.showUserNotification(message, 'success', false);
  }

  /**
   * Show an info notification to the user
   * @param {string} message - Info message to show
   */
  showInfo(message) {
    this.showUserNotification(message, 'info', false);
  }

  /**
   * Show a warning notification to the user
   * @param {string} message - Warning message to show
   */
  showWarning(message) {
    this.showUserNotification(message, 'warning', false);
  }

  /**
   * Show an error notification to the user
   * @param {string} message - Error message to show
   * @param {boolean} isCritical - If true, error won't auto-dismiss
   */
  showError(message, isCritical = false) {
    this.showUserNotification(message, 'error', isCritical);
  }

  /**
   * Get recent errors (for debugging)
   * @param {number} limit - Number of recent errors to return
   * @returns {Array} Recent errors
   */
  getRecentErrors(limit = 10) {
    return this.errorLog.slice(0, limit);
  }

  /**
   * Clear error log
   */
  clearErrors() {
    this.errorLog = [];
  }

  /**
   * Handle promise rejections globally
   * @param {Error} error - Unhandled promise rejection
   */
  handleUnhandledRejection(error) {
    this.handleApiError(error, 'Unhandled Promise Rejection', false);
  }

  /**
   * Handle JavaScript errors globally
   * @param {Error} error - JavaScript error
   * @param {string} source - Source of error
   */
  handleJavaScriptError(error, source = '') {
    this.handleApiError(error, `JavaScript Error: ${source}`, false);
  }
}

// Create singleton instance
const errorHandler = new ErrorHandler();

// Set up global error handlers
if (typeof window !== 'undefined') {
  window.addEventListener('unhandledrejection', (event) => {
    errorHandler.handleUnhandledRejection(event.reason);
    event.preventDefault(); // Prevent default browser error handling
  });

  window.addEventListener('error', (event) => {
    errorHandler.handleJavaScriptError(event.error, event.filename);
  });

  // Make available globally for debugging
  window.errorHandler = errorHandler;
}

export default errorHandler;
