// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

import { setup, type Preview } from '@storybook/vue3'
import { createPinia } from 'pinia'
import { createRouter, createMemoryHistory } from 'vue-router'
import '../src/assets/styles/main.css'

const pinia = createPinia()
const router = createRouter({ history: createMemoryHistory(), routes: [] })

// Stories mount components that call useXStore()/useRouter(); give every story
// app the same Pinia and router, which were created here but never installed.
setup((app) => {
  app.use(pinia)
  app.use(router)
})

const preview: Preview = {
  decorators: [
    (story) => ({
      components: { story },
      setup() {
        return {}
      },
      template: '<story />',
    }),
  ],
  parameters: {
    controls: {
      matchers: {
        color: /(background|color)$/i,
        date: /Date$/i,
      },
    },
  },
}

export default preview
