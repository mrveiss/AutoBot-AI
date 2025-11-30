/**
 * Store Monitor - Tracks Pinia store performance and state changes
 * Provides debugging insights for store operations
 */

import { createLogger } from '@/utils/debugUtils';

// Create scoped logger for StoreMonitor
const logger = createLogger('StoreMonitor');

class StoreMonitor {
  constructor() {
    this.isEnabled = !import.meta.env.PROD; // Only enable in development
    this.actionLog = [];
    this.performanceLog = [];
    this.maxLogSize = 100;
  }

  /**
   * Track store action performance
   * @param {string} storeName - Name of the store
   * @param {string} actionName - Name of the action
   * @param {Function} action - Action function to wrap
   * @returns {Function} Wrapped action with monitoring
   */
  wrapAction(storeName, actionName, action) {
    if (!this.isEnabled) {
      return action;
    }

    return async function(...args) {
      const startTime = performance.now();
      
      try {
        const result = await action.apply(this, args);
        const endTime = performance.now();
        const duration = endTime - startTime;

        // Log performance
        this.logActionPerformance(storeName, actionName, duration, 'success', args);

        // Track slow operations
        if (duration > 1000) { // > 1 second
          this.trackSlowOperation(storeName, actionName, duration, args);
        }

        return result;
      } catch (error) {
        const endTime = performance.now();
        const duration = endTime - startTime;
        
        this.logActionPerformance(storeName, actionName, duration, 'error', args, error);
        
        // Track errors
        this.trackStoreError(storeName, actionName, error, args);
        
        throw error;
      }
    }.bind(this);
  }

  /**
   * Log action performance
   */
  logActionPerformance(storeName, actionName, duration, status, args, error = null) {
    const logEntry = {
      timestamp: new Date().toISOString(),
      store: storeName,
      action: actionName,
      duration: Math.round(duration),
      status,
      argsCount: args.length,
      error: error?.message || null
    };

    this.performanceLog.unshift(logEntry);

    // Keep log size manageable
    if (this.performanceLog.length > this.maxLogSize) {
      this.performanceLog = this.performanceLog.slice(0, this.maxLogSize);
    }

    // Console logging for development
    if (status === 'error') {
      logger.warn(`🏪 Store Error [${storeName}.${actionName}]:`, error?.message, `(${duration}ms)`);
    } else if (duration > 500) {
      logger.info(`🏪 Slow Store Action [${storeName}.${actionName}]:`, `${duration}ms`);
    } else {
      logger.debug(`🏪 Store Action [${storeName}.${actionName}]:`, `${duration}ms`);
    }
  }

  /**
   * Track slow operations for performance analysis
   */
  trackSlowOperation(storeName, actionName, duration, args) {
    const slowOp = {
      timestamp: new Date().toISOString(),
      store: storeName,
      action: actionName,
      duration: Math.round(duration),
      argsCount: args.length,
      type: 'slow_operation'
    };

    // Send to RUM if available
    if (window.rum && typeof window.rum.reportCriticalIssue === 'function') {
      window.rum.reportCriticalIssue('slow_store_operation', slowOp);
    }

    logger.warn('🐌 Slow Store Operation:', slowOp);
  }

  /**
   * Track store errors
   */
  trackStoreError(storeName, actionName, error, args) {
    const errorInfo = {
      timestamp: new Date().toISOString(),
      store: storeName,
      action: actionName,
      error: error.message,
      stack: error.stack,
      argsCount: args.length
    };

    // Send to RUM if available
    if (window.rum && typeof window.rum.reportCriticalIssue === 'function') {
      window.rum.reportCriticalIssue('store_error', errorInfo);
    }
  }

  /**
   * Get performance statistics
   */
  getPerformanceStats() {
    if (!this.isEnabled) {
      return { enabled: false };
    }

    const stats = {
      totalActions: this.performanceLog.length,
      averageDuration: 0,
      slowActions: 0,
      errorRate: 0,
      storeBreakdown: new Map(),
      actionBreakdown: new Map()
    };

    if (this.performanceLog.length === 0) {
      return stats;
    }

    // Calculate averages and breakdowns
    let totalDuration = 0;
    let errorCount = 0;

    for (const entry of this.performanceLog) {
      totalDuration += entry.duration;
      
      if (entry.status === 'error') {
        errorCount++;
      }
      
      if (entry.duration > 500) {
        stats.slowActions++;
      }

      // Store breakdown
      const storeKey = entry.store;
      if (!stats.storeBreakdown.has(storeKey)) {
        stats.storeBreakdown.set(storeKey, { count: 0, totalDuration: 0 });
      }
      const storeStats = stats.storeBreakdown.get(storeKey);
      storeStats.count++;
      storeStats.totalDuration += entry.duration;

      // Action breakdown
      const actionKey = `${entry.store}.${entry.action}`;
      if (!stats.actionBreakdown.has(actionKey)) {
        stats.actionBreakdown.set(actionKey, { count: 0, totalDuration: 0, errors: 0 });
      }
      const actionStats = stats.actionBreakdown.get(actionKey);
      actionStats.count++;
      actionStats.totalDuration += entry.duration;
      if (entry.status === 'error') {
        actionStats.errors++;
      }
    }

    stats.averageDuration = Math.round(totalDuration / this.performanceLog.length);
    stats.errorRate = Math.round((errorCount / this.performanceLog.length) * 100);

    return stats;
  }

  /**
   * Clear all monitoring data
   */
  clear() {
    this.actionLog = [];
    this.performanceLog = [];
  }

  /**
   * Get recent actions for debugging
   */
  getRecentActions(limit = 20) {
    return this.performanceLog.slice(0, limit);
  }
}

// Export singleton instance
export const storeMonitor = new StoreMonitor();

// Make available globally for debugging
if (typeof window !== 'undefined') {
  window.storeMonitor = storeMonitor;
}

export default storeMonitor;