/**
 * Thumbnail Worker Composable
 *
 * Issue #4038: Web Worker-based thumbnail generation with dual-level caching
 *
 * Manages thumbnail generation using a Web Worker for CPU-intensive operations.
 * Implements dual-level caching:
 * - L1: Worker thread memory cache (fast, session-based)
 * - L2: localStorage cache (persistent, 24-hour TTL)
 *
 * Usage:
 * ```vue
 * <script setup>
 * import { useThumbnailWorker } from '@/composables/useThumbnailWorker'
 * const { generateThumbnail, cancelThumbnail, clearCache } = useThumbnailWorker()
 *
 * const thumbnail = await generateThumbnail(videoUrl, 5, 200, 150)
 * </script>
 * ```
 */

import { ref, computed, onMounted, onUnmounted } from 'vue'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('useThumbnailWorker')

interface CacheEntry {
  data: string // base64 image data
  timestamp: number // creation time
  expiresAt: number // expiration time
}

interface ThumbnailRequest {
  id: string
  videoUrl: string
  timestamp: number
  width: number
  height: number
  format: 'image/jpeg' | 'image/png' | 'image/webp'
  quality?: number
}

interface ThumbnailResult {
  id: string
  success: boolean
  data?: string
  error?: string
  processingTime: number
}

// Worker instance (lazy-loaded)
let workerInstance: Worker | null = null
let pendingRequests = new Map<string, (result: ThumbnailResult) => void>()

const CACHE_PREFIX = 'autobot-thumbnail-'
const CACHE_TTL = 24 * 60 * 60 * 1000 // 24 hours in milliseconds
const MEMORY_CACHE_LIMIT = 50 // Max entries in memory cache

// Memory cache (L1 - fast access, session-based)
const memoryCache = new Map<string, CacheEntry>()

/**
 * Initialize or get Web Worker instance
 */
function getWorker(): Worker {
  if (!workerInstance) {
    // Import worker module
    workerInstance = new Worker(
      new URL('../workers/thumbnailWorker.ts', import.meta.url),
      { type: 'module' }
    )

    // Handle messages from worker
    workerInstance.onmessage = (event: MessageEvent<ThumbnailResult>) => {
      const { id, success, data, error, processingTime } = event.data

      logger.debug(`Thumbnail generated [${id}]`, {
        success,
        size: data ? data.length : 0,
        processingTime: `${processingTime.toFixed(2)}ms`
      })

      // Cache successful results
      if (success && data) {
        const cacheKey = id
        const entry: CacheEntry = {
          data,
          timestamp: Date.now(),
          expiresAt: Date.now() + CACHE_TTL
        }

        // L1: Memory cache
        if (memoryCache.size >= MEMORY_CACHE_LIMIT) {
          // Remove oldest entry
          const oldestKey = [...memoryCache.entries()].sort(
            (a, b) => a[1].timestamp - b[1].timestamp
          )[0]?.[0]
          if (oldestKey) memoryCache.delete(oldestKey)
        }
        memoryCache.set(cacheKey, entry)

        // L2: localStorage cache
        try {
          localStorage.setItem(CACHE_PREFIX + cacheKey, JSON.stringify(entry))
        } catch (err) {
          logger.warn('Failed to cache thumbnail in localStorage:', err)
        }
      }

      // Resolve pending request
      const resolver = pendingRequests.get(id)
      if (resolver) {
        resolver(event.data)
        pendingRequests.delete(id)
      }
    }

    workerInstance.onerror = (error: ErrorEvent) => {
      logger.error('Worker error:', error.message)
    }
  }

  return workerInstance
}

/**
 * Generate cache key from request parameters
 */
function generateCacheKey(
  videoUrl: string,
  timestamp: number,
  width: number,
  height: number,
  format: string
): string {
  // Create a simple hash from parameters
  const str = `${videoUrl}:${timestamp}:${width}:${height}:${format}`
  let hash = 0
  for (let i = 0; i < str.length; i++) {
    const char = str.charCodeAt(i)
    hash = (hash << 5) - hash + char
    hash = hash & hash // Convert to 32-bit integer
  }
  return `thumb-${Math.abs(hash).toString(36)}`
}

/**
 * Get thumbnail from cache (L1 or L2)
 */
