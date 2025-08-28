/**
 * Centralized Caching Service for Frequently Accessed Data
 * Provides intelligent caching for API responses with TTL and invalidation
 */

class CacheService {
  constructor() {
    this.cache = new Map();
    this.defaultTTL = 5 * 60 * 1000; // 5 minutes
    this.strategies = {
      // Settings rarely change - cache for longer
      '/api/settings': 10 * 60 * 1000, // 10 minutes
      '/api/settings/': 10 * 60 * 1000,
      
      // System health can be cached briefly
      '/api/system/health': 30 * 1000, // 30 seconds
      
      // Knowledge base stats change infrequently
      '/api/knowledge_base/stats': 2 * 60 * 1000, // 2 minutes
      
      // Chat list changes often but can be cached briefly
      '/api/chats': 1 * 60 * 1000, // 1 minute
      
      // Prompts rarely change
      '/api/prompts/': 5 * 60 * 1000, // 5 minutes
      
      // User profile data
      '/api/user/profile': 5 * 60 * 1000
    };

    // Cleanup expired entries every minute
    this.cleanupInterval = setInterval(() => {
      this.cleanup();
    }, 60 * 1000);
  }

  /**
   * Get cached data for a key
   * @param {string} key - Cache key
   * @returns {any|null} Cached data or null if expired/not found
   */
  get(key) {
    const entry = this.cache.get(key);
    
    if (!entry) {
      return null;
    }

    // Check if expired
    if (Date.now() > entry.expiresAt) {
      this.cache.delete(key);
      return null;
    }

    entry.lastAccessed = Date.now();
    return entry.data;
  }

  /**
   * Set data in cache with TTL
   * @param {string} key - Cache key
   * @param {any} data - Data to cache
   * @param {number} ttl - Time to live in milliseconds (optional)
   */
  set(key, data, ttl = null) {
    const useTTL = ttl || this.getTTLForEndpoint(key) || this.defaultTTL;
    
    this.cache.set(key, {
      data,
      createdAt: Date.now(),
      lastAccessed: Date.now(),
      expiresAt: Date.now() + useTTL
    });
  }

  /**
   * Get TTL for specific endpoint
   * @param {string} endpoint - API endpoint
   * @returns {number|null} TTL in milliseconds
   */
  getTTLForEndpoint(endpoint) {
    // Find matching strategy
    for (const [pattern, ttl] of Object.entries(this.strategies)) {
      if (endpoint.includes(pattern)) {
        return ttl;
      }
    }
    return null;
  }

  /**
   * Invalidate cache for specific key or pattern
   * @param {string} keyOrPattern - Exact key or pattern to match
   */
  invalidate(keyOrPattern) {
    if (this.cache.has(keyOrPattern)) {
      this.cache.delete(keyOrPattern);
      return;
    }

    // Pattern-based invalidation
    for (const key of this.cache.keys()) {
      if (key.includes(keyOrPattern)) {
        this.cache.delete(key);
      }
    }
  }

  /**
   * Invalidate all cache entries for an endpoint category
   * @param {string} category - Category like 'chats', 'settings', etc.
   */
  invalidateCategory(category) {
    const pattern = `/api/${category}`;
    this.invalidate(pattern);
  }

  /**
   * Clear all cache
   */
  clear() {
    this.cache.clear();
  }

  /**
   * Get cache statistics
   * @returns {object} Cache stats
   */
  getStats() {
    const now = Date.now();
    let totalSize = 0;
    let expiredCount = 0;
    let validCount = 0;

    for (const [key, entry] of this.cache) {
      totalSize += JSON.stringify(entry.data).length;
      
      if (now > entry.expiresAt) {
        expiredCount++;
      } else {
        validCount++;
      }
    }

    return {
      totalEntries: this.cache.size,
      validEntries: validCount,
      expiredEntries: expiredCount,
      estimatedSizeBytes: totalSize,
      strategies: Object.keys(this.strategies).length
    };
  }

  /**
   * Cleanup expired entries
   */
  cleanup() {
    const now = Date.now();
    const toDelete = [];

    for (const [key, entry] of this.cache) {
      if (now > entry.expiresAt) {
        toDelete.push(key);
      }
    }

    toDelete.forEach(key => this.cache.delete(key));
    
    if (toDelete.length > 0) {
      console.debug(`🧹 Cache cleanup: removed ${toDelete.length} expired entries`);
    }
  }

  /**
   * Warm up cache with commonly accessed endpoints
   */
  async warmup() {
    const commonEndpoints = [
      '/api/system/health',
      '/api/settings/',
      '/api/knowledge_base/stats'
    ];

    console.log('🔥 Warming up cache...');
    
    for (const endpoint of commonEndpoints) {
      try {
        // Use a short TTL for warmup to avoid stale data
        const key = `warmup_${endpoint}`;
        if (!this.get(key)) {
          // This would typically call the API through ApiClient
          // For now, just mark that we attempted warmup
          this.set(key, { warmedUp: true }, 10 * 1000); // 10 seconds
        }
      } catch (error) {
        console.warn(`Cache warmup failed for ${endpoint}:`, error);
      }
    }
  }

  /**
   * Create a cache key for API requests
   * @param {string} endpoint - API endpoint
   * @param {object} params - Request parameters
   * @returns {string} Cache key
   */
  createKey(endpoint, params = {}) {
    if (Object.keys(params).length === 0) {
      return endpoint;
    }
    
    const sortedParams = Object.keys(params)
      .sort()
      .map(key => `${key}=${params[key]}`)
      .join('&');
    
    return `${endpoint}?${sortedParams}`;
  }

  /**
   * Destroy cache service and cleanup
   */
  destroy() {
    if (this.cleanupInterval) {
      clearInterval(this.cleanupInterval);
    }
    this.clear();
  }
}

// Export singleton instance
export const cacheService = new CacheService();

// Make available globally for debugging
if (typeof window !== 'undefined') {
  window.cacheService = cacheService;
}

export default cacheService;