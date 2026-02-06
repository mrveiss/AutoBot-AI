/**
 * Centralized Caching Service for Frequently Accessed Data
 * Provides intelligent caching for API responses with TTL and invalidation
 */

import { createLogger } from '@/utils/debugUtils'

// Create scoped logger for CacheService
const logger = createLogger('CacheService')

interface CacheEntry {
  data: any;
  createdAt: number;
  lastAccessed: number;
  expiresAt: number;
}

interface CacheStats {
  totalEntries: number;
  validEntries: number;
  expiredEntries: number;
  estimatedSizeBytes: number;
  strategies: number;
}

interface CacheStrategies {
  [key: string]: number;
}

class CacheService {
  private cache: Map<string, CacheEntry>;
  private defaultTTL: number;
  private strategies: CacheStrategies;
  private cleanupInterval: NodeJS.Timeout;

  constructor() {
    this.cache = new Map<string, CacheEntry>();
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
   * @param key - Cache key
   * @returns Cached data or null if expired/not found
   */
  get(key: string): any | null {
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
   * @param key - Cache key
   * @param data - Data to cache
   * @param ttl - Time to live in milliseconds (optional)
   */
  set(key: string, data: any, ttl: number | null = null): void {
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
   * @param endpoint - API endpoint
   * @returns TTL in milliseconds or null
   */
  getTTLForEndpoint(endpoint: string): number | null {
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
   * @param keyOrPattern - Exact key or pattern to match
   */
  invalidate(keyOrPattern: string): void {
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
   * @param category - Category like 'chats', 'settings', etc.
   */
  invalidateCategory(category: string): void {
    const pattern = `/api/${category}`;
    this.invalidate(pattern);
  }

  /**
   * Clear all cache
   */
  clear(): void {
    this.cache.clear();
  }

  /**
   * Get cache statistics
   * @returns Cache stats
   */
  getStats(): CacheStats {
    const now = Date.now();
    let totalSize = 0;
    let expiredCount = 0;
    let validCount = 0;

    for (const [_key, entry] of this.cache) {
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
  cleanup(): void {
    const now = Date.now();
    const toDelete: string[] = [];

    for (const [key, entry] of this.cache) {
      if (now > entry.expiresAt) {
        toDelete.push(key);
      }
    }

    toDelete.forEach(key => this.cache.delete(key));

    if (toDelete.length > 0) {
      logger.debug(`🧹 Cache cleanup: removed ${toDelete.length} expired entries`);
    }
  }

  /**
   * Warm up cache with commonly accessed endpoints
   */
  async warmup(): Promise<void> {
    const commonEndpoints = [
      '/api/system/health',
      '/api/settings/',
      '/api/knowledge_base/stats'
    ];

    logger.info('🔥 Warming up cache...');

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
        logger.warn(`Cache warmup failed for ${endpoint}:`, error);
      }
    }
  }

  /**
   * Create a cache key for API requests
   * @param endpoint - API endpoint
   * @param params - Request parameters
   * @returns Cache key
   */
  createKey(endpoint: string, params: Record<string, any> = {}): string {
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
  destroy(): void {
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
  (window as any).cacheService = cacheService;
}

export default cacheService;
