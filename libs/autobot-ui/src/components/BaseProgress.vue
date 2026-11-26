<!--
  Copyright 2025-2026 mrveiss
  SPDX-License-Identifier: Apache-2.0

  BaseProgress — a determinate progress bar on the kit tokens (issue 21662).

  A real `role="progressbar"` with aria-valuenow/min/max, so assistive tech reads the value.
  The kit holds no text: `label` is the accessible name and is supplied, translated, by the app.
  The value is clamped to 0-100. `variant` follows BaseBadge's semantic vocabulary.

    props : value (0-100), label (accessible name), variant, size (sm | md)
    style : `--aui-progress-block-size` on the bar or an ancestor overrides the bar thickness
-->
<script setup lang="ts">
import { computed } from 'vue'
import type { SemanticVariant } from '../types/semantic'

export type ProgressVariant = SemanticVariant
export type ProgressSize = 'sm' | 'md'

const props = withDefaults(
  defineProps<{
    /** Completion, 0-100; anything outside is clamped. */
    value: number
    /** Accessible name of the bar (translated by the app). */
    label: string
    variant?: ProgressVariant
    size?: ProgressSize
  }>(),
  { variant: 'primary', size: 'md' },
)

const clamped = computed(() => (Number.isFinite(props.value) ? Math.min(100, Math.max(0, props.value)) : 0))
</script>

<template>
  <div
    class="aui-progress"
    :class="[`aui-progress--${variant}`, `aui-progress--${size}`]"
    role="progressbar"
    :aria-label="label"
    aria-valuemin="0"
    aria-valuemax="100"
    :aria-valuenow="clamped"
  >
    <div class="aui-progress__fill" :style="{ inlineSize: `${clamped}%` }" />
  </div>
</template>

<style scoped>
.aui-progress {
  --aui-progress-color: var(--aui-color-primary);
  inline-size: 100%;
  overflow: hidden;
  border-radius: var(--aui-radius-full);
  background-color: var(--aui-color-surface-sunken);
}

.aui-progress--sm {
  block-size: var(--aui-progress-block-size, 0.25rem);
}
.aui-progress--md {
  block-size: var(--aui-progress-block-size, 0.5rem);
}

.aui-progress--neutral {
  --aui-progress-color: var(--aui-color-text-muted);
}
.aui-progress--success {
  --aui-progress-color: var(--aui-color-success);
}
.aui-progress--warning {
  --aui-progress-color: var(--aui-color-warning);
}
.aui-progress--error {
  --aui-progress-color: var(--aui-color-error-solid);
}
.aui-progress--info {
  --aui-progress-color: var(--aui-color-info-solid);
}

.aui-progress__fill {
  block-size: 100%;
  border-radius: inherit;
  background-color: var(--aui-progress-color);
  transition: inline-size var(--aui-transition);
}
</style>
