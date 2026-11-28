<!--
  Copyright 2025-2026 mrveiss
  SPDX-License-Identifier: Apache-2.0

  ChatFileEditorDialog -- the Chat files panel's create-file and edit-file dialog (#22349), on the kit
  `BaseModal` (focus trap, Escape, overlay close and focus return come from it). `mode="create"` asks for a name
  and optional content and is disabled until the name is non-empty; `mode="edit"` shows the file name as the title
  and edits its content. Submitting emits the draft; closing emits nothing but `update:open`. The caller owns
  what a save does, so a draft can be dropped when the conversation changes (#21337).
-->
<template>
  <BaseModal
    :model-value="open"
    :title="mode === 'create' ? $t('chat.filePanel.createNewFile') : filename"
    :close-label="$t('common.close')"
    size="md"
    @update:model-value="emit('update:open', $event)"
  >
    <BaseInput
      v-if="mode === 'create'"
      v-model="name"
      size="sm"
      class="mb-2"
      :aria-label="$t('chat.filePanel.filenamePlaceholder')"
      :placeholder="$t('chat.filePanel.filenamePlaceholder')"
      data-testid="editor-name"
      @keyup.enter="submit"
    />
    <textarea
      v-model="draft"
      class="w-full min-h-48 p-2 text-xs font-mono border border-[var(--aui-color-border)] rounded-md bg-[var(--aui-color-surface)] text-[var(--aui-color-text)] resize-none focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-[var(--aui-color-focus-ring)]"
      rows="8"
      :aria-label="mode === 'create' ? $t('chat.filePanel.contentPlaceholder') : $t('chat.filePanel.editFileTitle', { name: filename })"
      :placeholder="mode === 'create' ? $t('chat.filePanel.contentPlaceholder') : undefined"
      data-testid="editor-content"
    ></textarea>
    <template #actions>
      <BaseButton variant="ghost" size="sm" data-testid="editor-cancel" @click="emit('update:open', false)">{{ $t('common.cancel') }}</BaseButton>
      <BaseButton variant="primary" size="sm" :disabled="!canSubmit" data-testid="editor-submit" @click="submit">
        {{ mode === 'create' ? $t('common.create') : $t('common.save') }}
      </BaseButton>
    </template>
  </BaseModal>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { BaseButton, BaseInput, BaseModal } from '@autobot/ui'

const props = withDefaults(
  defineProps<{
    open: boolean
    mode: 'create' | 'edit'
    /** Edit mode: the file's name (the title) */
    filename?: string
    /** Edit mode: the content the editor opens with */
    content?: string
  }>(),
  { filename: '', content: '' },
)
const emit = defineEmits<{
  'update:open': [open: boolean]
  submit: [draft: { name: string; content: string }]
}>()

const name = ref('')
const draft = ref('')
const canSubmit = computed(() => props.mode === 'edit' || name.value.trim().length > 0)

// Each opening starts from the caller's content, not from the last draft.
watch(() => props.open, (isOpen) => {
  if (!isOpen) return
  name.value = ''
  draft.value = props.mode === 'edit' ? props.content : ''
}, { immediate: true })

function submit(): void {
  if (!canSubmit.value) return
  emit('submit', { name: name.value.trim(), content: draft.value })
}
</script>
