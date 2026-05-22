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

import Icon from '@/components/ui/Icon.vue'
import { computed, ref, watch } from 'vue'
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
// Edit State
// =============================================================================

/** Whether the inline editor is open */
const isEditing = ref(false)
/** Scratch buffer for the command being edited */
const editedCommand = ref('')
/** Validation error message, empty when valid */
const editError = ref('')
/** The saved override command (null means use original) */
const overriddenCommand = ref<string | null>(null)

// Bug 1 fix: reset all edit state whenever the displayed step changes so that
// an override or open editor from step N never leaks into step N+1.
watch(() => props.currentStep, resetEdit)

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

/** The command that will actually be executed — edited override or original */
const effectiveCommand = computed(() => {
  return overriddenCommand.value ?? props.currentStep?.command ?? ''
})

/** True when the displayed command differs from the original */
const isModified = computed(() => overriddenCommand.value !== null)

// =============================================================================
// Methods
// =============================================================================

function handleExecute(): void {
  if (!props.currentStep) return
  const step: WorkflowStep = { ...props.currentStep, command: effectiveCommand.value }
  logger.info('User confirmed step execution', { modified: isModified.value })
  emit('execute-step', step)
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
  // Bug 2 fix: clear edit state after emitting so the "Edited" badge does not
  // remain visible while the override is no longer in effect.
  resetEdit()
}

function handleClose(): void {
  emit('close')
}

function openEditDialog(): void {
  editedCommand.value = effectiveCommand.value
  editError.value = ''
  isEditing.value = true
  logger.info('User opened step editor')
}

function cancelEdit(): void {
  isEditing.value = false
  editedCommand.value = ''
  editError.value = ''
  logger.info('User cancelled step edit')
}

function saveEdit(): void {
  const trimmed = editedCommand.value.trim()
  if (!trimmed) {
    editError.value = t('terminal.modal.editCommandEmpty')
    return
  }
  overriddenCommand.value = trimmed
  isEditing.value = false
  editError.value = ''
  logger.info('User saved edited command')
}

function resetEdit(): void {
  overriddenCommand.value = null
  isEditing.value = false
  editedCommand.value = ''
  editError.value = ''
  logger.info('User reset command to original')
}
</script>

<template>
  <BaseModal
    v-model="isOpen"
    :title="t('terminal.window.workflowStepConfirmation')"
    size="md"
    :close-on-overlay="false"
    @close="handleClose"
  >
    <div class="step-confirmation" v-if="currentStep">
      <!-- Progress Bar -->
      <div class="step-progress">
        <div class="progress-header">
          <span class="step-counter">
            <Icon name="tasks" />
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
          <Icon name="terminal" />
          {{ t('terminal.window.commandToExecute') }}
          <span v-if="isModified" class="modified-badge">
            <Icon name="pencil-alt" />
            {{ t('terminal.modal.editedBadge') }}
          </span>
          <button
            v-if="!isEditing"
            class="edit-trigger"
            :aria-label="t('terminal.modal.editCommandAriaLabel')"
            @click="openEditDialog"
          >
            <Icon name="pencil-alt" />
            {{ t('terminal.modal.editCommand') }}
          </button>
        </div>
        <code class="command-text">{{ effectiveCommand }}</code>

        <!-- Inline Editor Panel -->
        <div v-if="isEditing" class="edit-panel">
          <label class="edit-label" for="step-edit-textarea">
            {{ t('terminal.modal.editCommandLabel') }}
          </label>
          <textarea
            id="step-edit-textarea"
            v-model="editedCommand"
            class="edit-textarea"
            rows="3"
            :placeholder="t('terminal.modal.editCommandPlaceholder')"
            :aria-describedby="editError ? 'step-edit-error' : undefined"
            @keydown.ctrl.enter.prevent="saveEdit"
            @keydown.escape.prevent="cancelEdit"
          ></textarea>
          <p v-if="editError" id="step-edit-error" class="edit-error" role="alert">
            <Icon name="exclamation-circle" />
            {{ editError }}
          </p>
          <div class="edit-actions">
            <button class="edit-action-btn edit-action-cancel" @click="cancelEdit">
              <Icon name="times" />
              {{ t('terminal.modal.editCancel') }}
            </button>
            <button v-if="isModified" class="edit-action-btn edit-action-reset" @click="resetEdit">
              <Icon name="undo" />
              {{ t('terminal.modal.editReset') }}
            </button>
            <button class="edit-action-btn edit-action-save" @click="saveEdit">
              <Icon name="check" />
              {{ t('terminal.modal.editSave') }}
            </button>
          </div>
        </div>
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
        variant="outline-solid"
        @click="handleTakeControl"
      >
        <Icon name="hand-paper" />
        {{ t('terminal.window.takeControlLabel') }}
      </BaseButton>

      <BaseButton
        v-if="remainingStepsCount > 0"
        variant="outline-solid"
        @click="handleExecuteAll"
      >
        <Icon name="forward" />
        {{ t('terminal.modal.executeAll') }}
      </BaseButton>

      <BaseButton
        variant="secondary"
        @click="handleSkip"
      >
        <Icon name="forward" />
        {{ t('terminal.window.skipLabel') }}
      </BaseButton>

      <BaseButton
        variant="success"
        @click="handleExecute"
      >
        <Icon name="play" />
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
  font-size: var(--text-sm);
}

