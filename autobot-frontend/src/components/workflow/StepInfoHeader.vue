<template>
  <div class="current-step-info">
    <div class="step-counter">
      Step {{ currentIndex + 1 }} of {{ totalSteps }}
    </div>
    <div class="step-description">
      <strong>{{ step?.description || 'Execute Command' }}</strong>
    </div>
    <div class="step-explanation">
      {{ step?.explanation || 'AI-generated workflow step' }}
    </div>
  </div>
</template>

<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss
/**
 * Step Info Header Component
 *
 * Displays current step information in workflow confirmation modal.
 * Extracted from AdvancedStepConfirmationModal.vue for better maintainability.
 *
 * Issue #184: Split oversized Vue components
 */

interface WorkflowStep {
  id?: string
  description: string
  command: string
  explanation?: string
  status?: 'pending' | 'executing' | 'completed' | 'failed' | 'skipped'
}

interface Props {
  step: WorkflowStep | null
  currentIndex: number
  totalSteps: number
}

defineProps<Props>()
</script>

<style scoped>
/** Issue #704: Migrated to design tokens */
.current-step-info {
  padding: var(--spacing-5);
  border-bottom: 1px solid var(--border-default);
  background: var(--bg-secondary);
}

.step-counter {
  display: inline-block;
  background: var(--color-primary);
  color: var(--text-on-primary);
  padding: var(--spacing-1-5) var(--spacing-4);
  border-radius: var(--radius-full);
  font-size: var(--text-sm);
  margin-bottom: var(--spacing-2);
}

.step-description {
  font-size: var(--text-lg);
  margin-bottom: var(--spacing-2);
  color: var(--text-primary);
}

.step-explanation {
  color: var(--text-secondary);
  font-size: var(--text-base);
}
</style>
