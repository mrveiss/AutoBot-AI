<template>
  <div class="overseer-plan">
    <!-- Plan Header -->
    <div class="plan-header">
      <div class="plan-title">
        <Icon name="sitemap" aria-hidden="true" />
        <span>{{ $t('chat.overseer.executionPlan') }}</span>
      </div>
      <BaseProgress
        class="plan-progress"
        :value="progressPercentage"
        :label="$t('chat.overseer.stepsProgress', { completed: completedSteps, total: totalSteps })"
        size="sm"
      />
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
          <Icon :name="getStepIcon(step)" aria-hidden="true" />
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
import { BaseProgress } from '@autobot/ui'
import Icon, { type IconName } from '@/components/ui/Icon.vue'


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

const STEP_ICONS: Record<string, IconName> = {
  pending: 'circle',
  running: 'spinner',
  streaming: 'stream',
  explaining: 'brain',
  completed: 'check-circle',
  failed: 'times-circle'
}

const getStepIcon = (step: { step_number: number }): IconName => STEP_ICONS[getStepStatus(step)] || STEP_ICONS.pending
</script>

<style scoped>
/* Mockup: the plan is a card; each step row carries its status as a tinted icon. */
.overseer-plan {
  margin-block-end: var(--aui-space-4);
  padding: var(--aui-space-4);
  border: 1px solid var(--aui-color-border);
  border-radius: var(--aui-radius-lg);
  background: var(--aui-color-surface-raised);
}
.plan-header { display: flex; align-items: center; gap: var(--aui-space-4); margin-block-end: var(--aui-space-3); padding-block-end: var(--aui-space-3); border-block-end: 1px solid var(--aui-color-border); }
.plan-title { display: flex; align-items: center; gap: var(--aui-space-2); color: var(--aui-color-primary); font-weight: var(--aui-font-weight-semibold); }
.plan-progress { flex: 1; }
.progress-text { color: var(--aui-color-text-muted); font-size: var(--aui-text-sm); }
.plan-analysis {
  display: flex;
  align-items: flex-start;
  gap: var(--aui-space-2);
  margin-block-end: var(--aui-space-4);
  padding: var(--aui-space-2) var(--aui-space-3);
  border-radius: var(--aui-radius-md);
  background: color-mix(in srgb, var(--aui-color-info) 10%, var(--aui-color-surface-raised));
  color: var(--aui-color-text-muted);
  font-size: var(--aui-text-sm);
}
.plan-analysis :deep(svg) { color: var(--aui-color-warning); }
.steps-preview { display: flex; flex-direction: column; gap: var(--aui-space-2); }
.step-preview {
  display: flex;
  align-items: center;
  gap: var(--aui-space-3);
  padding: var(--aui-space-2) var(--aui-space-3);
  border: 1px solid var(--aui-color-border);
  border-radius: var(--aui-radius-md);
  background: var(--aui-color-surface);
}
.step-number {
  display: flex;
  align-items: center;
  justify-content: center;
  inline-size: var(--aui-space-6);
  block-size: var(--aui-space-6);
  border-radius: var(--aui-radius-full);
  background: var(--aui-color-surface-sunken);
  color: var(--aui-color-text-muted);
  font-size: var(--aui-text-xs);
  font-weight: var(--aui-font-weight-semibold);
}
.step-info { flex: 1; min-inline-size: 0; }
.step-desc { display: block; overflow: hidden; color: var(--aui-color-text-muted); font-size: var(--aui-text-sm); text-overflow: ellipsis; white-space: nowrap; }
.step-command { display: block; overflow: hidden; color: var(--aui-color-text-muted); font-family: var(--aui-font-mono); font-size: var(--aui-text-xs); text-overflow: ellipsis; white-space: nowrap; }
.step-preview.running { border-color: var(--aui-color-info); }
.step-preview.running .step-desc { color: var(--aui-color-text); font-weight: var(--aui-font-weight-semibold); }
.step-preview.completed .step-status-icon { color: var(--aui-color-success); }
.step-preview.failed .step-status-icon { color: var(--aui-color-error); }
.step-preview.running .step-status-icon { color: var(--aui-color-info); }
.step-preview.pending .step-status-icon { color: var(--aui-color-text-muted); }
.step-status-icon { font-size: var(--aui-text-lg); }
</style>
