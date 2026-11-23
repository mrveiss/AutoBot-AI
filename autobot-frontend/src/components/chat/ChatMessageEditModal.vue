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
      class="flex-1 w-full px-3 py-2 border border-autobot-border rounded-md focus:outline-none focus:ring-2 focus:ring-electric-500 resize-none"
      :placeholder="$t('chat.messages.enterMessage')"
      rows="6"
      @keydown.ctrl.enter="emit('save')"
      @keydown.meta.enter="emit('save')"
    ></textarea>
    <div class="text-xs text-autobot-text-muted mt-2">{{ $t('chat.messages.ctrlEnterToSave') }}</div>

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

/** Focus the field once the dialog is open (as the stream did after opening it). */
watch(() => props.modelValue, async (open) => {
  if (!open) return
  await nextTick()
  textarea.value?.focus()
})
</script>
