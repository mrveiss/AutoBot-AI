<!--
  Copyright 2025-2026 mrveiss
  SPDX-License-Identifier: Apache-2.0

  ChatComposerActions -- the composer's icon-button row (#18243): attach, voice, emoji, and the advanced tools
  (vision, presets, MCP prompts, image generation), plus the overflow menu of quick actions (#1569). Every button
  is a named kit icon button with a tooltip. Presentational: it emits intents; the parent owns the state.
-->
<template>
  <div class="contents">
    <ChatHeaderIconButton placement="top" :label="$t('chat.input.attachFile')" icon="paperclip" :disabled="disabled" @click="emit('attach')" />
    <ChatHeaderIconButton
      placement="top"
      :label="$t('chat.input.voiceInput')"
      :icon="voiceRecording ? 'stop' : 'microphone'"
      :pressed="voiceRecording"
      :disabled="disabled && !voiceRecording"
      @click="emit('voice')"
    />
    <ChatHeaderIconButton adv placement="top" :label="$t('chat.input.analyzeImage')" icon="eye" :disabled="disabled" @click="emit('vision')" />
    <ChatHeaderIconButton adv placement="top" :label="$t('chat.input.managePresets')" icon="bookmark" :disabled="disabled" @click="emit('presets')" />
    <McpPromptPicker class="adv" :disabled="disabled" @insert="emit('prompt-insert', $event)" />
    <ChatHeaderIconButton
      adv
      placement="top"
      :label="$t('chat.input.generateImage')"
      :icon="imageGenerating ? 'spinner' : 'image'"
      :disabled="disabled || imageGenerating"
      @click="emit('image')"
    />
    <ChatHeaderIconButton
      data-emoji-trigger
      placement="top"
      :label="$t('chat.input.addEmoji')"
      icon="user"
      :disabled="disabled"
      :expanded="emojiOpen"
      @click="emit('emoji')"
    />
    <BaseDropdownMenu :items="menuItems" size="sm" side="top" align="end" @select="emit('quick-action', $event)">
      <template #trigger>
        <BaseButton variant="ghost" size="sm" class="min-w-11 min-h-11 sm:min-w-8 sm:min-h-8" :aria-label="$t('chat.input.moreActions')">
          <Icon name="ellipsis-h" />
        </BaseButton>
      </template>
    </BaseDropdownMenu>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { BaseButton, BaseDropdownMenu } from '@autobot/ui'
import type { MenuItem } from '@autobot/ui'
import Icon from '@/components/ui/Icon.vue'
import ChatHeaderIconButton from './ChatHeaderIconButton.vue'
import McpPromptPicker from './McpPromptPicker.vue'
import type { QuickAction } from '@/composables/chat/useComposerQuickActions'

const props = defineProps<{
  disabled: boolean
  voiceRecording: boolean
  imageGenerating: boolean
  emojiOpen: boolean
  quickActions: QuickAction[]
}>()
const emit = defineEmits<{
  attach: []
  voice: []
  vision: []
  presets: []
  image: []
  emoji: []
  'prompt-insert': [text: string]
  'quick-action': [id: string]
}>()

const menuItems = computed<MenuItem[]>(() =>
  props.quickActions.map((action) => ({ key: action.id, label: action.label, disabled: props.disabled })),
)
</script>
