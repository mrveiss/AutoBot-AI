/**
 * Cache Management Utilities
 * Handles browser cache clearing, service worker updates, and chunk reloading
 */

import { createLogger } from '@/utils/debugUtils'
import { fetchWithAuth } from '@/utils/fetchWithAuth'

// Create scoped logger for cacheManagement
const logger = createLogger('cacheManagement')

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


  try {
    // Clear service worker cache
    if (clearServiceWorker && 'serviceWorker' in navigator) {

      const registrations = await navigator.serviceWorker.getRegistrations()
      await Promise.all(registrations.map(registration => {
        return registration.unregister()
      }))

      // Clear caches API if available
      if ('caches' in window) {
        const cacheNames = await caches.keys()
        await Promise.all(cacheNames.map(name => {
          return caches.delete(name)
        }))
      }
    }

    // Clear localStorage
    if (clearLocalStorage) {
      localStorage.clear()
    }

    // Clear sessionStorage
    if (clearSessionStorage) {
      sessionStorage.clear()
    }

    // Show notification
    if (showNotification) {
      showCacheUpdateNotification('Cache cleared successfully. Reloading page...')
    }


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
    logger.error('Error clearing cache:', error)

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
  logger.error('Chunk loading error detected:', {
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
 * Check for application updates and prompt user with safety checks
 */
export async function checkForUpdates(): Promise<boolean> {
  try {
    // Prevent reload loops by checking if we just reloaded
    const lastReloadTime = localStorage.getItem('last-auto-reload')
    const now = Date.now()
    const reloadCooldown = 30000 // 30 seconds minimum between auto-reloads

    if (lastReloadTime && (now - parseInt(lastReloadTime)) < reloadCooldown) {
      return false
    }


    // Check if build hash has changed
    // Issue #552: Fixed path - backend has /api/services/version
    const response = await fetchWithAuth('/api/services/version', {
      cache: 'no-cache',
      headers: {
        'Cache-Control': 'no-cache, no-store, must-revalidate'
      }
    })

    if (response.ok) {
      const { version, buildHash } = await response.json()
      const currentBuildHash = localStorage.getItem('app-build-hash')

      if (currentBuildHash && currentBuildHash !== buildHash) {

        // Check for unsaved changes before showing notification
        const hasUnsavedChanges = checkForUnsavedChanges()

        // Show subtle notification with safety measures
        showSubtleUpdateNotification(version, buildHash, hasUnsavedChanges)
        localStorage.setItem('app-build-hash', buildHash)
        return true
      } else {
        localStorage.setItem('app-build-hash', buildHash)
      }
    }

  } catch (error) {
    logger.warn('Could not check for updates:', error)
  }

  return false
}

/**
 * Check for unsaved changes in the application
 */
function checkForUnsavedChanges(): boolean {
  try {
    // Check for unsaved chat messages
    const chatInput = document.querySelector('textarea[placeholder*="message"], input[placeholder*="message"], .chat-input textarea, .chat-input input') as HTMLInputElement | HTMLTextAreaElement
    if (chatInput && chatInput.value.trim().length > 0) {
      return true
    }

    // Check for forms with changes
    const forms = document.querySelectorAll('form')
    for (const form of forms) {
      const formData = new FormData(form)
      for (const [, value] of formData.entries()) {
        if (typeof value === 'string' && value.trim().length > 0) {
          return true
        }
      }
    }

    // Check for contenteditable elements with content
    const editableElements = document.querySelectorAll('[contenteditable="true"]')
    for (const element of editableElements) {
      if (element.textContent && element.textContent.trim().length > 0) {
        return true
      }
    }

    // Check if any input has the 'dirty' class or data attribute
    const dirtyInputs = document.querySelectorAll('input.dirty, textarea.dirty, [data-dirty="true"]')
    if (dirtyInputs.length > 0) {
      return true
    }

    return false
  } catch (error) {
    logger.warn('Error checking for unsaved changes:', error)
    return false // Assume no changes if check fails
  }
}

/**
 * Show subtle update notification under logo (non-intrusive)
 */
export function showSubtleUpdateNotification(version: string, buildHash: string, hasUnsavedChanges: boolean = false) {
  // Remove any existing update notifications
  const existing = document.querySelectorAll('.subtle-update-notification')
  existing.forEach(el => el.remove())

  // Find the logo area or main header to place the notification under
  const logoArea = document.querySelector('.logo, .app-header, .header, [class*="logo"], [class*="header"]') ||
                   document.querySelector('nav, header') ||
                   document.querySelector('#app > div:first-child') ||
                   document.body

  const notification = document.createElement('div')
  notification.className = 'subtle-update-notification'

  // Different styling based on whether there are unsaved changes
  const backgroundColor = hasUnsavedChanges ? 'linear-gradient(135deg, #fef3cd 0%, #fff8e1 100%)' : 'linear-gradient(135deg, #e8f5e8 0%, #f0f9ff 100%)'
  const borderColor = hasUnsavedChanges ? '#f59e0b' : '#10b981'
  const textColor = hasUnsavedChanges ? '#92400e' : '#065f46'

  notification.style.cssText = `
    background: ${backgroundColor};
    border: 1px solid ${borderColor};
    border-radius: 6px;
    padding: 8px 12px;
    margin: 8px 0;
    font-size: 13px;
    color: ${textColor};
    text-align: center;
    box-shadow: 0 2px 4px rgba(16, 185, 129, 0.1);
    animation: slideDown 0.3s ease-out;
    position: relative;
    z-index: 1000;
  `

  // If there are unsaved changes, show warning without auto-reload
  if (hasUnsavedChanges) {
    notification.innerHTML = `
      <div style="display: flex; align-items: center; justify-content: center; gap: 8px;">
        <svg width="16" height="16" viewBox="0 0 20 20" fill="currentColor" style="color: #f59e0b;">
          <path fill-rule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clip-rule="evenodd" />
        </svg>
        <span>
          <strong>Update available</strong> - v${version}
          <br>
          <span style="font-size: 11px; opacity: 0.9;">
            ⚠️ Unsaved changes detected. Please save your work first.
            <button onclick="performSafeReload()" style="background: none; border: 1px solid #f59e0b; color: #f59e0b; border-radius: 3px; padding: 2px 6px; margin-left: 8px; font-size: 10px; cursor: pointer;">Refresh anyway</button>
          </span>
        </span>
      </div>
    `
  } else {
    // DISABLED AUTO-REFRESH - Manual refresh only to avoid interruptions during development
    notification.innerHTML = `
      <div style="display: flex; align-items: center; justify-content: center; gap: 8px;">
        <svg width="16" height="16" viewBox="0 0 20 20" fill="currentColor" style="color: #10b981;">
          <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd" />
        </svg>
        <span>
          <strong>Update available</strong> - v${version}
          <span style="font-size: 11px; opacity: 0.8; margin-left: 8px;">
            <button onclick="performSafeReload()" style="background: none; border: 1px solid #059669; color: #059669; border-radius: 3px; padding: 2px 6px; margin-left: 8px; font-size: 10px; cursor: pointer;">Refresh now</button>
            <button onclick="this.parentElement.parentElement.parentElement.parentElement.remove()" style="background: none; border: 1px solid #6b7280; color: #6b7280; border-radius: 3px; padding: 2px 6px; margin-left: 4px; font-size: 10px; cursor: pointer;">Dismiss</button>
          </span>
        </span>
      </div>
    `
  }

  // Add safe reload function to global scope
  (window as any).performSafeReload = () => {
    // Record reload time to prevent loops
    localStorage.setItem('last-auto-reload', Date.now().toString())
    location.reload()
  }

  // Add cancel function to global scope
  (window as any).cancelAutoReload = () => {
    const intervalId = notification.getAttribute('data-countdown-interval')
    if (intervalId) {
      clearInterval(parseInt(intervalId))
    }
    notification.remove()
  }

  // Add CSS animation if not already present
  if (!document.querySelector('#subtle-update-styles')) {
    const styles = document.createElement('style')
    styles.id = 'subtle-update-styles'
    styles.textContent = `
      @keyframes slideDown {
        from { transform: translateY(-10px); opacity: 0; }
        to { transform: translateY(0); opacity: 1; }
      }
    `
    document.head.appendChild(styles)
  }

  // Insert the notification in a logical place
  if (logoArea && logoArea !== document.body) {
    logoArea.parentNode?.insertBefore(notification, logoArea.nextSibling)
  } else {
    document.body.insertBefore(notification, document.body.firstChild)
  }

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
 * Show subtle error notification under logo (non-intrusive)
 * Replacement for intrusive SystemStatusNotification errors
 */
export function showSubtleErrorNotification(title: string, message: string, severity: 'error' | 'warning' | 'info' = 'error') {
  // Remove any existing error notifications
  const existing = document.querySelectorAll('.subtle-error-notification')
  existing.forEach(el => el.remove())

  // Find the logo area or main header to place the notification under
  const logoArea = document.querySelector('.logo, .app-header, .header, [class*="logo"], [class*="header"]') ||
                   document.querySelector('nav, header') ||
                   document.querySelector('#app > div:first-child') ||
                   document.body

  const notification = document.createElement('div')
  notification.className = 'subtle-error-notification'

  // Styling based on severity
  const backgroundColor = {
    'error': 'linear-gradient(135deg, #fef2f2 0%, #fef8f8 100%)',
    'warning': 'linear-gradient(135deg, #fef3cd 0%, #fff8e1 100%)',
    'info': 'linear-gradient(135deg, #eff6ff 0%, #f0f9ff 100%)'
  }[severity]

  const borderColor = {
    'error': '#ef4444',
    'warning': '#f59e0b',
    'info': '#3b82f6'
  }[severity]

  const textColor = {
    'error': '#dc2626',
    'warning': '#92400e',
    'info': '#1d4ed8'
  }[severity]

  const iconColor = {
    'error': '#ef4444',
    'warning': '#f59e0b',
    'info': '#3b82f6'
  }[severity]

  notification.style.cssText = `
    background: ${backgroundColor};
    border: 1px solid ${borderColor};
    border-radius: 6px;
    padding: 8px 12px;
    margin: 8px 0;
    font-size: 13px;
    color: ${textColor};
    text-align: left;
    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    animation: slideDown 0.3s ease-out;
    position: relative;
    z-index: 1000;
    max-width: 500px;
  `

  // Icon based on severity
  const iconSvg = {
    'error': `<path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clip-rule="evenodd" />`,
    'warning': `<path fill-rule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clip-rule="evenodd" />`,
    'info': `<path fill-rule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z" clip-rule="evenodd" />`
  }[severity]

  notification.innerHTML = `
    <div style="display: flex; align-items: flex-start; gap: 8px;">
      <svg width="16" height="16" viewBox="0 0 20 20" fill="currentColor" style="color: ${iconColor}; flex-shrink: 0; margin-top: 2px;">
        ${iconSvg}
      </svg>
      <div style="flex-grow: 1; min-width: 0;">
        <div style="font-weight: 600; margin-bottom: 2px;">${title}</div>
        <div style="font-size: 12px; opacity: 0.9; line-height: 1.4;">${message}</div>
      </div>
      <button
        onclick="this.parentElement.parentElement.remove()"
        style="background: none; border: none; color: ${textColor}; opacity: 0.7; cursor: pointer; font-size: 16px; padding: 2px; line-height: 1; flex-shrink: 0;"
        title="Dismiss"
      >×</button>
    </div>
  `

  // Add CSS animation if not already present
  if (!document.querySelector('#subtle-error-styles')) {
    const styles = document.createElement('style')
    styles.id = 'subtle-error-styles'
    styles.textContent = `
      @keyframes slideDown {
        from { transform: translateY(-10px); opacity: 0; }
        to { transform: translateY(0); opacity: 1; }
      }
      .subtle-error-notification:hover {
        box-shadow: 0 4px 8px rgba(0,0,0,0.15);
      }
    `
    document.head.appendChild(styles)
  }

  // Insert the notification in a logical place
  if (logoArea && logoArea !== document.body) {
    logoArea.parentNode?.insertBefore(notification, logoArea.nextSibling)
  } else {
    document.body.insertBefore(notification, document.body.firstChild)
  }

  // Auto-hide after delay based on severity
  const autoHideDelay = {
    'error': 8000, // Errors stay longer
    'warning': 6000,
    'info': 4000
  }[severity]

  setTimeout(() => {
    if (notification.parentNode) {
      notification.style.animation = 'slideDown 0.3s ease-out reverse'
      setTimeout(() => notification.remove(), 300)
    }
  }, autoHideDelay)

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

      logger.warn('Global chunk loading failure detected:', error)

      // Prevent default error handling
      event.preventDefault()

      // Handle the error
      try {
        await handleChunkLoadingError(error)
      } catch (handlingError) {
        logger.error('Error handling chunk failure:', handlingError)
        // Fallback to hard reload
        window.location.reload()
      }
    }
  })

  // Handle script loading errors
  window.addEventListener('error', async (event) => {
    const target = event.target as HTMLScriptElement | HTMLLinkElement

    if (target && (target.tagName === 'SCRIPT' || target.tagName === 'LINK')) {
      const url = target.tagName === 'LINK'
        ? (target as HTMLLinkElement).href
        : (target as HTMLScriptElement).src

      logger.warn('Resource loading error detected:', {
        url: url,
        type: target.tagName
      })

      // Check if this looks like a chunk loading error
      if (url?.includes('/js/') || url?.includes('chunk')) {

        try {
          await handleChunkLoadingError(new Error(`Failed to load resource: ${url}`))
        } catch (handlingError) {
          logger.error('Error handling resource failure:', handlingError)
          window.location.reload()
        }
      }
    }
  }, true)

}

/**
 * Initialize cache management on app startup
 */
export function initializeCacheManagement() {
  setupGlobalChunkErrorHandlers()

  // Check for updates with subtle notifications (non-intrusive)
  setTimeout(() => {
    checkForUpdates()
  }, 2000)


}
