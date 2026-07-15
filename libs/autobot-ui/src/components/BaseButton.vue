<!--
  Copyright 2025-2026 mrveiss
  SPDX-License-Identifier: Apache-2.0

  BaseButton — canonical proof-of-pattern for @autobot/ui.

  Demonstrates the kit's rules that every later component follows:
    - styled ONLY via `--aui-*` semantic tokens (no literal colors) so each
      app renders it in its own identity;
    - scoped CSS (no dependency on the consuming app's Tailwind build);
    - accessible by default (real <button>, focus-visible ring, aria-busy,
      disabled while loading);
    - honors prefers-reduced-motion via the token motion values.
-->
<script setup lang="ts">
import { computed } from 'vue'

export type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger'
export type ButtonSize = 'sm' | 'md' | 'lg'

const props = withDefaults(
  defineProps<{
    variant?: ButtonVariant
    size?: ButtonSize
    type?: 'button' | 'submit' | 'reset'
    disabled?: boolean
    loading?: boolean
    block?: boolean
  }>(),
  {
    variant: 'primary',
    size: 'md',
    type: 'button',
    disabled: false,
    loading: false,
    block: false,
  },
)

const isDisabled = computed(() => props.disabled || props.loading)
</script>

<template>
  <button
    :type="type"
    :disabled="isDisabled"
    :aria-busy="loading || undefined"
    :class="['aui-btn', `aui-btn--${variant}`, `aui-btn--${size}`, { 'aui-btn--block': block, 'aui-btn--loading': loading }]"
  >
    <span v-if="loading" class="aui-btn__spinner" aria-hidden="true" />
    <span class="aui-btn__label"><slot /></span>
  </button>
</template>

<style scoped>
.aui-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: var(--aui-space-2);
  border: 1px solid transparent;
  border-radius: var(--aui-radius-md);
  font-family: var(--aui-font-sans);
  font-weight: var(--aui-font-weight-medium);
  line-height: 1.2;
  cursor: pointer;
  transition: background-color var(--aui-transition), border-color var(--aui-transition),
    color var(--aui-transition);
  user-select: none;
}

.aui-btn:focus-visible {
  outline: var(--aui-focus-ring-width) solid var(--aui-color-focus-ring);
  outline-offset: 1px;
}

.aui-btn:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

/* ---- sizes ---- */
.aui-btn--sm {
  padding: var(--aui-space-1) var(--aui-space-3);
  font-size: var(--aui-text-sm);
}
.aui-btn--md {
  padding: var(--aui-space-2) var(--aui-space-4);
  font-size: var(--aui-text-base);
}
.aui-btn--lg {
  padding: var(--aui-space-3) var(--aui-space-5);
  font-size: var(--aui-text-lg);
}

.aui-btn--block {
  width: 100%;
}

/* ---- variants (semantic tokens only) ---- */
.aui-btn--primary {
  background-color: var(--aui-color-primary);
  color: var(--aui-color-primary-contrast);
}
.aui-btn--primary:hover:not(:disabled) {
  background-color: var(--aui-color-primary-hover);
}
.aui-btn--primary:active:not(:disabled) {
  background-color: var(--aui-color-primary-active);
}

.aui-btn--secondary {
  background-color: var(--aui-color-surface);
  border-color: var(--aui-color-border-strong);
  color: var(--aui-color-text);
}
.aui-btn--secondary:hover:not(:disabled) {
  background-color: var(--aui-color-surface-raised);
}

.aui-btn--ghost {
  background-color: transparent;
  color: var(--aui-color-text);
}
.aui-btn--ghost:hover:not(:disabled) {
  background-color: var(--aui-color-surface-raised);
}

.aui-btn--danger {
  background-color: var(--aui-color-danger);
  color: var(--aui-color-danger-contrast);
}
.aui-btn--danger:hover:not(:disabled) {
  background-color: color-mix(in srgb, var(--aui-color-danger) 88%, black);
}

/* ---- loading spinner ---- */
.aui-btn__spinner {
  width: 1em;
  height: 1em;
  border: 2px solid currentColor;
  border-top-color: transparent;
  border-radius: var(--aui-radius-full);
  animation: aui-btn-spin 0.6s linear infinite;
}

@keyframes aui-btn-spin {
  to {
    transform: rotate(360deg);
  }
}

@media (prefers-reduced-motion: reduce) {
  .aui-btn__spinner {
    animation-duration: 1.4s;
  }
}
</style>
