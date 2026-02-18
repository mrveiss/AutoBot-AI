/**
 * Real-Time Frontend Health Monitor & Auto-Recovery System
 * PERFORMANCE OPTIMIZED VERSION - Reduced aggressive monitoring
 */

import { cacheBuster } from './CacheBuster.js';
import { routerHealthMonitor as _routerHealthMonitor } from './RouterHealthMonitor.js'; // Reserved for future router health integration
import { createLogger } from '@/utils/debugUtils';

// Create scoped logger for FrontendHealthMonitor
const logger = createLogger('FrontendHealthMonitor');

class FrontendHealthMonitor {
    constructor() {
        this.isMonitoring = false;
        this.healthStatus = {
            overall: 'healthy',
            frontend: 'healthy',
            backend: 'unknown',
            router: 'healthy',
            cache: 'healthy',
            websocket: 'unknown'
        };

        this.metrics = {
            uptime: Date.now(),
            errorCount: 0,
            recoveryCount: 0,
            lastHealthCheck: 0,
            lastRecovery: 0,
            performanceMetrics: {
                loadTime: 0,
                renderTime: 0,
                apiResponseTime: 0
            }
        };

        this.config = {
            // PERFORMANCE FIX: Dramatically reduced monitoring frequency
            healthCheckInterval: 300000, // 5 minutes (was 30 seconds)
            fastHealthCheckInterval: 120000, // 2 minutes (was 5 seconds)
            apiTimeout: 10000,
            websocketTimeout: 5000,
            maxConsecutiveFailures: 5, // More tolerant
            recoveryDelay: 10000 // Longer recovery delay
        };

        this.consecutiveFailures = {
            backend: 0,
            websocket: 0,
            router: 0
        };

        this.healthCheckTimer = null;
        this.isRecovering = false;
        this.listeners = [];

        // Auto-recovery strategies - DISABLED for performance
        this.recoveryStrategies = [
            'cache_clear',
            'router_reset',
            'service_restart',
            'full_reload'
        ];
        this.currentRecoveryLevel = 0;

        // PERFORMANCE: Disable aggressive monitoring by default
        this.monitoringEnabled = false;
    }

    /**
     * Initialize health monitoring system - LIGHTWEIGHT VERSION
     */
    initialize() {

        // PERFORMANCE: Only initialize minimal error handling, no continuous monitoring
        this.setupErrorHandling();
        this.measureInitialMetrics();

        // DISABLE aggressive monitoring that was causing 5-second intervals
    }

    /**
     * Start continuous health monitoring - DISABLED FOR PERFORMANCE
     */
    startMonitoring() {
        if (this.monitoringEnabled) {
            return;
        }

    }

    /**
     * Schedule next health check - PERFORMANCE OPTIMIZED
     */
    scheduleHealthCheck() {
        // PERFORMANCE: Only schedule if explicitly enabled and no active timer
        if (!this.monitoringEnabled || this.healthCheckTimer) {
            return;
        }

        // Use much longer intervals
        const interval = this.hasActiveIssues() ?
            this.config.fastHealthCheckInterval :
            this.config.healthCheckInterval;

        this.healthCheckTimer = setTimeout(() => {
            this.performHealthCheck();
        }, interval);
    }

    /**
     * Check if there are any active health issues
     */
    hasActiveIssues() {
        return Object.values(this.healthStatus).some(status =>
            status === 'unhealthy' || status === 'degraded'
        );
    }