.progress-percent {
  font-size: var(--text-xs);
  color: var(--text-secondary);
  font-weight: var(--font-medium, 500);
}

.progress-bar {
  height: 0.375rem;
  background: var(--bg-tertiary, #374151);
  border-radius: var(--radius-full);
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  background: var(--color-info, #3b82f6);
  border-radius: var(--radius-full);
  transition: width var(--duration-300) var(--ease-out);
}

/* Step Detail */
.step-description {
  font-size: var(--text-lg);
  font-weight: var(--font-semibold, 600);
  color: var(--text-primary);
  margin: 0 0 var(--spacing-2, 0.5rem) 0;
}

.step-explanation {
  color: var(--text-secondary);
  font-size: var(--text-sm);
  margin: var(--spacing-0);
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
  font-size: var(--text-xs);
  font-weight: var(--font-medium, 500);
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.command-text {
  display: block;
  padding: var(--spacing-3, 0.75rem);
  font-family: var(--font-mono, monospace);
  font-size: var(--text-sm);
  color: var(--color-success, #10b981);
  word-break: break-all;
  white-space: pre-wrap;
}

/* Modified badge */
.modified-badge {
  display: inline-flex;
  align-items: center;
  gap: var(--spacing-1);
  padding: var(--spacing-0-5) var(--spacing-2);
  background: var(--color-warning-bg, rgba(245, 158, 11, 0.15));
  color: var(--color-warning, #f59e0b);
  border-radius: var(--radius-full);
  font-size: 0.6875rem;
  font-weight: var(--font-medium, 500);
  text-transform: none;
  letter-spacing: 0;
}

/* Edit trigger button (inside command-label bar) */
.edit-trigger {
  margin-left: auto;
  display: inline-flex;
  align-items: center;
  gap: var(--spacing-1);
  padding: var(--spacing-0-5) var(--spacing-2);
  background: transparent;
  border: 1px solid var(--border-default);
  border-radius: var(--radius-sm, 0.25rem);
  color: var(--text-secondary);
  font-size: 0.6875rem;
  font-weight: var(--font-medium, 500);
  text-transform: none;
  letter-spacing: 0;
  cursor: pointer;
  transition: color var(--duration-150), border-color var(--duration-150);
}

.edit-trigger:hover {
  color: var(--text-primary);
  border-color: var(--color-info, #3b82f6);
}

/* Inline Edit Panel */
.edit-panel {
  border-top: 1px solid var(--border-default);
  padding: var(--spacing-3, 0.75rem);
  display: flex;
  flex-direction: column;
  gap: var(--spacing-2, 0.5rem);
  background: var(--bg-secondary);
}

.edit-label {
  font-size: var(--text-xs);
  font-weight: var(--font-medium, 500);
  color: var(--text-secondary);
}

.edit-textarea {
  width: 100%;
  font-family: var(--font-mono, monospace);
  font-size: var(--text-sm);
  color: var(--text-primary);
  background: var(--bg-terminal, #1a1b26);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-sm, 0.25rem);
  padding: var(--spacing-2, 0.5rem) var(--spacing-3, 0.75rem);
  resize: vertical;
  line-height: 1.5;
  box-sizing: border-box;
}

.edit-textarea:focus {
  outline: none;
  border-color: var(--color-info, #3b82f6);
  box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.25);
}
.edit-textarea:focus-visible {
  outline: 2px solid var(--color-primary);
  outline-offset: 2px;
}

.edit-error {
  display: flex;
  align-items: center;
  gap: var(--spacing-1, 0.25rem);
  font-size: 0.8125rem;
  color: var(--color-danger, #ef4444);
  margin: var(--spacing-0);
}

.edit-actions {
  display: flex;
  justify-content: flex-end;
  gap: var(--spacing-2, 0.5rem);
}

.edit-action-btn {
  display: inline-flex;
  align-items: center;
  gap: var(--spacing-1);
  padding: 0.3125rem 0.75rem;
  border-radius: var(--radius-sm, 0.25rem);
  font-size: 0.8125rem;
  font-weight: var(--font-medium, 500);
  cursor: pointer;
  border: 1px solid transparent;
  transition: background var(--duration-150), color var(--duration-150);
}

.edit-action-cancel {
  background: transparent;
  border-color: var(--border-default);
  color: var(--text-secondary);
}

.edit-action-cancel:hover {
  color: var(--text-primary);
  border-color: var(--text-secondary);
}

.edit-action-reset {
  background: transparent;
  border-color: var(--border-default);
  color: var(--color-warning, #f59e0b);
}

.edit-action-reset:hover {
  background: var(--color-warning-bg, rgba(245, 158, 11, 0.1));
}

.edit-action-save {
  background: var(--color-info, #3b82f6);
  color: #fff;
}

.edit-action-save:hover {
  background: var(--color-info-dark, #2563eb);
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
  font-size: var(--text-sm);
}

.guide-list {
  margin: var(--spacing-0);
  padding-left: var(--spacing-5);
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
