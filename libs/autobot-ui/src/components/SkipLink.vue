<!--
  Copyright 2025-2026 mrveiss
  SPDX-License-Identifier: Apache-2.0

  SkipLink — canonical "skip to main content" link for both apps (#17565).
  Promoted from autobot-slm-frontend (#754) so the main console stops
  hand-rolling its own. Visually hidden until focused; activating it moves
  FOCUS to the target, not just the scroll position. The kit hardcodes no
  user-facing text — the app passes its translated label. Token-only styling.
-->
<script setup lang="ts">
const props = withDefaults(
  defineProps<{
    /** Text shown when focused — the app's translated string. */
    label: string
    /** CSS selector of the element that receives focus. */
    target?: string
  }>(),
  { target: '#main-content' },
)

function skip(event: MouseEvent): void {
  const el = document.querySelector(props.target)
  if (!(el instanceof HTMLElement)) return
  event.preventDefault()
  // A non-interactive landmark only takes programmatic focus with tabindex.
  if (!el.hasAttribute('tabindex')) el.setAttribute('tabindex', '-1')
  el.focus()
}
</script>

<template>
  <a :href="target" class="aui-skip-link" @click="skip">{{ label }}</a>
</template>

<style scoped>
.aui-skip-link {
  position: absolute;
  top: 0;
  left: var(--aui-space-2);
  z-index: calc(var(--aui-z-modal) + 1);
  transform: translateY(-200%);
  padding: var(--aui-space-2) var(--aui-space-4);
  border-radius: 0 0 var(--aui-radius-md) var(--aui-radius-md);
  background: var(--aui-color-primary);
  color: var(--aui-color-primary-contrast);
  font-family: var(--aui-font-sans);
  font-size: var(--aui-text-sm);
  font-weight: var(--aui-font-weight-semibold);
  text-decoration: none;
}

.aui-skip-link:focus {
  transform: translateY(0);
  outline: var(--aui-focus-ring-width) solid var(--aui-color-focus-ring);
  outline-offset: 2px;
}
</style>
