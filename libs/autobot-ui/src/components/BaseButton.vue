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
import { computed, useAttrs } from 'vue'
import type { Component } from 'vue'

export type ButtonVariant =
  | 'primary' | 'secondary' | 'ghost' | 'error'
  | 'success' | 'warning' | 'info' | 'outline' | 'link'
export type ButtonSize = 'xs' | 'sm' | 'md' | 'lg' | 'xl'

const props = withDefaults(
  defineProps<{
    variant?: ButtonVariant
    size?: ButtonSize
    type?: 'button' | 'submit' | 'reset'
    /** Element or component to render. The kit never imports vue-router:
     *  callers pass `as="a"` or a RouterLink component, and `to`/`href`
     *  fall through as attrs. */
    as?: string | Component
    disabled?: boolean
    loading?: boolean
    block?: boolean
  }>(),
  {
    variant: 'primary',
    size: 'md',
    type: 'button',
    as: 'button',
    disabled: false,
    loading: false,
    block: false,
  },
)

defineOptions({ inheritAttrs: false })
const attrs = useAttrs()

const isDisabled = computed(() => props.disabled || props.loading)
const isNative = computed(() => props.as === 'button')
/** A disabled non-button (`as="a"`, a RouterLink) has no native `disabled`, so it is inert by hand. */
const isInertLink = computed(() => !isNative.value && isDisabled.value)

/** An inert component link (a RouterLink) renders as a plain `<a>` without its routing props:
 * its own navigate handler is never mounted, so no listener order can let it run. */
const renderAs = computed(() => (isInertLink.value && typeof props.as !== 'string' ? 'a' : props.as))
const boundAttrs = computed(() => {
  if (renderAs.value === props.as) return attrs
  const { to: _to, replace: _replace, ...rest } = attrs
  return rest
})

// Bound before the caller's attrs (v-bind below), so it runs before their @click and blocks it.
function blockInertClick(event: MouseEvent): void {
  if (!isInertLink.value) return
  event.preventDefault()
  event.stopImmediatePropagation()
}
</script>

<template>
  <component
    :is="renderAs"
    :type="isNative ? type : undefined"
    :disabled="isNative ? isDisabled : undefined"
    :aria-disabled="isInertLink ? 'true' : undefined"
    :tabindex="isInertLink ? -1 : undefined"
    :aria-busy="loading || undefined"
    @click="blockInertClick"
    v-bind="boundAttrs"
    :class="['aui-btn', `aui-btn--${variant}`, `aui-btn--${size}`, { 'aui-btn--block': block, 'aui-btn--loading': loading }]"
  >
    <span v-if="loading" class="aui-btn__spinner" aria-hidden="true" />
    <slot v-else name="icon-left" />
    <span class="aui-btn__label"><slot /></span>
  </component>
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

.aui-btn:disabled,
.aui-btn[aria-disabled='true'] {
  opacity: 0.55;
  cursor: not-allowed;
}

/* ---- sizes ---- */
.aui-btn--xs {
  padding: var(--aui-space-1) var(--aui-space-2);
  font-size: var(--aui-text-xs);
}
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

.aui-btn--xl {
  padding: var(--aui-space-4) var(--aui-space-6);
  font-size: var(--aui-text-xl);
}

.aui-btn--block {
  width: 100%;
}

/* ---- variants (semantic tokens only) ---- */
.aui-btn--primary {
  background-color: var(--aui-color-primary);
  color: var(--aui-color-primary-contrast);
}
.aui-btn--primary:hover:not(:disabled):not([aria-disabled='true']) {
  background-color: var(--aui-color-primary-hover);
}
.aui-btn--primary:active:not(:disabled):not([aria-disabled='true']) {
  background-color: var(--aui-color-primary-active);
}

.aui-btn--secondary {
  background-color: var(--aui-color-surface);
  border-color: var(--aui-color-border-strong);
  color: var(--aui-color-text);
}
.aui-btn--secondary:hover:not(:disabled):not([aria-disabled='true']) {
  background-color: var(--aui-color-surface-raised);
}

.aui-btn--ghost {
  background-color: transparent;
  color: var(--aui-color-text);
}
.aui-btn--ghost:hover:not(:disabled):not([aria-disabled='true']) {
  background-color: var(--aui-color-surface-raised);
}

.aui-btn--error {
  background-color: var(--aui-color-error);
  color: var(--aui-color-error-contrast);
}
.aui-btn--error:hover:not(:disabled):not([aria-disabled='true']) {
  background-color: color-mix(in srgb, var(--aui-color-error) 88%, black);
}

.aui-btn--success {
  background-color: var(--aui-color-success);
  color: var(--aui-color-success-contrast);
}
.aui-btn--success:hover:not(:disabled):not([aria-disabled='true']) {
  background-color: color-mix(in srgb, var(--aui-color-success) 88%, black);
}

.aui-btn--warning {
  background-color: var(--aui-color-warning);
  color: var(--aui-color-warning-contrast);
}
.aui-btn--warning:hover:not(:disabled):not([aria-disabled='true']) {
  background-color: color-mix(in srgb, var(--aui-color-warning) 88%, black);
}

.aui-btn--info {
  background-color: var(--aui-color-info);
  color: var(--aui-color-info-contrast);
}
.aui-btn--info:hover:not(:disabled):not([aria-disabled='true']) {
  background-color: color-mix(in srgb, var(--aui-color-info) 88%, black);
}

.aui-btn--outline {
  background-color: transparent;
  border-color: var(--aui-color-border-strong);
  color: var(--aui-color-text);
}
.aui-btn--outline:hover:not(:disabled):not([aria-disabled='true']) {
  background-color: var(--aui-color-surface-raised);
}

.aui-btn--link {
  background-color: transparent;
  color: var(--aui-color-primary);
  padding-left: 0;
  padding-right: 0;
  text-decoration: none;
}
.aui-btn--link:hover:not(:disabled):not([aria-disabled='true']) {
  color: var(--aui-color-primary-hover);
  text-decoration: underline;
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
