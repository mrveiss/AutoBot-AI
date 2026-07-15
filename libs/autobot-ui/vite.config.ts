// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'

export default defineConfig({
  plugins: [vue()],
  build: {
    lib: {
      entry: resolve(__dirname, 'index.ts'),
      name: 'AutobotUi',
      fileName: 'autobot-ui',
      formats: ['es', 'cjs'],
    },
    rollupOptions: {
      // vue is provided by the consuming app; never bundle it.
      external: ['vue'],
      output: {
        globals: {
          vue: 'Vue',
        },
      },
    },
  },
})
