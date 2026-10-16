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
          'hljs-theme',
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
import { useReducedMotion } from '@/composables/useReducedMotion'

const logger = createLogger('CodeCell')

const props = defineProps<{
  richPayload: CodePayload | null
}>()

const renderError = ref<string>('')
const highlightJsLoaded = ref(false)
const copyFeedback = ref<string>('')
const copyTimeout = ref<number>()
// #14770: third inline reader of this preference in the codebase; all three
// now go through the composable, which also makes them reactive.
const { prefersReducedMotion } = useReducedMotion()

const codeContent = computed(() => props.richPayload?.code)
const codeLanguage = computed(() => props.richPayload?.language || '')

// Lazy-load highlight.js and DOMPurify
let _cachedLibs: { hljs: typeof import('highlight.js')['default']; dompurify: typeof import('dompurify')['default'] } | null = null
async function loadLibraries() {
  if (_cachedLibs) return _cachedLibs

  try {
    const hljs = await import('highlight.js')
    const dompurify = await import('dompurify')
    highlightJsLoaded.value = true
    _cachedLibs = { hljs: hljs.default, dompurify: dompurify.default }
    return _cachedLibs
  } catch (err) {
    renderError.value = `Failed to load libraries: ${err instanceof Error ? err.message : String(err)}`
    throw err
  }
}

// Highlight code with syntax highlighting
const highlightedCode = ref<string>('')

async function updateHighlightedCode() {
  if (!codeContent.value) {
    highlightedCode.value = ''
    return
  }

  try {
    const libs = await loadLibraries()
    if (!libs) return

    const { hljs, dompurify } = libs

    let highlighted: string
    if (codeLanguage.value) {
      try {
        highlighted = hljs.highlight(codeContent.value, { language: codeLanguage.value }).value
      } catch {
        highlighted = hljs.highlightAuto(codeContent.value).value
      }
    } else {
      highlighted = hljs.highlightAuto(codeContent.value).value
    }

    // Sanitize HTML before rendering
    highlightedCode.value = dompurify.sanitize(highlighted, { ALLOWED_TAGS: ['span'], ALLOWED_ATTR: ['class'] })
  } catch (err) {
    renderError.value = `Syntax highlight failed: ${err instanceof Error ? err.message : String(err)}`
    highlightedCode.value = codeContent.value ?? ''
  }
}

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

// Watch payload changes and update highlighted code
watch(() => props.richPayload, () => {
  renderError.value = ''
  copyFeedback.value = ''
  updateHighlightedCode()
}, { immediate: true })

// Initial load
onMounted(() => {
  if (props.richPayload) {
    updateHighlightedCode().catch(err => {
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

/* Highlight.js colours from the active theme (#18497): one rule set, no
   dark/light switch on the OS colour scheme. */
.hljs-theme {
  background-color: var(--bg-card);
  color: var(--text-primary);
}

.hljs-theme :deep(.hljs-attr),
.hljs-theme :deep(.hljs-attribute) {
  color: var(--codecell-syntax-attr);
}

.hljs-theme :deep(.hljs-literal),
.hljs-theme :deep(.hljs-number) {
  color: var(--codecell-syntax-number);
}

.hljs-theme :deep(.hljs-string) {
  color: var(--codecell-syntax-string);
}

.hljs-theme :deep(.hljs-built_in),
.hljs-theme :deep(.hljs-builtin-name),
.hljs-theme :deep(.hljs-title),
.hljs-theme :deep(.hljs-function) {
  color: var(--codecell-syntax-callable);
}

.hljs-theme :deep(.hljs-keyword) {
  color: var(--codecell-syntax-keyword);
  font-weight: var(--codecell-syntax-keyword-weight);
}

.hljs-theme :deep(.hljs-comment) {
  color: var(--codecell-syntax-comment);
  font-style: var(--codecell-syntax-comment-style);
}

.hljs-theme :deep(.hljs-tag) {
  color: var(--codecell-syntax-tag);
}
</style>
