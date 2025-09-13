/**
 * Bulletproof Cache Busting System
 * Eliminates cache poisoning across all layers
 */

class CacheBuster {
    constructor() {
        this.buildId = import.meta.env.VITE_BUILD_TIMESTAMP || Date.now();
        this.sessionId = this.generateSessionId();
        this.requestCounter = 0;
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
                console.log('[CacheBuster] Cleared Cache API');
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

            console.log('[CacheBuster] All caches cleared');
        } catch (error) {
            console.error('[CacheBuster] Error clearing caches:', error);
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
            console.warn('[CacheBuster] Cache poisoning detected:', indicators);
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
        console.log('[CacheBuster] Handling cache poisoning...');

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
                console.warn('[CacheBuster] Resource loading error:', event.target.src || event.target.href);
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
                    console.debug('[CacheBuster] Potential cached response detected');
                }

                return response;
            } catch (error) {
                console.error('[CacheBuster] Fetch error:', error);
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

        console.log('[CacheBuster] Initialized with build ID:', this.buildId);
    }
}

// Export singleton instance
export const cacheBuster = new CacheBuster();

// Auto-initialize
if (typeof window !== 'undefined') {
    cacheBuster.initialize();
}

export default CacheBuster;