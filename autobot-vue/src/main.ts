import { createApp } from 'vue'
import App from './App.vue'
import router from './router'

import './assets/tailwind.css'
import './assets/vue-notus.css'

// Import RUM agent for development monitoring
import rumPlugin from './plugins/rum'

// Import RUM console helper for development
if (import.meta.env.DEV) {
  import('./utils/RumConsoleHelper')
}

const app = createApp(App)
app.use(router)

// Install RUM plugin for development monitoring
app.use(rumPlugin, { router })

app.mount('#app')
