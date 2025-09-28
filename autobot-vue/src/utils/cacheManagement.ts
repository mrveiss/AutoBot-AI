/**
 * Cache Management Utilities
 * Handles browser cache clearing, service worker updates, and chunk reloading
 */

export interface CacheManagementOptions {
  /** Force hard reload without cache */
  hardReload?: boolean
  /** Clear service worker cache */
  clearServiceWorker?: boolean
  /** Clear localStorage */
  clearLocalStorage?: boolean
  /** Clear sessionStorage */
  clearSessionStorage?: boolean
  /** Show user notification */
  showNotification?: boolean
}

/**
 * Clear various browser caches and storage
 */
export async function clearApplicationCache(options: CacheManagementOptions = {}) {
  const {
    hardReload = false,
    clearServiceWorker = true,
    clearLocalStorage = false,
    clearSessionStorage = false,
    showNotification = true
  } = options

  console.log('[CacheManagement] Starting cache clearing process...', options)

  try {
    // Clear service worker cache
    if (clearServiceWorker && 'serviceWorker' in navigator) {
      console.log('[CacheManagement] Clearing service worker cache...')

      const registrations = await navigator.serviceWorker.getRegistrations()
      await Promise.all(registrations.map(registration => {
        console.log('[CacheManagement] Unregistering service worker:', registration.scope)
        return registration.unregister()
      }))

      // Clear caches API if available
      if ('caches' in window) {
        const cacheNames = await caches.keys()
        await Promise.all(cacheNames.map(name => {
          console.log('[CacheManagement] Deleting cache:', name)
          return caches.delete(name)
        }))
      }
    }

    // Clear localStorage
    if (clearLocalStorage) {
      console.log('[CacheManagement] Clearing localStorage...')
      localStorage.clear()
    }

    // Clear sessionStorage
    if (clearSessionStorage) {
      console.log('[CacheManagement] Clearing sessionStorage...')
      sessionStorage.clear()
    }

    // Show notification
    if (showNotification) {
      showCacheUpdateNotification('Cache cleared successfully. Reloading page...')
    }

    console.log('[CacheManagement] Cache clearing completed')

    // Reload page
    if (hardReload) {
      // Force hard reload
      window.location.reload()
    } else {
      // Soft reload with cache busting
      const url = new URL(window.location.href)
      url.searchParams.set('_cb', Date.now().toString())
      window.location.href = url.toString()
    }

  } catch (error) {
    console.error('[CacheManagement] Error clearing cache:', error)

    if (showNotification) {
      showCacheUpdateNotification('Cache clearing failed. Performing hard reload...', 'error')
    }

    // Fallback to hard reload
    window.location.reload()
  }
}

/**
 * Handle chunk loading errors by clearing cache and retrying
 */
export async function handleChunkLoadingError(error: Error, componentName?: string) {
  console.error('[CacheManagement] Chunk loading error detected:', {
    error: error.message,
    component: componentName,
    stack: error.stack
  })

  // Check if this is a chunk loading error
  const isChunkError = error.message?.includes('Loading chunk') ||
                       error.message?.includes('ChunkLoadError') ||
                       error.message?.includes('Loading CSS chunk') ||
                       error.message?.includes('Failed to fetch')

  if (isChunkError) {
    console.log('[CacheManagement] Handling chunk loading error...')

    showCacheUpdateNotification(
      'Application files need to be updated. Refreshing page...',
      'warning'
    )

    // Clear cache and reload
    await clearApplicationCache({
      hardReload: true,
      clearServiceWorker: true,
      showNotification: false
    })
  } else {
    // Re-throw non-chunk errors
    throw error
  }
}

/**
 * Check for application updates and prompt user
 */
export async function checkForUpdates(): Promise<boolean> {
  try {
    console.log('[CacheManagement] Checking for updates...')

    // Check if build hash has changed
    const response = await fetch('/api/version', {
      cache: 'no-cache',
      headers: {
        'Cache-Control': 'no-cache, no-store, must-revalidate'
      }
    })

    if (response.ok) {
      const { version, buildHash } = await response.json()
      const currentBuildHash = localStorage.getItem('app-build-hash')

      if (currentBuildHash && currentBuildHash !== buildHash) {
        console.log('[CacheManagement] New version detected:', { version, buildHash })

        const shouldUpdate = confirm(
          'A new version of the application is available. Would you like to update now?'
        )

        if (shouldUpdate) {
          localStorage.setItem('app-build-hash', buildHash)
          await clearApplicationCache({ hardReload: true })
          return true
        }
      } else {
        localStorage.setItem('app-build-hash', buildHash)
      }
    }

  } catch (error) {
    console.warn('[CacheManagement] Could not check for updates:', error)
  }

  return false
}

