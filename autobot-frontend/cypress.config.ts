import { defineConfig } from 'cypress'

// Frontend URL configuration (matches NetworkConstants.FRONTEND_PORT = 5173)
// Environment variable: CYPRESS_BASE_URL
const FRONTEND_URL = process.env.CYPRESS_BASE_URL || 'http://localhost:5173'

export default defineConfig({
  e2e: {
    specPattern: 'cypress/e2e/**/*.{cy,spec}.{js,jsx,ts,tsx}',
    baseUrl: FRONTEND_URL,
    setupNodeEvents(_on, _config) {
      // implement node event listeners here
    },
  },
  component: {
    devServer: {
      framework: 'vue',
      bundler: 'vite',
    },
  },
})
