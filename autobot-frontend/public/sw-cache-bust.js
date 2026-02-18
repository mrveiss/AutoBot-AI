// AutoBot Service Worker for Cache Management
// Aggressive cache invalidation to prevent API configuration issues

const _CACHE_NAME = 'autobot-v1'; // Prefixed with _ to indicate intentionally unused (reserved for future use)
const CACHE_VERSION = Date.now();
const DYNAMIC_CACHE = `autobot-dynamic-${CACHE_VERSION}`;

// Assets to never cache (API configs, dynamic content)
const NEVER_CACHE = [
  '/api/',
  '/ws',
  '/config/',
  '.json',
  'environment.js',
  'api.js'
];

// Assets to cache with version control
const CACHE_ASSETS = [
  '/',
  '/index.html',
  '/assets/',
  '/js/',
  '/css/'
];

// Install event - clean up old caches
self.addEventListener('install', (event) => {
  console.log('[AutoBot SW] Installing service worker with cache version:', CACHE_VERSION);

  event.waitUntil(
    Promise.all([
      // Clear all existing caches
      caches.keys().then((cacheNames) => {
        return Promise.all(
          cacheNames
            .filter(cacheName => cacheName.startsWith('autobot-'))
            .map(cacheName => {
              console.log('[AutoBot SW] Deleting old cache:', cacheName);
              return caches.delete(cacheName);
            })
        );
      }),
      // Skip waiting to activate immediately
      self.skipWaiting()
    ])
  );
});

// Activate event - claim clients immediately
self.addEventListener('activate', (event) => {
  console.log('[AutoBot SW] Activating service worker');

  event.waitUntil(
    Promise.all([
      // Clean up any remaining old caches
      caches.keys().then((cacheNames) => {
        return Promise.all(
          cacheNames
            .filter(cacheName => !cacheName.includes(CACHE_VERSION))
            .map(cacheName => caches.delete(cacheName))
        );
      }),
      // Take control of all clients immediately
      self.clients.claim()
    ])
  );
});

// Fetch event - aggressive no-cache policy for API configs
self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);

  // Never cache API calls, configs, or dynamic content
  const shouldNeverCache = NEVER_CACHE.some(pattern =>
    url.pathname.includes(pattern)
  );

  if (shouldNeverCache) {
    console.log('[AutoBot SW] Never cache:', url.pathname);

    // Force fresh request with cache-busting headers
    // Issue #674: Only include body for methods that support it (not GET/HEAD)
    const requestInit = {
      method: event.request.method,
      headers: new Headers({
        ...event.request.headers,
        'Cache-Control': 'no-cache, no-store, must-revalidate',
        'Pragma': 'no-cache',
        'X-Cache-Bust': Date.now().toString()
      }),
      mode: event.request.mode,
      credentials: event.request.credentials,
      cache: 'no-store'
    };

    // Only add body for methods that support it (POST, PUT, PATCH, DELETE)
    if (!['GET', 'HEAD'].includes(event.request.method)) {
      requestInit.body = event.request.body;
    }

    const freshRequest = new Request(event.request.url, requestInit);

    event.respondWith(
      fetch(freshRequest).then(response => {
        // Ensure response has no-cache headers
        const responseHeaders = new Headers(response.headers);
        responseHeaders.set('Cache-Control', 'no-cache, no-store, must-revalidate');
        responseHeaders.set('Pragma', 'no-cache');
        responseHeaders.set('Expires', '0');

        return new Response(response.body, {
          status: response.status,
          statusText: response.statusText,
          headers: responseHeaders
        });
      }).catch(error => {
        console.error('[AutoBot SW] Fetch failed for never-cache resource:', error);
        return new Response('Network error', { status: 503 });
      })
    );
    return;
  }

  // For cacheable assets, use cache-first with version control
  if (CACHE_ASSETS.some(pattern => url.pathname.startsWith(pattern))) {
    event.respondWith(
      caches.open(DYNAMIC_CACHE).then(cache => {
        return cache.match(event.request).then(response => {
          if (response) {
            // Check if cached version is recent (less than 5 minutes old)
            const cachedTime = response.headers.get('x-cached-time');
            const now = Date.now();
            const maxAge = 5 * 60 * 1000; // 5 minutes

            if (cachedTime && (now - parseInt(cachedTime)) < maxAge) {
              console.log('[AutoBot SW] Serving from cache:', url.pathname);
              return response;
            }
          }

          // Fetch fresh version
          return fetch(event.request).then(fetchResponse => {
            if (fetchResponse.ok) {
              // Add timestamp to response for cache validation
              const responseHeaders = new Headers(fetchResponse.headers);
              responseHeaders.set('x-cached-time', Date.now().toString());

              const responseToCache = new Response(fetchResponse.body, {
                status: fetchResponse.status,
                statusText: fetchResponse.statusText,
                headers: responseHeaders
              });

              // Cache the response
              cache.put(event.request, responseToCache.clone());
              console.log('[AutoBot SW] Cached fresh resource:', url.pathname);

              return responseToCache;
            }
            return fetchResponse;
          });
        });
      })
    );
    return;
  }

  // Default: pass through without caching
  event.respondWith(fetch(event.request));
});

// Message handling for manual cache clearing
self.addEventListener('message', (event) => {
  if (event.data && event.data.type === 'CLEAR_CACHE') {
    console.log('[AutoBot SW] Manual cache clear requested');

    event.waitUntil(
      caches.keys().then((cacheNames) => {
        return Promise.all(
          cacheNames
            .filter(cacheName => cacheName.startsWith('autobot-'))
            .map(cacheName => caches.delete(cacheName))
        );
      }).then(() => {
        console.log('[AutoBot SW] All caches cleared');
        event.ports[0].postMessage({ success: true });
      })
    );
  }

  if (event.data && event.data.type === 'SKIP_WAITING') {
    self.skipWaiting();
  }
});

// Error handling
self.addEventListener('error', (error) => {
  console.error('[AutoBot SW] Service worker error:', error);
});

self.addEventListener('unhandledrejection', (event) => {
  console.error('[AutoBot SW] Unhandled promise rejection:', event.reason);
});

console.log('[AutoBot SW] Service worker loaded with cache version:', CACHE_VERSION);