/**
 * Show cache update notification to user
 */
export function showCacheUpdateNotification(message: string, type: 'info' | 'warning' | 'error' = 'info') {
  // Remove existing notifications
  const existing = document.querySelectorAll('.cache-notification')
  existing.forEach(el => el.remove())

  const notification = document.createElement('div')
  notification.className = 'cache-notification'

  const bgColor = {
    info: '#e3f2fd',
    warning: '#fff8e1',
    error: '#ffebee'
  }[type]

  const borderColor = {
    info: '#2196f3',
    warning: '#ff9800',
    error: '#f44336'
  }[type]

  const textColor = {
    info: '#1565c0',
    warning: '#e65100',
    error: '#c62828'
  }[type]

  notification.style.cssText = `
    position: fixed;
    top: 20px;
    right: 20px;
    background: ${bgColor};
    border: 2px solid ${borderColor};
    color: ${textColor};
    padding: 1rem 1.5rem;
    border-radius: 8px;
    box-shadow: 0 4px 12px rgba(0,0,0,0.15);
    z-index: 10000;
    max-width: 350px;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    font-size: 14px;
    line-height: 1.4;
    animation: slideIn 0.3s ease-out;
  `

  notification.innerHTML = `
    <div style="display: flex; align-items: center; gap: 8px;">
      <i class="fas fa-sync-alt" style="animation: spin 1s linear infinite;"></i>
      ${message}
    </div>
  `

  // Add CSS animation
  if (!document.querySelector('#cache-notification-styles')) {
    const styles = document.createElement('style')
    styles.id = 'cache-notification-styles'
    styles.textContent = `
      @keyframes slideIn {
        from { transform: translateX(100%); opacity: 0; }
        to { transform: translateX(0); opacity: 1; }
      }
      @keyframes spin {
        from { transform: rotate(0deg); }
        to { transform: rotate(360deg); }
      }
    `
    document.head.appendChild(styles)
  }

  document.body.appendChild(notification)

  // Auto-remove after 5 seconds
  setTimeout(() => {
    if (notification.parentNode) {
      notification.style.animation = 'slideIn 0.3s ease-out reverse'
      setTimeout(() => notification.remove(), 300)
    }
  }, 5000)
}

/**
 * Setup global error handlers for chunk loading failures
 */
export function setupGlobalChunkErrorHandlers() {
  // Handle unhandled promise rejections (chunk loading failures)
  window.addEventListener('unhandledrejection', async (event) => {
    const error = event.reason

    if (error?.message?.includes('Loading chunk') ||
        error?.message?.includes('ChunkLoadError') ||
        error?.message?.includes('Loading CSS chunk')) {

      console.warn('[CacheManagement] Global chunk loading failure detected:', error)

      // Prevent default error handling
      event.preventDefault()

      // Handle the error
      try {
        await handleChunkLoadingError(error)
      } catch (handlingError) {
        console.error('[CacheManagement] Error handling chunk failure:', handlingError)
        // Fallback to hard reload
        window.location.reload()
      }
    }
  })

  // Handle script loading errors
  window.addEventListener('error', async (event) => {
    const target = event.target as HTMLScriptElement | HTMLLinkElement

    if (target && (target.tagName === 'SCRIPT' || target.tagName === 'LINK')) {
      console.warn('[CacheManagement] Resource loading error detected:', {
        url: target.href || (target as HTMLScriptElement).src,
        type: target.tagName
      })

      // Check if this looks like a chunk loading error
      const url = target.href || (target as HTMLScriptElement).src
      if (url?.includes('/js/') || url?.includes('chunk')) {
        console.log('[CacheManagement] Chunk resource loading failure, clearing cache...')

        try {
          await handleChunkLoadingError(new Error(`Failed to load resource: ${url}`))
        } catch (handlingError) {
          console.error('[CacheManagement] Error handling resource failure:', handlingError)
          window.location.reload()
        }
      }
    }
  }, true)

  console.log('[CacheManagement] Global chunk error handlers initialized')
}

/**
 * Initialize cache management on app startup
 */
export function initializeCacheManagement() {
  setupGlobalChunkErrorHandlers()

  // Check for updates on app start
  setTimeout(() => {
    checkForUpdates()
  }, 2000)

  console.log('[CacheManagement] Cache management initialized')
}