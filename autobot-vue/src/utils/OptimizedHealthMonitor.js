/**
 * Optimized Frontend Health Monitor
 * Performance-aware monitoring with realistic network timeouts (30s budget per minute)
 * Event-driven architecture with intelligent adaptive intervals
 */

import { cacheBuster } from './CacheBuster.js';
import { createLogger } from '@/utils/debugUtils';

// Create scoped logger for OptimizedHealthMonitor
const logger = createLogger('OptimizedHealthMonitor');

class OptimizedHealthMonitor {
    constructor() {
        this.isMonitoring = false;
        this.performanceBudget = {
            maxOverheadPerMinute: 30000, // Maximum 30s monitoring overhead per minute (realistic for network requests)
            currentOverhead: 0,
            lastReset: Date.now()
        };

        // Health status with intelligent defaults
        this.healthStatus = {
            overall: 'healthy',
            backend: 'unknown',
            frontend: 'healthy',
            websocket: 'unknown',
            router: 'healthy',
            initialization: {
                status: 'unknown',
                message: ''
            }
        };

        // Adaptive monitoring configuration
        this.config = {
            // Adaptive intervals based on system state
            intervals: {
                healthy: 120000,    // 2 minutes when healthy
                degraded: 60000,    // 1 minute when degraded
                critical: 15000,    // 15 seconds when critical
                userActive: 10000   // 10 seconds when user viewing dashboard
            },
            performanceThresholds: {
                maxCheckDuration: 3000,  // 3s max per health check (realistic for network requests)
                degradeThreshold: 5000,   // 5s triggers interval increase
                criticalThreshold: 10000   // 10s triggers monitoring reduction (CRITICAL FIX: was 50ms)
            }
        };

        // Event-driven monitoring state
        this.eventListeners = new Map();
        this.consecutiveFailures = { backend: 0, websocket: 0 };
        this.healthCheckTimer = null;
        this.listeners = [];
        this.isUserViewing = false;
        this.lastHealthCheck = 0;

        // Performance tracking
        this.performanceMetrics = {
            checksPerformed: 0,
            totalCheckTime: 0,
            averageCheckTime: 0,
            lastSlowCheck: null
        };

        this.initialize();
    }

    /**
     * Initialize optimized monitoring system
     */
    initialize() {

        // Set up event-driven monitoring
        this.setupEventListeners();

        // Set up performance budget tracking
        this.setupPerformanceBudget();

        // Start with healthy interval
        this.scheduleNextCheck('healthy');

        this.isMonitoring = true;
    }

    /**
     * Set up event listeners for immediate response to issues
     */
    setupEventListeners() {
        // Page visibility - pause monitoring when user not present
        this.addEventListenerWithTracking('visibilitychange', () => {
            if (document.hidden) {
                this.pauseMonitoring();
            } else {
                this.resumeMonitoring();
            }
        });

        // Global error events - immediate health status update
        this.addEventListenerWithTracking('error', (event) => {
            this.onErrorDetected(event);
        });

        // Unhandled promise rejections
        this.addEventListenerWithTracking('unhandledrejection', (event) => {
            this.onErrorDetected(event);
        });

        // Network status changes
        this.addEventListenerWithTracking('online', () => {
            this.onNetworkStatusChange('online');
        });

        this.addEventListenerWithTracking('offline', () => {
            this.onNetworkStatusChange('offline');
        });

        // Router navigation events (when available)
        if (window.router) {
            window.router.afterEach(() => {
                this.onRouterNavigation();
            });
        }
    }

    /**
     * Add event listener with cleanup tracking
     */
    addEventListenerWithTracking(event, handler) {
        const boundHandler = handler.bind(this);
        window.addEventListener(event, boundHandler);
        this.eventListeners.set(event, boundHandler);
    }

    /**
     * Set up performance budget monitoring
     */
    setupPerformanceBudget() {
        // Reset performance budget every minute
        setInterval(() => {
            this.performanceBudget.currentOverhead = 0;
            this.performanceBudget.lastReset = Date.now();

            // Log performance stats
            if (this.performanceMetrics.checksPerformed > 0) {
            }
        }, 60000);
    }

