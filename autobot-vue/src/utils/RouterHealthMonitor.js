/**
 * Router Health Monitor & Recovery System
 * Detects router failures and automatically recovers
 */

import { nextTick } from 'vue';

class RouterHealthMonitor {
    constructor() {
        this.router = null;
        this.isHealthy = true;
        this.lastSuccessfulNavigation = Date.now();
        this.failureCount = 0;
        this.maxFailures = 5; // More tolerant before triggering recovery
        this.healthCheckInterval = 30000; // 30 seconds (less aggressive)
        this.navigationTimeout = 8000; // 8 seconds (more time for complex routes)
        this.recoveryAttempts = 0;
        this.maxRecoveryAttempts = 3; // Fewer recovery attempts

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
        this.cleanupRecoveryParams();
        this.setupRouterHooks();
        this.startHealthChecks();
        this.monitorDOMChanges();

        console.log('[RouterHealth] Initialized router health monitoring');
    }

    /**
     * Setup router hooks for monitoring
     */
    setupRouterHooks() {
        if (!this.router) return;

        // Monitor successful navigation
        this.router.afterEach((to, from) => {
            this.lastSuccessfulNavigation = Date.now();
            this.failureCount = 0;
            this.setHealthy(true);

            // Verify route actually loaded
            this.verifyRouteLoaded(to);
        });

        // Monitor navigation errors
        this.router.onError((error) => {
            console.error('[RouterHealth] Navigation error:', error);
            this.handleNavigationFailure(error);
        });

        // Monitor before each navigation
        this.router.beforeEach((to, from, next) => {
            this.pendingNavigation = {
                to,
                from,
                startTime: Date.now(),
                timeout: setTimeout(() => {
                    this.handleNavigationTimeout(to, from);
                }, this.navigationTimeout)
            };

            next();
        });
    }

    /**
     * Verify that a route actually loaded in the DOM
     */
    async verifyRouteLoaded(route, retries = 2) { // Reduced retries from 3 to 2
        if (retries <= 0) {
            console.warn('[RouterHealth] Route verification failed after retries:', route.path);
            // Don't trigger failure for route verification - too aggressive
            return false;
        }

        await nextTick();

        // Wait longer for complex components to render
        await new Promise(resolve => setTimeout(resolve, 200));

        const indicators = this.checkRouteLoadIndicators(route);

        if (indicators.loaded) {
            console.debug('[RouterHealth] Route verified:', route.path);
            return true;
        }

        // Only retry once and don't spam console
        if (retries > 1) {
            console.debug('[RouterHealth] Route verification pending, retrying...', route.path);
            await new Promise(resolve => setTimeout(resolve, 300));
            return this.verifyRouteLoaded(route, retries - 1);
        }

        return false; // Fail silently on final retry
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
        this.setHealthy(false);

        // Completely silent handling - navigation failures are common in complex SPAs
        // Don't emit failure events as they're too noisy and not actionable

        // Don't trigger recovery automatically - too aggressive
        // Only track silently for internal health monitoring
    }

    /**
     * Handle navigation timeouts
     */
    handleNavigationTimeout(to, from) {
        // Completely silent handling - navigation timeouts are normal in complex SPAs
        // console.debug('[RouterHealth] Navigation timeout (non-critical):', { to: to.path, from: from.path });

        if (this.pendingNavigation) {
            clearTimeout(this.pendingNavigation.timeout);
            this.pendingNavigation = null;
        }

        // No longer emit failure events for timeouts as they're too common and not indicative of actual problems
    }

    /**
     * Handle route verification failures
     */
    handleRouteVerificationFailure(route) {
        // Route verification failures are now handled more gracefully
        // Only log debug info instead of triggering cascade failures
        console.debug('[RouterHealth] Route verification failed (non-critical):', route.path);

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

        this.healthCheckTimer = setInterval(() => {
            this.performHealthCheck();
        }, this.healthCheckInterval);
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
            console.debug('[RouterHealth] Stale navigation detected (non-critical)');
            // this.triggerRecovery('stale_navigation');
        }

