<template>
  <transition name="slide-down">
    <div v-if="hasSelection" class="batch-toolbar">
      <div class="toolbar-content">
        <div class="toolbar-info">
          <i class="fas fa-check-square"></i>
          <span>{{ selectionCount }} document{{ selectionCount > 1 ? 's' : '' }} selected</span>
        </div>
        <div class="toolbar-actions">
          <BaseButton
            variant="primary"
            @click="$emit('vectorize')"
            :disabled="!canVectorize || isVectorizing"
            :loading="isVectorizing"
            class="toolbar-btn vectorize"
          >
            <i v-if="!isVectorizing" class="fas fa-cubes"></i>
            Vectorize Selected
          </BaseButton>
          <BaseButton
            variant="secondary"
            @click="$emit('deselect-all')"
            class="toolbar-btn cancel"
          >
            <i class="fas fa-times"></i>
            Clear Selection
          </BaseButton>
        </div>
      </div>
    </div>
  </transition>
</template>

<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss
/**
 * Knowledge Batch Toolbar Component
 *
 * Floating toolbar for batch operations on selected documents.
 * Extracted from KnowledgeBrowser.vue for better maintainability.
 *
 * Issue #184: Split oversized Vue components
 */

import BaseButton from '@/components/base/BaseButton.vue'

interface Props {
  hasSelection: boolean
  selectionCount: number
  canVectorize: boolean
  isVectorizing?: boolean
}

interface Emits {
  (e: 'vectorize'): void
  (e: 'deselect-all'): void
}

withDefaults(defineProps<Props>(), {
  isVectorizing: false
})

defineEmits<Emits>()
</script>

<style scoped>
/* Issue #704: Migrated to CSS design tokens */
.batch-toolbar {
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

.toolbar-content {
  display: flex;
  justify-content: space-between;
  align-items: center;
  max-width: 1200px;
  margin: 0 auto;
}

.toolbar-info {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  font-weight: var(--font-medium);
}

.toolbar-info i {
  font-size: 1.125rem;
}

.toolbar-actions {
  display: flex;
  gap: var(--spacing-3);
}

.toolbar-btn {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  padding: var(--spacing-2) var(--spacing-4);
  border-radius: var(--radius-md);
  font-weight: var(--font-medium);
  transition: all var(--duration-200) var(--ease-in-out);
}

.toolbar-btn.vectorize {
  background: var(--bg-primary);
  color: var(--color-primary-active);
}

.toolbar-btn.vectorize:hover:not(:disabled) {
  background: var(--color-primary-bg);
  transform: translateY(-1px);
}

.toolbar-btn.vectorize:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.toolbar-btn.cancel {
  background: var(--bg-primary-transparent);
  color: var(--text-on-primary);
  border: 1px solid var(--bg-primary-transparent-hover);
}

.toolbar-btn.cancel:hover {
  background: var(--bg-primary-transparent-hover);
}

/* Transition */
.slide-down-enter-active,
.slide-down-leave-active {
  transition: all var(--duration-300) var(--ease-in-out);
}

.slide-down-enter-from,
.slide-down-leave-to {
  opacity: 0;
  transform: translateY(-100%);
}

@media (max-width: 768px) {
  .toolbar-content {
    flex-direction: column;
    gap: var(--spacing-3);
  }

  .toolbar-actions {
    width: 100%;
    justify-content: stretch;
  }

  .toolbar-btn {
    flex: 1;
    justify-content: center;
  }
}
</style>
