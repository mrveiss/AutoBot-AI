<template>
  <!-- AI Document Editor — Issue #3245 -->
  <div class="ai-document-editor">
    <!-- Header bar -->
    <div class="editor-header">
      <div class="title-row">
        <input
          v-if="isEditingTitle"
          ref="titleInputRef"
          v-model="editableTitle"
          class="title-input"
          maxlength="500"
          aria-label="Document title"
          @blur="commitTitle"
          @keyup.enter="commitTitle"
          @keyup.escape="cancelTitle"
        />
        <h2
          v-else
          class="document-title"
          tabindex="0"
          title="Click to edit title"
          @click="startEditTitle"
          @keyup.enter="startEditTitle"
        >
          {{ localDoc?.title ?? 'Untitled Document' }}
        </h2>
      </div>

      <div class="header-actions">
        <BaseButton
          v-if="isDirty"
          variant="primary"
          size="sm"
          :disabled="composable.isSaving.value"
          @click="saveChanges"
        >
          {{ composable.isSaving.value ? 'Saving…' : 'Save' }}
        </BaseButton>
        <BaseButton
          variant="ghost"
          size="sm"
          :disabled="composable.isRefining.value"
          title="Refine with AI"
          @click="showRefinePanel = !showRefinePanel"
        >
          Refine
        </BaseButton>
        <slot name="extra-actions" />
      </div>
    </div>

    <!-- Error banner -->
    <div v-if="composable.error.value" class="error-banner" role="alert">
      {{ composable.error.value }}
    </div>

    <!-- Refine panel -->
    <div v-if="showRefinePanel" class="refine-panel">
      <textarea
        v-model="refineInstruction"
        class="refine-textarea"
        placeholder="Describe how to refine this document…"
        rows="3"
        maxlength="2000"
        aria-label="Refinement instruction"
      />
      <div class="refine-actions">
        <BaseButton
          variant="primary"
          size="sm"
          :disabled="!refineInstruction.trim() || composable.isRefining.value"
          @click="submitRefine"
        >
          {{ composable.isRefining.value ? 'Refining…' : 'Apply Refinement' }}
        </BaseButton>
        <BaseButton variant="ghost" size="sm" @click="showRefinePanel = false">
          Cancel
        </BaseButton>
      </div>
    </div>

    <!-- Markdown editor (textarea) -->
    <div class="editor-body">
      <textarea
        v-model="editableContent"
        class="content-editor"
        placeholder="Document content (markdown supported)…"
        spellcheck="true"
        aria-label="Document content"
        @input="onContentInput"
      />
    </div>

    <!-- Footer metadata -->
    <div class="editor-footer">
      <span v-if="localDoc" class="meta">
        Updated {{ formattedUpdatedAt }}
      </span>
      <span v-if="localDoc?.source_facts?.length" class="source-facts-count">
        {{ localDoc.source_facts.length }} source
        {{ localDoc.source_facts.length === 1 ? 'fact' : 'facts' }}
      </span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick } from 'vue'
import BaseButton from '@/components/base/BaseButton.vue'
import { useAIDocument, type AIDocument } from '@/composables/useAIDocument'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('AIDocumentEditor')

// ---------------------------------------------------------------------------
// Props / emits
// ---------------------------------------------------------------------------

const props = defineProps<{
  docId: string
}>()

const emit = defineEmits<{
  (e: 'saved', doc: AIDocument): void
  (e: 'refined', doc: AIDocument): void
  (e: 'error', message: string): void
}>()

// ---------------------------------------------------------------------------
// Composable
// ---------------------------------------------------------------------------

const composable = useAIDocument()

// ---------------------------------------------------------------------------
// Local state
// ---------------------------------------------------------------------------

const localDoc = ref<AIDocument | null>(null)
const editableTitle = ref('')
const editableContent = ref('')
const isEditingTitle = ref(false)
const isDirty = ref(false)
const showRefinePanel = ref(false)
const refineInstruction = ref('')
const titleInputRef = ref<HTMLInputElement | null>(null)

// ---------------------------------------------------------------------------
// Load document on mount / when docId changes
// ---------------------------------------------------------------------------

watch(
  () => props.docId,
  async (id) => {
    if (!id) return
    try {
      const doc = await composable.fetchDocument(id)
      localDoc.value = doc
      editableTitle.value = doc.title
      editableContent.value = doc.content
      isDirty.value = false
    } catch (err) {
      logger.error('Failed to load document', err)
      emit('error', composable.error.value ?? 'Failed to load document')
    }
  },
  { immediate: true }
)

// ---------------------------------------------------------------------------
// Title editing
// ---------------------------------------------------------------------------

function startEditTitle() {
  isEditingTitle.value = true
  nextTick(() => titleInputRef.value?.focus())
}

function commitTitle() {
  if (!editableTitle.value.trim()) {
    editableTitle.value = localDoc.value?.title ?? 'Untitled Document'
  }
  isEditingTitle.value = false
  if (localDoc.value && editableTitle.value !== localDoc.value.title) {
    isDirty.value = true
  }
}

