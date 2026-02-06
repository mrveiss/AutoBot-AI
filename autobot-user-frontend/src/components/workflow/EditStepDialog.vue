<template>
  <div v-if="show" class="edit-overlay" @click="$emit('cancel')">
    <div class="edit-dialog" @click.stop>
      <div class="edit-header">
        <h4>Edit Step {{ stepIndex + 1 }}</h4>
        <BaseButton
          variant="ghost"
          size="xs"
          @click="$emit('cancel')"
          class="close-button"
          aria-label="Close dialog"
        >x</BaseButton>
      </div>

      <div class="edit-content">
        <!-- Error Display -->
        <div v-if="error" class="error-message">
          <div class="error-icon">!</div>
          <div class="error-text">{{ error }}</div>
        </div>

        <!-- Success Display -->
        <div v-if="success" class="success-message">
          <div class="success-icon">OK</div>
          <div class="success-text">{{ success }}</div>
        </div>

        <div class="form-field">
          <label for="edit-description">Description:</label>
          <input
            id="edit-description"
            ref="descriptionInput"
            :value="step.description"
            @input="updateField('description', ($event.target as HTMLInputElement).value)"
            type="text"
            class="form-input"
            placeholder="Enter step description..."
          />
          <div v-if="validationErrors.description" class="field-error">
            {{ validationErrors.description }}
          </div>
        </div>

        <div class="form-field">
          <label for="edit-command">Command:</label>
          <textarea
            id="edit-command"
            :value="step.command"
            @input="updateField('command', ($event.target as HTMLTextAreaElement).value)"
            class="form-textarea"
            rows="3"
            placeholder="Enter command to execute..."
          ></textarea>
          <div v-if="validationErrors.command" class="field-error">
            {{ validationErrors.command }}
          </div>
        </div>

        <div class="form-field">
          <label for="edit-explanation">Explanation (optional):</label>
          <textarea
            id="edit-explanation"
            :value="step.explanation"
            @input="updateField('explanation', ($event.target as HTMLTextAreaElement).value)"
            class="form-textarea"
            rows="2"
            placeholder="Explain what this step does..."
          ></textarea>
        </div>

        <!-- Live Risk Assessment -->
        <div class="edit-risk-section">
          <div class="edit-risk-indicator" :class="riskLevel">
            <span class="risk-label">Live Risk Assessment: {{ riskLevel.toUpperCase() }}</span>
            <div class="risk-reasons">
              <div v-for="reason in riskReasons" :key="reason" class="risk-reason">
                - {{ reason }}
              </div>
            </div>
          </div>
        </div>
      </div>

      <div class="edit-actions">
        <BaseButton
          variant="success"
          @click="$emit('save')"
          :disabled="!isFormValid || saving"
          :loading="saving"
          aria-label="Save changes"
        >
          {{ saving ? 'Saving...' : 'Save Changes' }}
        </BaseButton>
        <BaseButton
          variant="secondary"
          @click="$emit('cancel')"
          :disabled="saving"
          aria-label="Cancel"
        >Cancel</BaseButton>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss
/**
 * Edit Step Dialog Component
 *
 * Dialog for editing a workflow step with live validation and risk assessment.
 * Extracted from AdvancedStepConfirmationModal.vue for better maintainability.
 *
 * Issue #184: Split oversized Vue components
 * Issue #704: Migrated to design tokens
 */

import { ref, computed, onMounted, nextTick } from 'vue'
import BaseButton from '@/components/base/BaseButton.vue'

interface EditingStep {
  description: string
  command: string
  explanation: string
}

interface Props {
  show: boolean
  stepIndex: number
  step: EditingStep
  saving?: boolean
  error?: string
  success?: string
  validationErrors?: Record<string, string>
}

interface Emits {
  (e: 'cancel'): void
  (e: 'save'): void
  (e: 'update', field: keyof EditingStep, value: string): void
}

const props = withDefaults(defineProps<Props>(), {
  saving: false,
  error: '',
  success: '',
  validationErrors: () => ({})
})

const emit = defineEmits<Emits>()

const descriptionInput = ref<HTMLInputElement | null>(null)

const isFormValid = computed(() => {
  return props.step.description.trim() !== '' &&
         props.step.command.trim() !== '' &&
         Object.keys(props.validationErrors).length === 0
})

const riskLevel = computed(() => {
  if (!props.step?.command) return 'low'
  const command = props.step.command.toLowerCase()

  if (command.includes('rm -rf') || command.includes('format') || command.includes('delete')) return 'critical'
  if (command.includes('sudo') || command.includes('chmod 777') || command.includes('chown')) return 'high'
  if (command.includes('install') || command.includes('update') || command.includes('modify')) return 'moderate'

  return 'low'
})

