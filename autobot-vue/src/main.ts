import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './router/index'

import './assets/tailwind.css'
import './assets/vue-notus.css'

// Import plugins
import rumPlugin from './plugins/rum'
import errorHandlerPlugin from './plugins/errorHandler'

// Import global services
import './services/GlobalWebSocketService.js'

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

app.use(pinia)
app.use(router)

// Install plugins in order: RUM first, then error handler
app.use(rumPlugin, { router })
app.use(errorHandlerPlugin)

app.mount('#app')
