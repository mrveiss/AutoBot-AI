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

// Clean up any recovery parameters from URL on app start
if (typeof window !== 'undefined') {
  const url = new URL(window.location.href)
  if (url.searchParams.has('_recovery') || url.searchParams.has('_router_recovery')) {
    url.searchParams.delete('_recovery')
    url.searchParams.delete('_router_recovery')
    window.history.replaceState({}, document.title, url.toString())
  }
}

// Import development and diagnostic tools
if (import.meta.env.DEV) {
  import('./utils/RumConsoleHelper')

  // PERFORMANCE OPTIMIZATION & DEBUGGING: Load API diagnostic tools
  import('./utils/ApiEndpointMapper').then(() => {
    console.log('✅ API Endpoint Mapper loaded');
  });

  import('./utils/ApiDiagnostics').then(() => {
    console.log('✅ API Diagnostics tools loaded');
    console.log('🔧 Use window.runApiDiagnostics() to test API connectivity');
    console.log('🔧 Use window.quickApiHealth() for quick health check');
  });
}

const app = createApp(App)
const pinia = createPinia()

// Configure pinia persistence plugin
pinia.use(piniaPluginPersistedstate)

app.use(pinia)
app.use(router)

// Install plugins in order: RUM first, then error handler
app.use(rumPlugin, { router })
app.use(errorHandlerPlugin)

app.mount('#app')
