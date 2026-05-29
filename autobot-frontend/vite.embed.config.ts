/**
 * Vite config for the standalone embed.js chat widget.
 *
 * Produces a single self-contained IIFE bundle:
 *   dist-embed/embed.js   (~80-120 kB gzipped, includes Vue 3 runtime)
 *
 * Usage in host pages:
 *   <script src="https://your-cdn.example.com/embed.js"
 *           data-api-url="https://autobot.example.com"
 *           data-org-id="acme"></script>
 */

import { fileURLToPath, URL } from 'node:url'
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    preserveSymlinks: true,
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
      'vue': 'vue/dist/vue.esm-bundler.js',
    },
  },
  define: {
    // Silence Vue feature flags in the bundle
    __VUE_OPTIONS_API__: 'false',
    __VUE_PROD_DEVTOOLS__: 'false',
    __VUE_PROD_HYDRATION_MISMATCH_DETAILS__: 'false',
  },
  build: {
    outDir: 'dist-embed',
    emptyOutDir: true,
    lib: {
      entry: fileURLToPath(new URL('./src/embed/embed-entry.ts', import.meta.url)),
      name: 'AutobotEmbed',
      formats: ['iife'],
      fileName: () => 'embed.js',
    },
    rollupOptions: {
      // Bundle everything — no external deps; host pages have nothing
      external: [],
      output: {
        // Single file, no chunks
        inlineDynamicImports: true,
      },
    },
    cssCodeSplit: false,
    minify: 'esbuild',
    sourcemap: false,
    target: 'es2018',
  },
})