const riskReasons = computed(() => {
  if (!props.step?.command) return []
  const command = props.step.command.toLowerCase()
  const reasons: string[] = []

  if (command.includes('rm -rf')) reasons.push('Recursive file deletion detected')
  if (command.includes('sudo')) reasons.push('Administrative privileges required')
  if (command.includes('chmod 777')) reasons.push('Permissive file permissions')
  if (command.includes('install')) reasons.push('Software installation/modification')
  if (command.includes('format')) reasons.push('Disk formatting operation')

  return reasons
})

const updateField = (field: keyof EditingStep, value: string) => {
  emit('update', field, value)
}

onMounted(async () => {
  if (props.show) {
    await nextTick()
    descriptionInput.value?.focus()
  }
})
</script>

<style scoped>
.edit-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: var(--overlay-backdrop);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: var(--z-modal);
}

.edit-dialog {
  background: var(--bg-primary);
  border: 2px solid var(--border-default);
  border-radius: var(--radius-xl);
  width: 600px;
  max-width: 90vw;
  max-height: 90vh;
  overflow-y: auto;
  color: var(--text-primary);
}

.edit-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--spacing-5);
  border-bottom: 1px solid var(--border-default);
  background: linear-gradient(135deg, var(--color-success-hover) 0%, var(--color-success-dark) 100%);
}

.edit-header h4 {
  margin: 0;
  color: var(--text-on-success);
  font-size: var(--text-lg);
  font-weight: var(--font-semibold);
}

.close-button {
  color: var(--text-on-success);
  font-size: var(--text-2xl);
  line-height: var(--leading-none);
}

.edit-content {
  padding: var(--spacing-5);
}

.edit-risk-section {
  margin-top: var(--spacing-4);
}

.edit-risk-indicator {
  padding: var(--spacing-4);
  border-radius: var(--radius-lg);
  border-left: 4px solid;
}

.edit-risk-indicator.low {
  background: var(--color-success-bg);
  border-left-color: var(--chart-green);
}

.edit-risk-indicator.moderate {
  background: var(--color-warning-bg);
  border-left-color: var(--color-warning-light);
}

.edit-risk-indicator.high {
  background: var(--color-error-bg);
  border-left-color: var(--color-error);
}

.edit-risk-indicator.critical {
  background: var(--color-error-bg);
  border-left-color: var(--color-error-hover);
  animation: pulse 2s infinite;
}

.risk-label {
  font-weight: var(--font-semibold);
  display: block;
  margin-bottom: var(--spacing-2);
  color: var(--text-primary);
}

.risk-reasons {
  margin-top: var(--spacing-2);
}

.risk-reason {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  margin-bottom: var(--spacing-1);
}

.edit-actions {
  display: flex;
  gap: var(--spacing-3);
  padding: var(--spacing-5);
  border-top: 1px solid var(--border-default);
  justify-content: flex-end;
}

.form-field {
  margin-bottom: var(--spacing-4);
}

.form-field label {
  display: block;
  margin-bottom: var(--spacing-1-5);
  font-weight: var(--font-semibold);
  color: var(--text-primary);
}

.form-input,
.form-textarea {
  width: 100%;
  background: var(--bg-primary);
  border: 1px solid var(--border-default);
  color: var(--text-primary);
  padding: var(--spacing-2-5);
  border-radius: var(--radius-md);
  font-family: inherit;
}

.form-input:focus,
.form-textarea:focus {
  outline: none;
  border-color: var(--color-info-hover);
}

.field-error {
  color: var(--color-error);
  font-size: var(--text-sm);
  margin-top: var(--spacing-1);
}

.error-message,
.success-message {
  display: flex;
  align-items: flex-start;
  gap: var(--spacing-2);
  padding: var(--spacing-3);
  border-radius: var(--radius-md);
  margin: var(--spacing-4) 0;
  font-size: var(--text-sm);
  line-height: var(--leading-snug);
}

.error-message {
  background-color: var(--color-error-bg);
  border: 1px solid var(--color-error-border);
  color: var(--color-error-light);
}

.success-message {
  background-color: var(--color-success-bg);
  border: 1px solid var(--color-success-border);
  color: var(--color-success);
}

.error-icon,
.success-icon {
  flex-shrink: 0;
  font-size: var(--text-base);
  font-weight: var(--font-bold);
}

.error-text,
.success-text {
  flex: 1;
  word-break: break-word;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.8; }
}

@media (max-width: 768px) {
  .edit-dialog {
    width: 100vw;
    max-width: 100vw;
    margin: 0;
    border-radius: 0;
    max-height: 100vh;
  }

  .edit-header {
    padding: var(--spacing-4);
  }

  .edit-content {
    padding: var(--spacing-4);
  }

  .edit-actions {
    flex-direction: column;
    gap: var(--spacing-2);
  }

  .form-input,
  .form-textarea {
    font-size: var(--text-base);
  }
}
</style>
