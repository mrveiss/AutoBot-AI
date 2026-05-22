import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'

export default defineConfig({
  plugins: [vue()],
  build: {
    lib: {
      entry: resolve(__dirname, 'index.ts'),
      name: 'AutobotTerminal',
      fileName: 'autobot-terminal',
      formats: ['es', 'cjs'],
    },
    rollupOptions: {
      external: ['vue', '@xterm/xterm', '@xterm/addon-fit', '@xterm/addon-web-links'],
      output: {
        globals: {
          vue: 'Vue',
        },
      },
    },
  },
})
