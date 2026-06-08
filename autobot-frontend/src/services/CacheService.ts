// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * Centralized Caching Service for Frequently Accessed Data
 * Provides intelligent caching for API responses with TTL and invalidation
 */

import { createLogger } from '@/utils/debugUtils'
import { getApiBase } from '@/config/ssot-config'

// Create scoped logger for CacheService
const logger = createLogger('CacheService')

interface CacheEntry {
  data: unknown;
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
  private cleanupInterval: ReturnType<typeof setInterval>;

  constructor() {
    this.cache = new Map<string, CacheEntry>();
    this.defaultTTL = 5 * 60 * 1000; // 5 minutes
    this.strategies = {
      [`${getApiBase()}/settings`]: 10 * 60 * 1000,
      [`${getApiBase()}/settings/`]: 10 * 60 * 1000,
      [`${getApiBase()}/system/health`]: 30 * 1000,
      [`${getApiBase()}/knowledge_base/stats`]: 2 * 60 * 1000,
      [`${getApiBase()}/chats`]: 1 * 60 * 1000,
      [`${getApiBase()}/prompts/`]: 5 * 60 * 1000,
      [`${getApiBase()}/user/profile`]: 5 * 60 * 1000
    };

    this.cleanupInterval = setInterval(() => {
      this.cleanup();
    }, 60 * 1000);
  }

  get(key: string): unknown | null {
    const entry = this.cache.get(key);

    if (!entry) {
      return null;
    }

    if (Date.now() > entry.expiresAt) {
      this.cache.delete(key);
      return null;
    }

    entry.lastAccessed = Date.now();
    return entry.data;
  }

  set(key: string, data: unknown, ttl: number | null = null): void {
    const useTTL = ttl || this.getTTLForEndpoint(key) || this.defaultTTL;

    this.cache.set(key, {
      data,
      createdAt: Date.now(),
      lastAccessed: Date.now(),
      expiresAt: Date.now() + useTTL
    });
  }

  getTTLForEndpoint(endpoint: string): number | null {
    for (const [pattern, ttl] of Object.entries(this.strategies)) {
      if (endpoint.includes(pattern)) {
        return ttl;
      }
    }
    return null;
  }

  invalidate(keyOrPattern: string): void {
    if (this.cache.has(keyOrPattern)) {
      this.cache.delete(keyOrPattern);
      return;
    }

    for (const key of this.cache.keys()) {
      if (key.includes(keyOrPattern)) {
        this.cache.delete(key);
      }
    }
  }

  invalidateCategory(category: string): void {
    const pattern = `${getApiBase()}/${category}`;
    this.invalidate(pattern);
  }

  clear(): void {
    this.cache.clear();
  }

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
      logger.debug(`Cache cleanup: removed ${toDelete.length} expired entries`);
    }
  }

  async warmup(): Promise<void> {
    const commonEndpoints = [
      `${getApiBase()}/system/health`,
      `${getApiBase()}/settings/`,
      `${getApiBase()}/knowledge_base/stats`
    ];

    logger.info('Warming up cache...');

    for (const endpoint of commonEndpoints) {
      try {
        const key = `warmup_${endpoint}`;
        if (!this.get(key)) {
          this.set(key, { warmedUp: true }, 10 * 1000);
        }
      } catch (error) {
        logger.warn(`Cache warmup failed for ${endpoint}:`, error);
      }
    }
  }

  createKey(endpoint: string, params: Record<string, string | number | boolean> = {}): string {
    if (Object.keys(params).length === 0) {
      return endpoint;
    }

    const sortedParams = Object.keys(params)
      .sort()
      .map(key => `${key}=${params[key]}`)
      .join('&');

    return `${endpoint}?${sortedParams}`;
  }

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
  (window as unknown as Record<string, unknown>).cacheService = cacheService;
}

export default cacheService;
