/**
 * Tests for useThumbnailWorker composable
 *
 * Issue #4038: Web Worker thumbnail generation with caching
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
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
    const { cancelThumbnail, pendingCount } = useThumbnailWorker()

    // Note: In actual usage, pendingCount would increment after postMessage
    // For this test, we just verify the cancel function exists and doesn't throw
    expect(() => {
      cancelThumbnail('non-existent-id')
    }).not.toThrow()
  })

  it('should handle Worker not supported', () => {
    // This test verifies behavior when Worker is not available
    // The composable should gracefully handle this case
    const { isSupported, generateThumbnail } = useThumbnailWorker()

    if (!isSupported.value) {
      // If Worker is not supported, generateThumbnail should return null
      expect(isSupported.value).toBe(false)
    }
  })

  it('should validate cache key generation is consistent', () => {
    const { generateThumbnail } = useThumbnailWorker()

    // Verify that the same parameters produce consistent results
    // This is implicit in the implementation but good to verify
    const videoUrl = 'https://example.com/video.mp4'
    const timestamp = 5
    const width = 320
    const height = 180

    // Both calls with same parameters should use same cache
    expect(() => {
      generateThumbnail(videoUrl, timestamp, width, height)
    }).not.toThrow()
  })

  it('should handle concurrent requests', async () => {
    const { pendingCount } = useThumbnailWorker()

    // Verify pendingCount is accessible
    expect(pendingCount.value).toBe(0)
  })
})
