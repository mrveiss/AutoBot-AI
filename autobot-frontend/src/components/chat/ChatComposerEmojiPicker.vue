<!--
  Copyright 2025-2026 mrveiss
  SPDX-License-Identifier: Apache-2.0

  ChatComposerEmojiPicker -- the small emoji popover above the composer (#18243). Emits the picked emoji
  and `close`; the open state, the caret insert and the click-outside handling belong to the parent.
-->
<template>
  <div class="absolute bottom-full end-0 z-[var(--aui-z-dropdown)] mb-2 w-80 max-w-full rounded-[var(--aui-radius-lg)] border border-[var(--aui-color-border)] bg-[var(--aui-color-surface)] shadow-[var(--aui-shadow-lg)]" role="dialog" :aria-label="$t('chat.input.addEmoji')">
    <div class="flex items-center justify-between border-b border-[var(--aui-color-border)] px-3 py-2">
      <span class="text-sm font-medium text-[var(--aui-color-text)]">{{ $t('chat.input.addEmoji') }}</span>
      <BaseButton variant="ghost" size="xs" :aria-label="$t('chat.input.closeEmojiPicker')" @click="emit('close')">
        <Icon name="times" />
      </BaseButton>
    </div>
    <div class="grid max-h-48 grid-cols-6 gap-1 overflow-y-auto p-3">
      <BaseButton
        v-for="emoji in EMOJIS"
        :key="emoji.code"
        variant="ghost"
        size="sm"
        :aria-label="$t(`chat.input.emoji.u${emoji.code}`)"
        @click="emit('pick', emoji.emoji)"
      >
        {{ emoji.emoji }}
      </BaseButton>
    </div>
  </div>
</template>

<script setup lang="ts">
import { BaseButton } from '@autobot/ui'
import Icon from '@/components/ui/Icon.vue'

/** The emoji and their locale key suffix (`chat.input.emoji.u<code>` names each for assistive tech). */
const EMOJIS = [
  { emoji: '😀', code: '1f600' }, { emoji: '😂', code: '1f602' }, { emoji: '😊', code: '1f60a' },
  { emoji: '😍', code: '1f60d' }, { emoji: '🤔', code: '1f914' }, { emoji: '👍', code: '1f44d' },
  { emoji: '👎', code: '1f44e' }, { emoji: '❤️', code: '2764' }, { emoji: '🔥', code: '1f525' },
  { emoji: '⭐', code: '2b50' }, { emoji: '💡', code: '1f4a1' }, { emoji: '✅', code: '2705' },
] as const

const emit = defineEmits<{ pick: [emoji: string]; close: [] }>()
</script>
