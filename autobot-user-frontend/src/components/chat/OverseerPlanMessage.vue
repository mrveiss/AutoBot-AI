<template>
  <div class="overseer-plan">
    <!-- Plan Header -->
    <div class="plan-header">
      <div class="plan-title">
        <i class="fas fa-sitemap" aria-hidden="true"></i>
        <span>Execution Plan</span>
      </div>
      <div class="plan-progress">
        <div class="progress-bar" :style="{ width: `${progressPercentage}%` }"></div>
      </div>
      <span class="progress-text">{{ completedSteps }}/{{ totalSteps }} steps</span>
    </div>

    <!-- Analysis -->
    <div class="plan-analysis">
      <i class="fas fa-lightbulb" aria-hidden="true"></i>
      <p>{{ plan.analysis }}</p>
    </div>

    <!-- Steps Preview -->
    <div class="steps-preview">
      <div
        v-for="step in plan.steps"
        :key="step.step_number"
        class="step-preview"
        :class="getStepClass(step)"
      >
        <div class="step-number">{{ step.step_number }}</div>
        <div class="step-info">
          <span class="step-desc">{{ step.description }}</span>
          <code v-if="step.command" class="step-command">{{ step.command }}</code>
        </div>
        <div class="step-status-icon">
          <i :class="getStepIcon(step)" aria-hidden="true"></i>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * OverseerPlanMessage Component
 *
 * Displays the execution plan overview from the Overseer Agent.
 * Shows all steps with their status and progress.
 *
 * @author mrveiss
 * @copyright 2025 mrveiss
 */

import { computed } from 'vue'
import type { OverseerPlan, OverseerStep } from '@/composables/useOverseerAgent'

const props = defineProps<{
  plan: OverseerPlan
  steps?: OverseerStep[]
}>()

// Computed
const totalSteps = computed(() => props.plan.steps.length)

const completedSteps = computed(() => {
  if (!props.steps) return 0
  return props.steps.filter(s => s.status === 'completed' || s.status === 'failed').length
})

const progressPercentage = computed(() => {
  if (totalSteps.value === 0) return 0
  return Math.round((completedSteps.value / totalSteps.value) * 100)
})

// Methods
const getStepStatus = (planStep: { step_number: number }): string => {
  if (!props.steps) return 'pending'
  const step = props.steps.find(s => s.step_number === planStep.step_number)
  return step?.status || 'pending'
}

const getStepClass = (step: { step_number: number }): Record<string, boolean> => {
  const status = getStepStatus(step)
  return {
    pending: status === 'pending',
    running: status === 'running' || status === 'streaming',
    completed: status === 'completed',
    failed: status === 'failed'
  }
}

const getStepIcon = (step: { step_number: number }): string => {
  const status = getStepStatus(step)
  const icons: Record<string, string> = {
    pending: 'fas fa-circle text-gray-500',
    running: 'fas fa-spinner fa-spin text-blue-400',
    streaming: 'fas fa-stream text-cyan-400',
    explaining: 'fas fa-brain text-purple-400',
    completed: 'fas fa-check-circle text-green-400',
    failed: 'fas fa-times-circle text-red-400'
  }
  return icons[status] || icons.pending
}
</script>

<style scoped>
.overseer-plan {
  @apply bg-gray-800/80 border border-indigo-600/50 rounded-lg p-4 mb-4;
}

.plan-header {
  @apply flex items-center gap-4 mb-3 pb-3 border-b border-gray-700;
}

.plan-title {
  @apply flex items-center gap-2 text-indigo-300 font-semibold;
}

.plan-progress {
  @apply flex-1 h-2 bg-gray-700 rounded-full overflow-hidden;
}

.progress-bar {
  @apply h-full bg-gradient-to-r from-indigo-500 to-purple-500 transition-all duration-300;
}

.progress-text {
  @apply text-gray-400 text-sm;
}

.plan-analysis {
  @apply flex items-start gap-2 text-gray-300 text-sm mb-4 bg-indigo-900/30 px-3 py-2 rounded;
}

.plan-analysis i {
  @apply text-yellow-400 mt-0.5;
}

.steps-preview {
  @apply space-y-2;
}

.step-preview {
  @apply flex items-center gap-3 px-3 py-2 rounded bg-gray-900/50 border border-gray-700;
  transition: all 0.2s ease;
}

.step-preview.running {
  @apply border-blue-500 bg-blue-900/20;
}

.step-preview.completed {
  @apply border-green-600/50 bg-green-900/20;
}

.step-preview.failed {
  @apply border-red-600/50 bg-red-900/20;
}

.step-number {
  @apply w-6 h-6 flex items-center justify-center bg-gray-700 text-gray-300 rounded-full text-xs font-semibold;
}

.step-preview.completed .step-number {
  @apply bg-green-700 text-green-100;
}

.step-preview.running .step-number {
  @apply bg-blue-600 text-white;
}

.step-info {
  @apply flex-1 min-w-0;
}

.step-desc {
  @apply block text-gray-300 text-sm truncate;
}

.step-command {
  @apply block text-gray-500 text-xs font-mono mt-0.5 truncate;
}

.step-status-icon {
  @apply text-lg;
}
</style>
