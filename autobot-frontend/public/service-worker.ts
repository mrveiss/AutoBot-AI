// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * AutoBot Service Worker
 *
 * Issue #4041: Service Worker caching strategy for PWA support
 *
 * Implements cache-first strategy for static assets (CSS, JS, fonts)
 * and network-first strategy for API calls with fallback to cache.
 *
 * Caching strategies:
 * - Cache-First: Static assets, fonts → Check cache first, fallback to network
 * - Network-First: API calls → Try network first, fallback to cache for offline support
 * - Network-Only: Critical API endpoints (no caching)
 *
 * Cache expiration: 24 hours (86400 seconds) for both static and API caches
 */

const CACHE_VERSION = 'v1'
const STATIC_CACHE = `autobot-static-${CACHE_VERSION}`
const API_CACHE = `autobot-api-${CACHE_VERSION}`
const DYNAMIC_CACHE = `autobot-dynamic-${CACHE_VERSION}`

// Cache expiration time in milliseconds (24 hours)
const CACHE_EXPIRATION_TIME = 24 * 60 * 60 * 1000 // 86400000ms

// Static assets to precache on install
const PRECACHE_URLS = [
  '/',
  '/index.html',
  '/manifest.json',
  '/favicon.ico',
  '/offline.html'
]

// API endpoints that should not be cached
const NO_CACHE_PATTERNS = [
  /\/api\/events\//,
  /\/api\/auth\//,
  /\/api\/sessions\/[^/]+\/sync/
]

// API endpoints to cache with network-first strategy
const _CACHEABLE_API_PATTERNS = [
  /\/api\/knowledge\//,
  /\/api\/templates\//,
  /\/api\/config\//
]

// Static asset extensions that should use cache-first strategy
const STATIC_ASSET_PATTERNS = [
  /\.(js|css|woff|woff2|ttf|eot|svg)(\?.*)?$/,
  /\.(png|jpg|jpeg|gif|webp|ico)(\?.*)?$/,
  /\/fonts\//,
  /\/assets\//
]

/**
 * Check if a URL should be cached
 */
function isCacheableUrl(url: string): boolean {
  return !NO_CACHE_PATTERNS.some(pattern => pattern.test(url))
}

/**
 * Check if a URL is an API endpoint
 */
function isApiUrl(url: string): boolean {
  return url.includes('/api/')
}

/**
 * Check if a URL is a static asset
 */
function isStaticAsset(url: string): boolean {
  return STATIC_ASSET_PATTERNS.some(pattern => pattern.test(url))
}

/**
 * Get appropriate cache name for a URL
 */
function _getCacheName(url: string): string {
  if (isApiUrl(url)) {
    return API_CACHE
  }
  return DYNAMIC_CACHE
}

/**
 * Get cache entry metadata
 */
function getCacheMetadata(response: Response): any {
  return {
    timestamp: Date.now(),
    url: response.url,
    status: response.status,
    headers: {
      contentType: response.headers.get('content-type'),
      cacheControl: response.headers.get('cache-control')
    }
  }
}

/**
 * Check if cache entry has expired
 */
function isCacheExpired(timestamp: number): boolean {
  return Date.now() - timestamp > CACHE_EXPIRATION_TIME
}

/**
 * Wrap response with metadata for expiration tracking
 */
async function wrapResponseWithMetadata(response: Response): Promise<Response> {
  const metadata = getCacheMetadata(response)
  const blob = await response.blob()

  // Create a new response with metadata in headers
  return new Response(blob, {
    status: response.status,
    statusText: response.statusText,
    headers: new Headers({
      ...Object.fromEntries(response.headers),
      'X-Cache-Timestamp': metadata.timestamp.toString(),
      'X-Cache-URL': metadata.url
    })
  })
}

/**
 * Clean up expired cache entries
 */
async function cleanupExpiredCache(cacheName: string): Promise<void> {
  const cache = await caches.open(cacheName)
  const keys = await cache.keys()

  for (const request of keys) {
    const response = await cache.match(request)
    if (response) {
      const timestamp = parseInt(response.headers.get('X-Cache-Timestamp') || '0', 10)
      if (timestamp && isCacheExpired(timestamp)) {
        cache.delete(request)
      }
    }
  }
}

/**
 * Install event: precache static assets
 */
self.addEventListener('install', (event: ExtendableEvent) => {
  event.waitUntil(
    caches.open(STATIC_CACHE).then((cache) => {
      return cache.addAll(PRECACHE_URLS).catch((err) => {
        console.warn('[SW] Precache failed (offline ok):', err)
        // Non-critical: offline installation is acceptable
      })
    })
  )
  // Force activation immediately
  ;(self as any).skipWaiting()
})

