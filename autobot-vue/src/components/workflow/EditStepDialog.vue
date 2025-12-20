<template>
  <div v-if="show" class="edit-overlay" @click="$emit('cancel')">
    <div class="edit-dialog" @click.stop>
      <div class="edit-header">
        <h4>✏️ Edit Step {{ stepIndex + 1 }}</h4>
        <BaseButton
          variant="ghost"
          size="xs"
          @click="$emit('cancel')"
          class="close-button"
          aria-label="Close dialog"
        >×</BaseButton>
      </div>

      <div class="edit-content">
        <!-- Error Display -->
        <div v-if="error" class="error-message">
          <div class="error-icon">⚠️</div>
          <div class="error-text">{{ error }}</div>
        </div>

        <!-- Success Display -->
        <div v-if="success" class="success-message">
          <div class="success-icon">✅</div>
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
                • {{ reason }}
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
          💾 {{ saving ? 'Saving...' : 'Save Changes' }}
        </BaseButton>
        <BaseButton
          variant="secondary"
          @click="$emit('cancel')"
          :disabled="saving"
          aria-label="Cancel"
        >❌ Cancel</BaseButton>
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
  background: rgba(0, 0, 0, 0.9);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 2000;
}

.edit-dialog {
  background: #1a1a1a;
  border: 2px solid #333;
  border-radius: 12px;
  width: 600px;
  max-width: 90vw;
  max-height: 90vh;
  overflow-y: auto;
  color: #ffffff;
}

.edit-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 20px;
  border-bottom: 1px solid #333;
  background: linear-gradient(135deg, #059669 0%, #047857 100%);
}

.edit-header h4 {
  margin: 0;
  color: #ffffff;
  font-size: 1.1em;
}

.close-button {
  color: #ffffff;
  font-size: 1.5em;
  line-height: 1;
}

.edit-content {
  padding: 20px;
}

.edit-risk-section {
  margin-top: 16px;
}

.edit-risk-indicator {
  padding: 16px;
  border-radius: 8px;
  border-left: 4px solid;
}

.edit-risk-indicator.low {
  background: rgba(34, 197, 94, 0.1);
  border-left-color: #22c55e;
}

.edit-risk-indicator.moderate {
  background: rgba(251, 191, 36, 0.1);
  border-left-color: #fbbf24;
}

.edit-risk-indicator.high {
  background: rgba(239, 68, 68, 0.1);
  border-left-color: #ef4444;
}

.edit-risk-indicator.critical {
  background: rgba(220, 38, 38, 0.1);
  border-left-color: #dc2626;
  animation: pulse 2s infinite;
}

.risk-label {
  font-weight: 600;
  display: block;
  margin-bottom: 8px;
  color: #f3f4f6;
}

.risk-reasons {
  margin-top: 8px;
}

.risk-reason {
  font-size: 0.9em;
  color: #d1d5db;
  margin-bottom: 4px;
}

.edit-actions {
  display: flex;
  gap: 12px;
  padding: 20px;
  border-top: 1px solid #333;
  justify-content: flex-end;
}

.form-field {
  margin-bottom: 16px;
}

.form-field label {
  display: block;
  margin-bottom: 6px;
  font-weight: 600;
  color: #f3f4f6;
}

.form-input,
.form-textarea {
  width: 100%;
  background: #0f1419;
  border: 1px solid #374151;
  color: #ffffff;
  padding: 10px;
  border-radius: 6px;
  font-family: inherit;
}

.form-input:focus,
.form-textarea:focus {
  outline: none;
  border-color: #2563eb;
}

.field-error {
  color: #ef4444;
  font-size: 0.85em;
  margin-top: 4px;
}

.error-message,
.success-message {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 12px;
  border-radius: 6px;
  margin: 16px 0;
  font-size: 14px;
  line-height: 1.4;
}

.error-message {
  background-color: rgba(220, 53, 69, 0.1);
  border: 1px solid rgba(220, 53, 69, 0.3);
  color: #ff6b6b;
}

.success-message {
  background-color: rgba(40, 167, 69, 0.1);
  border: 1px solid rgba(40, 167, 69, 0.3);
  color: #28a745;
}

.error-icon,
.success-icon {
  flex-shrink: 0;
  font-size: 16px;
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
    padding: 16px;
  }

  .edit-content {
    padding: 16px;
  }

  .edit-actions {
    flex-direction: column;
    gap: 8px;
  }

  .form-input,
  .form-textarea {
    font-size: 16px;
  }
}
</style>