    /**
     * Schedule next health check with adaptive intervals
     */
    scheduleNextCheck(healthState = null) {
        if (this.healthCheckTimer) {
            clearTimeout(this.healthCheckTimer);
        }

        // Determine interval based on health state
        const state = healthState || this.determineHealthState();
        let interval = this.config.intervals[state];

        // Adjust for user activity
        if (this.isUserViewing && state !== 'critical') {
            interval = this.config.intervals.userActive;
        }

        // Adjust for performance budget
        if (this.isPerformanceBudgetExceeded()) {
            interval = Math.max(interval * 2, this.config.intervals.healthy);
        }

        this.healthCheckTimer = setTimeout(() => {
            this.performHealthCheck();
        }, interval);
    }

    /**
     * Determine current health state for adaptive intervals
     */
    determineHealthState() {
        const overallHealth = this.healthStatus.overall;
        const hasConsecutiveFailures = Object.values(this.consecutiveFailures).some(count => count >= 2);

        if (overallHealth === 'critical' || hasConsecutiveFailures) {
            return 'critical';
        } else if (overallHealth === 'degraded') {
            return 'degraded';
        } else {
            return 'healthy';
        }
    }

    /**
     * Check if performance budget is exceeded
     */
    isPerformanceBudgetExceeded() {
        return this.performanceBudget.currentOverhead >= this.performanceBudget.maxOverheadPerMinute;
    }

    /**
     * Perform health check with performance monitoring
     */
    async performHealthCheck() {
        if (!this.isMonitoring || this.isPerformanceBudgetExceeded()) {
            this.scheduleNextCheck();
            return;
        }

        const startTime = performance.now();
        this.lastHealthCheck = Date.now();

        try {
            // Only perform essential health checks
            const healthResults = await Promise.race([
                this.performEssentialHealthChecks(),
                this.timeoutPromise(this.config.performanceThresholds.criticalThreshold)
            ]);

            this.processHealthResults(healthResults);
            this.updateOverallHealth();
            this.notifyHealthChange();

        } catch (error) {
            logger.warn('Health check failed or timed out:', error.message);
            this.handleHealthCheckFailure();
        } finally {
            // Track performance
            const duration = performance.now() - startTime;
            this.trackPerformance(duration);

            // Schedule next check
            this.scheduleNextCheck();
        }
    }

    /**
     * Perform only essential health checks
     */
    async performEssentialHealthChecks() {
        const checks = [];

        // Backend health - most critical
        checks.push(this.checkBackendHealth());

        // Only add additional checks if performance budget allows
        if (this.performanceBudget.currentOverhead < 25) {
            // WebSocket status check (lightweight)
            if (window.wsConnected !== undefined) {
                this.healthStatus.websocket = window.wsConnected ? 'healthy' : 'degraded';
            }
        }

        const results = await Promise.allSettled(checks);
        return results;
    }

    /**
     * Create timeout promise for performance enforcement
     */
    timeoutPromise(timeoutMs) {
        return new Promise((_, reject) => {
            setTimeout(() => reject(new Error(`Health check timeout after ${timeoutMs}ms`)), timeoutMs);
        });
    }

    /**
     * Check backend health with optimized approach
     */
    async checkBackendHealth() {
        const startTime = performance.now();

        try {
            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), 8000); // 8 second timeout

            const response = await fetch('/api/system/health', {
                signal: controller.signal,
                headers: cacheBuster.getBustHeaders()
            });

            clearTimeout(timeoutId);

