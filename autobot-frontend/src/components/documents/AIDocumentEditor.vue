<template>
  <!-- AI Document Editor — Issue #3245; Refined UI "Knowledge · AI documents" (#18244) -->
  <BaseCard class="ai-document-editor" flush>
    <header class="editor-header">
      <input
        v-if="isEditingTitle"
        ref="titleInputRef"
        v-model="editableTitle"
        class="title-input"
        maxlength="500"
        :aria-label="$t('documents.editor.titleLabel')"
        @blur="commitTitle"
        @keyup.enter="commitTitle"
        @keyup.escape="cancelTitle"
      />
      <BaseTooltip v-else :text="$t('documents.editor.editTitleTip')" placement="bottom" class="title-wrap">
        <template #default="{ describedby }">
          <h2
            class="document-title"
            tabindex="0"
            :aria-describedby="describedby"
            @click="startEditTitle"
            @keyup.enter="startEditTitle"
          >
            {{ localDoc?.title ?? $t('documents.editor.untitled') }}
          </h2>
        </template>
      </BaseTooltip>

      <div class="header-actions">
        <BaseButton v-if="isDirty" variant="primary" size="sm" :disabled="composable.isSaving.value" @click="saveChanges">
          {{ composable.isSaving.value ? $t('documents.editor.saving') : $t('common.save') }}
        </BaseButton>
        <BaseTooltip :text="$t('documents.editor.refineTip')" placement="left">
          <template #default="{ describedby }">
            <BaseButton
              variant="outline"
              size="sm"
              :aria-expanded="showRefinePanel"
              :aria-describedby="describedby"
              :disabled="composable.isRefining.value"
              @click="showRefinePanel = !showRefinePanel"
            >
              <Icon name="magic" aria-hidden="true" />
              {{ $t('documents.editor.refine') }}
            </BaseButton>
          </template>
        </BaseTooltip>
        <slot name="extra-actions" />
      </div>
    </header>

    <div v-if="composable.error.value" class="error-banner" role="alert">{{ composable.error.value }}</div>

    <section v-if="showRefinePanel" class="refine-panel">
      <label for="refine-instruction" class="refine-label">{{ $t('documents.editor.refineHeading') }}</label>
      <textarea
        id="refine-instruction"
        v-model="refineInstruction"
        class="refine-textarea"
        :placeholder="$t('documents.editor.refinePlaceholder')"
        rows="3"
        maxlength="2000"
      />
      <div class="refine-actions">
        <BaseButton
          variant="primary"
          size="sm"
          :disabled="!refineInstruction.trim() || composable.isRefining.value"
          @click="submitRefine"
        >
          {{ composable.isRefining.value ? $t('documents.editor.refining') : $t('documents.editor.applyRefinement') }}
        </BaseButton>
        <BaseButton variant="ghost" size="sm" @click="showRefinePanel = false">{{ $t('common.cancel') }}</BaseButton>
      </div>
    </section>

    <div class="editor-body">
      <textarea
        v-model="editableContent"
        class="content-editor"
        :placeholder="$t('documents.editor.contentPlaceholder')"
        spellcheck="true"
        :aria-label="$t('documents.editor.contentLabel')"
        @input="onContentInput"
      />
    </div>

    <footer class="editor-footer">
      <span v-if="localDoc" class="meta">{{ $t('documents.editor.updated', { when: formattedUpdatedAt }) }}</span>
      <BaseTooltip v-if="localDoc?.source_facts?.length" class="adv" :text="$t('documents.editor.sourceFactsTip')" placement="top">
        <template #default="{ describedby }">
          <BaseBadge variant="info" size="sm" tabindex="0" :aria-describedby="describedby">
            {{ $t('documents.editor.sourceFacts', { count: localDoc.source_facts.length }) }}
          </BaseBadge>
        </template>
      </BaseTooltip>
    </footer>
  </BaseCard>
</template>

<script setup lang="ts">
import { formatISOString } from '@/utils/formatHelpers'
import { ref, computed, watch, nextTick } from 'vue'
import { useI18n } from 'vue-i18n'
import { BaseBadge, BaseButton, BaseCard, BaseTooltip } from '@autobot/ui'
import Icon from '@/components/ui/Icon.vue'
import { useAIDocument, type AIDocument } from '@/composables/useAIDocument'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('AIDocumentEditor')
const { t } = useI18n()

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
  (e: 'load-error', message: string): void
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
      logger.error(t('documents.editor.loadFailed'), err)
      const msg = composable.error.value ?? t('documents.editor.loadFailed')
      emit('error', msg)
      emit('load-error', msg)
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
    editableTitle.value = localDoc.value?.title ?? t('documents.editor.untitled')
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
  } catch {
    emit('error', composable.error.value ?? t('documents.editor.saveFailed'))
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
  } catch {
    emit('error', composable.error.value ?? t('documents.editor.refineFailed'))
  }
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const formattedUpdatedAt = computed(() => {
  if (!localDoc.value) return ''
  return formatISOString(localDoc.value.updated_at)
})
</script>

<style scoped>
.ai-document-editor {
  display: flex;
  flex-direction: column;
  min-inline-size: 0;
}

.editor-header {
  display: flex;
  align-items: center;
  gap: var(--spacing-3);
  padding: var(--spacing-3) var(--spacing-4);
  border-block-end: var(--bw) solid var(--line);
}

.title-wrap {
  flex: 1;
  min-inline-size: 0;
}

.document-title {
  margin: 0;
  font-size: var(--text-lg);
  font-weight: 600;
  color: var(--text);
  cursor: text;
  overflow-wrap: anywhere;
}

.title-input {
  flex: 1;
  min-inline-size: 0;
  padding: var(--spacing-1) var(--spacing-2);
  border: var(--bw) solid var(--border);
  border-radius: var(--radius-md);
  background: var(--surface);
  color: var(--text);
  font: inherit;
  font-size: var(--text-lg);
  font-weight: 600;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
}

.error-banner {
  padding: var(--spacing-2) var(--spacing-4);
  background: var(--bad-bg);
  color: var(--bad-fg);
  font-size: var(--text-sm);
}

.refine-panel {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-2);
  padding: var(--spacing-3) var(--spacing-4);
  background: var(--surface2);
  border-block-end: var(--bw) solid var(--line);
}

.refine-label {
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--text);
}

.refine-textarea,
.content-editor {
  inline-size: 100%;
  box-sizing: border-box;
  padding: var(--spacing-3);
  border: var(--bw) solid var(--border);
  border-radius: var(--radius-md);
  background: var(--surface);
  color: var(--text);
  font: inherit;
  font-size: var(--text-sm);
  resize: vertical;
}

.refine-actions {
  display: flex;
  gap: var(--spacing-2);
}

.editor-body {
  display: flex;
  flex: 1;
  padding: var(--spacing-3) var(--spacing-4);
}

.content-editor {
  flex: 1;
  min-block-size: 300px;
  background: var(--surface2);
  font-family: var(--font-mono);
  line-height: 1.7;
}

.title-input:focus-visible,
.refine-textarea:focus-visible,
.content-editor:focus-visible,
.document-title:focus-visible {
  outline: 3px solid var(--focus);
  outline-offset: 2px;
}

.editor-footer {
  display: flex;
  align-items: center;
  gap: var(--spacing-3);
  padding: var(--spacing-3) var(--spacing-4);
  border-block-start: var(--bw) solid var(--line);
  font-size: var(--text-sm);
  color: var(--muted);
}
</style>