function getCachedThumbnail(cacheKey: string): string | null {
  // Check L1 memory cache
  const memoryEntry = memoryCache.get(cacheKey)
  if (memoryEntry) {
    if (Date.now() < memoryEntry.expiresAt) {
      logger.debug(`Thumbnail hit (memory): ${cacheKey}`)
      return memoryEntry.data
    } else {
      // Remove expired entry
      memoryCache.delete(cacheKey)
    }
  }

  // Check L2 localStorage cache
  try {
    const storedData = localStorage.getItem(CACHE_PREFIX + cacheKey)
    if (storedData) {
      const entry: CacheEntry = JSON.parse(storedData)
      if (Date.now() < entry.expiresAt) {
        logger.debug(`Thumbnail hit (localStorage): ${cacheKey}`)
        // Promote to memory cache
        memoryCache.set(cacheKey, entry)
        return entry.data
      } else {
        // Remove expired entry
        localStorage.removeItem(CACHE_PREFIX + cacheKey)
      }
    }
  } catch (err) {
    logger.warn('Failed to read thumbnail from localStorage:', err)
  }

  return null
}

/**
 * Composable for thumbnail generation
 */
export function useThumbnailWorker() {
  const isSupported = ref(
    typeof Worker !== 'undefined' && typeof OffscreenCanvas !== 'undefined'
  )
  const pendingCount = computed(() => pendingRequests.size)

  let requestId = 0

  /**
   * Generate thumbnail from video URL
   */
  async function generateThumbnail(
    videoUrl: string,
    timestamp: number = 0,
    width: number = 320,
    height: number = 180,
    format: 'image/jpeg' | 'image/png' | 'image/webp' = 'image/jpeg',
    quality: number = 0.85
  ): Promise<string | null> {
    if (!isSupported.value) {
      logger.warn('Web Worker or OffscreenCanvas not supported')
      return null
    }

    const cacheKey = generateCacheKey(videoUrl, timestamp, width, height, format)

    // Check cache first
    const cached = getCachedThumbnail(cacheKey)
    if (cached) {
      return cached
    }

    // Generate thumbnail using worker
    const id = `thumb-${++requestId}-${Date.now()}`
    const request: ThumbnailRequest = {
      id,
      videoUrl,
      timestamp,
      width,
      height,
      format,
      quality
    }

    return new Promise<string | null>((resolve) => {
      // Set timeout for request
      const timeout = setTimeout(() => {
        pendingRequests.delete(id)
        logger.warn(`Thumbnail generation timeout: ${id}`)
        resolve(null)
      }, 30000) // 30 second timeout

      // Register request handler
      pendingRequests.set(id, (result: ThumbnailResult) => {
        clearTimeout(timeout)
        if (result.success && result.data) {
          resolve(`data:${format};base64,${result.data}`)
        } else {
          logger.error(`Thumbnail generation failed: ${result.error}`)
          resolve(null)
        }
      })

      // Send request to worker
      try {
        getWorker().postMessage(request)
      } catch (err) {
        clearTimeout(timeout)
        pendingRequests.delete(id)
        logger.error('Failed to post message to worker:', err)
        resolve(null)
      }
    })
  }

  /**
   * Cancel pending thumbnail generation
   */
  function cancelThumbnail(id: string): void {
    pendingRequests.delete(id)
  }

  /**
   * Clear all caches
   */
  function clearCache(): void {
    // Clear memory cache
    memoryCache.clear()

    // Clear localStorage cache
    try {
      const keysToDelete: string[] = []
      for (let i = 0; i < localStorage.length; i++) {
        const key = localStorage.key(i)
        if (key?.startsWith(CACHE_PREFIX)) {
          keysToDelete.push(key)
        }
      }
      keysToDelete.forEach(key => localStorage.removeItem(key))
    } catch (err) {
      logger.warn('Failed to clear localStorage cache:', err)
    }

    logger.info('Thumbnail cache cleared')
  }

  /**
   * Get cache statistics
   */
  function getCacheStats() {
    let localStorageSize = 0
    try {
      for (let i = 0; i < localStorage.length; i++) {
        const key = localStorage.key(i)
        if (key?.startsWith(CACHE_PREFIX)) {
          localStorageSize++
        }
      }
    } catch (err) {
      logger.warn('Failed to count localStorage entries:', err)
    }

    return {
      memoryCacheSize: memoryCache.size,
      localStorageCacheSize: localStorageSize,
      pendingRequests: pendingRequests.size
    }
  }

  /**
   * Cleanup on unmount
   */
  onUnmounted(() => {
    // Terminate worker if no longer needed
    if (workerInstance && pendingRequests.size === 0) {
      workerInstance.terminate()
      workerInstance = null
    }
  })

  return {
    isSupported,
    pendingCount,
    generateThumbnail,
    cancelThumbnail,
    clearCache,
    getCacheStats
  }
}
