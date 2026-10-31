<!--
  Copyright 2025-2026 mrveiss
  SPDX-License-Identifier: Apache-2.0

  BasePopover — a non-modal panel anchored to a trigger, on the kit tokens (#14779).

  The behaviour (aria-haspopup/aria-expanded/aria-controls on the trigger, role="dialog" on the
  panel, focus moved in on open and restored on close, Escape and outside-press dismissal,
  collision-aware positioning, portalling) comes from the headless Reka UI popover. This
  wrapper supplies the structure and the `--aui-*` styling. The kit holds no strings: `label`
  is the panel's accessible name, translated by the app.

    props  : label, open (v-model, optional), size (sm | md | lg), side, align
    slots  : `trigger` — one focusable element (receives the trigger behaviour);
             default — the panel content, scoped `{ close }`
    emits  : update:open

  Unscoped styles on purpose: the panel is portalled out of this component's subtree, and a
  scoped style does not reliably reach the inner positioned element. Every class is `aui-popover`.
-->
<script setup lang="ts">
import { PopoverContent, PopoverPortal, PopoverRoot, PopoverTrigger } from 'reka-ui'

export type PopoverSize = 'sm' | 'md' | 'lg'

withDefaults(
  defineProps<{
    /** Accessible name of the panel (translated by the app). */
    label: string
    open?: boolean
    size?: PopoverSize
    side?: 'top' | 'right' | 'bottom' | 'left'
    align?: 'start' | 'center' | 'end'
  }>(),
  { open: undefined, size: 'md', side: 'bottom', align: 'center' },
)

const emit = defineEmits<{ 'update:open': [open: boolean] }>()
</script>

<template>
  <PopoverRoot v-slot="{ close }" :open="open" @update:open="emit('update:open', $event)">
    <PopoverTrigger as-child>
      <slot name="trigger" />
    </PopoverTrigger>
    <PopoverPortal>
      <PopoverContent
        class="aui-popover"
        :class="`aui-popover--${size}`"
        :aria-label="label"
        :side="side"
        :align="align"
        :side-offset="8"
        :collision-padding="8"
      >
        <slot :close="close" />
      </PopoverContent>
    </PopoverPortal>
  </PopoverRoot>
</template>

<style>
.aui-popover {
  z-index: var(--aui-z-dropdown);
  width: 18rem;
  max-width: calc(100vw - 2 * var(--aui-space-4));
  padding: var(--aui-space-4);
  border: 1px solid var(--aui-color-border);
  border-radius: var(--aui-radius-lg);
  background: var(--aui-color-surface);
  box-shadow: var(--aui-shadow-lg);
  color: var(--aui-color-text);
  font-family: var(--aui-font-sans);
  font-size: var(--aui-text-sm);
}

.aui-popover--sm {
  width: 12rem;
  padding: var(--aui-space-3);
}

.aui-popover--lg {
  width: 26rem;
}

.aui-popover:focus-visible {
  outline: var(--aui-focus-ring-width) solid var(--aui-color-focus-ring);
  outline-offset: 2px;
}
</style>
