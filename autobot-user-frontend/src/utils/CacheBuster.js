/**
 * Bulletproof Cache Busting System
 * Eliminates cache poisoning across all layers
 */

import { createLogger } from '@/utils/debugUtils';

// Create scoped logger for CacheBuster
const logger = createLogger('CacheBuster');

class CacheBuster {
    constructor() {
        this.buildId = import.meta.env.VITE_BUILD_TIMESTAMP || Date.now();
        this.sessionId = this.generateSessionId();
        this.requestCounter = 0;

        // Error logging rate limiting
        this.lastConnectionErrorLog = 0;
        this.connectionErrorCount = 0;
        this.connectionErrorCooldown = 5000; // Log once every 5 seconds max
    }

    generateSessionId() {
        return `${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
    }

    /**
     * Generate cache-busting parameters for any request
     */
    getCacheBustParams() {
        this.requestCounter++;
        return {
            _cb: this.buildId,
            _sid: this.sessionId,
            _req: this.requestCounter,
            _ts: Date.now()
        };
    }

    /**
     * Add cache-busting to URL
     */
    bustUrl(url) {
        const params = this.getCacheBustParams();
        const urlObj = new URL(url, window.location.origin);

        Object.entries(params).forEach(([key, value]) => {
            urlObj.searchParams.set(key, value);
        });

        return urlObj.toString();
    }

    /**
     * Add cache-busting headers to fetch requests
     */
    getBustHeaders() {
        const params = this.getCacheBustParams();
        return {
            'Cache-Control': 'no-cache, no-store, must-revalidate',
            'Pragma': 'no-cache',
            'Expires': '0',
            'X-Cache-Bust': params._cb,
            'X-Session-ID': params._sid,
            'X-Request-ID': params._req,
            'X-Timestamp': params._ts,
            'If-None-Match': '*', // Force cache bypass
            'If-Modified-Since': new Date(0).toUTCString() // Force revalidation
        };
    }

    /**
     * Force reload of critical resources
     */
    forceCriticalResourceReload() {
        // Reload CSS with cache busting
        const cssLinks = document.querySelectorAll('link[rel="stylesheet"]');
        cssLinks.forEach(link => {
            const newLink = link.cloneNode();
            newLink.href = this.bustUrl(link.href);
            link.parentNode.insertBefore(newLink, link);
            link.remove();
        });

        // Clear all caches
        this.clearAllCaches();
    }

    /**
     * Clear all browser caches
     */
    async clearAllCaches() {
        try {
            // Clear Cache API
            if ('caches' in window) {
                const cacheNames = await caches.keys();
                await Promise.all(
                    cacheNames.map(cacheName => caches.delete(cacheName))
                );
            }

            // Clear localStorage
            localStorage.clear();

            // Clear sessionStorage
            sessionStorage.clear();

            // Clear IndexedDB
            if ('indexedDB' in window) {
                // This is a simplified approach - in production you might want to be more selective
                indexedDB.databases?.().then(databases => {
                    databases.forEach(db => {
                        indexedDB.deleteDatabase(db.name);
                    });
                });
            }

        } catch (error) {
            logger.error('[CacheBuster] Error clearing caches:', error);
        }
    }

    /**
     * Detect and handle cache poisoning
     */
    detectCachePoisoning() {
        const indicators = {
            staleManifest: this.checkManifestStaleness(),
            missingAssets: this.checkMissingAssets(),
            versionMismatch: this.checkVersionMismatch()
        };

        const isPoisoned = Object.values(indicators).some(indicator => indicator);

        if (isPoisoned) {
            logger.warn('[CacheBuster] Cache poisoning detected:', indicators);
            this.handleCachePoisoning();
        }

        return isPoisoned;
    }

    checkManifestStaleness() {
        const manifestMeta = document.querySelector('meta[name="build-timestamp"]');
        if (!manifestMeta) return false;

        const manifestTime = parseInt(manifestMeta.content);
        const currentTime = Date.now();
        const maxAge = 24 * 60 * 60 * 1000; // 24 hours

        return (currentTime - manifestTime) > maxAge;
    }

    checkMissingAssets() {
        // Check if critical assets are loading
        const scripts = document.querySelectorAll('script[src]');
        const links = document.querySelectorAll('link[href]');

        let missingCount = 0;
        [...scripts, ...links].forEach(element => {
            if (element.dataset.loadError) {
                missingCount++;
            }
        });

        return missingCount > 0;
    }

    checkVersionMismatch() {
        // Check if the current build ID matches expected
        const expectedBuildId = document.querySelector('meta[name="build-id"]')?.content;
        return expectedBuildId && expectedBuildId !== this.buildId.toString();
    }

    async handleCachePoisoning() {
        // CRITICAL FIX: Prevent infinite reload loop
        // Check if we've already reloaded recently (within last 10 seconds)
        const reloadKey = 'cachebuster_last_reload';
        const lastReload = sessionStorage.getItem(reloadKey);
        const now = Date.now();

        if (lastReload && (now - parseInt(lastReload)) < 10000) {
            logger.warn('[CacheBuster] Skipping reload - already reloaded recently to prevent infinite loop');
            return;
        }

        // Store reload timestamp
        sessionStorage.setItem(reloadKey, now.toString());

        // Clear all caches
        await this.clearAllCaches();

        // Reload critical resources
        this.forceCriticalResourceReload();

        // Reload page with cache busting
        const currentUrl = new URL(window.location);
        currentUrl.searchParams.set('cache_bust', Date.now());
        currentUrl.searchParams.set('force_reload', '1');

        window.location.href = currentUrl.toString();
    }

    /**
     * Monitor for cache-related errors
     */
    setupCacheErrorMonitoring() {
        // Monitor for resource loading errors
        window.addEventListener('error', (event) => {
            if (event.target && (event.target.tagName === 'SCRIPT' || event.target.tagName === 'LINK')) {
                logger.warn('[CacheBuster] Resource loading error:', event.target.src || event.target.href);
                event.target.dataset.loadError = 'true';

                // Trigger cache poisoning detection
                setTimeout(() => this.detectCachePoisoning(), 1000);
            }
        }, true);

        // Monitor for fetch errors
        const originalFetch = window.fetch;
        window.fetch = async (...args) => {
            try {
                const response = await originalFetch(...args);

                // Check for stale responses
                if (response.status === 304 || response.headers.get('x-cache') === 'HIT') {
                }

                // Reset connection error counter on successful response
                if (this.connectionErrorCount > 0) {
                    this.connectionErrorCount = 0;
                }

                return response;
            } catch (error) {
                // Rate-limit connection/timeout error logging to prevent console spam
                const isConnectionOrTimeoutError =
                    error.name === 'AbortError' ||
                    error.name === 'TimeoutError' ||
                    error.message?.includes('Failed to fetch') ||
                    error.message?.includes('ERR_CONNECTION_REFUSED') ||
                    error.message?.includes('NetworkError') ||
                    error.message?.includes('Network request failed') ||
                    error.message?.includes('signal is aborted') ||
                    error.message?.includes('signal timed out') ||
                    error.message?.includes('timed out') ||
                    error.message?.includes('timeout');

                if (isConnectionOrTimeoutError) {
                    this.connectionErrorCount++;
                    const now = Date.now();

                    // Only log once every cooldown period
                    if (now - this.lastConnectionErrorLog >= this.connectionErrorCooldown) {
                        logger.warn(
                            `[CacheBuster] Backend connection/timeout error (${this.connectionErrorCount} failed requests in last ${
                                Math.round((now - this.lastConnectionErrorLog) / 1000)
                            }s) - Backend may be busy or restarting`
                        );
                        this.lastConnectionErrorLog = now;
                    }
                    // Don't log individual timeout errors - they're rate-limited
                } else {
                    // Log non-connection errors immediately (these are unexpected)
                    logger.error('[CacheBuster] Fetch error:', error);
                }

                throw error;
            }
        };
    }

    /**
     * Initialize cache busting system
     */
    initialize() {
        this.setupCacheErrorMonitoring();

        // Run initial cache poisoning check
        setTimeout(() => this.detectCachePoisoning(), 2000);

        // Periodic cache health checks
        setInterval(() => this.detectCachePoisoning(), 60000); // Every minute

    }
}

// Export singleton instance
export const cacheBuster = new CacheBuster();

// Auto-initialize
if (typeof window !== 'undefined') {
    cacheBuster.initialize();
}

export default CacheBuster;
