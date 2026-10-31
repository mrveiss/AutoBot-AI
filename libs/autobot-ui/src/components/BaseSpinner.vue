<!--
  Copyright 2025-2026 mrveiss
  SPDX-License-Identifier: Apache-2.0

  BaseSpinner — the one rotating loading indicator for content areas (#19906).
  Inside an action button use `BaseButton :loading` instead. Token-only styling;
  inherits the surrounding text color. The kit hardcodes no user-facing text: pass
  a translated `label` to announce the state, or omit it where a visible label is
  already next to the spinner (it is then hidden from assistive tech).
-->
<script setup lang="ts">
export type SpinnerSize = 'xs' | 'sm' | 'md' | 'lg' | 'xl'

withDefaults(defineProps<{ size?: SpinnerSize; label?: string }>(), { size: 'md' })
</script>

<template>
  <span
    class="aui-spinner"
    :class="`aui-spinner--${size}`"
    :role="label ? 'status' : undefined"
    :aria-hidden="label ? undefined : 'true'"
  >
    <span v-if="label" class="aui-spinner__label">{{ label }}</span>
  </span>
</template>

<style scoped>
.aui-spinner {
  position: relative;
  display: inline-block;
  flex-shrink: 0;
  box-sizing: border-box;
  border: 2px solid currentColor;
  border-top-color: transparent;
  border-radius: var(--aui-radius-full);
  animation: aui-spin 0.8s linear infinite;
}
.aui-spinner--xs { width: 0.75rem; height: 0.75rem; }
.aui-spinner--sm { width: 1rem; height: 1rem; }
.aui-spinner--md { width: 1.5rem; height: 1.5rem; }
.aui-spinner--lg { width: 2rem; height: 2rem; border-width: 3px; }
.aui-spinner--xl { width: 3rem; height: 3rem; border-width: 4px; }

.aui-spinner__label {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
}

@keyframes aui-spin {
  to {
    transform: rotate(360deg);
  }
}

@media (prefers-reduced-motion: reduce) {
  .aui-spinner {
    animation: none;
  }
}
</style>
