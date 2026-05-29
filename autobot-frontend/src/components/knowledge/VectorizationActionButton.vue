<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<!-- Author: mrveiss -->

<template>
  <button
    class="vectorization-action-btn"
    :class="buttonClass"
    :disabled="isDisabled"
    :title="tooltipText"
    @click.stop="handleClick"
  >
    <Icon :name="iconClass" />
    <span v-if="showLabel" class="btn-label">{{ labelText }}</span>
  </button>
</template>

<script setup lang="ts">
/**
 * VectorizationActionButton Component (Issue #3388)
 *
 * Action button to trigger vectorization for a single knowledge base document.
 * Disabled when the document is already vectorized or has a pending job in flight.
 */
import Icon from '@/components/ui/Icon.vue'

import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { createLogger } from '@/utils/debugUtils'
import type { VectorizationStatus } from '@/composables/useKnowledgeVectorization'

const { t } = useI18n()
const logger = createLogger('VectorizationActionButton')

// =============================================================================
// Props & Emits
// =============================================================================

interface Props {
  documentId: string
  status: VectorizationStatus
  /** Show text label next to the icon (default: false — icon-only) */
  showLabel?: boolean
  /** Compact icon-only variant (smaller padding) */
  compact?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  showLabel: false,
  compact: false
})

const emit = defineEmits<{
  /** Emitted when the user requests vectorization for documentId */
  (e: 'vectorize', documentId: string): void
}>()

// =============================================================================
// Computed
// =============================================================================

const isDisabled = computed(() => {
  return props.status === 'vectorized' || props.status === 'pending'
})

const isRetry = computed(() => props.status === 'failed')

const buttonClass = computed(() => {
  const classes: string[] = []

  if (props.compact) classes.push('compact')

  if (isDisabled.value) {
    classes.push('is-disabled')
  } else if (isRetry.value) {
    classes.push('is-retry')
  } else {
    classes.push('is-vectorize')
  }

  return classes.join(' ')
})

const iconClass = computed(() => {
  if (props.status === 'pending') return 'spinner'
  if (isRetry.value) return 'redo'
  return 'cube'
})

const labelText = computed(() => {
  if (props.status === 'vectorized') return t('knowledge.vectorization.actionAlreadyDone')
  if (props.status === 'pending') return t('knowledge.vectorization.actionInProgress')
  if (isRetry.value) return t('knowledge.vectorization.actionRetry')
  return t('knowledge.vectorization.actionVectorize')
})

const tooltipText = computed(() => {
  if (props.status === 'vectorized') return t('knowledge.vectorization.tooltipAlreadyDone')
  if (props.status === 'pending') return t('knowledge.vectorization.tooltipInProgress')
  if (isRetry.value) return t('knowledge.vectorization.tooltipRetry')
  return t('knowledge.vectorization.tooltipVectorize')
})

// =============================================================================
// Handlers
// =============================================================================

function handleClick(): void {
  if (isDisabled.value) return
  logger.debug('Vectorize requested for document: %s', props.documentId)
  emit('vectorize', props.documentId)
}
</script>

<style scoped>
/* Issue #3388: Vectorization action button */
.vectorization-action-btn {
  display: inline-flex;
  align-items: center;
  gap: var(--spacing-1-5);
  padding: var(--spacing-1-5) var(--spacing-3);
  border: none;
  border-radius: var(--radius-sm);
  font-size: var(--text-xs);
  font-weight: var(--font-medium);
  cursor: pointer;
  transition: all var(--duration-200) var(--ease-in-out);
  white-space: nowrap;
}

.vectorization-action-btn.compact {
  padding: var(--spacing-1) var(--spacing-2);
}

/* Vectorize (default) */
.vectorization-action-btn.is-vectorize {
  background: var(--color-primary);
  color: var(--text-on-primary);
}

.vectorization-action-btn.is-vectorize:hover {
  background: var(--color-primary-hover);
  transform: scale(1.05);
  box-shadow: var(--shadow-primary);
}

/* Retry (failed) */
.vectorization-action-btn.is-retry {
  background: var(--color-error);
  color: var(--text-on-primary);
}

.vectorization-action-btn.is-retry:hover {
  background: var(--color-error-hover);
  transform: scale(1.05);
}

/* Disabled (vectorized or pending) */
.vectorization-action-btn.is-disabled,
.vectorization-action-btn:disabled {
  background: var(--bg-tertiary);
  color: var(--text-muted);
  cursor: not-allowed;
  opacity: 0.6;
}

.btn-label {
  white-space: nowrap;
}
</style>
