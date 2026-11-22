<!--
  Copyright 2025-2026 mrveiss
  SPDX-License-Identifier: Apache-2.0
  AutoBot - AI-Powered Automation Platform
  Author: mrveiss

  ChatInputStatusBar — the line under the chat input: typing hint, character count, voice
  status, keyboard hint, and the Stop control while a reply is streaming (#17829).
  Moved out of ChatInput.vue, which is at its size ceiling.
-->
<template>
  <div class="flex items-center justify-between text-xs text-autobot-text-muted">
    <div class="flex items-center gap-3">
      <span v-if="typingVisible" class="flex items-center gap-1 text-autobot-primary">
        <Icon name="keyboard" />
        {{ $t('chat.input.typing') }}
      </span>
      <span v-if="characterCount > 0" class="transition-colors" :class="{ 'text-autobot-warning font-medium': nearLimit }">
        {{ characterCount }}/{{ maxCharacters }}
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
        <Icon name="stop" aria-hidden="true" />
        {{ $t('chat.stopGenerating') }}
      </BaseButton>
      <span v-if="failed" class="text-autobot-error" role="status" data-testid="stop-failed">{{ $t('chat.input.stopFailed') }}</span>
      <span v-if="voiceRecording" class="flex items-center gap-1 text-autobot-error">
        <Icon name="circle" class="text-red-500 animate-pulse" />
        {{ $t('chat.input.recording') }}
      </span>
      <span class="hidden sm:block">{{ $t('chat.input.keyboardHint') }}</span>
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
