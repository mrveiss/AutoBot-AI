/**
 * Real-Time Frontend Health Monitor & Auto-Recovery System
 * Continuously monitors all aspects of frontend health and automatically recovers from failures
 */

import { cacheBuster } from './CacheBuster.js';
import { routerHealthMonitor } from './RouterHealthMonitor.js';

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
            healthCheckInterval: 30000, // 30 seconds
            fastHealthCheckInterval: 5000, // 5 seconds when issues detected
            apiTimeout: 10000,
            websocketTimeout: 5000,
            maxConsecutiveFailures: 3,
            recoveryDelay: 2000
        };

        this.consecutiveFailures = {
            backend: 0,
            websocket: 0,
            router: 0
        };

        this.healthCheckTimer = null;
        this.isRecovering = false;
        this.listeners = [];

        // Auto-recovery strategies
        this.recoveryStrategies = [
            'cache_clear',
            'router_reset',
            'service_restart',
            'full_reload'
        ];
        this.currentRecoveryLevel = 0;
    }

    /**
     * Initialize health monitoring system
     */
    initialize() {
        this.startMonitoring();
        this.setupPerformanceMonitoring();
        this.setupErrorHandling();
        this.measureInitialMetrics();

        console.log('[HealthMonitor] Real-time health monitoring initialized');
    }

    /**
     * Start continuous health monitoring
     */
    startMonitoring() {
        if (this.isMonitoring) return;

        this.isMonitoring = true;
        this.scheduleHealthCheck();

        // Monitor page visibility to adjust check frequency
        document.addEventListener('visibilitychange', () => {
            if (document.visibilityState === 'visible') {
                this.performImmediateHealthCheck();
            }
        });

        console.log('[HealthMonitor] Continuous monitoring started');
    }

    /**
     * Schedule next health check
     */
    scheduleHealthCheck() {
        if (this.healthCheckTimer) {
            clearTimeout(this.healthCheckTimer);
        }

        // Use faster interval if issues are detected
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
     * Perform comprehensive health check
     */
    async performHealthCheck() {
        try {
            this.metrics.lastHealthCheck = Date.now();

            // Run all health checks in parallel
            const healthChecks = await Promise.allSettled([
                this.checkBackendHealth(),
                this.checkWebSocketHealth(),
                this.checkRouterHealth(),
                this.checkCacheHealth(),
                this.checkPerformanceHealth()
            ]);

            // Process results
            this.processHealthCheckResults(healthChecks);

            // Determine overall health
            this.updateOverallHealth();

            // Trigger recovery if needed
            if (this.shouldTriggerRecovery()) {
                this.triggerAutoRecovery();
            }

            // Notify listeners
            this.notifyHealthChange();

        } catch (error) {
            console.error('[HealthMonitor] Health check failed:', error);
            this.healthStatus.overall = 'unhealthy';
        } finally {
            // Schedule next check
            this.scheduleHealthCheck();
        }
    }

    /**
     * Perform immediate health check (triggered by events)
     */
    async performImmediateHealthCheck() {
        console.log('[HealthMonitor] Performing immediate health check');
        await this.performHealthCheck();
    }

    /**
     * Check backend API health
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
     * Check WebSocket connection health
     */
    async checkWebSocketHealth() {
        return new Promise((resolve) => {
            try {
                const wsUrl = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
                const ws = new WebSocket(`${wsUrl}//${window.location.host}/ws`);

                const timeout = setTimeout(() => {
                    ws.close();
                    this.consecutiveFailures.websocket++;
                    this.healthStatus.websocket = 'unhealthy';
                    resolve({ status: 'unhealthy', error: 'WebSocket connection timeout' });
                }, this.config.websocketTimeout);

                ws.onopen = () => {
                    clearTimeout(timeout);
                    ws.close();
                    this.consecutiveFailures.websocket = 0;
                    this.healthStatus.websocket = 'healthy';
                    resolve({ status: 'healthy' });
                };

                ws.onerror = (error) => {
                    clearTimeout(timeout);
                    ws.close();
                    this.consecutiveFailures.websocket++;
                    this.healthStatus.websocket = 'unhealthy';
                    resolve({ status: 'unhealthy', error: 'WebSocket connection failed' });
                };

            } catch (error) {
                this.consecutiveFailures.websocket++;
                this.healthStatus.websocket = 'unhealthy';
                resolve({ status: 'unhealthy', error: error.message });
            }
        });
    }

    /**
     * Check router health
     */
    async checkRouterHealth() {
        try {
            if (routerHealthMonitor) {
                const routerStatus = routerHealthMonitor.getHealthStatus();

                if (routerStatus.isHealthy) {
                    this.healthStatus.router = 'healthy';
                    this.consecutiveFailures.router = 0;
                } else {
                    this.consecutiveFailures.router++;
                    this.healthStatus.router = this.consecutiveFailures.router >= this.config.maxConsecutiveFailures ?
                        'unhealthy' : 'degraded';
                }

                return {
                    status: this.healthStatus.router,
                    routerStatus
                };
            } else {
                this.healthStatus.router = 'unknown';
                return { status: 'unknown', error: 'Router health monitor not available' };
            }
        } catch (error) {
            this.healthStatus.router = 'unhealthy';
            return { status: 'unhealthy', error: error.message };
        }
    }

    /**
     * Check cache system health
     */
    async checkCacheHealth() {
        try {
            if (cacheBuster) {
                const cacheHealthy = !cacheBuster.detectCachePoisoning();
                this.healthStatus.cache = cacheHealthy ? 'healthy' : 'degraded';
                return { status: this.healthStatus.cache };
            } else {
                this.healthStatus.cache = 'unknown';
                return { status: 'unknown', error: 'Cache buster not available' };
            }
        } catch (error) {
            this.healthStatus.cache = 'unhealthy';
            return { status: 'unhealthy', error: error.message };
        }
    }

    /**
     * Check performance health
     */
    async checkPerformanceHealth() {
        try {
            const performanceEntries = performance.getEntriesByType('navigation');
            if (performanceEntries.length > 0) {
                const entry = performanceEntries[0];
                this.metrics.performanceMetrics.loadTime = entry.loadEventEnd - entry.loadEventStart;
                this.metrics.performanceMetrics.renderTime = entry.domContentLoadedEventEnd - entry.domContentLoadedEventStart;
            }

            // Check memory usage if available
            if (performance.memory) {
                const memoryUsage = performance.memory.usedJSHeapSize / performance.memory.totalJSHeapSize;
                if (memoryUsage > 0.9) {
                    return { status: 'degraded', memoryUsage };
                }
            }

            return { status: 'healthy' };
        } catch (error) {
            return { status: 'unknown', error: error.message };
        }
    }

    /**
     * Process health check results
     */
    processHealthCheckResults(results) {
        results.forEach((result, index) => {
            if (result.status === 'rejected') {
                console.error(`[HealthMonitor] Health check ${index} failed:`, result.reason);
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
     * Determine if auto-recovery should be triggered
     */
    shouldTriggerRecovery() {
        return this.healthStatus.overall === 'unhealthy' &&
               !this.isRecovering &&
               (Date.now() - this.metrics.lastRecovery) > this.config.recoveryDelay;
    }

    /**
     * Trigger automatic recovery
     */
    async triggerAutoRecovery() {
        if (this.isRecovering) return;

        this.isRecovering = true;
        this.metrics.lastRecovery = Date.now();
        this.metrics.recoveryCount++;

        console.log(`[HealthMonitor] Triggering auto-recovery level ${this.currentRecoveryLevel}`);

        try {
            const strategy = this.recoveryStrategies[this.currentRecoveryLevel];
            await this.executeRecoveryStrategy(strategy);

            // Check if recovery was successful
            await new Promise(resolve => setTimeout(resolve, 2000));
            await this.performImmediateHealthCheck();

            if (this.healthStatus.overall === 'healthy') {
                console.log('[HealthMonitor] Auto-recovery successful');
                this.currentRecoveryLevel = 0; // Reset recovery level
            } else {
                // Escalate to next recovery level
                this.currentRecoveryLevel = Math.min(
                    this.currentRecoveryLevel + 1,
                    this.recoveryStrategies.length - 1
                );
            }

        } catch (error) {
            console.error('[HealthMonitor] Auto-recovery failed:', error);
        } finally {
            this.isRecovering = false;
        }
    }

    /**
     * Execute specific recovery strategy
     */
    async executeRecoveryStrategy(strategy) {
        console.log(`[HealthMonitor] Executing recovery strategy: ${strategy}`);

        switch (strategy) {
            case 'cache_clear':
                if (cacheBuster) {
                    await cacheBuster.clearAllCaches();
                    cacheBuster.forceCriticalResourceReload();
                }
                break;

            case 'router_reset':
                if (routerHealthMonitor) {
                    await routerHealthMonitor.triggerRecovery('health_monitor_recovery');
                }
                break;

            case 'service_restart':
                // Attempt to restart critical services
                await this.restartCriticalServices();
                break;

            case 'full_reload':
                console.log('[HealthMonitor] Triggering full page reload as last resort');
                window.location.reload(true);
                break;

            default:
                console.warn(`[HealthMonitor] Unknown recovery strategy: ${strategy}`);
        }
    }

    /**
     * Restart critical frontend services
     */
    async restartCriticalServices() {
        try {
            // Reinitialize health monitoring systems
            if (cacheBuster && typeof cacheBuster.initialize === 'function') {
                cacheBuster.initialize();
            }

            if (routerHealthMonitor && typeof routerHealthMonitor.initialize === 'function') {
                routerHealthMonitor.initialize();
            }

            // Clear all timers and restart
            this.stopMonitoring();
            await new Promise(resolve => setTimeout(resolve, 1000));
            this.startMonitoring();

        } catch (error) {
            console.error('[HealthMonitor] Service restart failed:', error);
            throw error;
        }
    }

    /**
     * Setup performance monitoring
     */
    setupPerformanceMonitoring() {
        if (window.performance && window.performance.observer) {
            const observer = new PerformanceObserver((list) => {
                list.getEntries().forEach((entry) => {
                    if (entry.entryType === 'navigation') {
                        this.metrics.performanceMetrics.loadTime = entry.loadEventEnd - entry.loadEventStart;
                    }
                });
            });

            observer.observe({ entryTypes: ['navigation', 'resource'] });
        }
    }

    /**
     * Setup global error handling
     */
    setupErrorHandling() {
        window.addEventListener('error', (event) => {
            this.metrics.errorCount++;
            console.error('[HealthMonitor] Global error detected:', event.error);

            // Trigger immediate health check on critical errors
            if (event.error && event.error.message) {
                const criticalErrors = ['ChunkLoadError', 'Loading chunk', 'Loading CSS chunk'];
                if (criticalErrors.some(error => event.error.message.includes(error))) {
                    this.performImmediateHealthCheck();
                }
            }
        });

        window.addEventListener('unhandledrejection', (event) => {
            this.metrics.errorCount++;
            console.error('[HealthMonitor] Unhandled promise rejection:', event.reason);
            this.performImmediateHealthCheck();
        });
    }

    /**
     * Measure initial performance metrics
     */
    measureInitialMetrics() {
        // Measure time to interactive
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
     * Notify listeners of health changes
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
                console.error('[HealthMonitor] Listener error:', error);
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
            consecutiveFailures: { ...this.consecutiveFailures }
        };
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

// Auto-initialize
if (typeof window !== 'undefined') {
    window.frontendHealthMonitor = frontendHealthMonitor;
}

export default FrontendHealthMonitor;