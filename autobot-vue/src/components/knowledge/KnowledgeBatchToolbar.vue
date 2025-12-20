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
.batch-toolbar {
  position: sticky;
  top: 0;
  z-index: 20;
  background: linear-gradient(135deg, #1e40af 0%, #3b82f6 100%);
  color: white;
  padding: 0.75rem 1.5rem;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
  border-radius: 0 0 0.75rem 0.75rem;
  margin: 0 1rem 1rem 1rem;
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
  gap: 0.5rem;
  font-weight: 500;
}

.toolbar-info i {
  font-size: 1.125rem;
}

.toolbar-actions {
  display: flex;
  gap: 0.75rem;
}

.toolbar-btn {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem 1rem;
  border-radius: 0.5rem;
  font-weight: 500;
  transition: all 0.2s;
}

.toolbar-btn.vectorize {
  background: white;
  color: #1e40af;
}

.toolbar-btn.vectorize:hover:not(:disabled) {
  background: #f0f9ff;
  transform: translateY(-1px);
}

.toolbar-btn.vectorize:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.toolbar-btn.cancel {
  background: rgba(255, 255, 255, 0.2);
  color: white;
  border: 1px solid rgba(255, 255, 255, 0.3);
}

.toolbar-btn.cancel:hover {
  background: rgba(255, 255, 255, 0.3);
}

/* Transition */
.slide-down-enter-active,
.slide-down-leave-active {
  transition: all 0.3s ease;
}

.slide-down-enter-from,
.slide-down-leave-to {
  opacity: 0;
  transform: translateY(-100%);
}

@media (max-width: 768px) {
  .toolbar-content {
    flex-direction: column;
    gap: 0.75rem;
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
