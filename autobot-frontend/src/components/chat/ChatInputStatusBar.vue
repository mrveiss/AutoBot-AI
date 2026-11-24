<!--
  Copyright 2025-2026 mrveiss
  SPDX-License-Identifier: Apache-2.0
  AutoBot - AI-Powered Automation Platform
  Author: mrveiss

  ChatInputStatusBar -- the line under the chat input: typing hint, character counter (with the room left near the
  limit), voice status, keyboard hint, and the Stop control while a reply is streaming (#17829). Kit button and
  tokens only (#18243).
-->
<template>
  <div class="mt-2 flex items-center justify-between gap-3 text-xs text-[var(--aui-color-text-muted)]">
    <div class="flex items-center gap-3">
      <span v-if="typingVisible" class="inline-flex items-center gap-1 text-[var(--aui-color-primary)]">
        <Icon name="keyboard" size="sm" />
        {{ $t('chat.input.typing') }}
      </span>
      <span
        v-if="characterCount > 0"
        class="font-mono transition-colors"
        :class="nearLimit ? 'font-medium text-[var(--aui-color-warning)]' : ''"
        data-testid="character-count"
      >
        {{ characterCount }}/{{ maxCharacters }}<template v-if="nearLimit"> · {{ $t('chat.input.charactersLeft', { count: maxCharacters - characterCount }) }}</template>
      </span>
    </div>

    <div class="flex items-center gap-3">
      <BaseButton
        v-if="store.isTyping"
        variant="secondary"
        size="xs"
        :loading="stopping"
        data-testid="stop-generating"
        @click="stop"
      >
        <template #icon-left><Icon name="stop" size="sm" aria-hidden="true" /></template>
        {{ $t('chat.stopGenerating') }}
      </BaseButton>
      <span v-if="failed" class="text-[var(--aui-color-error)]" role="status" data-testid="stop-failed">{{ $t('chat.input.stopFailed') }}</span>
      <span v-if="voiceRecording" class="inline-flex items-center gap-1 text-[var(--aui-color-error)]" role="status">
        <Icon name="circle" size="xs" class="animate-pulse fill-current motion-reduce:animate-none" />
        {{ $t('chat.input.recording') }}
      </span>
      <span class="hidden sm:block">{{ $t('chat.input.keyboardHint') }}<span class="adv"> · {{ $t('chat.input.keyboardHintAdvanced') }}</span></span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { BaseButton } from '@autobot/ui'
import Icon from '@/components/ui/Icon.vue'
import { useChatStore } from '@/stores/useChatStore'
import { useStopGeneration } from '@/composables/useStopGeneration'

defineProps<{
  typingVisible: boolean
  characterCount: number
  maxCharacters: number
  nearLimit: boolean
  voiceRecording: boolean
}>()

const store = useChatStore()
const { stopping, failed, stop } = useStopGeneration()
</script>
