/**
 * Performance Emergency Configuration
 * TEMPORARILY DISABLE AGGRESSIVE MONITORING FOR IMMEDIATE PERFORMANCE FIX
 */

import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('Performance')

export const PERFORMANCE_MODE = {
  // Master performance switch - set to true for emergency performance mode
  ENABLED: true,

  // Monitoring intervals (in milliseconds) - dramatically increased for performance
  INTERVALS: {
    // System health checks
    HEALTH_CHECK_NORMAL: 300000,    // 5 minutes (was 30 seconds)
    HEALTH_CHECK_DEGRADED: 120000,  // 2 minutes (was 5 seconds)

    // Component-specific intervals
    RUM_DASHBOARD_REFRESH: 300000,     // 5 minutes (was 5 seconds) - EMERGENCY FIX
    CONNECTION_STATUS_UPDATE: 120000,  // 2 minutes (was 5 seconds) - EMERGENCY FIX
    CHAT_CONNECTION_CHECK: 300000,     // 5 minutes (was 30 seconds)
    SYSTEM_MONITOR_REFRESH: 180000,    // 3 minutes (was frequent)
    MULTI_MACHINE_HEALTH: 300000,      // 5 minutes (was 30 seconds)
    NOTIFICATION_CLEANUP: 120000,      // 2 minutes (was 10 seconds)

    // Backend services
    BACKEND_FALLBACK_MONITOR: 300000,  // 5 minutes
    SERVICE_MONITOR_REFRESH: 240000,   // 4 minutes
    VALIDATION_DASHBOARD: 300000,      // 5 minutes
    WORKFLOW_PROGRESS: 180000,         // 3 minutes

    // Desktop and terminal
    DESKTOP_CONNECTION_CHECK: 180000,  // 3 minutes (was 10 seconds)
    PLAYWRIGHT_HEALTH_CHECK: 300000,  // 5 minutes
    TERMINAL_FOCUS_CHECK: 60000,       // 1 minute

    // File operations
    LOG_VIEWER_REFRESH: 180000,        // 3 minutes (was 30 seconds)
    FILE_BROWSER_REFRESH: 120000,      // 2 minutes

    // Monitoring dashboards
    DASHBOARD_UPDATE: 300000,   // 5 minutes
    CHARTS_UPDATE: 180000,      // 3 minutes
    MCP_DASHBOARD_REFRESH: 300000,     // 5 minutes (was 30 seconds)
  },

  // Feature toggles - disable aggressive features
  FEATURES: {
    // Health monitoring
    FRONTEND_HEALTH_MONITOR: false,     // DISABLED - was creating WebSocket connections every 5 seconds
    ROUTER_HEALTH_MONITOR: false,       // DISABLED - was doing expensive DOM queries
    AUTOMATIC_RECOVERY: false,          // DISABLED - was causing page reloads
    WEBSOCKET_HEALTH_CHECKS: false,     // DISABLED - was creating connections constantly

    // UI components
    RUM_DASHBOARD: false,               // DISABLED - was refreshing every 5 seconds
    REAL_TIME_METRICS: false,           // DISABLED - was updating constantly
    PERFORMANCE_OBSERVER: false,        // DISABLED - was consuming resources
    DOM_MUTATION_OBSERVER: false,       // DISABLED - was monitoring DOM changes

    // Background tasks
    CACHE_POISONING_DETECTION: false,   // DISABLED - was running every minute
    BACKGROUND_VALIDATION: false,       // DISABLED - was running constant checks
    AUTO_CLEANUP_TASKS: false,          // DISABLED - were running every 10 seconds

    // Development features
    HOT_MODULE_REPLACEMENT_MONITORING: false,  // May be causing reload loops
    DEV_SERVER_POLLING: false,                 // May be polling file system
  },

  // Reduced batch sizes and limits
  LIMITS: {
    MAX_CONCURRENT_HEALTH_CHECKS: 1,    // Reduced from unlimited
    MAX_NOTIFICATIONS_DISPLAYED: 3,     // Reduced from 10
    MAX_CACHED_RESPONSES: 50,           // Reduced from unlimited
    MAX_WEBSOCKET_RECONNECT_ATTEMPTS: 2, // Reduced from 10

    // Component limits
    MAX_CHAT_HISTORY_ITEMS: 50,         // Reduced for performance
    MAX_LOG_ENTRIES_DISPLAYED: 100,     // Reduced for performance
    MAX_CONCURRENT_FILE_OPERATIONS: 2,  // Reduced for performance
  },

  // Timeouts (in milliseconds) - more forgiving
  TIMEOUTS: {
    API_REQUEST: 15000,          // 15 seconds (was 10)
    WEBSOCKET_CONNECTION: 10000, // 10 seconds (was 5)
    HEALTH_CHECK: 20000,         // 20 seconds (was 10)
    FILE_OPERATION: 30000,       // 30 seconds (was 10)

    // Component timeouts
    COMPONENT_MOUNT: 5000,       // 5 seconds max mount time
    ROUTE_NAVIGATION: 10000,     // 10 seconds max navigation time
    ASYNC_OPERATION: 15000,      // 15 seconds max async operation
  },

  // Debug configuration
  DEBUG: {
    LOG_PERFORMANCE_ISSUES: true,       // Log performance problems
    LOG_DISABLED_FEATURES: true,        // Log what was disabled
    SHOW_PERFORMANCE_WARNINGS: true,    // Show performance warnings
    MEASURE_COMPONENT_RENDER_TIME: false, // Disable for performance
  }
};

