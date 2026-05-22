<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<!-- Author: mrveiss -->

<template>
  <transition name="slide-down">
    <div v-if="selectedCount > 0" class="batch-selection-toolbar">
      <div class="toolbar-inner">
        <!-- Selection summary -->
        <div class="selection-summary">
          <Icon name="check-square" class="selection-icon" />
          <span class="selection-label">
            {{ t('knowledge.batchSelection.selected', { count: selectedCount }) }}
          </span>
          <span v-if="eligibleCount < selectedCount" class="eligible-note">
            ({{ t('knowledge.batchSelection.eligible', { count: eligibleCount }) }})
          </span>
        </div>

        <!-- Actions -->
        <div class="toolbar-actions">
          <button
            class="action-btn vectorize-btn"
            :disabled="eligibleCount === 0 || isVectorizing"
            :title="vectorizeBtnTooltip"
            @click="handleVectorize"
          >
            <Icon name="spinner" class="animate-spin" v-if="isVectorizing" />
            <Icon name="cubes" v-else />
            <span>{{ vectorizeBtnLabel }}</span>
          </button>

          <button
            class="action-btn clear-btn"
            :title="t('knowledge.batchSelection.clearSelectionTitle')"
            @click="emit('deselect-all')"
          >
            <Icon name="times" />
            <span>{{ t('knowledge.batchSelection.clearSelection') }}</span>
          </button>
        </div>
      </div>
    </div>
  </transition>
</template>

<script setup lang="ts">
/**
 * BatchSelectionToolbar Component (Issue #3388)
 *
 * Appears when one or more KB documents are selected, offering a "Vectorize
 * selected" bulk action.  Counts only non-vectorized documents as eligible so
 * the button copy is accurate.
 *
 * Does NOT duplicate KnowledgeBatchToolbar.vue (tree-browser sticky header) or
 * BulkActionsToolbar.vue (export/delete/tags for entry list).  This toolbar is
 * the vectorization-specific selection bar for general KB views.
 */

import Icon from '@/components/ui/Icon.vue'
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { createLogger } from '@/utils/debugUtils'
import type { VectorizationStatus } from '@/composables/useKnowledgeVectorization'

const { t } = useI18n()
const logger = createLogger('BatchSelectionToolbar')

// =============================================================================
// Props & Emits
// =============================================================================

interface SelectedDocumentInfo {
  id: string
  status: VectorizationStatus
}

interface Props {
  /** Documents currently selected by the user */
  selectedDocuments: SelectedDocumentInfo[]
  /** True while a batch vectorization job is in flight */
  isVectorizing?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  isVectorizing: false
})

const emit = defineEmits<{
  /** Request batch vectorization for the provided document IDs */
  (e: 'vectorize', documentIds: string[]): void
  /** Request clearing the current selection */
  (e: 'deselect-all'): void
}>()

// =============================================================================
// Computed
// =============================================================================

const selectedCount = computed(() => props.selectedDocuments.length)

/**
 * Documents that are not yet vectorized and not already pending.
 * Vectorized documents are skipped so the count is honest.
 */
const eligibleDocuments = computed(() =>
  props.selectedDocuments.filter(d => d.status !== 'vectorized' && d.status !== 'pending')
)

const eligibleCount = computed(() => eligibleDocuments.value.length)

const vectorizeBtnLabel = computed(() => {
  if (props.isVectorizing) return t('knowledge.batchSelection.vectorizing')
  if (eligibleCount.value === 0) return t('knowledge.batchSelection.noneEligible')
  return t('knowledge.batchSelection.vectorizeSelected', { count: eligibleCount.value })
})

const vectorizeBtnTooltip = computed(() => {
  if (props.isVectorizing) return t('knowledge.batchSelection.vectorizingTooltip')
  if (eligibleCount.value === 0) return t('knowledge.batchSelection.noneEligibleTooltip')
  return t('knowledge.batchSelection.vectorizeSelectedTooltip', { count: eligibleCount.value })
})

// =============================================================================
// Handlers
// =============================================================================

function handleVectorize(): void {
  if (eligibleCount.value === 0 || props.isVectorizing) return
  const ids = eligibleDocuments.value.map(d => d.id)
  logger.debug('Batch vectorize requested for %d documents', ids.length)
  emit('vectorize', ids)
}
</script>

<style scoped>
/* Issue #3388: Batch selection toolbar */
.batch-selection-toolbar {
  position: sticky;
  top: 0;
  z-index: 20;
  background: var(--color-primary);
  color: var(--text-on-primary);
  padding: var(--spacing-3) var(--spacing-6);
  box-shadow: var(--shadow-lg);
  border-radius: 0 0 var(--radius-lg) var(--radius-lg);
  margin: 0 var(--spacing-4) var(--spacing-4) var(--spacing-4);
}

.toolbar-inner {
  display: flex;
  justify-content: space-between;
  align-items: center;
  max-width: 1200px;
  margin: 0 auto;
}

/* Selection summary */
.selection-summary {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  font-weight: var(--font-medium);
}

.selection-icon {
  font-size: var(--text-lg);
}

.selection-label {
  font-size: var(--text-sm);
}

.eligible-note {
  font-size: var(--text-xs);
  opacity: 0.8;
}

/* Actions */
.toolbar-actions {
  display: flex;
  align-items: center;
  gap: var(--spacing-3);
}

.action-btn {
  display: inline-flex;
  align-items: center;
  gap: var(--spacing-2);
  padding: var(--spacing-2) var(--spacing-4);
  border-radius: var(--radius-md);
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
  border: none;
  cursor: pointer;
  transition: all var(--duration-200) var(--ease-in-out);
}

.vectorize-btn {
  background: var(--bg-primary);
  color: var(--color-primary-active);
}

.vectorize-btn:hover:not(:disabled) {
  background: var(--color-primary-bg);
  transform: translateY(-1px);
}

.vectorize-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.clear-btn {
  background: var(--bg-primary-transparent);
  color: var(--text-on-primary);
  border: 1px solid var(--bg-primary-transparent-hover);
}

.clear-btn:hover {
  background: var(--bg-primary-transparent-hover);
}

/* Slide-down transition */
.slide-down-enter-active,
.slide-down-leave-active {
  transition: all var(--duration-300) var(--ease-in-out);
}

.slide-down-enter-from,
.slide-down-leave-to {
  opacity: 0;
  transform: translateY(-100%);
}

/* Responsive */
@media (max-width: 768px) {
  .toolbar-inner {
    flex-direction: column;
    gap: var(--spacing-3);
  }

  .toolbar-actions {
    width: 100%;
    justify-content: stretch;
  }

  .action-btn {
    flex: 1;
    justify-content: center;
  }
}
</style>
