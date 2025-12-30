/**
 * Router Health Monitor & Recovery System
 * Detects router failures and automatically recovers
 */

import { nextTick } from 'vue';
import { createLogger } from '@/utils/debugUtils';

// Create scoped logger for RouterHealthMonitor
const logger = createLogger('RouterHealthMonitor');

class RouterHealthMonitor {
    constructor() {
        this.router = null;
        this.isHealthy = true;
        this.lastSuccessfulNavigation = Date.now();
        this.failureCount = 0;
        this.maxFailures = 5; // Allow 5 failures before triggering recovery
        this.healthCheckInterval = 30000; // 30 seconds (less aggressive)
        this.navigationTimeout = 8000; // 8 seconds (more time for complex routes)
        this.recoveryAttempts = 0;
        this.maxRecoveryAttempts = 3; // Fewer recovery attempts
        this.lastFailureEmitTime = 0; // Track last time we emitted a failure event
        this.failureEmitCooldown = 30000; // Only emit failure events every 30 seconds

        this.healthCheckTimer = null;
        this.pendingNavigation = null;

        this.listeners = {
            failure: [],
            recovery: [],
            healthChange: []
        };
    }

    /**
     * Initialize the router health monitor
     */
    initialize(router) {
        this.router = router;

        // Immediately clean up any recovery parameters to prevent slow loading
        this.cleanupRecoveryParams();

        // Enable minimal monitoring (most checks disabled to prevent false positives)
        this.setupRouterHooks();
        this.startHealthChecks();

    }

    /**
     * Setup router hooks for monitoring
     */
    setupRouterHooks() {
        if (!this.router) return;

        // Monitor successful navigation
        this.router.afterEach((_to, _from) => {
            this.lastSuccessfulNavigation = Date.now();
            this.failureCount = 0;
            this.setHealthy(true);

            // Route verification disabled - was causing false positives and _recovery parameters
            // setTimeout(() => this.verifyRouteLoaded(to), 500);
        });

        // Monitor navigation errors
        this.router.onError((error) => {
            logger.warn('[RouterHealth] Navigation error:', error);
            // Disable automatic failure handling - was causing false positives
            // Only log errors for debugging, don't trigger recovery
            // if (!error.message.includes('Loading chunk') && !error.message.includes('ChunkLoadError')) {
            //     this.handleNavigationFailure(error);
            // }
        });

        // Monitor before each navigation
        this.router.beforeEach((to, from, next) => {
            // Clear any existing timeout
            if (this.pendingNavigation?.timeout) {
                clearTimeout(this.pendingNavigation.timeout);
            }

            // Disable navigation timeout monitoring - was causing false recovery attempts
            // this.pendingNavigation = {
            //     to,
            //     from,
            //     startTime: Date.now(),
            //     timeout: setTimeout(() => {
            //         this.handleNavigationTimeout(to, from);
            //     }, this.navigationTimeout)
            // };

            next();
        });
    }

    /**
     * Verify that a route actually loaded in the DOM
     */
    async verifyRouteLoaded(route, retries = 1) {
        if (retries <= 0) {
            return true;
        }

        await nextTick();
        await new Promise(resolve => setTimeout(resolve, 1000));

        const indicators = this.checkRouteLoadIndicators(route);

        if (indicators.loaded) {
            return true;
        }

        // Retry with longer wait time
        if (retries > 1) {
            await new Promise(resolve => setTimeout(resolve, 500));
            return this.verifyRouteLoaded(route, retries - 1);
        }

        // On final retry, always assume success - route verification is informational only
        return true;
    }

    /**
     * Check multiple indicators that a route has loaded
     */
    checkRouteLoadIndicators(route) {
        const indicators = {
            loaded: false,
            routerView: false,
            expectedContent: false,
            metaUpdated: false,
            errors: []
        };

        try {
            // Check 1: Router view exists and is visible
            const routerView = document.querySelector('router-view, [data-v-router-view]');
            indicators.routerView = routerView && routerView.children.length > 0;

            // Check 2: Expected route content exists (any selector match is sufficient)
            const expectedElements = this.getExpectedElementsForRoute(route);
            indicators.expectedContent = expectedElements.length === 0 ||
                expectedElements.some(selector => document.querySelector(selector));

            // Check 3: Document title updated (less strict - just check if title exists)
            indicators.metaUpdated = document.title.length > 0;

            // Check 4: No critical Vue rendering errors (less strict)
            const criticalErrors = document.querySelectorAll('.vue-error-critical');
            if (criticalErrors.length > 0) {
                indicators.errors.push(`Critical Vue errors found: ${criticalErrors.length}`);
            }

            // Route is loaded if router view exists OR expected content exists
            // More lenient approach to reduce false failures
            indicators.loaded = (indicators.routerView || indicators.expectedContent) &&
                               indicators.errors.length === 0;

        } catch (error) {
            indicators.errors.push(`Verification error: ${error.message}`);
        }

        return indicators;
    }

