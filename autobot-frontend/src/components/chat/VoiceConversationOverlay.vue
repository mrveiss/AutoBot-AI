<!--
  Copyright 2025-2026 mrveiss
  SPDX-License-Identifier: Apache-2.0

  VoiceConversationOverlay -- the voice UI in its second, user-selectable placement (#11999): a modal over the chat
  with the conversation bubbles. Restyle only (#22349): the layout is unchanged; the header controls, the notices,
  the hands-free controls and the mic are the parts the voice panel uses, and the mic icon and hint logic is
  `useVoiceConversationView`'s. Every mode, transport and behaviour is `useVoiceConversation`'s, untouched.
-->
<template>
  <Teleport to="body">
    <Transition name="voice-overlay">
      <div
        v-if="voice.isActive.value"
        id="chat-overlay-voice"
        ref="overlayRef"
        class="voice-overlay"
        tabindex="-1"
        @keydown.escape="close"
      >
        <!-- Backdrop grain texture -->
        <div class="voice-overlay__grain" aria-hidden="true"></div>

        <div class="voice-overlay__panel" role="dialog" aria-modal="true" :aria-label="$t('chat.voice.title')">
          <header class="voice-overlay__header">
            <div class="flex items-center gap-3">
              <div class="voice-overlay__tile"><Icon name="headset" /></div>
              <div>
                <h2 class="text-base font-semibold text-autobot-text-primary">{{ $t('chat.voice.title') }}</h2>
                <p class="text-xs text-autobot-text-muted" data-testid="voice-status">{{ voice.stateLabel.value }}</p>
              </div>
            </div>
            <div class="flex items-center gap-2">
              <VoiceModeControls
                :mode="voice.mode.value"
                :language="voice.currentLanguage.value"
                :connection="view.connection.value"
                @update:mode="voice.setMode"
              />
              <ChatHeaderIconButton :label="$t('chat.voice.closeVoiceChat')" icon="times" data-testid="voice-close" @click="close" />
            </div>
          </header>

          <div ref="conversationRef" class="voice-overlay__conversation">
            <div v-if="voice.bubbles.value.length === 0" class="voice-overlay__empty">
              <Icon name="comments" class="text-2xl opacity-20" />
              <p>{{ $t('chat.voice.tapMicToStart') }}</p>
            </div>
            <TransitionGroup name="bubble" tag="div" class="space-y-3">
              <div
                v-for="bubble in voice.bubbles.value"
                :key="bubble.id"
                class="voice-overlay__bubble"
                :class="`voice-overlay__bubble--${bubble.sender}`"
              >
                <div class="voice-overlay__bubble-icon">
                  <Icon :name="bubble.sender === 'user' ? 'user' : 'robot'" />
                </div>
                <div class="voice-overlay__bubble-content">
                  <span class="voice-overlay__bubble-sender">
                    {{ bubble.sender === 'user' ? $t('chat.voice.you') : $t('chat.voice.autobot') }}
                  </span>
                  <p>{{ bubble.content }}</p>
                </div>
              </div>
            </TransitionGroup>
            <Transition name="fade">
              <div v-if="voice.currentTranscript.value" class="voice-overlay__live-transcript" data-testid="voice-transcript">
                <Icon name="ellipsis-h" class="animate-pulse me-2" />
                {{ voice.currentTranscript.value }}
              </div>
            </Transition>
          </div>

          <VoiceConversationNotices
            class="px-5"
            :error="voice.errorMessage.value"
            :show-insecure-context="view.showInsecureContextWarning.value"
            :origin="origin"
          />
          <VoiceHandsFreeControls
            v-if="view.isHandsFree.value"
            class="voice-overlay__hf"
            :level="voice.audioLevel.value"
            :silence-ms="voice.silenceThreshold.value"
            :label="$t('chat.voice.silenceTimeout')"
            @update:silence-ms="voice.silenceThreshold.value = $event"
          />
          <VoiceMicButton
            class="voice-overlay__controls"
            :state="voice.state.value"
            :icon="view.micIcon.value"
            :label="voice.stateLabel.value"
            :hint="view.micHint.value"
            @click="voice.toggleListening()"
          />
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
import { nextTick, onBeforeUnmount, ref, watch } from 'vue'
import Icon from '@/components/ui/Icon.vue'
import ChatHeaderIconButton from '@/components/chat/ChatHeaderIconButton.vue'
import VoiceConversationNotices from '@/components/chat/VoiceConversationNotices.vue'
import VoiceHandsFreeControls from '@/components/chat/VoiceHandsFreeControls.vue'
import VoiceMicButton from '@/components/chat/VoiceMicButton.vue'
import VoiceModeControls from '@/components/chat/VoiceModeControls.vue'
import { useVoiceConversationView, VOICE_HINT_KEYS } from '@/composables/chat/useVoiceConversationView'
import { useVoiceConversation } from '@/composables/useVoiceConversation'

const emit = defineEmits<{ (e: 'close'): void }>()

const voice = useVoiceConversation()
const view = useVoiceConversationView(voice, VOICE_HINT_KEYS.overlay)
const overlayRef = ref<HTMLElement | null>(null)
const conversationRef = ref<HTMLElement | null>(null)
const origin = window.location.origin

function close(): void {
  voice.deactivate()
  emit('close')
}

// Auto-scroll the conversation when new bubbles arrive
watch(() => voice.bubbles.value.length, async () => {
  await nextTick()
  if (conversationRef.value) conversationRef.value.scrollTop = conversationRef.value.scrollHeight
})

// Focus the overlay for keyboard accessibility
watch(() => voice.isActive.value, async (active) => {
  if (!active) return
  await nextTick()
  overlayRef.value?.focus()
})

onBeforeUnmount(() => voice.cleanup())
</script>

<style scoped>
.voice-overlay {
  position: fixed;
  inset: 0;
  z-index: var(--aui-z-modal);
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--aui-color-overlay);
  backdrop-filter: blur(12px);
  outline: none;
}
/* Subtle noise grain for depth: a colourless fractal-noise SVG, as before the restyle. */
.voice-overlay__grain {
  position: absolute;
  inset: 0;
  opacity: 0.03;
  background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E");
  pointer-events: none;
}
.voice-overlay__panel {
  position: relative;
  display: flex;
  flex-direction: column;
  width: 100%;
  max-width: 480px;
  max-height: 85vh;
  margin: var(--aui-space-4);
  border: 1px solid var(--aui-color-border);
  border-radius: var(--aui-radius-lg);
  background: var(--aui-color-surface);
  box-shadow: var(--aui-shadow-xl);
  overflow: hidden;
}
.voice-overlay__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--aui-space-4) var(--aui-space-5);
  border-bottom: 1px solid var(--aui-color-border);
  background: var(--aui-color-surface-raised);
}
.voice-overlay__tile {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 2rem;
  height: 2rem;
  border-radius: var(--aui-radius-lg);
  background: color-mix(in srgb, var(--aui-color-primary) 15%, transparent);
  color: var(--aui-color-primary);
}
.voice-overlay__conversation {
  flex: 1;
  overflow-y: auto;
  padding: var(--aui-space-5);
  min-height: 200px;
  max-height: 40vh;
  scroll-behavior: smooth;
}
.voice-overlay__empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--aui-space-3);
  height: 100%;
  min-height: 120px;
  color: var(--aui-color-text-muted);
  font-size: var(--aui-text-sm);
}
.voice-overlay__bubble {
  --bubble-tone: var(--aui-color-success);
  display: flex;
  gap: var(--aui-space-3);
  align-items: flex-start;
}
.voice-overlay__bubble--user {
  --bubble-tone: var(--aui-color-primary);
  flex-direction: row-reverse;
}
.voice-overlay__bubble-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  width: 1.75rem;
  height: 1.75rem;
  border-radius: var(--aui-radius-full);
  background: color-mix(in srgb, var(--bubble-tone) 18%, transparent);
  color: var(--bubble-tone);
}
.voice-overlay__bubble-content {
  max-width: 80%;
  padding: var(--aui-space-2) var(--aui-space-3);
  border: 1px solid color-mix(in srgb, var(--bubble-tone) 20%, var(--aui-color-border));
  border-radius: var(--aui-radius-lg);
  background: color-mix(in srgb, var(--bubble-tone) 10%, var(--aui-color-surface));
  color: var(--aui-color-text);
  font-size: var(--aui-text-sm);
  line-height: 1.5;
}
.voice-overlay__bubble-sender {
  display: block;
  margin-bottom: var(--aui-space-1);
  font-size: var(--aui-text-xs);
  font-weight: var(--aui-font-weight-semibold);
  text-transform: uppercase;
  opacity: 0.6;
}
.voice-overlay__live-transcript {
  margin-top: var(--aui-space-3);
  padding: var(--aui-space-2) var(--aui-space-3);
  border: 1px dashed color-mix(in srgb, var(--aui-color-info) 30%, transparent);
  border-radius: var(--aui-radius-lg);
  background: color-mix(in srgb, var(--aui-color-info) 8%, transparent);
  color: var(--aui-color-info);
  font-size: var(--aui-text-sm);
  font-style: italic;
}
.voice-overlay__hf {
  padding: var(--aui-space-2) var(--aui-space-5) 0;
}
.voice-overlay__controls {
  padding: var(--aui-space-5);
  border-top: 1px solid var(--aui-color-border);
}

