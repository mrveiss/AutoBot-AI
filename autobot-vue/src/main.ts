import { createApp } from 'vue'
import App from './App.vue'
import router from './router'

import './assets/tailwind.css'
import './assets/vue-notus.css'

// Import plugins
import rumPlugin from './plugins/rum'
import errorHandlerPlugin from './plugins/errorHandler'

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
app.use(router)

// Install plugins in order: RUM first, then error handler
app.use(rumPlugin, { router })
app.use(errorHandlerPlugin)

app.mount('#app')
