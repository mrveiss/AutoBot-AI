<template>
  <div class="modal-actions">
    <div class="primary-actions">
      <BaseButton
        variant="success"
        @click="$emit('execute')"
        :disabled="!hasCurrentStep"
        class="execute-btn"
        aria-label="Execute this step"
      >
        ✅ Execute This Step
      </BaseButton>
      <BaseButton
        variant="secondary"
        @click="$emit('skip')"
        class="skip-btn"
        aria-label="Skip this step"
      >
        ⏭️ Skip This Step
      </BaseButton>
      <BaseButton
        variant="primary"
        @click="$emit('manual-control')"
        class="manual-btn"
        aria-label="Take manual control"
      >
        👤 Take Manual Control
      </BaseButton>
    </div>

    <div class="secondary-actions">
      <BaseButton
        variant="info"
        @click="$emit('execute-all')"
        class="execute-all-btn"
        aria-label="Execute all remaining steps"
      >
        🚀 Execute All Remaining
      </BaseButton>
      <BaseButton
        variant="success"
        @click="$emit('save-workflow')"
        class="save-workflow-btn"
        aria-label="Save workflow"
      >
        💾 Save Workflow
      </BaseButton>
      <BaseButton
        variant="secondary"
        @click="$emit('toggle-advanced')"
        class="toggle-advanced-btn"
        aria-label="Toggle advanced options"
      >
        ⚙️ {{ showAdvanced ? 'Hide' : 'Show' }} Advanced
      </BaseButton>
    </div>
  </div>
</template>

<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss
/**
 * Modal Action Buttons Component
 *
 * Action buttons for the workflow confirmation modal.
 * Extracted from AdvancedStepConfirmationModal.vue for better maintainability.
 *
 * Issue #184: Split oversized Vue components
 */

import BaseButton from '@/components/base/BaseButton.vue'

interface Props {
  hasCurrentStep: boolean
  showAdvanced: boolean
}

interface Emits {
  (e: 'execute'): void
  (e: 'skip'): void
  (e: 'manual-control'): void
  (e: 'execute-all'): void
  (e: 'save-workflow'): void
  (e: 'toggle-advanced'): void
}

defineProps<Props>()
defineEmits<Emits>()
</script>

<style scoped>
.modal-actions {
  padding: 20px;
}

.primary-actions {
  display: flex;
  gap: 12px;
  margin-bottom: 16px;
  flex-wrap: wrap;
}

.secondary-actions {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}

@media (max-width: 768px) {
  .modal-actions {
    padding: 16px;
  }

  .primary-actions,
  .secondary-actions {
    flex-direction: column;
    gap: 8px;
  }
}

@media (max-width: 768px) and (orientation: landscape) {
  .primary-actions,
  .secondary-actions {
    flex-direction: row;
    flex-wrap: wrap;
  }
}
</style>
