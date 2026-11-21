<!--
  Copyright 2025-2026 mrveiss
  SPDX-License-Identifier: Apache-2.0

  ChatHeaderActions -- the panel and voice toggles of the chat header (#18243), extracted from
  ChatInterface. Pure presentation: the state lives in ChatInterface, this emits the intents.
  Voice chat and Compare are advanced (`.adv`); the voice-output toggle, the file panel and the
  collaboration panel stay visible in Minimal mode.
-->
<template>
  <div role="group" :aria-label="$t('chat.header.voiceControls')" class="chat-header-voice-group">
    <ChatHeaderIconButton
      :label="voiceOutputEnabled ? $t('chat.interface.voiceOutputOn') : $t('chat.interface.voiceOutputOff')"
      :icon="isSpeaking || voiceOutputEnabled ? 'volume-up' : 'volume-mute'"
      :icon-class="isSpeaking ? 'animate-pulse' : ''"
      :pressed="voiceOutputEnabled"
      @click="emit('toggle-voice-output')"
    />
    <ChatHeaderIconButton
      adv
      :label="$t('chat.interface.voiceChat')"
      icon="headset"
      :pressed="voiceExpanded"
      :expanded="voiceExpanded"
      :controls="voiceControlsId"
      @click="emit('toggle-voice-conversation')"
      @el="emit('button-el', 'voice', $event)"
    />
  </div>
  <ChatHeaderIconButton
    v-if="hasSession"
    :label="$t('chat.interface.toggleFilePanel')"
    icon="paperclip"
    :pressed="showFilePanel"
    :expanded="showFilePanel"
    controls="chat-panel-files"
    @click="emit('toggle-panel', 'files')"
    @el="emit('button-el', 'files', $event)"
  />
  <!-- Issue #4414: multi-model comparison toggle -->
  <ChatHeaderIconButton
    adv
    :label="$t('chat.compare.toggleTitle')"
    icon="columns"
    :pressed="showComparePanel"
    @click="emit('toggle-compare')"
  />
  <!-- #16443: collaboration panel toggle, collaborative sessions only -->
  <ChatHeaderIconButton
    v-if="isCollaborative"
    :label="$t('collaboration.panel.title')"
    icon="users"
    :pressed="showCollaborationPanel"
    :expanded="showCollaborationPanel"
    controls="chat-panel-collaboration"
    @click="emit('toggle-panel', 'collaboration')"
    @el="emit('button-el', 'collaboration', $event)"
  />
</template>

<script setup lang="ts">
import ChatHeaderIconButton from './ChatHeaderIconButton.vue'
import type { ChatSidePanel } from '@/composables/useChatSidePanels'

defineProps<{
  voiceOutputEnabled: boolean
  isSpeaking: boolean
  voiceExpanded: boolean
  voiceControlsId: string
  hasSession: boolean
  isCollaborative: boolean
  showFilePanel: boolean
  showComparePanel: boolean
  showCollaborationPanel: boolean
}>()

const emit = defineEmits<{
  'toggle-voice-output': []
  'toggle-voice-conversation': []
  'toggle-panel': [panel: ChatSidePanel]
  'toggle-compare': []
  'button-el': [panel: ChatSidePanel, element: HTMLElement | null]
}>()
</script>

<style scoped>
/* GH#8755: proximity grouping for the audio actions, on the kit surface token. */
.chat-header-voice-group {
  display: flex;
  align-items: center;
  gap: var(--aui-space-1);
  border-radius: var(--aui-radius-md);
  background: var(--surface2);
}
</style>