            if (response.ok) {
                const healthData = await response.json();

                // Extract initialization status if available
                if (healthData.initialization) {
                    this.healthStatus.initialization = {
                        status: healthData.initialization.status || 'unknown',
                        message: healthData.initialization.message || ''
                    };
                }

                this.healthStatus.backend = 'healthy';
                this.consecutiveFailures.backend = 0;
                return { status: 'healthy', responseTime: performance.now() - startTime };
            } else {
                throw new Error(`Backend responded with status: ${response.status}`);
            }

        } catch (error) {
            this.consecutiveFailures.backend++;

            if (this.consecutiveFailures.backend >= 3) {
                this.healthStatus.backend = 'critical';
            } else {
                this.healthStatus.backend = 'degraded';
            }

            return {
                status: 'unhealthy',
                error: error.message,
                consecutiveFailures: this.consecutiveFailures.backend
            };
        }
    }

    /**
     * Process health check results
     */
    processHealthResults(results) {
        results.forEach((result, index) => {
            if (result.status === 'rejected') {
                logger.warn(`Health check ${index} failed:`, result.reason);
            }
        });
    }

    /**
     * Update overall health status
     */
    updateOverallHealth() {
        const statuses = [this.healthStatus.backend, this.healthStatus.frontend];

        if (statuses.includes('critical')) {
            this.healthStatus.overall = 'critical';
        } else if (statuses.includes('degraded')) {
            this.healthStatus.overall = 'degraded';
        } else if (statuses.every(status => status === 'healthy')) {
            this.healthStatus.overall = 'healthy';
        } else {
            this.healthStatus.overall = 'unknown';
        }
    }

    /**
     * Handle health check failure
     */
    handleHealthCheckFailure() {
        this.healthStatus.overall = 'degraded';
        // Don't trigger aggressive recovery - let user decide
    }

    /**
     * Track monitoring performance
     */
    trackPerformance(duration) {
        this.performanceBudget.currentOverhead += duration;
        this.performanceMetrics.checksPerformed++;
        this.performanceMetrics.totalCheckTime += duration;
        this.performanceMetrics.averageCheckTime = this.performanceMetrics.totalCheckTime / this.performanceMetrics.checksPerformed;

        // Log slow checks
        if (duration > this.config.performanceThresholds.degradeThreshold) {
            this.performanceMetrics.lastSlowCheck = { duration, timestamp: Date.now() };
            logger.warn(`Slow health check: ${duration.toFixed(1)}ms`);
        }
    }

    /**
     * Event handlers
     */
    onErrorDetected(_event) {
        this.healthStatus.frontend = 'degraded';
        this.updateOverallHealth();
        this.notifyHealthChange();
    }

    onNetworkStatusChange(status) {
        if (status === 'offline') {
            this.healthStatus.backend = 'critical';
        }
        this.updateOverallHealth();
        this.notifyHealthChange();
    }

    onRouterNavigation() {
        // Router navigation successful - mark as healthy
        this.healthStatus.router = 'healthy';
    }

    /**
     * User interaction methods
     */
    setUserViewing(isViewing) {
        this.isUserViewing = isViewing;

        // Reschedule with appropriate interval
        this.scheduleNextCheck();
    }

    pauseMonitoring() {
        this.isMonitoring = false;
        if (this.healthCheckTimer) {
            clearTimeout(this.healthCheckTimer);
        }
    }

    resumeMonitoring() {
        this.isMonitoring = true;
        this.scheduleNextCheck();
    }

    /**
     * Manual health check for user-triggered refresh
     */
    async performManualHealthCheck() {
        return this.performHealthCheck();
    }

    /**
     * Listener management
     */
    onHealthChange(callback) {
        this.listeners.push(callback);
    }

    notifyHealthChange() {
        const healthData = {
            status: this.healthStatus,
            metrics: this.performanceMetrics,
            timestamp: Date.now(),
            monitoring: {
                isActive: this.isMonitoring,
                performanceBudget: this.performanceBudget,
                lastCheck: this.lastHealthCheck
            }
        };

        this.listeners.forEach(callback => {
            try {
                callback(healthData);
            } catch (error) {
                logger.error('Listener error:', error);
            }
        });
    }

    /**
     * Get current health status
     */
    getHealthStatus() {
        return {
            ...this.healthStatus,
            isMonitoring: this.isMonitoring,
            performanceMetrics: this.performanceMetrics,
            consecutiveFailures: this.consecutiveFailures,
            lastHealthCheck: this.lastHealthCheck
        };
    }

    /**
     * Cleanup resources
     */
    destroy() {

        this.pauseMonitoring();

        // Remove event listeners
        this.eventListeners.forEach((handler, event) => {
            window.removeEventListener(event, handler);
        });
        this.eventListeners.clear();

        this.listeners = [];
    }
}

// Export singleton instance
export const optimizedHealthMonitor = new OptimizedHealthMonitor();

// Make available globally for debugging
if (typeof window !== 'undefined') {
    window.optimizedHealthMonitor = optimizedHealthMonitor;
}

export default OptimizedHealthMonitor;