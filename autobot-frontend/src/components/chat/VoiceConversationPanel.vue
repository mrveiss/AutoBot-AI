<!--
  Copyright 2025-2026 mrveiss
  SPDX-License-Identifier: Apache-2.0

  VoiceConversationPanel -- the "Voice chat" aside (#22349, on the Refined UI Chat mockup): the title and live status,
  the mode controls, the state ring with the live transcript, the notices, the hands-free controls and the mic.
  Restyle only: every mode, transport and behaviour is `useVoiceConversation`'s, untouched. The aside is an advanced
  surface (`.adv`), as in the mockup. The placement in the overlay is `VoiceConversationOverlay`; both use the same
  parts and `useVoiceConversationView`.
-->
<template>
  <aside
    ref="panelRef"
    class="voice-panel adv w-70 min-w-70 max-w-70 h-full flex flex-col bg-autobot-bg-card border-l border-autobot-border"
    tabindex="-1"
    :aria-label="$t('chat.voice.title')"
    @keydown.escape="close"
  >
    <div class="flex flex-col gap-2 p-3 border-b border-autobot-border shrink-0">
      <div class="flex items-center justify-between gap-2">
        <div class="flex items-center gap-2 min-w-0">
          <div class="flex items-center justify-center shrink-0 size-7 rounded-md bg-[color-mix(in_srgb,var(--aui-color-primary)_15%,transparent)] text-[var(--aui-color-primary)]"><Icon name="headset" /></div>
          <div class="min-w-0">
            <h2 class="text-sm font-semibold text-autobot-text-primary">{{ $t('chat.voice.title') }}</h2>
            <p class="text-xs text-autobot-text-muted truncate" data-testid="voice-status">{{ voice.stateLabel.value }}</p>
          </div>
        </div>
        <ChatHeaderIconButton :label="$t('chat.voice.closeVoicePanel')" icon="times" data-testid="voice-close" @click="close" />
      </div>
      <VoiceModeControls
        :mode="voice.mode.value"
        :language="voice.currentLanguage.value"
        :connection="view.connection.value"
        @update:mode="voice.setMode"
      />
    </div>

    <div class="flex-1 flex flex-col items-center justify-center p-4 gap-4 overflow-y-auto">
      <VoiceStateRing :state="voice.state.value" :icon="view.stateIcon.value" :label="voice.stateLabel.value" />
      <div v-if="voice.currentTranscript.value" class="w-full px-3 py-2 border border-dashed border-[color-mix(in_srgb,var(--aui-color-info)_30%,transparent)] rounded-md bg-[color-mix(in_srgb,var(--aui-color-info)_8%,transparent)] text-[var(--aui-color-info)] text-xs italic break-words" data-testid="voice-transcript">
        <Icon name="ellipsis-h" class="animate-pulse me-1 text-xs" />
        {{ voice.currentTranscript.value }}
      </div>
    </div>

    <VoiceConversationNotices
      class="px-3 shrink-0"
      :error="voice.errorMessage.value"
      :show-insecure-context="view.showInsecureContextWarning.value"
      :origin="origin"
    />
    <VoiceHandsFreeControls
      v-if="view.isHandsFree.value"
      class="px-3 pt-2 shrink-0"
      :level="voice.audioLevel.value"
      :silence-ms="voice.silenceThreshold.value"
      :label="$t('chat.voice.silence')"
      @update:silence-ms="voice.silenceThreshold.value = $event"
    />
    <VoiceMicButton
      class="shrink-0 pt-4 px-3 pb-5 border-t border-[var(--aui-color-border)]"
      :state="voice.state.value"
      :icon="view.micIcon.value"
      :label="voice.stateLabel.value"
      :hint="view.micHint.value"
      @click="voice.toggleListening()"
    />
  </aside>
</template>

<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import Icon from '@/components/ui/Icon.vue'
import ChatHeaderIconButton from '@/components/chat/ChatHeaderIconButton.vue'
import VoiceConversationNotices from '@/components/chat/VoiceConversationNotices.vue'
import VoiceHandsFreeControls from '@/components/chat/VoiceHandsFreeControls.vue'
import VoiceMicButton from '@/components/chat/VoiceMicButton.vue'
import VoiceModeControls from '@/components/chat/VoiceModeControls.vue'
import VoiceStateRing from '@/components/chat/VoiceStateRing.vue'
import { useVoiceConversationView, VOICE_HINT_KEYS } from '@/composables/chat/useVoiceConversationView'
import { useVoiceConversation } from '@/composables/useVoiceConversation'

const emit = defineEmits<{ (e: 'close'): void }>()

const voice = useVoiceConversation()
const view = useVoiceConversationView(voice, VOICE_HINT_KEYS.panel)
const panelRef = ref<HTMLElement | null>(null)
const origin = window.location.origin

function close(): void {
  voice.deactivate()
  emit('close')
}

onBeforeUnmount(() => voice.cleanup())

// Focus the panel for keyboard accessibility (mirrors VoiceConversationOverlay)
onMounted(async () => {
  await nextTick()
  panelRef.value?.focus()
})
</script>