/**
 * Get interval for a specific monitoring task
 */
export function getPerformanceInterval(intervalName, defaultValue) {
  if (!PERFORMANCE_MODE.ENABLED) {
    return defaultValue;
  }

  return PERFORMANCE_MODE.INTERVALS[intervalName] || defaultValue;
}

/**
 * Check if a feature should be enabled
 */
export function isFeatureEnabled(featureName) {
  if (!PERFORMANCE_MODE.ENABLED) {
    return true; // All features enabled when performance mode off
  }

  const enabled = PERFORMANCE_MODE.FEATURES[featureName];

  if (enabled === false && PERFORMANCE_MODE.DEBUG.LOG_DISABLED_FEATURES) {
    logger.debug(`Feature "${featureName}" DISABLED for performance`);
  }

  return enabled !== false; // Default to true unless explicitly false
}

/**
 * Get performance limit for a specific resource
 */
export function getPerformanceLimit(limitName, defaultValue) {
  if (!PERFORMANCE_MODE.ENABLED) {
    return defaultValue;
  }

  return PERFORMANCE_MODE.LIMITS[limitName] || defaultValue;
}

/**
 * Get timeout for a specific operation
 */
export function getPerformanceTimeout(timeoutName, defaultValue) {
  if (!PERFORMANCE_MODE.ENABLED) {
    return defaultValue;
  }

  return PERFORMANCE_MODE.TIMEOUTS[timeoutName] || defaultValue;
}

/**
 * Log performance issue
 */
export function logPerformanceIssue(component, issue, data = {}) {
  if (PERFORMANCE_MODE.DEBUG.LOG_PERFORMANCE_ISSUES) {
    logger.warn(`${component}: ${issue}`, data);
  }
}

/**
 * Show performance warning to user
 */
export function showPerformanceWarning(message) {
  if (PERFORMANCE_MODE.DEBUG.SHOW_PERFORMANCE_WARNINGS) {
    logger.warn(message);

    // Could also show user notification here if needed
    if (typeof window !== 'undefined' && window.appStore) {
      window.appStore.addSystemNotification?.({
        severity: 'warning',
        title: 'Performance Issue',
        message: message,
        autoHide: 5000
      });
    }
  }
}

// Export performance mode status
export function isPerformanceModeEnabled() {
  return PERFORMANCE_MODE.ENABLED;
}

// Emergency performance reset
export function enableEmergencyPerformanceMode() {
  PERFORMANCE_MODE.ENABLED = true;
  logger.info('EMERGENCY PERFORMANCE MODE ENABLED');

  // Could trigger immediate cleanup here
  if (typeof window !== 'undefined') {
    // Clear all intervals that might be running
    for (let i = 1; i < 99999; i++) {
      window.clearInterval(i);
      window.clearTimeout(i);
    }

    logger.info('Cleared all existing intervals and timeouts');
  }
}

// Disable performance mode (restore normal operation)
export function disablePerformanceMode() {
  PERFORMANCE_MODE.ENABLED = false;
  logger.info('Performance mode DISABLED - normal operation restored');
}

export default PERFORMANCE_MODE;