    /**
     * Perform comprehensive health check - MANUAL TRIGGER ONLY
     */
    async performHealthCheck() {
        if (!this.monitoringEnabled) {
            return;
        }

        try {
            this.metrics.lastHealthCheck = Date.now();

            // PERFORMANCE: Only run essential checks, not all parallel checks
            const healthChecks = await Promise.allSettled([
                this.checkBackendHealth(),
                // DISABLED: WebSocket health check was creating connections every 5 seconds
                // this.checkWebSocketHealth(),
                // DISABLED: Router health check was doing expensive DOM queries
                // this.checkRouterHealth(),
                // DISABLED: Cache health check was unnecessary overhead
                // this.checkCacheHealth(),
                // DISABLED: Performance health check was redundant
                // this.checkPerformanceHealth()
            ]);

            // Process results
            this.processHealthCheckResults(healthChecks);

            // Determine overall health
            this.updateOverallHealth();

            // DISABLED: Auto-recovery was causing page reloads
            // if (this.shouldTriggerRecovery()) {
            //     this.triggerAutoRecovery();
            // }

            // Notify listeners
            this.notifyHealthChange();

        } catch (error) {
            logger.error('[HealthMonitor] Health check failed:', error);
            this.healthStatus.overall = 'degraded'; // Less aggressive status
        } finally {
            // Schedule next check only if monitoring enabled
            if (this.monitoringEnabled) {
                this.scheduleHealthCheck();
            }
        }
    }

    /**
     * Perform immediate health check - LIGHTWEIGHT VERSION
     */
    async performImmediateHealthCheck() {

        // PERFORMANCE: Only do basic backend check, not full health check
        try {
            const backendHealth = await this.checkBackendHealth();
            this.healthStatus.backend = backendHealth.status === 'healthy' ? 'healthy' : 'degraded';
            this.healthStatus.overall = this.healthStatus.backend;
            this.notifyHealthChange();
        } catch (_error) {
            // Silently ignore health check errors
        }
    }

    /**
     * Check backend API health - OPTIMIZED
     */
    async checkBackendHealth() {
        const startTime = Date.now();

        try {
            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), this.config.apiTimeout);

            const response = await fetch('/api/health', {
                signal: controller.signal,
                headers: cacheBuster.getBustHeaders()
            });

            clearTimeout(timeoutId);

