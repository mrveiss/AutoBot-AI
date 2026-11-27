<!--
  Copyright 2025-2026 mrveiss
  SPDX-License-Identifier: Apache-2.0

  VoiceMicButton -- the voice UI's microphone control (#22349): a round button with pulse rings while listening and
  the hint under it. It is the one raw `<button>` of the voice UI: the kit button has no round, state-glowing form.
  The accessible name is the state label; the button is disabled while the reply is being processed.
  Presentational; shared by the voice panel and the voice overlay. The behaviour on click is the caller's.
-->
<template>
  <div class="voice-mic flex flex-col items-center">
    <div class="voice-mic__container">
      <template v-if="state === 'listening'">
        <div class="voice-mic__pulse" data-testid="voice-pulse"></div>
        <div class="voice-mic__pulse voice-mic__pulse--late" data-testid="voice-pulse"></div>
      </template>
      <button
        type="button"
        class="voice-mic__btn"
        :class="`voice-mic__btn--${state}`"
        :disabled="state === 'processing'"
        :aria-label="label"
        data-testid="voice-mic"
        @click="emit('click')"
      >
        <Icon :name="icon" />
      </button>
    </div>
    <p class="text-xs text-autobot-text-muted text-center mt-1" data-testid="voice-hint">{{ hint }}</p>
  </div>
</template>

<script setup lang="ts">
import Icon, { type IconName } from '@/components/ui/Icon.vue'
import type { ConversationState } from '@/composables/useVoiceConversation'

defineProps<{ state: ConversationState; icon: IconName; label: string; hint: string }>()
const emit = defineEmits<{ click: [] }>()
</script>

<style scoped>
.voice-mic__container {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 4.5rem;
  height: 4.5rem;
}
.voice-mic__pulse {
  position: absolute;
  inset: 0;
  border: 2px solid color-mix(in srgb, var(--aui-color-primary) 30%, transparent);
  border-radius: var(--aui-radius-full);
  animation: voice-pulse 2s ease-out infinite;
}
.voice-mic__pulse--late { animation-delay: 0.6s; }
.voice-mic__btn {
  --voice-tone: var(--aui-color-primary);
  position: relative;
  z-index: var(--aui-z-raised);
  display: flex;
  align-items: center;
  justify-content: center;
  width: 3rem;
  height: 3rem;
  border: 2px solid color-mix(in srgb, var(--voice-tone) 30%, transparent);
  border-radius: var(--aui-radius-full);
  background: color-mix(in srgb, var(--voice-tone) 10%, transparent);
  color: var(--voice-tone);
  cursor: pointer;
  transition: background-color var(--aui-transition), border-color var(--aui-transition);
}
.voice-mic__btn:hover:not(:disabled) {
  background: color-mix(in srgb, var(--voice-tone) 20%, transparent);
  border-color: color-mix(in srgb, var(--voice-tone) 50%, transparent);
}
.voice-mic__btn:focus-visible {
  outline: var(--aui-focus-ring-width) solid var(--aui-color-focus-ring);
  outline-offset: 2px;
}
.voice-mic__btn:disabled { cursor: not-allowed; opacity: 0.5; }
.voice-mic__btn--listening { --voice-tone: var(--aui-color-error); animation: voice-mic-glow 1.5s ease-in-out infinite alternate; }
.voice-mic__btn--processing { --voice-tone: var(--aui-color-info); }
.voice-mic__btn--speaking { --voice-tone: var(--aui-color-success); animation: voice-mic-glow 1s ease-in-out infinite alternate; }

@keyframes voice-pulse {
  from { transform: scale(0.7); opacity: 0.8; }
  to { transform: scale(1.3); opacity: 0; }
}
@keyframes voice-mic-glow {
  from { box-shadow: 0 0 1rem -0.25rem color-mix(in srgb, var(--voice-tone) 20%, transparent); }
  to { box-shadow: 0 0 1.75rem -0.25rem color-mix(in srgb, var(--voice-tone) 40%, transparent); }
}
@media (prefers-reduced-motion: reduce) {
  .voice-mic__pulse, .voice-mic__btn { animation: none; }
}
</style>
