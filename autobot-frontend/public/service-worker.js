/**
 * AutoBot Service Worker - Caching Strategy Implementation
 *
 * Issue #4015: Service Worker with stale-while-revalidate strategy
 *
 * Implements multiple caching strategies:
 * - Static Assets: Cache-first (JS, CSS, fonts, images)
 * - Analytics API: Stale-while-revalidate with long TTL (5 minutes)
 * - Other APIs: Network-first with cache fallback
 * - Critical Endpoints: Network-only (auth, events)
 */

const CACHE_VERSION = 'v1'
const STATIC_CACHE = `autobot-static-${CACHE_VERSION}`
const API_CACHE = `autobot-api-${CACHE_VERSION}`
const ANALYTICS_CACHE = `autobot-analytics-${CACHE_VERSION}`

// Cache expiration times
const STATIC_CACHE_EXPIRY = 24 * 60 * 60 * 1000 // 24 hours
const ANALYTICS_CACHE_EXPIRY = 5 * 60 * 1000 // 5 minutes
const API_CACHE_EXPIRY = 2 * 60 * 1000 // 2 minutes

// Static assets that should be cached aggressively
const STATIC_ASSET_PATTERNS = [
  /\.(js|css|woff|woff2|ttf|eot|svg)(\?.*)?$/i,
  /\.(png|jpg|jpeg|gif|webp|ico)(\?.*)?$/i,
  /\/fonts\//,
  /\/assets\//
]

// Analytics API patterns to cache with stale-while-revalidate
const ANALYTICS_PATTERNS = [
  /\/api\/analytics\//,
  /\/api\/metrics\//,
  /\/api\/reports\//
]

// API endpoints that must never be cached
const NO_CACHE_PATTERNS = [
  /\/api\/auth\//,
  /\/api\/events\//,
  /\/api\/sessions\/[^/]+\/sync/,
  /\/ws/
]

/**
 * Check if a URL matches any pattern in the list
 */
function matchesPattern(url, patterns) {
  return patterns.some(pattern => pattern.test(url))
}

/**
 * Get cache entry with timestamp
 */
async function getCacheEntryWithTime(cache, request) {
  const response = await cache.match(request)
  if (!response) return null

  const timestamp = parseInt(response.headers.get('X-Cache-Time') || '0', 10)
  return { response, timestamp }
}

/**
 * Check if cache entry is still valid
 */
function isCacheValid(timestamp, maxAge) {
  return timestamp && Date.now() - timestamp < maxAge
}

/**
 * Wrap response with cache timestamp
 */
function wrapResponseWithTime(response) {
  const headers = new Headers(response.headers)
  headers.set('X-Cache-Time', Date.now().toString())
  headers.set('X-Cache-Source', 'service-worker')

  return new Response(response.body, {
    status: response.status,
    statusText: response.statusText,
    headers
  })
}

/**
 * Clean up expired cache entries
 */
async function cleanupExpiredCache(cacheName, maxAge) {
  const cache = await caches.open(cacheName)
  const keys = await cache.keys()

  for (const request of keys) {
    const entry = await getCacheEntryWithTime(cache, request)
    if (entry && !isCacheValid(entry.timestamp, maxAge)) {
      cache.delete(request)
    }
  }
}

/**
 * Install event
 */
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(STATIC_CACHE).then((cache) => {
      // Precache critical assets
      return cache.addAll([
        '/',
        '/index.html',
        '/manifest.json',
        '/favicon.ico',
        '/offline.html'
      ]).catch(() => {
        // Precache failures are non-critical
      })
    })
  )
  self.skipWaiting()
})

/**
 * Activate event
 */
self.addEventListener('activate', (event) => {
  event.waitUntil(
    (async () => {
      // Delete old cache versions
      const cacheNames = await caches.keys()
      await Promise.all(
        cacheNames
          .filter((name) => {
            return !(
              name === STATIC_CACHE ||
              name === API_CACHE ||
              name === ANALYTICS_CACHE
            )
          })
          .map((name) => caches.delete(name))
      )

      // Clean up expired entries
      await Promise.all([
        cleanupExpiredCache(STATIC_CACHE, STATIC_CACHE_EXPIRY),
        cleanupExpiredCache(ANALYTICS_CACHE, ANALYTICS_CACHE_EXPIRY),
        cleanupExpiredCache(API_CACHE, API_CACHE_EXPIRY)
      ])
    })()
  )
  self.clients.claim()
})

/**
 * Fetch event with multiple caching strategies
 */
