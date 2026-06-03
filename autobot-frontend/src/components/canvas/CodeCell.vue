<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss | Author: mrveiss -->
<template>
  <div class="code-cell space-y-2">
    <!-- Error state -->
    <div v-if="renderError" class="p-4 rounded border border-error bg-error-bg">
      <p class="text-error font-medium text-sm">❌ Code render failed</p>
      <p class="text-text-secondary text-xs mt-1">{{ renderError }}</p>
    </div>

    <!-- Success: render code + copy button -->
    <div v-else-if="codeContent">
      <!-- Copy button + feedback -->
      <div class="flex items-center justify-between p-2 bg-bg-secondary rounded-t border border-b-0 border-border-secondary">
        <span class="text-xs text-text-secondary font-medium">
          {{ codeLanguage || 'code' }}
        </span>
        <button
          data-testid="btn-copy-code"
          :aria-label="`Copy ${codeLanguage || 'code'}`"
          class="px-2 py-1 text-xs rounded border border-border-secondary hover:bg-bg-tertiary transition-colors"
          @click="copyToClipboard"
        >
          {{ copyFeedback || '📋 Copy' }}
        </button>
      </div>

      <!-- Code block with syntax highlighting -->
      <pre
        :class="[
          'p-4 rounded-b rounded-none bg-bg-card border border-t-0 border-border-secondary overflow-auto',
          'text-xs leading-relaxed font-mono',
          isDark ? 'hljs-dark' : 'hljs-light',
        ]"
        role="region"
        aria-label="Code block"
      ><code v-html="highlightedCode" /></pre>

      <!-- Live region for a11y copy feedback -->
      <div
        aria-live="polite"
        aria-atomic="true"
        class="sr-only"
        role="status"
      >
        {{ copyFeedback }}
      </div>
    </div>

    <!-- Loading skeleton -->
    <div
      v-else
      :class="[
        'p-4 rounded border border-border-default space-y-1',
        !prefersReducedMotion && 'animate-pulse',
      ]"
      aria-busy="true"
      aria-label="Loading code…"
    >
      <div class="h-3 bg-bg-tertiary rounded w-20" />
      <div class="h-3 bg-bg-tertiary rounded w-full" />
      <div class="h-3 bg-bg-tertiary rounded w-5/6" />
      <div class="h-3 bg-bg-tertiary rounded w-4/5" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import type { CodePayload } from '@/types/canvas'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('CodeCell')

const props = defineProps<{
  richPayload: CodePayload | null
}>()

const renderError = ref<string>('')
const highlightJsLoaded = ref(false)
const copyFeedback = ref<string>('')
const copyTimeout = ref<number>()
const prefersReducedMotion = typeof window !== 'undefined'
  ? window.matchMedia('(prefers-reduced-motion: reduce)').matches
  : false

const isDark = typeof window !== 'undefined'
  ? window.matchMedia('(prefers-color-scheme: dark)').matches
  : false

const codeContent = computed(() => props.richPayload?.code)
const codeLanguage = computed(() => props.richPayload?.language || '')

// Lazy-load highlight.js and DOMPurify
async function loadLibraries() {
  if (highlightJsLoaded.value) return

  try {
    const hljs = await import('highlight.js')
    const dompurify = await import('dompurify')
    highlightJsLoaded.value = true
    return { hljs: hljs.default, dompurify: dompurify.default }
  } catch (err) {
    renderError.value = `Failed to load libraries: ${err instanceof Error ? err.message : String(err)}`
    throw err
  }
}

// Highlight code with syntax highlighting
const highlightedCode = computed(async () => {
  if (!codeContent.value) return ''

  try {
    const libs = await loadLibraries()
    if (!libs) return ''

    const { hljs, dompurify } = libs

    let highlighted: string
    if (codeLanguage.value) {
      try {
        highlighted = hljs.highlight(codeContent.value, { language: codeLanguage.value }).value
      } catch {
        // Fallback to plaintext if language not supported
        highlighted = hljs.highlightAuto(codeContent.value).value
      }
    } else {
      highlighted = hljs.highlightAuto(codeContent.value).value
    }

    // Sanitize HTML before rendering
    return dompurify.sanitize(highlighted, { ALLOWED_TAGS: ['span'], ALLOWED_ATTR: ['class'] })
  } catch (err) {
    renderError.value = `Syntax highlight failed: ${err instanceof Error ? err.message : String(err)}`
    return codeContent.value
  }
})

// Copy code to clipboard
async function copyToClipboard() {
  if (!codeContent.value) return

  try {
    await navigator.clipboard.writeText(codeContent.value)
    copyFeedback.value = '✓ Copied!'

    // Reset feedback after 2s
    if (copyTimeout.value) clearTimeout(copyTimeout.value)
    copyTimeout.value = window.setTimeout(() => {
      copyFeedback.value = ''
    }, 2000)
  } catch (err) {
    copyFeedback.value = '❌ Copy failed'
    logger.error('copy failed:', err)
  }
}

// Watch payload changes
watch(() => props.richPayload, () => {
  renderError.value = ''
  copyFeedback.value = ''
}, { immediate: true })

// Initial load
onMounted(() => {
  if (props.richPayload) {
    loadLibraries().catch(err => {
      logger.error('init error:', err)
    })
  }
})

// Cleanup
onMounted(() => {
  return () => {
    if (copyTimeout.value) clearTimeout(copyTimeout.value)
  }
})
</script>

<style scoped>
.code-cell {
  /* Code cell styling */
}

/* Accessibility: focus styles */
button:focus-visible {
  outline: 2px solid var(--color-focus-ring);
  outline-offset: 2px;
}

/* Screen reader only (sr-only) */
.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border-width: 0;
}

/* Highlight.js theme: dark mode */
.hljs-dark {
  background-color: var(--color-bg-card);
  color: var(--color-text-primary);
}

.hljs-dark :deep(.hljs-attr),
.hljs-dark :deep(.hljs-attribute) {
  color: #88bbff;
}

.hljs-dark :deep(.hljs-literal),
.hljs-dark :deep(.hljs-number) {
  color: #d19a66;
}

.hljs-dark :deep(.hljs-string) {
  color: #98c379;
}

.hljs-dark :deep(.hljs-built_in),
.hljs-dark :deep(.hljs-builtin-name) {
  color: #61afef;
}

.hljs-dark :deep(.hljs-title),
.hljs-dark :deep(.hljs-function) {
  color: #61afef;
}

.hljs-dark :deep(.hljs-keyword) {
  color: #c678dd;
}

.hljs-dark :deep(.hljs-comment) {
  color: #5c6370;
  font-style: italic;
}

/* Highlight.js theme: light mode */
.hljs-light {
  background-color: var(--color-bg-card);
  color: var(--color-text-primary);
}

.hljs-light :deep(.hljs-attr),
.hljs-light :deep(.hljs-attribute) {
  color: #0184bc;
}

.hljs-light :deep(.hljs-literal),
.hljs-light :deep(.hljs-number) {
  color: #986801;
}

.hljs-light :deep(.hljs-string) {
  color: #50a14f;
}

.hljs-light :deep(.hljs-built_in),
.hljs-light :deep(.hljs-builtin-name) {
  color: #4078f2;
}

.hljs-light :deep(.hljs-title),
.hljs-light :deep(.hljs-function) {
  color: #4078f2;
}

.hljs-light :deep(.hljs-keyword) {
  color: #a626a4;
}

.hljs-light :deep(.hljs-comment) {
  color: #a0a1a7;
  font-style: italic;
}
</style>
