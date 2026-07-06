// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import { createApp } from 'vue'
import { createPinia } from 'pinia'
import piniaPluginPersistedstate from 'pinia-plugin-persistedstate'
import App from './App.vue'
import router from './router/index'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('main');

import './assets/tailwind.css'
import './assets/vue-notus.css'
// Import fonts from local npm packages (avoid CDN tracking prevention warnings)
import '@fortawesome/fontawesome-free/css/all.min.css'
// Import only latin subset with weights actually used (400, 500, 600, 700)
import '@fontsource/inter/latin-400.css'
import '@fontsource/inter/latin-500.css'
import '@fontsource/inter/latin-600.css'
import '@fontsource/inter/latin-700.css'

// Import legacy theme system (Issue #548) - loaded BEFORE design system so tokens win
import './assets/styles/theme.css'
import './assets/styles/view.css'

// Import CSS Design System (Issue #704/#901) - SSOT - must come AFTER legacy to override
import './assets/css/index.css'

// Interaction polish — shell press feedback + stronger easing (#10488 B2)
import './assets/css/interaction-polish.css'

// Global reset (* { margin:0; padding:0; box-sizing:border-box }, body { margin:0;
// min-height:100vh }) — must load AFTER vue-notus and component packages so their
// leaked unscoped body{padding...} rules can't push the layout off-viewport.
// Without this, the page does not fill the viewport and views without
// .view-container don't scroll properly.
import './assets/base.css'

// @autobot/ui shared kit: token contract fallbacks first, then this app's
// adapter (mapping --aui-* onto the app's own design tokens). Loaded AFTER
// the app design-system CSS above so the tokens the adapter references are
// already defined (#10750 C2c, #10860 Task-C).
import '@autobot/ui/tokens'
import './assets/aui-theme.css'

// Initialize theme early to prevent flash of unstyled content
import { initializeTheme } from '@/composables/useTheme'
initializeTheme()
import { initializeThemeVariant } from '@/composables/useThemeVariant'
initializeThemeVariant()
// Import xterm CSS globally to avoid dependency resolution issues
import '@xterm/xterm/css/xterm.css'

// Import i18n
import i18n from './i18n'

// Import plugins
import rumPlugin from './plugins/rum'
import errorHandlerPlugin from './plugins/errorHandler'
import ApiPlugin from './plugins/api'
import { mountAllPlugins } from '@/plugins/registry'

// Import global services
import './services/GlobalWebSocketService'
import './services/LiveEventService'

// Import async component error handling setup
import { setupAsyncComponentErrorHandler } from './utils/asyncComponentHelpers'

// Import cache management system
import { initializeCacheManagement } from './utils/cacheManagement'

// Initialize async component error handling
setupAsyncComponentErrorHandler()

// Initialize cache management system (includes chunk error handlers)
initializeCacheManagement()

// Clean up any recovery parameters from URL on app start
if (typeof window !== 'undefined') {
  const url = new URL(window.location.href)
  if (url.searchParams.has('_recovery') || url.searchParams.has('_router_recovery')) {
    url.searchParams.delete('_recovery')
    url.searchParams.delete('_router_recovery')
    url.searchParams.delete('_cb') // Also clean up cache-busting parameter
    window.history.replaceState({}, '', url.toString())
  }
}

// Create Pinia store with persistence
const pinia = createPinia()
pinia.use(piniaPluginPersistedstate)

// Create Vue app
const app = createApp(App)

// Use plugins
app.use(pinia)
app.use(i18n)
app.use(router)
app.use(rumPlugin, { router })
app.use(errorHandlerPlugin)
app.use(ApiPlugin)

// Register plugin UI components from the plugin mount registry (#6972 / #7793)
mountAllPlugins(app)

// Global error handler for uncaught errors
app.config.errorHandler = (err, _instance, info) => {
  logger.error('Vue Error Handler:', { error: err, info })

  // Check if this is a chunk loading error
  const error = err as Error
  if (error?.message?.includes('Loading chunk') ||
      error?.message?.includes('ChunkLoadError') ||
      error?.message?.includes('Loading CSS chunk')) {
    logger.warn('Chunk loading error detected, initiating cache clear...')

    // Import and use cache management
    import('./utils/cacheManagement').then(({ handleChunkLoadingError }) => {
      handleChunkLoadingError(error, _instance?.$?.type?.name || 'Unknown')
    }).catch(cacheError => {
      logger.error('Failed to handle chunk error:', cacheError)
      // Fallback to hard reload
      window.location.reload()
    })
  }
}

// Global warning handler
app.config.warnHandler = (msg, _instance, trace) => {
  if (import.meta.env.DEV) {
    logger.warn('Vue Warning:', { message: msg, trace })
  }
}

