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
.settings-section {
  margin-bottom: 30px;
  background: #ffffff;
  border: 1px solid #e1e5e9;
  border-radius: 8px;
  padding: 24px;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
}

.settings-section h3 {
  margin: 0 0 20px 0;
  color: #2c3e50;
  font-weight: 600;
  font-size: 18px;
  border-bottom: 2px solid #3498db;
  padding-bottom: 8px;
}

.prompts-list {
  margin-bottom: 20px;
}

.prompt-item {
  background: #f8f9fa;
  border: 1px solid #dee2e6;
  border-radius: 6px;
  padding: 16px;
  margin-bottom: 12px;
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
}

.prompt-item h4 {
  margin: 0 0 8px 0;
  color: #495057;
  font-size: 14px;
  font-weight: 600;
}

.prompt-item p {
  margin: 0;
  color: #6c757d;
  font-size: 13px;
  flex: 1;
}

.prompt-item button {
  background: #007acc;
  color: white;
  border: none;
  padding: 6px 12px;
  border-radius: 4px;
  cursor: pointer;
  font-size: 12px;
  font-weight: 500;
  transition: background-color 0.2s ease;
  flex-shrink: 0;
}

.prompt-item button:hover {
  background: #005999;
}

.prompt-editor {
  background: #f8f9fa;
  border: 1px solid #dee2e6;
  border-radius: 6px;
  padding: 20px;
  margin-bottom: 20px;
}

.prompt-editor h4 {
  margin: 0 0 16px 0;
  color: #495057;
  font-size: 16px;
  font-weight: 600;
}

.prompt-editor textarea {
  width: 100%;
  min-height: 200px;
  padding: 12px;
  border: 1px solid #ced4da;
  border-radius: 4px;
  font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
  font-size: 13px;
  line-height: 1.5;
  resize: vertical;
  box-sizing: border-box;
}

.prompt-editor textarea:focus {
  outline: none;
  border-color: #007acc;
  box-shadow: 0 0 0 2px rgba(0, 122, 204, 0.2);
}

.editor-actions {
  display: flex;
  gap: 12px;
  margin-top: 16px;
  flex-wrap: wrap;
}

.editor-actions button {
  border: none;
  padding: 10px 16px;
  border-radius: 5px;
  cursor: pointer;
  font-size: 14px;
  font-weight: 500;
  transition: background-color 0.2s ease;
}

.editor-actions button:first-child {
  background: #28a745;
  color: white;
}

.editor-actions button:first-child:hover {
  background: #218838;
}

.editor-actions button:nth-child(2) {
  background: #ffc107;
  color: #212529;
}

.editor-actions button:nth-child(2):hover {
  background: #e0a800;
}

.editor-actions button:last-child {
  background: #6c757d;
  color: white;
}

.editor-actions button:last-child:hover {
  background: #5a6268;
}

.prompts-controls {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
}

.control-button {
  background: #007acc;
  color: white;
  border: none;
  padding: 10px 16px;
  border-radius: 5px;
  cursor: pointer;
  font-size: 14px;
  font-weight: 500;
  transition: background-color 0.2s ease;
}

.control-button:hover {
  background: #005999;
}

.control-button.small {
  padding: 8px 12px;
  font-size: 13px;
}

/* Dark theme support */
@media (prefers-color-scheme: dark) {
  .settings-section {
    background: #2d2d2d;
    border-color: #404040;
  }

  .settings-section h3 {
    color: #ffffff;
    border-bottom-color: #4fc3f7;
  }

  .prompt-item {
    background: #383838;
    border-color: #555;
  }

  .prompt-item h4 {
    color: #ffffff;
  }

  .prompt-item p {
    color: #cccccc;
  }

  .prompt-editor {
    background: #383838;
    border-color: #555;
  }

  .prompt-editor h4 {
    color: #ffffff;
  }

  .prompt-editor textarea {
    background: #404040;
    border-color: #555;
    color: #ffffff;
  }

  .prompt-editor textarea:focus {
    border-color: #4fc3f7;
    box-shadow: 0 0 0 2px rgba(79, 195, 247, 0.2);
  }
}

/* Mobile responsive */
@media (max-width: 768px) {
  .settings-section {
    padding: 16px;
    margin-bottom: 20px;
  }

  .prompt-item {
    flex-direction: column;
    align-items: flex-start;
    gap: 12px;
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