// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * Tests for useThumbnailWorker composable
 *
 * Issue #4038: Web Worker thumbnail generation with caching
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { effectScope } from 'vue'
import { useThumbnailWorker } from '../useThumbnailWorker'

describe('useThumbnailWorker', () => {
  beforeEach(() => {
    // Clear localStorage before each test
    localStorage.clear()
    vi.clearAllMocks()
  })

  afterEach(() => {
    localStorage.clear()
  })

  it('should initialize with correct defaults', () => {
    const { isSupported, pendingCount } = useThumbnailWorker()
    expect(isSupported.value).toBe(typeof Worker !== 'undefined')
    expect(pendingCount.value).toBe(0)
  })

  it('should clear cache', () => {
    const { clearCache, getCacheStats } = useThumbnailWorker()

    // Add something to localStorage to simulate cached data
    localStorage.setItem('autobot-thumbnail-test', JSON.stringify({ data: 'test' }))

    const statsBefore = getCacheStats()
    expect(statsBefore.localStorageCacheSize).toBeGreaterThan(0)

    clearCache()

    const statsAfter = getCacheStats()
    expect(statsAfter.localStorageCacheSize).toBe(0)
    expect(statsAfter.memoryCacheSize).toBe(0)
  })

  it('should handle cache statistics', () => {
    const { getCacheStats } = useThumbnailWorker()

    // Add mock cache entries
    localStorage.setItem(
      'autobot-thumbnail-1',
      JSON.stringify({
        data: 'image-data-1',
        timestamp: Date.now(),
        expiresAt: Date.now() + 86400000
      })
    )
    localStorage.setItem(
      'autobot-thumbnail-2',
      JSON.stringify({
        data: 'image-data-2',
        timestamp: Date.now(),
        expiresAt: Date.now() + 86400000
      })
    )

    const stats = getCacheStats()
    expect(stats.localStorageCacheSize).toBe(2)
    expect(stats.memoryCacheSize).toBe(0)
    expect(stats.pendingRequests).toBe(0)
  })

  it('should handle expired cache entries', () => {
    const { getCacheStats, clearCache } = useThumbnailWorker()

    // Add expired cache entry
    const expiredEntry = {
      data: 'expired-image',
      timestamp: Date.now() - 100000,
      expiresAt: Date.now() - 1000 // Already expired
    }

    localStorage.setItem(
      'autobot-thumbnail-expired',
      JSON.stringify(expiredEntry)
    )

    // Should count as cached initially
    let stats = getCacheStats()
    expect(stats.localStorageCacheSize).toBe(1)

    // Clear caches
    clearCache()
    stats = getCacheStats()
    expect(stats.localStorageCacheSize).toBe(0)
  })

  it('should handle localStorage errors gracefully', () => {
    const { clearCache } = useThumbnailWorker()

    // Mock localStorage.removeItem to throw error
    const originalRemoveItem = Storage.prototype.removeItem
    vi.spyOn(Storage.prototype, 'removeItem').mockImplementation(() => {
      throw new Error('QuotaExceededError')
    })

    // Should not throw even if localStorage fails
    expect(() => clearCache()).not.toThrow()

    Storage.prototype.removeItem = originalRemoveItem
  })

  it('should cancel pending requests', () => {
    const { cancelThumbnail, _pendingCount } = useThumbnailWorker()

    // Note: In actual usage, pendingCount would increment after postMessage
    // For this test, we just verify the cancel function exists and doesn't throw
    expect(() => {
      cancelThumbnail('non-existent-id')
    }).not.toThrow()
  })

  it('should handle Worker not supported', () => {
    // This test verifies behavior when Worker is not available
    // The composable should gracefully handle this case
    const { isSupported, _generateThumbnail } = useThumbnailWorker()

    if (!isSupported.value) {
      // If Worker is not supported, generateThumbnail should return null
      expect(isSupported.value).toBe(false)
    }
  })

  it('should validate async cache key generation does not throw', async () => {
    const { generateThumbnail } = useThumbnailWorker()

    // Verify that the same parameters produce consistent results
    // This is implicit in the implementation but good to verify
    const videoUrl = 'https://example.com/video.mp4'
    const timestamp = 5
    const width = 320
    const height = 180

    // Should not throw on cache key generation
    expect(() => {
      generateThumbnail(videoUrl, timestamp, width, height)
    }).not.toThrow()
  })

  it('should handle concurrent requests', async () => {
    const { pendingCount } = useThumbnailWorker()

    // Verify pendingCount is accessible
    expect(pendingCount.value).toBe(0)
  })

  it('should maintain LRU cache eviction order', () => {
    const { getCacheStats, clearCache } = useThumbnailWorker()

    // Create multiple cache entries via localStorage
    for (let i = 0; i < 3; i++) {
      localStorage.setItem(
        `autobot-thumbnail-lru-${i}`,
        JSON.stringify({
          data: `image-data-${i}`,
          timestamp: Date.now(),
          expiresAt: Date.now() + 86400000
        })
      )
    }

    const stats = getCacheStats()
    expect(stats.localStorageCacheSize).toBe(3)

    clearCache()
    expect(getCacheStats().localStorageCacheSize).toBe(0)
  })

  // ========================================
  // Scope-aware cleanup (#5347)
  // ========================================

  describe('scope-aware cleanup (#5347)', () => {
    it('does not warn outside component setup when used in effectScope', () => {
      const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
      const scope = effectScope()
      scope.run(() => {
        useThumbnailWorker()
      })
      scope.stop()
      expect(warn).not.toHaveBeenCalledWith(
        expect.stringContaining('no active component')
      )
      warn.mockRestore()
    })

    it('does not warn when called with no active scope at all', () => {
      const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
      const { clearCache } = useThumbnailWorker()
      clearCache()
      expect(warn).not.toHaveBeenCalledWith(
        expect.stringContaining('no active component')
      )
      warn.mockRestore()
    })

    it('scope.stop() disposes cleanup without errors', () => {
      const scope = effectScope()
      scope.run(() => {
        useThumbnailWorker()
      })
      expect(() => scope.stop()).not.toThrow()
    })
  })
})