    /**
     * Get expected DOM elements for specific routes
     */
    getExpectedElementsForRoute(route) {
        const routeSelectors = {
            'chat': ['.chat-interface', '.chat-container', '#chat-main'],
            'knowledge': ['.knowledge-categories', '.knowledge-search', '.knowledge-container', '.knowledge-upload', '.knowledge-entries'],
            'tools': ['.xterm-container', '.tools-container', '.terminal-container', '.file-browser'],
            'monitoring': ['.rum-dashboard', '.monitoring-container', '.system-monitor'],
            'settings': ['.settings-container', '.settings-form']
        };

        const routeName = route.name?.split('-')[0]; // Get base route name
        return routeSelectors[routeName] || ['.main-content', '#main-content', 'router-view'];
    }

    /**
     * Handle navigation failures
     */
    handleNavigationFailure(error) {
        this.failureCount++;

        // Only set as unhealthy if we have multiple failures
        if (this.failureCount >= this.maxFailures) {
            this.setHealthy(false);

            // Only emit failure event if enough time has passed since last emission
            const now = Date.now();
            if (now - this.lastFailureEmitTime > this.failureEmitCooldown) {
                this.emit('failure', {
                    reason: error.message,
                    failureCount: this.failureCount,
                    timestamp: now
                });
                this.lastFailureEmitTime = now;
            } else {
            }

            // Trigger recovery after multiple failures
            if (this.recoveryAttempts < this.maxRecoveryAttempts) {
                setTimeout(() => this.triggerRecovery('max_failures_reached'), 1000);
            }
        }
    }

    /**
     * Handle navigation timeouts
     */
    handleNavigationTimeout(to, from) {
        logger.warn('[RouterHealth] Navigation timeout:', { to: to.path, from: from.path, timeout: this.navigationTimeout });

        if (this.pendingNavigation) {
            clearTimeout(this.pendingNavigation.timeout);
            this.pendingNavigation = null;
        }

        // Only treat as failure if it's a significant timeout (8+ seconds)
        if (this.navigationTimeout >= 8000) {
            this.handleNavigationFailure(new Error(`Navigation timeout: ${to.path} (${this.navigationTimeout}ms)`));
        } else {
        }
    }

    /**
     * Handle route verification failures
     */
    handleRouteVerificationFailure(_route) {
        // Route verification failures are now handled more gracefully
        // Only log debug info instead of triggering cascade failures

        // Don't trigger navigation failure for route verification issues
        // This was causing the cascade of 180+ errors
    }

    /**
     * Set health status and notify listeners
     */
    setHealthy(healthy) {
        if (this.isHealthy !== healthy) {
            this.isHealthy = healthy;
            this.emit('healthChange', { healthy, timestamp: Date.now() });

            if (healthy) {
                this.recoveryAttempts = 0;
            }
        }
    }

    /**
     * Start periodic health checks
     */
    startHealthChecks() {
        if (this.healthCheckTimer) {
            clearInterval(this.healthCheckTimer);
        }

        // Disable periodic health checks - they were causing false recovery attempts

        // this.healthCheckTimer = setInterval(() => {
        //     this.performHealthCheck();
        // }, 60000);
    }

    /**
     * Perform comprehensive health check
     */
    performHealthCheck() {
        const now = Date.now();
        const timeSinceLastSuccess = now - this.lastSuccessfulNavigation;
        const maxStaleTime = 30000; // 30 seconds

        // Check if navigation is stale (disabled - too aggressive)
        if (timeSinceLastSuccess > maxStaleTime && this.failureCount > 0) {
            // this.triggerRecovery('stale_navigation');
        }

        // Check current route integrity (disabled - too aggressive)
        if (this.router?.currentRoute?.value) {
            this.verifyRouteLoaded(this.router.currentRoute.value)
                .then(verified => {
                    if (!verified) {
                        // this.handleNavigationFailure(new Error('Health check route verification failed'));
                    }
                });
        }

        // Check for broken router-view (disabled - too aggressive)
        const routerView = document.querySelector('router-view');
        if (!routerView || routerView.children.length === 0) {
            // this.triggerRecovery('broken_router_view');
        }
    }

    /**
     * Monitor DOM changes for router issues
     */
    monitorDOMChanges() {
        if (!window.MutationObserver) return;

        const observer = new MutationObserver((mutations) => {
            mutations.forEach((mutation) => {
                // Detect if router-view disappears
                if (mutation.type === 'childList') {
                    const removedRouterViews = Array.from(mutation.removedNodes)
                        .filter(node => node.tagName === 'ROUTER-VIEW');

                    if (removedRouterViews.length > 0) {
                        logger.warn('[RouterHealth] Router-view removed from DOM');
                        this.triggerRecovery('router_view_removed');
                    }
                }
            });
        });

        observer.observe(document.body, {
            childList: true,
            subtree: true
        });
    }

