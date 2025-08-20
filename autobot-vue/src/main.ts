import { createApp } from 'vue'
import App from './App.vue'
import router from './router'

import './assets/tailwind.css'
import './assets/vue-notus.css'

// Import plugins
import rumPlugin from './plugins/rum'
import errorHandlerPlugin from './plugins/errorHandler'

// Import RUM console helper for development
if (import.meta.env.DEV) {
  import('./utils/RumConsoleHelper')
}

const app = createApp(App)
app.use(router)

// Install plugins in order: RUM first, then error handler
app.use(rumPlugin, { router })
app.use(errorHandlerPlugin)

app.mount('#app')