/* Overlay enter/leave */
.voice-overlay-enter-active,
.voice-overlay-leave-active,
.voice-overlay-enter-active .voice-overlay__panel,
.voice-overlay-leave-active .voice-overlay__panel {
  transition: opacity var(--aui-transition), transform var(--aui-transition);
}
.voice-overlay-enter-from,
.voice-overlay-leave-to,
.voice-overlay-enter-from .voice-overlay__panel,
.voice-overlay-leave-to .voice-overlay__panel {
  opacity: 0;
}
.voice-overlay-enter-from .voice-overlay__panel {
  transform: translateY(var(--aui-space-5)) scale(0.96);
}
.voice-overlay-leave-to .voice-overlay__panel {
  transform: translateY(var(--aui-space-3)) scale(0.98);
}
.bubble-enter-active,
.fade-enter-active,
.fade-leave-active {
  transition: opacity var(--aui-transition), transform var(--aui-transition);
}
.bubble-enter-from {
  opacity: 0;
  transform: translateY(var(--aui-space-2));
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
@media (prefers-reduced-motion: reduce) {
  .voice-overlay-enter-active,
  .voice-overlay-leave-active,
  .voice-overlay-enter-active .voice-overlay__panel,
  .voice-overlay-leave-active .voice-overlay__panel,
  .bubble-enter-active,
  .fade-enter-active,
  .fade-leave-active {
    transition: none;
  }
}
</style>