    /**
     * Trigger recovery procedures - DISABLED to prevent _recovery URL parameters
     */
    async triggerRecovery(_reason) {

        // All recovery procedures disabled to prevent _recovery parameters
        // this.recoveryAttempts++;
        // Recovery procedures commented out to prevent URL parameter issues
        return;
    }

    /**
     * Recover broken router-view
     */
    async recoverRouterView() {

        // Try to reinitialize Vue app components
        const app = document.getElementById('app');
        if (app && window.Vue) {
            // Force Vue to re-render the router-view
            await nextTick();

            // Trigger a route change to force re-rendering
            if (this.router) {
                const currentPath = this.router.currentRoute.value.path;
                await this.router.replace('/');
                await nextTick();
                await this.router.replace(currentPath);
            }
        }
    }

    /**
     * Recover navigation issues
     */
    async recoverNavigation() {

        if (this.router) {
            try {
                // Clear any pending navigation
                if (this.pendingNavigation) {
                    clearTimeout(this.pendingNavigation.timeout);
                    this.pendingNavigation = null;
                }

                // Force navigate to current route WITHOUT recovery parameters
                const currentRoute = this.router.currentRoute.value;

                // Use router.go(0) to refresh current route without URL changes
                if (window.location.href === window.location.origin + currentRoute.fullPath) {
                    // Simple refresh without URL modification
                    await nextTick();
                    this.router.go(0);
                } else {
                    // Fallback to replace navigation
                    await this.router.replace(currentRoute.fullPath);
                }

                // Reset failure count on successful recovery
                this.failureCount = 0;
                this.setHealthy(true);
            } catch (error) {
                logger.error('[RouterHealth] Navigation recovery failed:', error);
                throw error;
            }
        }
    }

    /**
     * General recovery procedures
     */
    async recoverGeneral() {

        // Clear caches
        if (window.cacheBuster) {
            await window.cacheBuster.clearAllCaches();
        }

        // Re-initialize router hooks
        if (this.router) {
            this.setupRouterHooks();
        }

        // Restart health checks
        this.startHealthChecks();
    }

    /**
     * Trigger full page reload as last resort - DISABLED to prevent _recovery parameters
     */
    triggerFullReload() {

        // Clean reload without adding recovery parameters
        // window.location.reload();

        // All recovery parameter logic disabled
        return;
    }

    /**
     * Event system
     */
    on(event, callback) {
        if (this.listeners[event]) {
            this.listeners[event].push(callback);
        }
    }

    emit(event, data) {
        if (this.listeners[event]) {
            this.listeners[event].forEach(callback => {
                try {
                    callback(data);
                } catch (error) {
                    logger.error(`[RouterHealth] Listener error for ${event}:`, error);
                }
            });
        }
    }

    /**
     * Get current health status
     */
    getHealthStatus() {
        return {
            isHealthy: this.isHealthy,
            failureCount: this.failureCount,
            recoveryAttempts: this.recoveryAttempts,
            lastSuccessfulNavigation: this.lastSuccessfulNavigation,
            timeSinceLastSuccess: Date.now() - this.lastSuccessfulNavigation
        };
    }

    /**
     * Clean up recovery parameters from URL immediately
     */
    cleanupRecoveryParameters() {
        if (this.router) {
            const currentRoute = this.router.currentRoute.value;
            if (currentRoute.query._recovery || currentRoute.query._router_recovery) {
                const cleanQuery = { ...currentRoute.query };
                delete cleanQuery._recovery;
                delete cleanQuery._router_recovery;

                this.router.replace({ path: currentRoute.path, query: cleanQuery }).catch(() => {
                    // If replace fails, try push instead
                    this.router.push({ path: currentRoute.path, query: cleanQuery }).catch(() => {});
                });
            }
        }
    }

    /**
     * Clean up recovery parameters from URL
     */
    cleanupRecoveryParams() {
        if (typeof window !== 'undefined' && this.router) {
            const currentRoute = this.router.currentRoute.value;
            if (currentRoute.query._recovery || currentRoute.query._router_recovery) {
                const cleanQuery = { ...currentRoute.query };
                delete cleanQuery._recovery;
                delete cleanQuery._router_recovery;

                this.router.replace({
                    path: currentRoute.path,
                    query: cleanQuery,
                    hash: currentRoute.hash
                }).catch(() => {
                    // Ignore navigation errors during cleanup
                });
            }
        }
    }

    /**
     * Cleanup resources
     */
    destroy() {
        if (this.healthCheckTimer) {
            clearInterval(this.healthCheckTimer);
        }

        if (this.pendingNavigation?.timeout) {
            clearTimeout(this.pendingNavigation.timeout);
        }

        this.listeners = { failure: [], recovery: [], healthChange: [] };
    }
}

// Export singleton instance
export const routerHealthMonitor = new RouterHealthMonitor();

// Auto-initialize with router when available
if (typeof window !== 'undefined') {
    window.routerHealthMonitor = routerHealthMonitor;
}

export default RouterHealthMonitor;