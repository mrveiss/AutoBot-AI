<!--
  Copyright 2025-2026 mrveiss
  SPDX-License-Identifier: Apache-2.0

  VoiceHandsFreeControls -- the hands-free mode's controls (#22349, #1030): the live input level on the kit
  `BaseProgress` and the silence-timeout slider with its value. The kit has no range slider (a gap recorded on
  the issue), so the slider is a native range input on tokens. Presentational; the caller owns the values.
-->
<template>
  <div class="voice-hf flex flex-col gap-2">
    <BaseProgress :value="level * 100" :label="$t('chat.voice.inputLevel')" size="sm" data-testid="voice-level" />
    <div class="flex items-center gap-2">
      <label :for="sliderId" class="text-xs text-autobot-text-muted whitespace-nowrap">{{ label }}</label>
      <input
        :id="sliderId"
        type="range"
        min="500"
        max="3000"
        step="100"
        class="voice-hf__slider flex-1"
        :value="silenceMs"
        data-testid="voice-silence"
        @input="emit('update:silenceMs', Number(($event.target as HTMLInputElement).value))"
      />
      <span class="text-xs text-autobot-text-secondary tabular-nums min-w-8 text-end" data-testid="voice-silence-value">
        {{ $t('chat.voice.silenceValue', { seconds: (silenceMs / 1000).toFixed(1) }) }}
      </span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useId } from 'vue'
import { BaseProgress } from '@autobot/ui'

defineProps<{
  /** The input level, 0 to 1 */
  level: number
  /** The silence timeout in milliseconds */
  silenceMs: number
  /** The slider's visible label (the panel and the overlay word it differently) */
  label: string
}>()
const emit = defineEmits<{ 'update:silenceMs': [value: number] }>()

const sliderId = `voice-silence-${useId()}`
</script>

<style scoped>
.voice-hf__slider {
  height: 0.25rem;
  appearance: none;
  border-radius: var(--aui-radius-full);
  background: var(--aui-color-border);
  outline: none;
  cursor: pointer;
}
.voice-hf__slider:focus-visible {
  outline: var(--aui-focus-ring-width) solid var(--aui-color-focus-ring);
  outline-offset: 2px;
}
.voice-hf__slider::-webkit-slider-thumb {
  appearance: none;
  width: 0.75rem;
  height: 0.75rem;
  border: 2px solid var(--aui-color-surface);
  border-radius: var(--aui-radius-full);
  background: var(--aui-color-primary);
  cursor: pointer;
}
.voice-hf__slider::-moz-range-thumb {
  width: 0.75rem;
  height: 0.75rem;
  border: 2px solid var(--aui-color-surface);
  border-radius: var(--aui-radius-full);
  background: var(--aui-color-primary);
  cursor: pointer;
}
</style>
