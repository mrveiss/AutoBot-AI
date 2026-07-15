<template>
  <div class="overseer-plan">
    <!-- Plan Header -->
    <div class="plan-header">
      <div class="plan-title">
        <Icon name="sitemap" aria-hidden="true" />
        <span>{{ $t('chat.overseer.executionPlan') }}</span>
      </div>
      <div class="plan-progress">
        <div class="progress-bar" :style="{ width: `${progressPercentage}%` }"></div>
      </div>
      <span class="progress-text">{{ $t('chat.overseer.stepsProgress', { completed: completedSteps, total: totalSteps }) }}</span>
    </div>

    <!-- Analysis -->
    <div class="plan-analysis">
      <Icon name="lightbulb" aria-hidden="true" />
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
import Icon from '@/components/ui/Icon.vue'


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
    pending: 'fas fa-circle text-autobot-text-muted',
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
@reference "../../assets/tailwind.css";
.overseer-plan {
  @apply bg-autobot-bg-secondary border border-indigo-600/50 rounded-lg p-4 mb-4;
}

.plan-header {
  @apply flex items-center gap-4 mb-3 pb-3 border-b border-autobot-border;
}

.plan-title {
  @apply flex items-center gap-2 text-indigo-300 font-semibold;
}

.plan-progress {
  @apply flex-1 h-2 bg-autobot-bg-secondary rounded-full overflow-hidden;
}

.progress-bar {
  @apply h-full bg-linear-to-r from-indigo-500 to-purple-500 transition-all duration-300;
}

.progress-text {
  @apply text-autobot-text-muted text-sm;
}

.plan-analysis {
  @apply flex items-start gap-2 text-autobot-text-secondary text-sm mb-4 bg-indigo-900/30 px-3 py-2 rounded;
}

.plan-analysis i {
  @apply text-yellow-400 mt-0.5;
}

.steps-preview {
  @apply space-y-2;
}

.step-preview {
  @apply flex items-center gap-3 px-3 py-2 rounded bg-autobot-bg-primary border border-autobot-border;
  transition: all var(--duration-200) var(--ease-out);
}

.step-preview.running {
  border-color: var(--color-primary);
  background: var(--color-info-bg);
}

.step-preview.completed {
  border-color: var(--color-success);
  background: var(--color-success-bg);
}

.step-preview.failed {
  border-color: var(--color-error);
  background: var(--color-error-bg);
}

.step-number {
  @apply w-6 h-6 flex items-center justify-center bg-autobot-bg-secondary text-autobot-text-secondary rounded-full text-xs font-semibold;
}

.step-preview.completed .step-number {
  background: var(--color-success-bg);
  color: var(--color-success);
}

.step-preview.running .step-number {
  background: var(--color-primary);
  color: var(--text-inverse);
}

.step-info {
  @apply flex-1 min-w-0;
}

.step-desc {
  @apply block text-autobot-text-secondary text-sm truncate;
}

.step-command {
  @apply block text-autobot-text-muted text-xs font-mono mt-0.5 truncate;
}

.step-status-icon {
  @apply text-lg;
}
</style>
