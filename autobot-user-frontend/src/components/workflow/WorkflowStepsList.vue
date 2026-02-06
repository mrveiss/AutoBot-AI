<template>
  <div class="workflow-management">
    <div class="section-header">
      <h4>📋 Workflow Steps Management</h4>
      <BaseButton
        variant="outline"
        size="sm"
        @click="showManager = !showManager"
        :aria-label="showManager ? '▼ Hide Steps' : '▶ Show Steps'"
      >
        {{ showManager ? '▼ Hide' : '▶ Show' }}
      </BaseButton>
    </div>

    <div v-if="showManager" class="steps-manager">
      <!-- Steps List -->
      <div class="steps-list">
        <div
          v-for="(step, index) in steps"
          :key="step.id || index"
          class="step-item"
          :class="{ 'current': index === currentIndex, 'completed': index < currentIndex }"
        >
          <div class="step-controls">
            <BaseButton
              variant="outline"
              size="xs"
              @click="$emit('move-up', index)"
              :disabled="index === 0"
              aria-label="Move step up"
            >↑</BaseButton>
            <BaseButton
              variant="outline"
              size="xs"
              @click="$emit('move-down', index)"
              :disabled="index === steps.length - 1"
              aria-label="Move step down"
            >↓</BaseButton>
            <BaseButton
              variant="danger"
              size="xs"
              @click="$emit('delete', index)"
              :disabled="steps.length <= 1"
              aria-label="Delete step"
            >🗑️</BaseButton>
          </div>

          <div class="step-info">
            <div class="step-number">{{ index + 1 }}</div>
            <div class="step-details">
              <div class="step-title">{{ step.description }}</div>
              <div class="step-command"><code>{{ step.command }}</code></div>
            </div>
          </div>

          <div class="step-actions">
            <BaseButton
              variant="outline"
              size="xs"
              @click="$emit('edit', index)"
              aria-label="Edit step"
            >✏️ Edit</BaseButton>
            <BaseButton
              variant="success"
              size="xs"
              @click="$emit('insert-after', index)"
              aria-label="Insert step after"
            >➕ Insert After</BaseButton>
          </div>
        </div>
      </div>

      <!-- Add New Step -->
      <div class="add-step-section">
        <BaseButton
          variant="success"
          @click="showAddForm = !showAddForm"
          class="add-step-btn"
          aria-label="Add new step"
        >
          ➕ Add New Step
        </BaseButton>

        <div v-if="showAddForm" class="add-step-form">
          <div class="form-field">
            <label>Description:</label>
            <input
              v-model="newStep.description"
              type="text"
              class="form-input"
              placeholder="Enter step description..."
            />
          </div>

          <div class="form-field">
            <label>Command:</label>
            <textarea
              v-model="newStep.command"
              class="form-textarea"
              rows="2"
              placeholder="Enter command to execute..."
            ></textarea>
          </div>

          <div class="form-field">
            <label>Explanation (optional):</label>
            <textarea
              v-model="newStep.explanation"
              class="form-textarea"
              rows="2"
              placeholder="Explain what this step does..."
            ></textarea>
          </div>

          <div class="form-actions">
            <BaseButton variant="success" @click="addStep" aria-label="Add step">
              ✅ Add Step
            </BaseButton>
            <BaseButton variant="secondary" @click="cancelAdd" aria-label="Cancel">
              ❌ Cancel
            </BaseButton>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss
/**
 * Workflow Steps List Component
 *
 * Displays and manages workflow steps with reordering, editing, and adding.
 * Extracted from AdvancedStepConfirmationModal.vue for better maintainability.
 *
 * Issue #184: Split oversized Vue components
 */

import { ref } from 'vue'
import BaseButton from '@/components/base/BaseButton.vue'

interface WorkflowStep {
  id?: string
  description: string
  command: string
  explanation?: string
  status?: 'pending' | 'executing' | 'completed' | 'failed' | 'skipped'
}

