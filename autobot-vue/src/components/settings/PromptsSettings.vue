<template>
  <div v-if="promptsSettings && isSettingsLoaded" class="settings-section">
    <h3>Prompt Management</h3>

    <!-- Prompts List -->
    <div class="prompts-list">
      <div
        v-for="prompt in promptsSettings.list || []"
        :key="prompt.id"
        class="prompt-item"
      >
        <h4>{{ prompt.name || prompt.id }}</h4>
        <p>{{ prompt.description || 'No description available' }}</p>
        <button @click="selectPrompt(prompt)" aria-label="Edit prompt">
          Edit
        </button>
      </div>
    </div>

    <!-- No Prompts Message -->
    <EmptyState
      v-if="!promptsSettings.list || promptsSettings.list.length === 0"
      icon="fas fa-file-code"
      message="No prompts available."
    >
      <template #actions>
        <button @click="$emit('load-prompts')" aria-label="Load prompts" class="btn-primary">
          Load Prompts
        </button>
      </template>
    </EmptyState>

    <!-- Prompt Editor -->
    <div
      v-if="promptsSettings.selectedPrompt"
      class="prompt-editor"
    >
      <h4>Editing: {{ promptsSettings.selectedPrompt.name || promptsSettings.selectedPrompt.id }}</h4>
      <textarea
        :value="promptsSettings.editedContent || ''"
        @input="handleTextareaInput"
        rows="10"
        placeholder="Edit prompt content here..."
      ></textarea>
      <div class="editor-actions">
        <button @click="$emit('save-prompt')" aria-label="Save changes">
          Save Changes
        </button>
        <button
          @click="$emit('revert-prompt-to-default', promptsSettings.selectedPrompt.id)"
          aria-label="Revert to default"
        >
          Revert to Default
        </button>
        <button @click="clearSelectedPrompt()" aria-label="Cancel">
          Cancel
        </button>
      </div>
    </div>

    <!-- Prompts Controls -->
    <div class="prompts-controls">
      <button
        class="control-button small"
        @click="$emit('load-prompts')"
        aria-label="Load prompts"
      >
        Load Prompts
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import EmptyState from '@/components/ui/EmptyState.vue'

interface Prompt {
  id: string
  name?: string
  description?: string
}

interface PromptsSettings {
  list: Prompt[]
  selectedPrompt: Prompt | null
  editedContent: string
}

interface Props {
  promptsSettings: PromptsSettings | null
  isSettingsLoaded: boolean
}

interface Emits {
  (e: 'prompt-selected', prompt: Prompt): void
  (e: 'edited-content-changed', content: string): void
  (e: 'selected-prompt-cleared'): void
  (e: 'load-prompts'): void
  (e: 'save-prompt'): void
  (e: 'revert-prompt-to-default', id: string): void
}

const props = defineProps<Props>()
const emit = defineEmits<Emits>()

const selectPrompt = (prompt: Prompt) => {
  emit('prompt-selected', prompt)
}

const updateEditedContent = (content: string) => {
  emit('edited-content-changed', content)
}

// Issue #156 Fix: Typed event handler to replace inline $event.target usage
const handleTextareaInput = (event: Event) => {
  const target = event.target as HTMLTextAreaElement
  updateEditedContent(target.value)
}

const clearSelectedPrompt = () => {
  emit('selected-prompt-cleared')
}
</script>

<style scoped>
/**
 * Issue #704: CSS Design System - Using design tokens
 * All colors reference CSS custom properties from design-tokens.css
 */

.settings-section {
  margin-bottom: var(--spacing-8);
  background: var(--bg-card);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-lg);
  padding: var(--spacing-6);
  box-shadow: var(--shadow-sm);
}

.settings-section h3 {
  margin: 0 0 var(--spacing-5) 0;
  color: var(--text-primary);
  font-weight: var(--font-semibold);
  font-size: var(--text-lg);
  border-bottom: 2px solid var(--color-primary);
  padding-bottom: var(--spacing-2);
}

