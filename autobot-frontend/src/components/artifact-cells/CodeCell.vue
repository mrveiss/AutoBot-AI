<!--
  AutoBot - AI-Powered Automation Platform
  Copyright (c) 2025 mrveiss
  Author: mrveiss

  CodeCell.vue - Syntax-highlighted code rendering component
  Renders code with syntax highlighting, copy functionality, and a11y support
  Issue MVA-485
-->
<template>
  <div class="code-cell">
    <!-- Placeholder for empty content -->
    <div v-if="!richPayload" class="code-placeholder">
      <div class="placeholder-content">
        <Icon name="code" />
        <span>{{ $t('code.cellPlaceholder', 'Code') }}</span>
      </div>
    </div>

    <!-- Code content -->
    <div v-else class="code-wrapper">
      <div class="code-header">
        <span v-if="language" class="code-language">{{ language }}</span>
        <button class="copy-button" @click="copyCode" :aria-label="copyAriaLabel">
          <Icon :name="copyButtonIcon" />
          <span class="copy-text">{{ copyButtonText }}</span>
        </button>
      </div>

      <pre class="code-container"><code
        :class="codeClasses"
        v-html="highlightedCode"
        role="region"
        aria-label="Highlighted code"
      /></pre>

      <!-- Accessible aria-live region for copy feedback -->
      <div
        :id="`copy-status-${cellId}`"
        role="status"
        aria-live="polite"
        aria-atomic="true"
        class="copy-status"
      >
        {{ copyStatus }}
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import Icon from '@/components/ui/Icon.vue'
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import DOMPurify from 'dompurify'

const { t } = useI18n()

// Props
interface CodeCellProps {
  richPayload?: Record<string, unknown> | null
  language?: string
  showLineNumbers?: boolean
  copyable?: boolean
}

const props = withDefaults(defineProps<CodeCellProps>(), {
  richPayload: null,
  language: undefined,
  showLineNumbers: false,
  copyable: true
})

// Emits
interface CodeCellEmits {
  copied: [code: string]
}

defineEmits<CodeCellEmits>()

// State
const cellId = ref<string>(`code-${crypto.randomUUID()}`)
const highlightedCode = ref<string>('')
const copyStatus = ref<string>('')
const copyTimeout = ref<ReturnType<typeof setTimeout> | null>(null)
let hljs: any = null

// Computed
const rawCode = computed(() => {
  if (!props.richPayload || typeof props.richPayload !== 'object') {
    return ''
  }

  const payload = props.richPayload as Record<string, unknown>
  if (typeof payload.code === 'string') {
    return payload.code
  }
  if (typeof payload.content === 'string') {
    return payload.content
  }
  if (typeof payload.text === 'string') {
    return payload.text
  }

  return JSON.stringify(payload, null, 2)
})

const codeClasses = computed(() => {
  const classes = ['hljs']
  if (props.language) {
    classes.push(`language-${props.language}`)
  }
  return classes
})

const copyButtonText = computed(() => {
  if (copyStatus.value) {
    return t('code.copied', 'Copied!')
  }
  return t('code.copy', 'Copy')
})

const copyButtonIcon = computed(() => {
  if (copyStatus.value) {
    return ['fas', 'fa-check']
  }
  return ['fas', 'fa-copy']
})

const copyAriaLabel = computed(() => {
  return t('code.copyCodeAriaLabel', 'Copy code to clipboard')
})

const language = computed(() => {
  return props.language || (props.richPayload as Record<string, unknown>)?.language
})

// Methods
const loadHighlightJs = async () => {
  if (!hljs) {
    hljs = await import('highlight.js')
  }
  return hljs
}

const highlightCode = async () => {
  if (!rawCode.value) {
    highlightedCode.value = ''
    return
  }

  try {
    const hl = await loadHighlightJs()
    if (!hl) {
      throw new Error('Failed to load highlight.js')
    }

    let highlighted: string

    if (props.language) {
      highlighted = hl.highlight(rawCode.value, {
        language: props.language,
        ignoreIllegals: true
      }).value
    } else {
      highlighted = hl.highlightAuto(rawCode.value).value
    }

    // Sanitize the highlighted HTML to prevent XSS
    highlightedCode.value = DOMPurify.sanitize(highlighted, {
      ALLOWED_TAGS: ['span', 'br'],
      ALLOWED_ATTR: ['class']
    })
  } catch (error) {
    // Fallback to plain text if highlighting fails
    highlightedCode.value = DOMPurify.sanitize(rawCode.value, {
      ALLOWED_TAGS: [],
      ALLOWED_ATTR: []
    })
  }
}

