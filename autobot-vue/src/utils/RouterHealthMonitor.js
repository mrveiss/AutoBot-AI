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
        this.maxFailures = 3;
        this.healthCheckInterval = 10000; // 10 seconds
        this.navigationTimeout = 5000; // 5 seconds
        this.recoveryAttempts = 0;
        this.maxRecoveryAttempts = 5;

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
    async verifyRouteLoaded(route, retries = 3) {
        if (retries <= 0) {
            console.error('[RouterHealth] Route verification failed after retries:', route.path);
            this.handleRouteVerificationFailure(route);
            return false;
        }

        await nextTick();

        // Wait a bit more for components to render
        await new Promise(resolve => setTimeout(resolve, 100));

        const indicators = this.checkRouteLoadIndicators(route);

        if (indicators.loaded) {
            console.debug('[RouterHealth] Route verified:', route.path);
            return true;
        }

        console.warn('[RouterHealth] Route verification failed, retrying...', indicators);
        await new Promise(resolve => setTimeout(resolve, 500));
        return this.verifyRouteLoaded(route, retries - 1);
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

            // Check 2: Expected route content exists
            const expectedElements = this.getExpectedElementsForRoute(route);
            indicators.expectedContent = expectedElements.length > 0 &&
                expectedElements.every(selector => document.querySelector(selector));

            // Check 3: Document title updated
            indicators.metaUpdated = document.title.includes(route.meta?.title || '');

            // Check 4: No Vue rendering errors
            const vueErrors = document.querySelectorAll('[data-vue-error], .vue-error');
            if (vueErrors.length > 0) {
                indicators.errors.push(`Vue errors found: ${vueErrors.length}`);
            }

            // Route is loaded if at least 2 indicators pass
            const passedCount = [indicators.routerView, indicators.expectedContent, indicators.metaUpdated]
                .filter(Boolean).length;

            indicators.loaded = passedCount >= 2 && indicators.errors.length === 0;

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
            'chat': ['[data-chat-interface]', '.chat-container', '#chat-main'],
            'knowledge': ['[data-knowledge-interface]', '.knowledge-container', '.knowledge-search'],
            'tools': ['[data-tools-interface]', '.tools-container', '.terminal-container'],
            'monitoring': ['[data-monitoring-interface]', '.monitoring-container', '.system-monitor'],
            'settings': ['[data-settings-interface]', '.settings-container', '.settings-form']
        };

        const routeName = route.name?.split('-')[0]; // Get base route name
        return routeSelectors[routeName] || ['.main-content', '#main-content'];
    }

    /**
     * Handle navigation failures
     */
    handleNavigationFailure(error) {
        this.failureCount++;
        this.setHealthy(false);

        console.error('[RouterHealth] Navigation failure:', error);

        if (this.failureCount >= this.maxFailures) {
            this.triggerRecovery('max_failures_reached');
        }

        this.emit('failure', { error, failureCount: this.failureCount });
    }

    /**
     * Handle navigation timeouts
     */
    handleNavigationTimeout(to, from) {
        console.warn('[RouterHealth] Navigation timeout:', { to: to.path, from: from.path });

        this.handleNavigationFailure(new Error('Navigation timeout'));

        if (this.pendingNavigation) {
            clearTimeout(this.pendingNavigation.timeout);
            this.pendingNavigation = null;
        }
    }

    /**
     * Handle route verification failures
     */
    handleRouteVerificationFailure(route) {
        console.error('[RouterHealth] Route verification failed:', route.path);

        this.handleNavigationFailure(new Error(`Route verification failed: ${route.path}`));
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

        // Check if navigation is stale
        if (timeSinceLastSuccess > maxStaleTime && this.failureCount > 0) {
            console.warn('[RouterHealth] Stale navigation detected');
            this.triggerRecovery('stale_navigation');
        }

        // Check current route integrity
        if (this.router?.currentRoute?.value) {
            this.verifyRouteLoaded(this.router.currentRoute.value)
                .then(verified => {
                    if (!verified) {
                        this.handleNavigationFailure(new Error('Health check route verification failed'));
                    }
                });
        }

        // Check for broken router-view
        const routerView = document.querySelector('router-view');
        if (!routerView || routerView.children.length === 0) {
            console.warn('[RouterHealth] Router-view appears broken');
            this.triggerRecovery('broken_router_view');
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

        // Add recovery flag to URL to prevent infinite reload loops
        const url = new URL(window.location);
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