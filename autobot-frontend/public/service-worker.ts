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
 */

const CACHE_VERSION = 'v1'
const STATIC_CACHE = `autobot-static-${CACHE_VERSION}`
const API_CACHE = `autobot-api-${CACHE_VERSION}`
const DYNAMIC_CACHE = `autobot-dynamic-${CACHE_VERSION}`

// Static assets to precache on install
const PRECACHE_URLS = [
  '/',
  '/index.html',
  '/manifest.json',
  '/favicon.ico'
]

// API endpoints that should not be cached
const NO_CACHE_PATTERNS = [
  /\/api\/events\//,
  /\/api\/auth\//,
  /\/api\/sessions\/[^/]+\/sync/
]

// API endpoints to cache with network-first strategy
const CACHEABLE_API_PATTERNS = [
  /\/api\/knowledge\//,
  /\/api\/templates\//,
  /\/api\/config\//
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
 * Get appropriate cache name for a URL
 */
function getCacheName(url: string): string {
  if (isApiUrl(url)) {
    return API_CACHE
  }
  return DYNAMIC_CACHE
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
 * Activate event: clean up old caches
 */
self.addEventListener('activate', (event: ExtendableEvent) => {
  event.waitUntil(
    caches.keys().then((cacheNames) => {
      return Promise.all(
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
    })
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
  if (!isApiUrl(url)) {
    event.respondWith(
      caches.match(request).then((response) => {
        if (response) {
          return response
        }

        return fetch(request).then((response) => {
          // Cache successful responses
          if (!response || response.status !== 200 || response.type === 'error') {
            return response
          }

          const responseToCache = response.clone()
          caches.open(DYNAMIC_CACHE).then((cache) => {
            cache.put(request, responseToCache)
          })

          return response
        })
      })
    )
    return
  }

  // Network-first strategy for API calls
  event.respondWith(
    fetch(request)
      .then((response) => {
        // Cache successful API responses
        if (response && response.status === 200) {
          const responseToCache = response.clone()
          caches.open(API_CACHE).then((cache) => {
            cache.put(request, responseToCache)
          })
        }
        return response
      })
      .catch(() => {
        // Fallback to cache on network error
        return (
          caches.match(request).then((response) => {
            if (response) {
              return response
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
          }) || new Response('Offline', { status: 503 })
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
})