// Mount the app
app.mount('#app')

// Register Service Worker for caching strategy (Issue #4015, #4041, #3275)
// #6767: Skip registration on IP-based hosts (172.x, 10.x, 192.168.x, bare-IP) — these
// deployments almost always use self-signed TLS.  Chrome emits an unrecoverable
// SecurityError *before* our catch block, polluting the console with a red error.
// Proactively gating on hostname prevents the attempt entirely.  Localhost is
// explicitly allowed because it is a secure context even without HTTPS.
const _swHostIsIp = window.location.hostname !== 'localhost' &&
  /^(\d{1,3}\.){3}\d{1,3}$/.test(window.location.hostname)

if ('serviceWorker' in navigator && !_swHostIsIp) {
  window.addEventListener('load', async () => {
    try {
      // Register the service worker with stale-while-revalidate strategy (Issue #4015)
      const registration = await navigator.serviceWorker.register(
        '/service-worker.js' + (import.meta.env.DEV ? '' : `?v=${Date.now()}`),
        { scope: '/' }
      )

      logger.debug('Service Worker registered successfully', {
        scope: registration.scope,
        updateViaCache: registration.updateViaCache
      })

      // Check for updates periodically
      setInterval(() => {
        registration.update().catch(err => {
          logger.warn('Service Worker update check failed:', err)
        })
      }, 60000) // Check every minute

      // Handle Service Worker state changes
      registration.addEventListener('updatefound', () => {
        const newWorker = registration.installing
        if (newWorker) {
          newWorker.addEventListener('statechange', () => {
            if (
              newWorker.state === 'installed' &&
              navigator.serviceWorker.controller
            ) {
              logger.info('New Service Worker available - user update prompt can be shown')
              // You can show a prompt to user to refresh the page here
            }
          })
        }
      })
    } catch (error) {
      // Service Worker is optional — app works fine without it.
      // #6790: SecurityError on self-signed cert deploys is expected and not
      // actionable for users; surface it at debug only. Other failures
      // (network, syntax, scope) are still real → warn.
      const isCertError =
        error instanceof Error &&
        error.name === 'SecurityError' &&
        /SSL certificate/i.test(error.message)
      if (isCertError) {
        logger.debug('Service Worker registration skipped (untrusted cert)')
      } else {
        logger.warn('Service Worker registration failed:', error)
      }
    }
  })
} else if (_swHostIsIp) {
  logger.debug('Service Worker skipped (IP-based host — likely self-signed TLS; #6767)')
}

// Performance monitoring in development
if (import.meta.env.DEV) {
  logger.debug('Application mounted successfully')
  logger.debug('Vue DevTools should be available')

  // Import chunk testing utilities in development
  import('./utils/chunkTestUtility').then(chunkTest => {
    logger.debug('Chunk testing utilities loaded')

    // Run quick validation to ensure fixes are working
    chunkTest.quickChunkValidation().then(passed => {
      if (passed) {
        logger.debug('✅ Chunk loading fixes validated successfully')
      } else {
        logger.warn('⚠️ Chunk loading validation failed')
      }
    })

    // Make test utilities available globally for debugging
    if (typeof window !== 'undefined') {
      logger.debug('Development tools available:')
      logger.debug('  - window.chunkTest.runComprehensive() - Run full chunk tests')
      logger.debug('  - window.chunkTest.quickValidation() - Quick validation')
      logger.debug('  - window.chunkTest.testComponents([...]) - Test specific components')
    }
  }).catch(error => {
    logger.warn('Failed to load chunk testing utilities:', error)
  })

  // Log chunk loading performance
  if ('performance' in window && window.performance.getEntriesByType) {
    setTimeout(() => {
      const resources = window.performance.getEntriesByType('resource')
      const chunks = resources.filter(r => r.name.includes('.js') && r.name.includes('/js/'))

      if (chunks.length > 0) {
        logger.debug('Chunk loading performance:', {
          totalChunks: chunks.length,
          averageLoadTime: chunks.reduce((sum, chunk) => sum + chunk.duration, 0) / chunks.length,
          slowestChunk: chunks.reduce((slowest, chunk) =>
            chunk.duration > slowest.duration ? chunk : slowest
          )
        })
      } else {
        logger.debug('Running in development mode - dynamic module loading')
      }

      // Test async component loading
      import('./utils/asyncComponentHelpers').then(({ AsyncComponentErrorRecovery }) => {
        const stats = AsyncComponentErrorRecovery.getStats()
        if (stats.failedCount > 0) {
          logger.warn('Detected failed async components:', stats)
        } else {
          logger.debug('No async component failures detected')
        }
      })
    }, 3000)
  }
}
