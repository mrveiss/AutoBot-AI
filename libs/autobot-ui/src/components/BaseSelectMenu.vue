<!--
  Copyright 2025-2026 mrveiss
  SPDX-License-Identifier: Apache-2.0

  BaseSelectMenu — a single-choice select whose list is a styled listbox, on the kit tokens
  (#14779).

  The behaviour (role="combobox" trigger with aria-expanded/aria-controls, role="listbox" with
  role="option" rows and aria-selected, Arrow/Home/End/typeahead, Enter/Space to choose, Escape
  to close, RTL direction, collision-aware positioning, portalling, a native form value when
  `name` is set) comes from the headless Reka UI select. This wrapper supplies the structure
  and the `--aui-*` styling. The kit holds no strings: `label` names the control,
  `placeholder` shows while nothing is chosen, and every row is `options[].label`, all
  translated by the app.

    props  : options, label, modelValue (v-model), placeholder, size (sm | md | lg),
             variant (default | subtle), disabled, name, required, dir
    emits  : update:modelValue

  Unscoped styles on purpose: the list is portalled out of this component's subtree, and a
  scoped style does not reliably reach the inner positioned element. Every class is `aui-select`.
-->
<script setup lang="ts">
import {
  SelectContent,
  SelectItem,
  SelectItemText,
  SelectPortal,
  SelectRoot,
  SelectTrigger,
  SelectValue,
  SelectViewport,
} from 'reka-ui'
import { computed } from 'vue'
import { resolveDirection, type KitDirection } from '../utils/direction'

export type SelectMenuSize = 'sm' | 'md' | 'lg'
export type SelectMenuVariant = 'default' | 'subtle'
export interface SelectMenuOption {
  value: string
  label: string
  disabled?: boolean
}

const props = withDefaults(
  defineProps<{
    options: SelectMenuOption[]
    /** Accessible name of the control (translated by the app). */
    label: string
    modelValue?: string
    placeholder?: string
    size?: SelectMenuSize
    variant?: SelectMenuVariant
    disabled?: boolean
    name?: string
    required?: boolean
    dir?: KitDirection
  }>(),
  {
    modelValue: undefined,
    placeholder: undefined,
    size: 'md',
    variant: 'default',
    disabled: false,
    name: undefined,
    required: false,
    dir: undefined,
  },
)

const emit = defineEmits<{ 'update:modelValue': [value: string] }>()

const direction = computed(() => resolveDirection(props.dir))
</script>

<template>
  <SelectRoot
    :model-value="modelValue"
    :disabled="disabled"
    :name="name"
    :required="required"
    :dir="direction"
    @update:model-value="emit('update:modelValue', String($event))"
  >
    <SelectTrigger
      class="aui-select__trigger"
      :class="[`aui-select__trigger--${size}`, `aui-select__trigger--${variant}`]"
      :aria-label="label"
    >
      <SelectValue :placeholder="placeholder" />
      <svg
        class="aui-select__chevron"
        viewBox="0 0 20 20"
        width="16"
        height="16"
        fill="none"
        stroke="currentColor"
        stroke-width="2"
        stroke-linecap="round"
        stroke-linejoin="round"
        aria-hidden="true"
        focusable="false"
      >
        <path d="M5 8l5 5 5-5" />
      </svg>
    </SelectTrigger>
    <SelectPortal>
      <SelectContent class="aui-select" position="popper" :side-offset="4">
        <SelectViewport class="aui-select__viewport">
          <SelectItem
            v-for="option in options"
            :key="option.value"
            class="aui-select__option"
            :value="option.value"
            :disabled="option.disabled"
          >
            <SelectItemText>{{ option.label }}</SelectItemText>
          </SelectItem>
        </SelectViewport>
      </SelectContent>
    </SelectPortal>
  </SelectRoot>
</template>

<style>
.aui-select__trigger {
  --aui-select-height: var(--aui-input-height-md);
  display: inline-flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--aui-space-2);
  min-width: 10rem;
  height: var(--aui-select-height);
  padding: 0 var(--aui-input-padding-x);
  border: 1px solid var(--aui-input-border);
  border-radius: var(--aui-radius-md);
  background: var(--aui-input-bg);
  color: var(--aui-color-text);
  font-family: var(--aui-font-sans);
  font-size: var(--aui-text-sm);
  cursor: pointer;
}

.aui-select__trigger--sm {
  --aui-select-height: var(--aui-input-height-sm);
  font-size: var(--aui-text-xs);
}

.aui-select__trigger--lg {
  --aui-select-height: var(--aui-input-height-lg);
  font-size: var(--aui-text-base);
}

.aui-select__trigger--subtle {
  border-color: transparent;
  background: var(--aui-color-surface-sunken);
}

.aui-select__trigger[data-placeholder] {
  color: var(--aui-color-text-muted);
}

.aui-select__trigger:focus-visible {
  outline: var(--aui-focus-ring-width) solid var(--aui-color-focus-ring);
  outline-offset: 2px;
}

.aui-select__trigger[data-disabled] {
  cursor: not-allowed;
  opacity: 0.5;
}

.aui-select__chevron {
  flex-shrink: 0;
  color: var(--aui-color-text-muted);
}

.aui-select {
  z-index: var(--aui-z-dropdown);
  min-width: var(--reka-select-trigger-width);
  max-height: var(--reka-select-content-available-height);
  overflow: hidden;
  border: 1px solid var(--aui-color-border);
  border-radius: var(--aui-radius-md);
  background: var(--aui-color-surface);
  box-shadow: var(--aui-shadow-md);
  color: var(--aui-color-text);
  font-family: var(--aui-font-sans);
  font-size: var(--aui-text-sm);
}

.aui-select__viewport {
  padding: var(--aui-space-1);
}

.aui-select__option {
  display: flex;
  align-items: center;
  padding: var(--aui-space-2) var(--aui-space-3);
  border-radius: var(--aui-radius-sm);
  outline: none;
  cursor: pointer;
  user-select: none;
}

.aui-select__option[data-highlighted] {
  background: var(--aui-color-surface-raised);
}

.aui-select__option[data-state='checked'] {
  color: var(--aui-color-primary);
  font-weight: var(--aui-font-weight-semibold);
}

.aui-select__option[data-disabled] {
  cursor: not-allowed;
  opacity: 0.5;
}
</style>