self.addEventListener('fetch', (event) => {
  const { request } = event
  const url = request.url

  // Only handle GET requests
  if (request.method !== 'GET') {
    return
  }

  // Skip non-cacheable URLs
  if (matchesPattern(url, NO_CACHE_PATTERNS)) {
    event.respondWith(fetch(request).catch(() => {
      if (request.mode === 'navigate') {
        return caches.match('/offline.html')
      }
      return new Response('Offline', { status: 503 })
    }))
    return
  }

  // Cache-first strategy for static assets
  if (matchesPattern(url, STATIC_ASSET_PATTERNS)) {
    event.respondWith(
      caches.open(STATIC_CACHE).then((cache) => {
        return cache.match(request).then((response) => {
          if (response) {
            const timestamp = parseInt(response.headers.get('X-Cache-Time') || '0', 10)
            if (isCacheValid(timestamp, STATIC_CACHE_EXPIRY)) {
              return response
            }
            // Cache expired, remove it
            cache.delete(request)
          }

          // Fetch from network
          return fetch(request).then((response) => {
            if (response && response.status === 200) {
              const wrapped = wrapResponseWithTime(response.clone())
              cache.put(request, wrapped.clone())
              return wrapped
            }
            return response
          }).catch(() => {
            // Return cached version if available, even if expired
            return cache.match(request)
          })
        })
      })
    )
    return
  }

  // Stale-while-revalidate for analytics APIs
  if (matchesPattern(url, ANALYTICS_PATTERNS)) {
    event.respondWith(
      caches.open(ANALYTICS_CACHE).then((cache) => {
        return cache.match(request).then((cachedResponse) => {
          // Check if cached response is still valid
          if (cachedResponse) {
            const timestamp = parseInt(cachedResponse.headers.get('X-Cache-Time') || '0', 10)
            if (isCacheValid(timestamp, ANALYTICS_CACHE_EXPIRY)) {
              // Return cached response and update in background
              fetch(request).then((freshResponse) => {
                if (freshResponse && freshResponse.status === 200) {
                  const wrapped = wrapResponseWithTime(freshResponse.clone())
                  cache.put(request, wrapped)
                }
              }).catch(() => {
                // Background update failed, no action needed
              })
              return cachedResponse
            }
          }

          // Fetch fresh response
          return fetch(request).then((response) => {
            if (response && response.status === 200) {
              const wrapped = wrapResponseWithTime(response.clone())
              cache.put(request, wrapped.clone())
              return wrapped
            }
            return response
          }).catch(() => {
            // Return stale cache if available
            return cachedResponse || new Response('Offline', { status: 503 })
          })
        })
      })
    )
    return
  }

  // Network-first for other APIs
  event.respondWith(
    fetch(request).then((response) => {
      if (response && response.status === 200) {
        const cache = caches.open(API_CACHE)
        const wrapped = wrapResponseWithTime(response.clone())
        cache.then((c) => c.put(request, wrapped.clone()))
        return wrapped
      }
      return response
    }).catch(() => {
      // Fallback to cache
      return caches.match(request).then((cachedResponse) => {
        if (cachedResponse) {
          return cachedResponse
        }

        // Return offline response
        if (request.mode === 'navigate') {
          return caches.match('/offline.html')
        }

        return new Response(
          JSON.stringify({
            error: 'offline',
            message: 'Service temporarily unavailable'
          }),
          {
            status: 503,
            headers: new Headers({
              'Content-Type': 'application/json'
            })
          }
        )
      })
    })
  )
})

/**
 * Message event for cache management
 */
self.addEventListener('message', (event) => {
  if (event.data && event.data.type === 'SKIP_WAITING') {
    self.skipWaiting()
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
        cleanupExpiredCache(STATIC_CACHE, STATIC_CACHE_EXPIRY),
        cleanupExpiredCache(ANALYTICS_CACHE, ANALYTICS_CACHE_EXPIRY),
        cleanupExpiredCache(API_CACHE, API_CACHE_EXPIRY)
      ]).then(() => {
        event.ports[0]?.postMessage({ type: 'CLEANUP_COMPLETE' })
      })
    )
  }
})

// ==================================================================================
// Web Push Notifications (GH#4459)
// ==================================================================================

/**
 * Push event handler — shows a browser notification when the backend delivers
 * a Web Push message.  Expected payload shape:
 *   { title: string, body: string, url?: string, icon?: string }
 */
self.addEventListener('push', (event) => {
  if (!event.data) return

  let payload = { title: 'AutoBot', body: 'You have a new notification.', url: '/', icon: '/favicon.ico' }
  try {
    Object.assign(payload, event.data.json())
  } catch {
    payload.body = event.data.text() || payload.body
  }

  event.waitUntil(
    self.registration.showNotification(payload.title, {
      body: payload.body,
      icon: payload.icon || '/favicon.ico',
      badge: '/favicon.ico',
      data: { url: payload.url || '/' },
    })
  )
})

/**
 * Notification click handler — focuses the AutoBot tab (or opens a new one)
 * and navigates to the URL embedded in the notification data.
 */
self.addEventListener('notificationclick', (event) => {
  event.notification.close()

  const targetUrl = (event.notification.data && event.notification.data.url) || '/'

  event.waitUntil(
    clients
      .matchAll({ type: 'window', includeUncontrolled: true })
      .then((windowClients) => {
        // Re-use an existing AutoBot tab if one is open
        for (const client of windowClients) {
          if (new URL(client.url).origin === self.location.origin && 'focus' in client) {
            client.navigate(targetUrl)
            return client.focus()
          }
        }
        // Otherwise open a new tab
        if (clients.openWindow) {
          return clients.openWindow(targetUrl)
        }
      })
  )
})

// Log service worker activation
console.log('[AutoBot SW] Service Worker loaded with stale-while-revalidate strategy')