const copyCode = async () => {
  if (!props.copyable || !rawCode.value) {
    return
  }

  try {
    // Clear any existing timeout
    if (copyTimeout.value) {
      clearTimeout(copyTimeout.value)
    }

    // Copy to clipboard
    await navigator.clipboard.writeText(rawCode.value)

    // Update status
    copyStatus.value = copyButtonText.value

    // Emit event
    const emit = defineEmits<CodeCellEmits>()
    emit('copied', rawCode.value)

    // Reset status after 2 seconds
    copyTimeout.value = setTimeout(() => {
      copyStatus.value = ''
    }, 2000)
  } catch (error) {
    copyStatus.value = t('code.copyFailed', 'Failed to copy')
    copyTimeout.value = setTimeout(() => {
      copyStatus.value = ''
    }, 2000)
  }
}

// Lifecycle
onMounted(() => {
  highlightCode()
})
</script>

<style scoped>
/**
 * Code cell styling with design tokens
 * Supports light/dark syntax highlighting themes and WCAG AA accessibility
 */
.code-cell {
  position: relative;
  width: 100%;
  background: var(--bg-card);
  border-radius: var(--radius-lg);
  border: 1px solid var(--border-subtle);
  overflow: hidden;
}

.code-placeholder {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 200px;
  gap: var(--spacing-md);
  color: var(--text-secondary);
}

.placeholder-content {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--spacing-sm);
}

.placeholder-content i {
  font-size: 48px;
  color: var(--text-tertiary);
}

.code-wrapper {
  position: relative;
  width: 100%;
}

.code-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--spacing-md);
  background: var(--bg-secondary);
  border-bottom: 1px solid var(--border-subtle);
}

.code-language {
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.copy-button {
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);
  padding: var(--spacing-xs) var(--spacing-sm);
  background: transparent;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-sm);
  color: var(--text-secondary);
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
  cursor: pointer;
  transition: all 0.2s ease;
}

.copy-button:hover {
  background: var(--bg-tertiary);
  color: var(--text-primary);
  border-color: var(--border-default);
}

.copy-button:active {
  background: var(--bg-elevated);
  color: var(--color-success);
}

.copy-button i {
  font-size: var(--text-sm);
}

.code-container {
  margin: 0;
  padding: var(--spacing-md);
  background: var(--bg-secondary);
  color: var(--text-primary);
  font-family: var(--font-mono);
  font-size: var(--text-sm);
  line-height: 1.5;
  overflow-x: auto;
  white-space: pre;
  -webkit-overflow-scrolling: touch;
}

.code-container code {
  display: block;
  word-break: break-word;
  white-space: pre-wrap;
  color: inherit;
}

/* Syntax highlighting - light theme (when prefers-color-scheme: light) */
@media (prefers-color-scheme: light) {
  .code-container {
    background: var(--bg-primary);
    color: #333;
  }

  :deep(.hljs-string),
  :deep(.hljs-attr),
  :deep(.hljs-bullet) {
    color: #008000;
  }

  :deep(.hljs-number),
  :deep(.hljs-literal) {
    color: #0000ff;
  }

  :deep(.hljs-attr),
  :deep(.hljs-variable) {
    color: #0000ff;
  }

  :deep(.hljs-comment) {
    color: #008080;
  }

  :deep(.hljs-tag) {
    color: #800000;
  }

  :deep(.hljs-keyword) {
    color: #0000ff;
  }
}

/* Syntax highlighting - dark theme (when prefers-color-scheme: dark) */
@media (prefers-color-scheme: dark) {
  :deep(.hljs-string) {
    color: #85e89d;
  }

  :deep(.hljs-number),
  :deep(.hljs-literal) {
    color: #79b8ff;
  }

  :deep(.hljs-attr),
  :deep(.hljs-variable) {
    color: #79b8ff;
  }

  :deep(.hljs-comment) {
    color: #6a737d;
  }

  :deep(.hljs-tag) {
    color: #f97583;
  }

  :deep(.hljs-keyword) {
    color: #f97583;
  }

  :deep(.hljs-function) {
    color: #79b8ff;
  }

  :deep(.hljs-built_in) {
    color: #f97583;
  }
}

/* Accessible copy status - visually hidden but announced to screen readers */
.copy-status {
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

/* Ensure focus visibility for keyboard navigation */
.copy-button:focus-visible {
  outline: 2px solid var(--color-focus);
  outline-offset: 2px;
}

/* Support for prefers-reduced-motion */
@media (prefers-reduced-motion: reduce) {
  .copy-button {
    transition: none;
  }
}

/* Line number support (optional future enhancement) */
.code-container.show-line-numbers {
  padding-left: 3rem;
  counter-reset: line-numbers;
}

.code-container.show-line-numbers code {
  counter-increment: line-numbers;
}
</style>
