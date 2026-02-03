<template>
  <div class="command-section">
    <label class="section-label">Command to Execute:</label>
    <div class="command-preview">
      <code>{{ command }}</code>
      <BaseButton
        variant="outline"
        size="xs"
        @click="showEditor = !showEditor"
        class="edit-command-btn"
        aria-label="Edit command"
      >
        📝 Edit
      </BaseButton>
    </div>

    <!-- Command Editor -->
    <div v-if="showEditor" class="command-editor">
      <textarea
        v-model="editedCommand"
        class="command-input"
        rows="3"
        placeholder="Edit the command..."
      ></textarea>
      <div class="editor-actions">
        <BaseButton variant="success" size="sm" @click="saveEdit" aria-label="Save edit">
          💾 Save
        </BaseButton>
        <BaseButton variant="secondary" size="sm" @click="cancelEdit" aria-label="Cancel edit">
          ❌ Cancel
        </BaseButton>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss
/**
 * Command Preview Component
 *
 * Displays and allows editing of a command in workflow confirmation.
 * Extracted from AdvancedStepConfirmationModal.vue for better maintainability.
 *
 * Issue #184: Split oversized Vue components
 */

import { ref, watch } from 'vue'
import BaseButton from '@/components/base/BaseButton.vue'

interface Props {
  command: string
}

interface Emits {
  (e: 'save', command: string): void
}

const props = defineProps<Props>()
const emit = defineEmits<Emits>()

const showEditor = ref(false)
const editedCommand = ref(props.command)

watch(() => props.command, (newCommand) => {
  editedCommand.value = newCommand
}, { immediate: true })

const saveEdit = () => {
  if (editedCommand.value.trim()) {
    emit('save', editedCommand.value.trim())
    showEditor.value = false
  }
}

const cancelEdit = () => {
  editedCommand.value = props.command
  showEditor.value = false
}
</script>

<style scoped>
/**
 * Issue #704: Migrated to design tokens
 * All hardcoded colors replaced with CSS custom properties from design-tokens.css
 */
.command-section {
  padding: var(--spacing-5);
  border-bottom: 1px solid var(--border-default);
}

.section-label {
  display: block;
  font-weight: var(--font-semibold);
  margin-bottom: var(--spacing-3);
  color: var(--text-primary);
}

.command-preview {
  display: flex;
  align-items: center;
  gap: var(--spacing-3);
  background: var(--bg-code);
  padding: var(--spacing-3);
  border-radius: var(--radius-lg);
  border: 1px solid var(--border-default);
}

.command-preview code {
  flex: 1;
  font-family: var(--font-mono);
  background: none;
  color: var(--chart-green);
}

.command-editor {
  margin-top: var(--spacing-3);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-lg);
  background: var(--bg-code);
}

.command-input {
  width: 100%;
  background: transparent;
  border: none;
  padding: var(--spacing-3);
  color: var(--text-on-primary);
  font-family: var(--font-mono);
  resize: vertical;
}

.command-input:focus {
  outline: none;
}

.editor-actions {
  display: flex;
  gap: var(--spacing-2);
  padding: var(--spacing-3);
  border-top: 1px solid var(--border-default);
}

@media (max-width: 768px) {
  .command-preview {
    flex-direction: column;
    align-items: stretch;
    gap: var(--spacing-2);
  }
}
</style>
