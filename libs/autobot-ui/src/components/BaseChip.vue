<!--
  Copyright 2025-2026 mrveiss
  SPDX-License-Identifier: Apache-2.0

  BaseChip -- the toggle chip (#21995): a small pill button that switches one option on
  and off and says so with `aria-pressed` (the composer's web, deep-research and
  reasoning switches). Not BaseBadge (a static label), not BaseSwitch (a form control),
  not BaseButton (a command; its pressed style is for icon buttons).

  Kit rules (see BaseButton.vue): `--aui-*` tokens only, scoped CSS keyed on `data-slot`,
  and no text -- the label is supplied, translated, by the app in the default slot.
  The chip is controlled: `pressed` in, `update:pressed` out. Enter and Space are the
  native button's own activation, so no key handler exists to double-fire.
-->
<script setup lang="ts">
export type ChipSize = 'sm' | 'md'

const props = withDefaults(
  defineProps<{
    pressed?: boolean
    size?: ChipSize
    disabled?: boolean
  }>(),
  { pressed: false, size: 'md', disabled: false },
)

const emit = defineEmits<{ 'update:pressed': [value: boolean] }>()

function onClick(): void {
  if (props.disabled) return
  emit('update:pressed', !props.pressed)
}
</script>

<template>
  <button
    type="button"
    data-slot="chip"
    :class="['aui-chip', `aui-chip--${size}`, { 'aui-chip--pressed': pressed }]"
    :aria-pressed="pressed ? 'true' : 'false'"
    :disabled="disabled"
    @click="onClick"
  >
    <span v-if="$slots.icon" data-slot="chip-icon" class="aui-chip__icon" aria-hidden="true">
      <slot name="icon" />
    </span>
    <span data-slot="chip-label"><slot /></span>
  </button>
</template>

<style scoped>
[data-slot="chip"] {
  --aui-chip-pad-y: var(--aui-space-1);
  --aui-chip-pad-x: var(--aui-space-3);
  display: inline-flex;
  align-items: center;
  gap: var(--aui-space-1);
  padding: var(--aui-chip-pad-y) var(--aui-chip-pad-x);
  border: 1px solid var(--aui-color-border-strong);
  border-radius: var(--aui-radius-full);
  background-color: transparent;
  color: var(--aui-color-text-muted);
  font-family: var(--aui-font-sans);
  font-size: var(--aui-text-sm);
  font-weight: var(--aui-font-weight-medium);
  line-height: 1.2;
  white-space: nowrap;
  cursor: pointer;
  user-select: none;
  transition: background-color var(--aui-transition), border-color var(--aui-transition),
    color var(--aui-transition);
}

[data-slot="chip"]:hover:not(:disabled) {
  background-color: var(--aui-color-surface-raised);
  color: var(--aui-color-text);
}

[data-slot="chip"]:focus-visible {
  outline: var(--aui-focus-ring-width) solid var(--aui-color-focus-ring);
  outline-offset: 1px;
}

[data-slot="chip"]:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

/* ---- sizes ---- */
.aui-chip--sm {
  --aui-chip-pad-y: 0.125rem;
  --aui-chip-pad-x: var(--aui-space-2);
  font-size: var(--aui-text-xs);
}

/* Compact layout density tightens the chip; the attribute is set by the app shell. */
:where([data-layout-density='compact']) [data-slot="chip"] {
  --aui-chip-pad-y: 0.125rem;
  --aui-chip-pad-x: var(--aui-space-2);
}

/* ---- pressed: a surface fill, an accent border and full-strength text ---- */
[data-slot="chip"][aria-pressed='true'] {
  background-color: var(--aui-color-surface-raised);
  border-color: var(--aui-color-primary);
  color: var(--aui-color-text);
}

[data-slot="chip-icon"] {
  display: inline-flex;
  align-items: center;
  flex-shrink: 0;
}

@media (prefers-reduced-motion: reduce) {
  [data-slot="chip"] {
    transition: none;
  }
}
</style>
