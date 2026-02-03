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

// Import CSS Design System (Issue #704) - SSOT for all design tokens
// This provides centralized theming with dark/light mode support
import './assets/css/index.css'

// Import legacy theme system (Issue #548) - will be migrated to design system
import './assets/styles/theme.css'
import './assets/styles/view.css'

// Initialize theme early to prevent flash of unstyled content
import { initializeTheme } from '@/composables/useTheme'
initializeTheme()
// Import xterm CSS globally to avoid dependency resolution issues
import '@xterm/xterm/css/xterm.css'

// Import plugins
import rumPlugin from './plugins/rum'
import errorHandlerPlugin from './plugins/errorHandler'

// Import global services
import './services/GlobalWebSocketService.js'

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
app.use(router)

// Install RUM plugin for development monitoring
app.use(rumPlugin, { router })

// Use plugins
app.use(pinia)
app.use(router)
app.use(rumPlugin)
app.use(errorHandlerPlugin)

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