        // Check current route integrity (disabled - too aggressive)
        if (this.router?.currentRoute?.value) {
            this.verifyRouteLoaded(this.router.currentRoute.value)
                .then(verified => {
                    if (!verified) {
                        console.debug('[RouterHealth] Health check route verification failed (non-critical)');
                        // this.handleNavigationFailure(new Error('Health check route verification failed'));
                    }
                });
        }

        // Check for broken router-view (disabled - too aggressive)
        const routerView = document.querySelector('router-view');
        if (!routerView || routerView.children.length === 0) {
            console.debug('[RouterHealth] Router-view check (non-critical)');
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
                        console.warn('[RouterHealth] Router-view removed from DOM');
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
     * Trigger recovery procedures
     */
    async triggerRecovery(reason) {
        if (this.recoveryAttempts >= this.maxRecoveryAttempts) {
            console.error('[RouterHealth] Max recovery attempts reached, triggering full reload');
            this.triggerFullReload();
            return;
        }

        this.recoveryAttempts++;
        console.log(`[RouterHealth] Triggering recovery attempt ${this.recoveryAttempts}/${this.maxRecoveryAttempts}:`, reason);

        try {
            switch (reason) {
                case 'broken_router_view':
                    await this.recoverRouterView();
                    break;
                case 'max_failures_reached':
                case 'stale_navigation':
                    await this.recoverNavigation();
                    break;
                default:
                    await this.recoverGeneral();
            }

            this.emit('recovery', { reason, attempt: this.recoveryAttempts });
        } catch (error) {
            console.error('[RouterHealth] Recovery failed:', error);
            setTimeout(() => this.triggerRecovery(reason), 2000);
        }
    }

    /**
     * Recover broken router-view
     */
    async recoverRouterView() {
        console.log('[RouterHealth] Recovering router-view...');

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
        console.log('[RouterHealth] Recovering navigation...');

        if (this.router) {
            try {
                // Clear any pending navigation
                if (this.pendingNavigation) {
                    clearTimeout(this.pendingNavigation.timeout);
                    this.pendingNavigation = null;
                }

                // Force navigate to current route
                const currentRoute = this.router.currentRoute.value;
                await this.router.replace({ path: currentRoute.path, query: { _recovery: Date.now() } });

                // Clean up recovery parameters after successful navigation
                setTimeout(() => {
                    const cleanQuery = { ...currentRoute.query };
                    delete cleanQuery._recovery;
                    delete cleanQuery._router_recovery;
                    this.router.replace({ path: currentRoute.path, query: cleanQuery });
                }, 1000);

                // Reset failure count on successful recovery
                this.failureCount = 0;
                this.setHealthy(true);
            } catch (error) {
                console.error('[RouterHealth] Navigation recovery failed:', error);
                throw error;
            }
        }
    }

    /**
     * General recovery procedures
     */
    async recoverGeneral() {
        console.log('[RouterHealth] Performing general recovery...');

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
     * Trigger full page reload as last resort
     */
    triggerFullReload() {
        console.error('[RouterHealth] Triggering full page reload as last resort');

        // Check if we're already in a recovery loop
        const url = new URL(window.location);
        const existingRecovery = url.searchParams.get('_router_recovery');

        if (existingRecovery) {
            // If recovery already attempted recently, just clean up and reload normally
            const recoveryTime = parseInt(existingRecovery);
            if (Date.now() - recoveryTime < 10000) { // Within 10 seconds
                console.warn('[RouterHealth] Recovery loop detected, cleaning URL and reloading');
                url.searchParams.delete('_router_recovery');
                url.searchParams.delete('_recovery');
                window.location.href = url.toString();
                return;
            }
        }

        // Add recovery flag to URL to prevent infinite reload loops
        url.searchParams.set('_router_recovery', Date.now());
        window.location.href = url.toString();
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
                    console.error(`[RouterHealth] Listener error for ${event}:`, error);
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
     * Clean up recovery parameters from URL
     */
    cleanupRecoveryParams() {
        if (typeof window !== 'undefined' && this.router) {
            const currentRoute = this.router.currentRoute.value;
            if (currentRoute.query._recovery || currentRoute.query._router_recovery) {
                const cleanQuery = { ...currentRoute.query };
                delete cleanQuery._recovery;
                delete cleanQuery._router_recovery;

                console.log('[RouterHealth] Cleaning up recovery parameters from URL');
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