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
.command-section {
  padding: 20px;
  border-bottom: 1px solid #333;
}

.section-label {
  display: block;
  font-weight: 600;
  margin-bottom: 12px;
  color: #f3f4f6;
}

.command-preview {
  display: flex;
  align-items: center;
  gap: 12px;
  background: #0f1419;
  padding: 12px;
  border-radius: 8px;
  border: 1px solid #374151;
}

.command-preview code {
  flex: 1;
  font-family: 'JetBrains Mono', 'Fira Code', monospace;
  background: none;
  color: #22c55e;
}

.command-editor {
  margin-top: 12px;
  border: 1px solid #374151;
  border-radius: 8px;
  background: #0f1419;
}

.command-input {
  width: 100%;
  background: transparent;
  border: none;
  padding: 12px;
  color: #ffffff;
  font-family: 'JetBrains Mono', 'Fira Code', monospace;
  resize: vertical;
}

.command-input:focus {
  outline: none;
}

.editor-actions {
  display: flex;
  gap: 8px;
  padding: 12px;
  border-top: 1px solid #374151;
}

@media (max-width: 768px) {
  .command-preview {
    flex-direction: column;
    align-items: stretch;
    gap: 8px;
  }
}
</style>
