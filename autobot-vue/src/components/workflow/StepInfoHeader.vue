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
.current-step-info {
  padding: 20px;
  border-bottom: 1px solid #333;
  background: #0f1419;
}

.step-counter {
  display: inline-block;
  background: #2563eb;
  color: #ffffff;
  padding: 6px 16px;
  border-radius: 20px;
  font-size: 0.9em;
  margin-bottom: 8px;
}

.step-description {
  font-size: 1.1em;
  margin-bottom: 8px;
  color: #f3f4f6;
}

.step-explanation {
  color: #d1d5db;
  font-size: 0.95em;
}
</style>