interface Props {
  steps: WorkflowStep[]
  currentIndex: number
}

interface Emits {
  (e: 'move-up', index: number): void
  (e: 'move-down', index: number): void
  (e: 'delete', index: number): void
  (e: 'edit', index: number): void
  (e: 'insert-after', index: number): void
  (e: 'add', step: WorkflowStep): void
}

defineProps<Props>()
const emit = defineEmits<Emits>()

const showManager = ref(false)
const showAddForm = ref(false)
const newStep = ref({ description: '', command: '', explanation: '' })

const addStep = () => {
  if (!newStep.value.description.trim() || !newStep.value.command.trim()) return

  emit('add', { ...newStep.value })
  newStep.value = { description: '', command: '', explanation: '' }
  showAddForm.value = false
}

const cancelAdd = () => {
  newStep.value = { description: '', command: '', explanation: '' }
  showAddForm.value = false
}
</script>

<style scoped>
/* Issue #704: Migrated to CSS design tokens */
.workflow-management {
  border-bottom: 1px solid var(--border-primary);
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 20px;
}

.section-header h4 {
  margin: 0;
  color: var(--text-primary);
}

.steps-manager {
  padding: 0 20px 20px;
}

.steps-list {
  margin-bottom: 20px;
}

.step-item {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 16px;
  margin-bottom: 12px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-secondary);
  border-radius: 8px;
}

.step-item.current {
  border-color: var(--color-primary);
  background: var(--color-primary-alpha-10);
}

.step-item.completed {
  border-color: var(--color-success);
  background: var(--color-success-alpha-10);
}

.step-controls {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.step-info {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 16px;
}

.step-number {
  background: var(--color-primary);
  color: var(--text-on-primary);
  width: 32px;
  height: 32px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 600;
  font-size: 0.9em;
}

.step-details {
  flex: 1;
}

.step-title {
  font-weight: 600;
  margin-bottom: 4px;
  color: var(--text-primary);
}

.step-command {
  font-size: 0.85em;
  color: var(--text-tertiary);
}

.step-command code {
  background: var(--bg-tertiary);
  padding: 2px 6px;
  border-radius: 4px;
  font-family: 'JetBrains Mono', 'Fira Code', monospace;
}

.step-actions {
  display: flex;
  gap: 8px;
}

.add-step-section {
  border-top: 1px solid var(--border-secondary);
  padding-top: 20px;
}

.add-step-form {
  margin-top: 16px;
  padding: 16px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-secondary);
  border-radius: 8px;
}

.form-field {
  margin-bottom: 16px;
}

.form-field label {
  display: block;
  margin-bottom: 6px;
  font-weight: 600;
  color: var(--text-primary);
}

.form-input,
.form-textarea {
  width: 100%;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-secondary);
  color: var(--text-primary);
  padding: 10px;
  border-radius: 6px;
  font-family: inherit;
}

.form-input:focus,
.form-textarea:focus {
  outline: none;
  border-color: var(--color-primary);
}

.form-actions {
  display: flex;
  gap: 12px;
}

@media (max-width: 1024px) {
  .step-item {
    flex-direction: column;
    align-items: flex-start;
    gap: 12px;
  }

  .step-info {
    width: 100%;
    flex-direction: column;
    align-items: flex-start;
    gap: 8px;
  }

  .step-details {
    width: 100%;
  }

  .step-actions {
    width: 100%;
    justify-content: flex-start;
  }
}

@media (max-width: 768px) {
  .step-item {
    padding: 12px;
  }

  .step-controls {
    flex-direction: row;
    gap: 6px;
    order: 3;
    width: 100%;
    justify-content: flex-start;
  }

  .step-info {
    order: 1;
    margin-bottom: 8px;
  }

  .step-actions {
    order: 2;
    margin-bottom: 8px;
  }

  .form-actions {
    flex-direction: column;
    gap: 8px;
  }
}
</style>
