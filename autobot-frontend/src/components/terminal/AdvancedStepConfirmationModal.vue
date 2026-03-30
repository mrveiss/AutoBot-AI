<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<!-- Author: mrveiss -->

<script setup lang="ts">
/**
 * Advanced Step Confirmation Modal (#2674)
 *
 * Displays workflow step details and allows the user to confirm, skip,
 * take manual control, or execute all remaining steps. Used by
 * TerminalWindow.vue during automated workflow execution.
 */

import { computed } from 'vue'
import BaseModal from '@/components/ui/BaseModal.vue'
import BaseButton from '@/components/base/BaseButton.vue'
import { useI18n } from 'vue-i18n'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('AdvancedStepConfirmationModal')

// =============================================================================
// Type Definitions
// =============================================================================

interface WorkflowStep {
  command: string
  description?: string
  explanation?: string
  stepNumber?: number
  totalSteps?: number
  requiresConfirmation?: boolean
}

// =============================================================================
// Props & Emits
// =============================================================================

const props = defineProps<{
  /** Whether the modal is visible */
  visible: boolean
  /** The current step awaiting confirmation */
  currentStep: WorkflowStep | null
  /** Zero-based index of the current step */
  currentStepIndex: number
  /** Full list of workflow steps */
  workflowSteps: WorkflowStep[]
  /** Terminal session ID */
  sessionId: string
}>()

const emit = defineEmits<{
  (e: 'execute-step', step: WorkflowStep): void
  (e: 'skip-step', index: number): void
  (e: 'take-manual-control'): void
  (e: 'execute-all'): void
  (e: 'close'): void
}>()

const { t } = useI18n()

// =============================================================================
// Computed
// =============================================================================

const isOpen = computed({
  get: () => props.visible,
  set: () => emit('close')
})

const currentStepNumber = computed(() => {
  return props.currentStep?.stepNumber ?? props.currentStepIndex + 1
})

const totalSteps = computed(() => {
  return props.currentStep?.totalSteps ?? props.workflowSteps.length
})

const remainingStepsCount = computed(() => {
  return Math.max(0, props.workflowSteps.length - props.currentStepIndex - 1)
})

const progressPercent = computed(() => {
  if (totalSteps.value <= 0) return 0
  return Math.round((currentStepNumber.value / totalSteps.value) * 100)
})

// =============================================================================
// Methods
// =============================================================================

function handleExecute(): void {
  if (!props.currentStep) return
  logger.info('User confirmed step execution')
  emit('execute-step', props.currentStep)
}

function handleSkip(): void {
  logger.info('User skipped step')
  emit('skip-step', props.currentStepIndex)
}

function handleTakeControl(): void {
  logger.info('User took manual control')
  emit('take-manual-control')
}

function handleExecuteAll(): void {
  logger.info('User chose to execute all remaining steps')
  emit('execute-all')
}

function handleClose(): void {
  emit('close')
}
</script>

