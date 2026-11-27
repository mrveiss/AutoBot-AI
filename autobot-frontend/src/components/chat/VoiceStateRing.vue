<!--
  Copyright 2025-2026 mrveiss
  SPDX-License-Identifier: Apache-2.0

  VoiceStateRing -- the voice UI's state indicator (#22349): a ring with the state icon and the state label under
  it, coloured by state (idle, listening, processing, speaking) from the `--aui-*` tokens. Presentational; shared
  by the voice panel and the voice overlay.
-->
<template>
  <div class="voice-state flex flex-col items-center gap-3">
    <div class="voice-state__ring" :class="`voice-state__ring--${state}`" data-testid="voice-state-ring">
      <Icon :name="icon" />
    </div>
    <p class="text-sm font-medium voice-state__label" :class="`voice-state__label--${state}`" data-testid="voice-state-label">
      {{ label }}
    </p>
  </div>
</template>

<script setup lang="ts">
import Icon, { type IconName } from '@/components/ui/Icon.vue'
import type { ConversationState } from '@/composables/useVoiceConversation'

defineProps<{ state: ConversationState; icon: IconName; label: string }>()
</script>

<style scoped>
.voice-state__ring {
  --voice-tone: var(--aui-color-text-muted);
  display: flex;
  align-items: center;
  justify-content: center;
  width: 4rem;
  height: 4rem;
  border: 2px solid var(--aui-color-border);
  border-radius: var(--aui-radius-full);
  color: var(--voice-tone);
  transition: border-color var(--aui-transition), color var(--aui-transition);
}
.voice-state__ring--listening { --voice-tone: var(--aui-color-error); animation: voice-ring-glow 1.5s ease-in-out infinite alternate; }
.voice-state__ring--processing { --voice-tone: var(--aui-color-info); }
.voice-state__ring--speaking { --voice-tone: var(--aui-color-success); animation: voice-ring-glow 1s ease-in-out infinite alternate; }
.voice-state__ring--listening,
.voice-state__ring--processing,
.voice-state__ring--speaking {
  border-color: color-mix(in srgb, var(--voice-tone) 50%, transparent);
}
.voice-state__label { color: var(--aui-color-text-muted); }
.voice-state__label--listening { color: var(--aui-color-error); }
.voice-state__label--processing { color: var(--aui-color-info); }
.voice-state__label--speaking { color: var(--aui-color-success); }

@keyframes voice-ring-glow {
  from { box-shadow: 0 0 1rem -0.25rem color-mix(in srgb, var(--voice-tone) 15%, transparent); }
  to { box-shadow: 0 0 1.75rem -0.25rem color-mix(in srgb, var(--voice-tone) 35%, transparent); }
}
@media (prefers-reduced-motion: reduce) {
  .voice-state__ring { animation: none; }
}
</style>
