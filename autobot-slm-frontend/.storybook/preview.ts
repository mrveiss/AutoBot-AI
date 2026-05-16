// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

import type { Preview } from '@storybook/vue3'
import { createPinia } from 'pinia'
import { createRouter, createMemoryHistory } from 'vue-router'
import '../src/assets/styles/main.css'

const pinia = createPinia()
const router = createRouter({ history: createMemoryHistory(), routes: [] })

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
