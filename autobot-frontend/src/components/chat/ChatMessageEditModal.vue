<template>
  <BaseModal
    :close-label="$t('ui.modal.closeDialog')"
    :model-value="modelValue"
    :title="$t('chat.messages.editMessage')"
    size="md"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <textarea
      ref="textarea"
      v-model="content"
      :style="TEXTAREA_STYLE"
      :placeholder="$t('chat.messages.enterMessage')"
      rows="6"
      @keydown.ctrl.enter="emit('save')"
      @keydown.meta.enter="emit('save')"
    ></textarea>
    <div :style="HINT_STYLE">{{ $t('chat.messages.ctrlEnterToSave') }}</div>

    <template #actions>
      <BaseButton variant="secondary" @click="emit('cancel')">{{ $t('common.cancel') }}</BaseButton>
      <BaseButton variant="primary" :disabled="!content.trim()" @click="emit('save')">{{ $t('common.save') }}</BaseButton>
    </template>
  </BaseModal>
</template>

<script setup lang="ts">
/** Edit-message dialog (#18243, step 5a batch 2), split out of ChatMessages.vue. State lives in useChatMessageEdit. */
import { nextTick, ref, watch } from 'vue'
import { BaseButton, BaseModal } from '@autobot/ui'

const props = defineProps<{ modelValue: boolean }>()
const content = defineModel<string>('content', { required: true })
const emit = defineEmits<{ 'update:modelValue': [open: boolean]; save: []; cancel: [] }>()

const textarea = ref<HTMLTextAreaElement>()

/** Kit tokens only. The field keeps the browser focus outline (no custom ring to restyle). */
const TEXTAREA_STYLE = {
  flex: 1,
  inlineSize: '100%',
  padding: 'var(--aui-space-2) var(--aui-space-3)',
  resize: 'none',
  border: '1px solid var(--aui-input-border)',
  borderRadius: 'var(--aui-radius-md)',
  background: 'var(--aui-input-bg)',
  color: 'var(--aui-color-text)',
  font: 'inherit',
} as const
const HINT_STYLE = {
  marginBlockStart: 'var(--aui-space-2)',
  color: 'var(--aui-color-text-muted)',
  fontSize: 'var(--aui-text-xs)',
} as const

/** Focus the field once the dialog is open (as the stream did after opening it). */
watch(() => props.modelValue, async (open) => {
  if (!open) return
  await nextTick()
  textarea.value?.focus()
})
</script>
