import { createApp } from 'vue'
import { createPinia } from 'pinia'
import piniaPluginPersistedstate from 'pinia-plugin-persistedstate'
import App from './App.vue'
import router from './router/index'

import './assets/tailwind.css'
import './assets/vue-notus.css'
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

// Use plugins
app.use(pinia)
app.use(router)
app.use(rumPlugin)
app.use(errorHandlerPlugin)

// Global error handler for uncaught errors
app.config.errorHandler = (err, instance, info) => {
  console.error('[Vue Error Handler]', err, info)

  // Check if this is a chunk loading error
  if (err?.message?.includes('Loading chunk') ||
      err?.message?.includes('ChunkLoadError') ||
      err?.message?.includes('Loading CSS chunk')) {
    console.warn('[Vue Error Handler] Chunk loading error detected, initiating cache clear...')

    // Import and use cache management
    import('./utils/cacheManagement').then(({ handleChunkLoadingError }) => {
      handleChunkLoadingError(err as Error, instance?.$?.type?.name || 'Unknown')
    }).catch(cacheError => {
      console.error('[Vue Error Handler] Failed to handle chunk error:', cacheError)
      // Fallback to hard reload
      window.location.reload()
    })
  }
}

// Global warning handler
app.config.warnHandler = (msg, instance, trace) => {
  if (import.meta.env.DEV) {
    console.warn('[Vue Warning]', msg, trace)
  }
}

// Mount the app
app.mount('#app')

// Performance monitoring in development
if (import.meta.env.DEV) {
  console.log('[AutoBot Frontend] Application mounted successfully')
  console.log('[AutoBot Frontend] Vue DevTools should be available')

  // Import chunk testing utilities in development
  import('./utils/chunkTestUtility').then(chunkTest => {
    console.log('[AutoBot Frontend] Chunk testing utilities loaded')

    // Run quick validation to ensure fixes are working
    chunkTest.quickChunkValidation().then(passed => {
      if (passed) {
        console.log('[AutoBot Frontend] ✅ Chunk loading fixes validated successfully')
      } else {
        console.warn('[AutoBot Frontend] ⚠️ Chunk loading validation failed')
      }
    })

    // Make test utilities available globally for debugging
    if (typeof window !== 'undefined') {
      console.log('[AutoBot Frontend] Development tools available:')
      console.log('  - window.chunkTest.runComprehensive() - Run full chunk tests')
      console.log('  - window.chunkTest.quickValidation() - Quick validation')
      console.log('  - window.chunkTest.testComponents([...]) - Test specific components')
    }
  }).catch(error => {
    console.warn('[AutoBot Frontend] Failed to load chunk testing utilities:', error)
  })

  // Log chunk loading performance
  if ('performance' in window && window.performance.getEntriesByType) {
    setTimeout(() => {
      const resources = window.performance.getEntriesByType('resource')
      const chunks = resources.filter(r => r.name.includes('.js') && r.name.includes('/js/'))

      if (chunks.length > 0) {
        console.log('[AutoBot Frontend] Chunk loading performance:', {
          totalChunks: chunks.length,
          averageLoadTime: chunks.reduce((sum, chunk) => sum + chunk.duration, 0) / chunks.length,
          slowestChunk: chunks.reduce((slowest, chunk) =>
            chunk.duration > slowest.duration ? chunk : slowest
          )
        })
      } else {
        console.log('[AutoBot Frontend] Running in development mode - dynamic module loading')
      }

      // Test async component loading
      import('./utils/asyncComponentHelpers').then(({ AsyncComponentErrorRecovery }) => {
        const stats = AsyncComponentErrorRecovery.getStats()
        if (stats.failedCount > 0) {
          console.warn('[AutoBot Frontend] Detected failed async components:', stats)
        } else {
          console.log('[AutoBot Frontend] No async component failures detected')
        }
      })
    }, 3000)
  }
}