function cancelTitle() {
  editableTitle.value = localDoc.value?.title ?? ''
  isEditingTitle.value = false
}

// ---------------------------------------------------------------------------
// Content change tracking
// ---------------------------------------------------------------------------

function onContentInput() {
  isDirty.value = true
}

// ---------------------------------------------------------------------------
// Save
// ---------------------------------------------------------------------------

async function saveChanges() {
  if (!localDoc.value || !isDirty.value) return
  try {
    const updated = await composable.updateDocument(localDoc.value.id, {
      title: editableTitle.value,
      content: editableContent.value,
    })
    localDoc.value = updated
    isDirty.value = false
    emit('saved', updated)
  } catch (err) {
    emit('error', composable.error.value ?? 'Save failed')
  }
}

// ---------------------------------------------------------------------------
// Refinement
// ---------------------------------------------------------------------------

async function submitRefine() {
  if (!localDoc.value || !refineInstruction.value.trim()) return
  try {
    const refined = await composable.refineDocument(localDoc.value.id, {
      instruction: refineInstruction.value.trim(),
    })
    localDoc.value = refined
    editableContent.value = refined.content
    editableTitle.value = refined.title
    isDirty.value = false
    refineInstruction.value = ''
    showRefinePanel.value = false
    emit('refined', refined)
  } catch (err) {
    emit('error', composable.error.value ?? 'Refinement failed')
  }
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const formattedUpdatedAt = computed(() => {
  if (!localDoc.value) return ''
  try {
    return new Date(localDoc.value.updated_at).toLocaleString()
  } catch {
    return localDoc.value.updated_at
  }
})
</script>

<style scoped>
.ai-document-editor {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--bg-primary, #1e1e1e);
  color: var(--text-primary, #e0e0e0);
  border-radius: var(--radius-lg);
  overflow: hidden;
}

.editor-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--spacing-3) var(--spacing-4);
  border-bottom: 1px solid var(--border-default, #333);
  gap: var(--spacing-3);
}

.title-row {
  flex: 1;
  min-width: 0;
}

.document-title {
  margin: var(--spacing-0);
  font-size: 1.1rem;
  font-weight: 600;
  cursor: pointer;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  outline: none;
  padding: var(--spacing-0-5) var(--spacing-1);
  border-radius: var(--radius-default);
  transition: background var(--duration-150);
}
.document-title:focus-visible {
  outline: 2px solid var(--color-primary);
  outline-offset: 2px;
}

.document-title:hover {
  background: var(--color-background-hover, #2a2a2a);
}

.title-input {
  width: 100%;
  background: var(--color-background-input, #2a2a2a);
  color: inherit;
  border: 1px solid var(--color-primary, #4caf50);
  border-radius: var(--radius-default);
  font-size: 1.1rem;
  font-weight: 600;
  padding: var(--spacing-0-5) var(--spacing-2);
  outline: none;
}
.title-input:focus-visible {
  outline: 2px solid var(--color-primary);
  outline-offset: 2px;
}

.header-actions {
  display: flex;
  gap: var(--spacing-2);
  flex-shrink: 0;
}

.error-banner {
  background: var(--color-error-bg, #3c1515);
  color: var(--color-error, #f87171);
  padding: var(--spacing-2) var(--spacing-4);
  font-size: 0.85rem;
  border-bottom: 1px solid var(--color-error, #f87171);
}

.refine-panel {
  padding: var(--spacing-3) var(--spacing-4);
  border-bottom: 1px solid var(--border-default, #333);
  background: var(--color-background-secondary, #252525);
  display: flex;
  flex-direction: column;
  gap: var(--spacing-2);
}

.refine-textarea {
  width: 100%;
  resize: vertical;
  background: var(--color-background-input, #2a2a2a);
  color: inherit;
  border: 1px solid var(--border-default, #444);
  border-radius: var(--radius-default);
  padding: var(--spacing-2);
  font-size: 0.9rem;
  font-family: inherit;
  outline: none;
  box-sizing: border-box;
}

.refine-textarea:focus {
  border-color: var(--color-primary, #4caf50);
}
.refine-textarea:focus-visible {
  outline: 2px solid var(--color-primary);
  outline-offset: 2px;
}

.refine-actions {
  display: flex;
  gap: var(--spacing-2);
}

.editor-body {
  flex: 1;
  display: flex;
  overflow: hidden;
}

.content-editor {
  flex: 1;
  resize: none;
  background: transparent;
  color: inherit;
  border: none;
  padding: var(--spacing-4);
  font-size: 0.95rem;
  font-family: 'JetBrains Mono', 'Fira Code', monospace;
  line-height: 1.6;
  outline: none;
  width: 100%;
  box-sizing: border-box;
}
.content-editor:focus-visible {
  outline: 2px solid var(--color-primary);
  outline-offset: 2px;
}

.editor-footer {
  display: flex;
  align-items: center;
  gap: var(--spacing-4);
  padding: var(--spacing-1-5) var(--spacing-4);
  font-size: var(--text-xs);
  color: var(--text-muted, #888);
  border-top: 1px solid var(--border-default, #333);
}

.source-facts-count {
  margin-left: auto;
}
</style>
