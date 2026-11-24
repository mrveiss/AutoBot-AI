<!--
  Copyright 2025-2026 mrveiss
  SPDX-License-Identifier: Apache-2.0

  ChatImageGenDialog -- the composer's "Generate image" dialog (GH#9015, #18243): a prompt and a provider on
  the kit modal (focus trap, Escape, overlay close). The prompt, provider and open state are the caller's
  (`useComposerImageGen`); `submit` fires from the button or Ctrl+Enter.
-->
<template>
  <BaseModal
    :model-value="open"
    :title="$t('chat.input.generateImageTitle')"
    :close-label="$t('ui.modal.closeDialog')"
    size="sm"
    @update:model-value="emit('update:open', $event)"
    @close="emit('update:open', false)"
  >
    <div class="flex flex-col gap-3">
      <label class="text-sm font-medium text-[var(--aui-color-text-muted)]" for="image-gen-prompt">{{ $t('chat.input.imagePromptLabel') }}</label>
      <textarea
        id="image-gen-prompt"
        :value="prompt"
        class="w-full resize-none rounded-[var(--aui-radius-md)] border border-[var(--aui-input-border)] bg-[var(--aui-input-bg)] px-3 py-2 text-sm text-[var(--aui-color-text)] focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-[var(--aui-color-focus-ring)]"
        :placeholder="$t('chat.input.imagePromptPlaceholder')"
        rows="3"
        @input="emit('update:prompt', ($event.target as HTMLTextAreaElement).value)"
        @keydown.ctrl.enter="emit('submit')"
      />
      <fieldset class="m-0 flex flex-wrap gap-3 border-0 p-0">
        <legend class="text-sm font-medium text-[var(--aui-color-text-muted)]">{{ $t('chat.input.imageProvider') }}</legend>
        <label v-for="p in IMAGE_PROVIDERS" :key="p" class="inline-flex cursor-pointer items-center gap-2 text-sm text-[var(--aui-color-text)]">
          <input type="radio" name="image-provider" :value="p" :checked="provider === p" @change="emit('update:provider', p)" />
          <span>{{ $t(`chat.input.imageProviders.${p}`) }}</span>
        </label>
      </fieldset>
    </div>
    <template #actions>
      <BaseButton variant="ghost" @click="emit('update:open', false)">{{ $t('common.cancel') }}</BaseButton>
      <BaseButton variant="primary" :disabled="!prompt.trim() || generating" :loading="generating" @click="emit('submit')">
        <template #icon-left><Icon name="magic" /></template>
        {{ generating ? $t('chat.input.generating') : $t('chat.input.generate') }}
      </BaseButton>
    </template>
  </BaseModal>
</template>

<script setup lang="ts">
import { BaseButton, BaseModal } from '@autobot/ui'
import Icon from '@/components/ui/Icon.vue'
import { IMAGE_PROVIDERS, type ImageProvider } from '@/composables/chat/useComposerImageGen'

defineProps<{ open: boolean; prompt: string; provider: ImageProvider; generating: boolean }>()
const emit = defineEmits<{
  'update:open': [value: boolean]
  'update:prompt': [value: string]
  'update:provider': [value: ImageProvider]
  submit: []
}>()
</script>