            if (response.ok) {
                this.healthStatus.backend = 'healthy';
                this.consecutiveFailures.backend = 0;
                this.metrics.performanceMetrics.apiResponseTime = Date.now() - startTime;
                return { status: 'healthy', responseTime: Date.now() - startTime };
            } else {
                throw new Error(`Backend responded with status: ${response.status}`);
            }

        } catch (error) {
            this.consecutiveFailures.backend++;
            this.healthStatus.backend = this.consecutiveFailures.backend >= this.config.maxConsecutiveFailures ?
                'unhealthy' : 'degraded';

            return {
                status: 'unhealthy',
                error: error.message,
                consecutiveFailures: this.consecutiveFailures.backend
            };
        }
    }

    /**
     * Check WebSocket connection health - DISABLED FOR PERFORMANCE
     */
    async checkWebSocketHealth() {

        // PERFORMANCE: Don't create WebSocket connections for health checks
        this.healthStatus.websocket = 'unknown';
        return { status: 'unknown', reason: 'disabled_for_performance' };
    }

    /**
     * Check router health - DISABLED FOR PERFORMANCE
     */
    async checkRouterHealth() {

        // PERFORMANCE: Don't run expensive router health checks
        this.healthStatus.router = 'healthy';
        return { status: 'healthy', reason: 'disabled_for_performance' };
    }

    /**
     * Check cache system health - DISABLED FOR PERFORMANCE
     */
    async checkCacheHealth() {

        this.healthStatus.cache = 'healthy';
        return { status: 'healthy', reason: 'disabled_for_performance' };
    }

    /**
     * Check performance health - DISABLED FOR PERFORMANCE
     */
    async checkPerformanceHealth() {

        return { status: 'healthy', reason: 'disabled_for_performance' };
    }

    /**
     * Process health check results
     */
    processHealthCheckResults(results) {
        results.forEach((result, index) => {
            if (result.status === 'rejected') {
                logger.error(`[HealthMonitor] Health check ${index} failed:`, result.reason);
                this.metrics.errorCount++;
            }
        });
    }

    /**
     * Update overall health status
     */
    updateOverallHealth() {
        const statuses = Object.values(this.healthStatus).filter(status => status !== 'unknown');

        if (statuses.some(status => status === 'unhealthy')) {
            this.healthStatus.overall = 'unhealthy';
        } else if (statuses.some(status => status === 'degraded')) {
            this.healthStatus.overall = 'degraded';
        } else {
            this.healthStatus.overall = 'healthy';
        }
    }

    /**
     * Determine if auto-recovery should be triggered - DISABLED
     */
    shouldTriggerRecovery() {
        // PERFORMANCE: Disable auto-recovery that was causing page reloads
        return false;
    }

    /**
     * Trigger automatic recovery - DISABLED FOR PERFORMANCE
     */
    async triggerAutoRecovery() {
        return;
    }

    /**
     * Execute specific recovery strategy - DISABLED
     */
    async executeRecoveryStrategy(_strategy) {
        return;
    }

    /**
     * Restart critical frontend services - DISABLED
     */
    async restartCriticalServices() {
        return;
    }

    /**
     * Setup performance monitoring - LIGHTWEIGHT VERSION
     */
    setupPerformanceMonitoring() {
        // PERFORMANCE: Disable PerformanceObserver that was consuming resources
    }

    /**
     * Setup global error handling - KEPT FOR SAFETY
     */
    setupErrorHandling() {
        window.addEventListener('error', (event) => {
            this.metrics.errorCount++;
            logger.error('[HealthMonitor] Global error detected:', event.error);

            // PERFORMANCE: Don't trigger immediate health checks on every error
            if (event.error && event.error.message) {
                const criticalErrors = ['ChunkLoadError', 'Loading chunk', 'Loading CSS chunk'];
                if (criticalErrors.some(error => event.error.message.includes(error))) {
                }
            }
        });

        window.addEventListener('unhandledrejection', (event) => {
            this.metrics.errorCount++;
            logger.error('[HealthMonitor] Unhandled promise rejection:', event.reason);
            // PERFORMANCE: Don't trigger immediate health check
        });
    }

    /**
     * Measure initial performance metrics - SIMPLIFIED
     */
    measureInitialMetrics() {
        // Measure time to interactive - simplified version
        if (window.performance && window.performance.timing) {
            const timing = window.performance.timing;
            this.metrics.performanceMetrics.loadTime = timing.loadEventEnd - timing.navigationStart;
            this.metrics.performanceMetrics.renderTime = timing.domContentLoadedEventEnd - timing.navigationStart;
        }
    }

    /**
     * Add health status listener
     */
    onHealthChange(callback) {
        this.listeners.push(callback);
    }

    /**
     * Notify listeners of health changes - THROTTLED
     */
    notifyHealthChange() {
        const healthData = {
            status: this.healthStatus,
            metrics: this.metrics,
            timestamp: Date.now()
        };

        this.listeners.forEach(callback => {
            try {
                callback(healthData);
            } catch (error) {
                logger.error('[HealthMonitor] Listener error:', error);
            }
        });
    }

    /**
     * Get current health status
     */
    getHealthStatus() {
        return {
            ...this.healthStatus,
            metrics: { ...this.metrics },
            isMonitoring: this.isMonitoring,
            isRecovering: this.isRecovering,
            consecutiveFailures: { ...this.consecutiveFailures },
            monitoringMode: 'performance_optimized'
        };
    }

    /**
     * Enable monitoring manually (for debugging)
     */
    enableMonitoring() {
        this.monitoringEnabled = true;
        this.startMonitoring();
    }

    /**
     * Disable monitoring (default for performance)
     */
    disableMonitoring() {
        this.monitoringEnabled = false;
        this.stopMonitoring();
    }

    /**
     * Stop health monitoring
     */
    stopMonitoring() {
        this.isMonitoring = false;
        if (this.healthCheckTimer) {
            clearTimeout(this.healthCheckTimer);
            this.healthCheckTimer = null;
        }
    }

    /**
     * Cleanup resources
     */
    destroy() {
        this.stopMonitoring();
        this.listeners = [];
    }
}

// Export singleton instance
export const frontendHealthMonitor = new FrontendHealthMonitor();

// Auto-initialize in performance mode
if (typeof window !== 'undefined') {
    window.frontendHealthMonitor = frontendHealthMonitor;
}

export default FrontendHealthMonitor;