<template>
  <BaseModal
    v-model="isOpen"
    :title="t('terminal.window.workflowStepConfirmation')"
    size="medium"
    :close-on-overlay="false"
    @close="handleClose"
  >
    <div class="step-confirmation" v-if="currentStep">
      <!-- Progress Bar -->
      <div class="step-progress">
        <div class="progress-header">
          <span class="step-counter">
            <i class="fas fa-tasks" aria-hidden="true"></i>
            {{ t('terminal.window.stepProgress', { current: currentStepNumber, total: totalSteps }) }}
          </span>
          <span class="progress-percent">{{ progressPercent }}%</span>
        </div>
        <div
          class="progress-bar"
          role="progressbar"
          :aria-valuenow="progressPercent"
          aria-valuemin="0"
          aria-valuemax="100"
        >
          <div class="progress-fill" :style="{ width: progressPercent + '%' }"></div>
        </div>
      </div>

      <!-- Step Description -->
      <div class="step-detail">
        <h4 class="step-description">
          {{ currentStep.description || currentStep.command }}
        </h4>
        <p v-if="currentStep.explanation" class="step-explanation">
          {{ currentStep.explanation }}
        </p>
        <p v-else class="step-explanation">
          {{ t('terminal.window.aiWantsToExecute') }}
        </p>
      </div>

      <!-- Command Preview -->
      <div class="command-preview">
        <div class="command-label">
          <i class="fas fa-terminal" aria-hidden="true"></i>
          {{ t('terminal.window.commandToExecute') }}
        </div>
        <code class="command-text">{{ currentStep.command }}</code>
      </div>

      <!-- Action Guide -->
      <div class="action-guide">
        <p class="guide-title">
          <strong>{{ t('terminal.window.chooseAction') }}</strong>
        </p>
        <ul class="guide-list">
          <li>
            <strong>{{ t('terminal.window.executeLabel') }}</strong>
            {{ t('terminal.window.executeDesc') }}
          </li>
          <li>
            <strong>{{ t('terminal.window.skipLabel') }}</strong>
            {{ t('terminal.window.skipDesc') }}
          </li>
          <li>
            <strong>{{ t('terminal.window.takeControlLabel') }}</strong>
            {{ t('terminal.window.takeControlDesc') }}
          </li>
        </ul>
      </div>
    </div>

    <!-- No step data fallback -->
    <div v-else class="step-confirmation-empty">
      <p>{{ t('terminal.window.noStepData') }}</p>
    </div>

    <template #actions>
      <BaseButton
        variant="outline"
        @click="handleTakeControl"
      >
        <i class="fas fa-hand-paper" aria-hidden="true"></i>
        {{ t('terminal.window.takeControlLabel') }}
      </BaseButton>

      <BaseButton
        v-if="remainingStepsCount > 0"
        variant="outline"
        @click="handleExecuteAll"
      >
        <i class="fas fa-forward" aria-hidden="true"></i>
        {{ t('terminal.modal.executeAll') }}
      </BaseButton>

      <BaseButton
        variant="secondary"
        @click="handleSkip"
      >
        <i class="fas fa-step-forward" aria-hidden="true"></i>
        {{ t('terminal.window.skipLabel') }}
      </BaseButton>

      <BaseButton
        variant="success"
        @click="handleExecute"
      >
        <i class="fas fa-play" aria-hidden="true"></i>
        {{ t('terminal.window.executeLabel') }}
      </BaseButton>
    </template>
  </BaseModal>
</template>

<style scoped>
.step-confirmation {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-5, 1.25rem);
}

/* Progress */
.step-progress {
  background: var(--bg-secondary);
  border-radius: var(--radius-md, 0.375rem);
  padding: var(--spacing-4, 1rem);
}

.progress-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--spacing-2, 0.5rem);
}

.step-counter {
  display: flex;
  align-items: center;
  gap: var(--spacing-2, 0.5rem);
  font-weight: var(--font-semibold, 600);
  color: var(--text-primary);
  font-size: 0.875rem;
}

.progress-percent {
  font-size: 0.75rem;
  color: var(--text-secondary);
  font-weight: var(--font-medium, 500);
}

.progress-bar {
  height: 0.375rem;
  background: var(--bg-tertiary, #374151);
  border-radius: 9999px;
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  background: var(--color-info, #3b82f6);
  border-radius: 9999px;
  transition: width 0.3s ease;
}

/* Step Detail */
.step-description {
  font-size: 1.125rem;
  font-weight: var(--font-semibold, 600);
  color: var(--text-primary);
  margin: 0 0 var(--spacing-2, 0.5rem) 0;
}

.step-explanation {
  color: var(--text-secondary);
  font-size: 0.875rem;
  margin: 0;
  line-height: 1.5;
}

/* Command Preview */
.command-preview {
  background: var(--bg-terminal, #1a1b26);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md, 0.375rem);
  overflow: hidden;
}

.command-label {
  display: flex;
  align-items: center;
  gap: var(--spacing-2, 0.5rem);
  padding: var(--spacing-2, 0.5rem) var(--spacing-3, 0.75rem);
  background: var(--bg-tertiary, #374151);
  font-size: 0.75rem;
  font-weight: var(--font-medium, 500);
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.command-text {
  display: block;
  padding: var(--spacing-3, 0.75rem);
  font-family: var(--font-mono, monospace);
  font-size: 0.875rem;
  color: var(--color-success, #10b981);
  word-break: break-all;
  white-space: pre-wrap;
}

/* Action Guide */
.action-guide {
  background: var(--bg-secondary);
  border-radius: var(--radius-md, 0.375rem);
  padding: var(--spacing-4, 1rem);
}

.guide-title {
  margin: 0 0 var(--spacing-2, 0.5rem) 0;
  color: var(--text-primary);
  font-size: 0.875rem;
}

.guide-list {
  margin: 0;
  padding-left: 1.25rem;
  display: flex;
  flex-direction: column;
  gap: var(--spacing-1, 0.25rem);
}

.guide-list li {
  font-size: 0.8125rem;
  color: var(--text-secondary);
  line-height: 1.5;
}

.guide-list li strong {
  color: var(--text-primary);
}

/* Empty State */
.step-confirmation-empty {
  text-align: center;
  padding: var(--spacing-8, 2rem);
  color: var(--text-secondary);
}
</style>