.prompts-list {
  margin-bottom: var(--spacing-5);
}

.prompt-item {
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  padding: var(--spacing-4);
  margin-bottom: var(--spacing-3);
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: var(--spacing-4);
}

.prompt-item h4 {
  margin: 0 0 var(--spacing-2) 0;
  color: var(--text-primary);
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
}

.prompt-item p {
  margin: 0;
  color: var(--text-secondary);
  font-size: var(--text-xs);
  flex: 1;
}

.prompt-item button {
  background: var(--color-primary);
  color: var(--text-on-primary);
  border: none;
  padding: var(--spacing-1-5) var(--spacing-3);
  border-radius: var(--radius-sm);
  cursor: pointer;
  font-size: var(--text-xs);
  font-weight: var(--font-medium);
  transition: background-color var(--duration-200) ease;
  flex-shrink: 0;
}

.prompt-item button:hover {
  background: var(--color-primary-dark);
}

.prompt-editor {
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  padding: var(--spacing-5);
  margin-bottom: var(--spacing-5);
}

.prompt-editor h4 {
  margin: 0 0 var(--spacing-4) 0;
  color: var(--text-primary);
  font-size: var(--text-base);
  font-weight: var(--font-semibold);
}

.prompt-editor textarea {
  width: 100%;
  min-height: 200px;
  padding: var(--spacing-3);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-sm);
  font-family: var(--font-mono);
  font-size: var(--text-xs);
  line-height: var(--leading-normal);
  resize: vertical;
  box-sizing: border-box;
  background: var(--bg-primary);
  color: var(--text-primary);
}

.prompt-editor textarea:focus {
  outline: none;
  border-color: var(--color-primary);
  box-shadow: var(--shadow-focus);
}

.editor-actions {
  display: flex;
  gap: var(--spacing-3);
  margin-top: var(--spacing-4);
  flex-wrap: wrap;
}

.editor-actions button {
  border: none;
  padding: var(--spacing-2-5) var(--spacing-4);
  border-radius: var(--radius-md);
  cursor: pointer;
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
  transition: background-color var(--duration-200) ease;
}

.editor-actions button:first-child {
  background: var(--color-success);
  color: var(--text-on-success);
}

.editor-actions button:first-child:hover {
  background: var(--color-success-dark);
}

.editor-actions button:nth-child(2) {
  background: var(--color-warning);
  color: var(--text-on-warning);
}

.editor-actions button:nth-child(2):hover {
  background: var(--color-warning-dark);
}

.editor-actions button:last-child {
  background: var(--text-tertiary);
  color: var(--text-on-primary);
}

.editor-actions button:last-child:hover {
  background: var(--text-secondary);
}

.prompts-controls {
  display: flex;
  justify-content: flex-end;
  gap: var(--spacing-3);
}

.control-button {
  background: var(--color-primary);
  color: var(--text-on-primary);
  border: none;
  padding: var(--spacing-2-5) var(--spacing-4);
  border-radius: var(--radius-md);
  cursor: pointer;
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
  transition: background-color var(--duration-200) ease;
}

.control-button:hover {
  background: var(--color-primary-dark);
}

.control-button.small {
  padding: var(--spacing-2) var(--spacing-3);
  font-size: var(--text-xs);
}

/* Mobile responsive */
@media (max-width: 768px) {
  .settings-section {
    padding: var(--spacing-4);
    margin-bottom: var(--spacing-5);
  }

  .prompt-item {
    flex-direction: column;
    align-items: flex-start;
    gap: var(--spacing-3);
  }

  .prompt-item button {
    align-self: flex-end;
  }

  .editor-actions {
    justify-content: stretch;
  }

  .editor-actions button {
    flex: 1;
  }

  .prompts-controls {
    justify-content: stretch;
  }

  .control-button {
    flex: 1;
  }
}
</style>