/**
 * Activate event: clean up old caches and expired entries
 */
self.addEventListener('activate', (event: ExtendableEvent) => {
  event.waitUntil(
    (async () => {
      // Delete old cache versions
      const cacheNames = await caches.keys()
      await Promise.all(
        cacheNames
          .filter((name) => {
            // Keep current caches, delete old versions
            return !(
              name === STATIC_CACHE ||
              name === API_CACHE ||
              name === DYNAMIC_CACHE
            )
          })
          .map((name) => caches.delete(name))
      )

      // Clean up expired entries from current caches
      await Promise.all([
        cleanupExpiredCache(STATIC_CACHE),
        cleanupExpiredCache(API_CACHE),
        cleanupExpiredCache(DYNAMIC_CACHE)
      ])
    })()
  )
  // Claim clients immediately
  ;(self as any).clients.claim()
})

/**
 * Fetch event: implement caching strategies
 */
self.addEventListener('fetch', (event: FetchEvent) => {
  const { request } = event
  const url = request.url

  // Skip non-GET requests
  if (request.method !== 'GET') {
    return
  }

  // Skip non-cacheable URLs
  if (!isCacheableUrl(url)) {
    return
  }

  // Cache-first strategy for static assets
  if (isStaticAsset(url)) {
    event.respondWith(
      caches.match(request).then(async (response) => {
        if (response) {
          // Check if cache is expired
          const timestamp = parseInt(response.headers.get('X-Cache-Timestamp') || '0', 10)
          if (timestamp && !isCacheExpired(timestamp)) {
            return response
          }
          // Cache expired, remove it and fetch from network
          const cache = await caches.open(DYNAMIC_CACHE)
          cache.delete(request)
        }

        return fetch(request).then(async (response) => {
          // Cache successful responses
          if (!response || response.status !== 200 || response.type === 'error') {
            return response
          }

          const wrappedResponse = await wrapResponseWithMetadata(response)
          const responseToCache = wrappedResponse.clone()
          caches.open(DYNAMIC_CACHE).then((cache) => {
            cache.put(request, responseToCache)
          })

          return wrappedResponse
        })
      })
    )
    return
  }

  // Network-first strategy for API calls
  event.respondWith(
    fetch(request)
      .then(async (response) => {
        // Cache successful API responses
        if (response && response.status === 200) {
          const wrappedResponse = await wrapResponseWithMetadata(response)
          const responseToCache = wrappedResponse.clone()
          caches.open(API_CACHE).then((cache) => {
            cache.put(request, responseToCache)
          })
          return wrappedResponse
        }
        return response
      })
      .catch(async () => {
        // Fallback to cache on network error
        const cachedResponse = await caches.match(request)
        if (cachedResponse) {
          return cachedResponse
        }

        // Check if request is for HTML (main page navigation)
        if (request.mode === 'navigate') {
          return caches.match('/offline.html').then((offlineResponse) => {
            if (offlineResponse) {
              return offlineResponse
            }
            // Fallback if offline.html is not cached
            return new Response(
              'Offline - please check your connection',
              { status: 503, statusText: 'Service Unavailable' }
            )
          })
        }

        // No cache available - return offline response
        return new Response(
          JSON.stringify({
            error: 'offline',
            message: 'Service temporarily unavailable. Please check your connection.'
          }),
          {
            status: 503,
            statusText: 'Service Unavailable',
            headers: new Headers({
              'Content-Type': 'application/json'
            })
          }
        )
      })
  )
})

/**
 * Message event: allow clients to control caching
 */
self.addEventListener('message', (event: ExtendableMessageEvent) => {
  if (event.data && event.data.type === 'SKIP_WAITING') {
    ;(self as any).skipWaiting()
  }

  if (event.data && event.data.type === 'CLEAR_CACHES') {
    event.waitUntil(
      caches.keys().then((cacheNames) => {
        return Promise.all(cacheNames.map((name) => caches.delete(name)))
      })
    )
  }

  if (event.data && event.data.type === 'CLEANUP_EXPIRED') {
    event.waitUntil(
      Promise.all([
        cleanupExpiredCache(STATIC_CACHE),
        cleanupExpiredCache(API_CACHE),
        cleanupExpiredCache(DYNAMIC_CACHE)
      ]).then(() => {
        event.ports[0]?.postMessage({ type: 'CLEANUP_COMPLETE' })
      })
    )
  }
})
