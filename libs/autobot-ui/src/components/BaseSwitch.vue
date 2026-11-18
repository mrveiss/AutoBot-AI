<!--
  Copyright 2025-2026 mrveiss
  SPDX-License-Identifier: Apache-2.0

  BaseSwitch — an on/off switch (#14780 group 2).

  Replaces the hand-rolled switches the audit on #14780 counted (45 in 24 files): Tailwind
  `peer-checked` checkboxes in the SLM settings pages and `role="switch"` buttons in the user
  app. A real <button role="switch" aria-checked>, so Space and Enter toggle it natively and
  assistive tech announces it as a switch. A switch always has an accessible name: `label`
  (translated by the app), which the hand-rolled checkboxes lacked.

    props   : modelValue (v-model), label (accessible name), disabled, size (sm | md)
    emits   : update:modelValue, change (after a toggle, with the new value)
-->
<script setup lang="ts">
export type SwitchSize = 'sm' | 'md'

const props = withDefaults(
  defineProps<{
    modelValue: boolean
    label: string
    disabled?: boolean
    size?: SwitchSize
  }>(),
  { disabled: false, size: 'md' },
)

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  change: [value: boolean]
}>()

function toggle(): void {
  if (props.disabled) return
  const next = !props.modelValue
  emit('update:modelValue', next)
  emit('change', next)
}
</script>

<template>
  <button
    type="button"
    role="switch"
    class="aui-switch"
    :class="[`aui-switch--${size}`, { 'aui-switch--on': modelValue }]"
    :aria-checked="modelValue"
    :aria-label="label"
    :disabled="disabled"
    @click="toggle"
  >
    <span class="aui-switch__thumb" aria-hidden="true" />
  </button>
</template>

<style scoped>
.aui-switch {
  --aui-switch-w: 2.75rem;
  --aui-switch-h: 1.5rem;
  --aui-switch-pad: 2px;
  position: relative;
  display: inline-flex;
  flex-shrink: 0;
  align-items: center;
  width: var(--aui-switch-w);
  height: var(--aui-switch-h);
  padding: var(--aui-switch-pad);
  border: 1px solid var(--aui-color-border-strong);
  border-radius: var(--aui-radius-full);
  background: var(--aui-color-surface-sunken);
  cursor: pointer;
  transition: background-color var(--aui-transition-fast), border-color var(--aui-transition-fast);
}

.aui-switch--sm {
  --aui-switch-w: 2.25rem;
  --aui-switch-h: 1.25rem;
}

.aui-switch--on {
  background: var(--aui-color-primary);
  border-color: var(--aui-color-primary);
}

.aui-switch:focus-visible {
  outline: var(--aui-focus-ring-width) solid var(--aui-color-focus-ring);
  outline-offset: 2px;
}

.aui-switch:disabled {
  cursor: not-allowed;
  opacity: 0.5;
}

.aui-switch__thumb {
  width: calc(var(--aui-switch-h) - 2 * var(--aui-switch-pad) - 2px);
  height: calc(var(--aui-switch-h) - 2 * var(--aui-switch-pad) - 2px);
  border-radius: var(--aui-radius-full);
  background: var(--aui-color-surface);
  box-shadow: var(--aui-shadow-sm);
  transition: transform var(--aui-transition-fast);
}

.aui-switch--on .aui-switch__thumb {
  transform: translateX(calc(var(--aui-switch-w) - var(--aui-switch-h)));
}

@media (prefers-reduced-motion: reduce) {
  .aui-switch,
  .aui-switch__thumb {
    transition: none;
  }
}
</style>
