<!--
  Copyright 2025-2026 mrveiss
  SPDX-License-Identifier: Apache-2.0

  BaseAccordion — a stack of collapsible sections on the kit tokens (#14779).

  The behaviour (heading + button triggers, aria-expanded, aria-controls, region panels labelled
  by their trigger, Arrow/Home/End focus movement, single or multiple open) comes from the
  headless Reka UI accordion. This wrapper supplies the structure and the `--aui-*` styling.
  The kit holds no strings: every heading is `items[].label`, translated by the app.

    props  : items, type (single | multiple), modelValue (v-model) | defaultValue, collapsible,
             variant (default | flush), size (sm | md), orientation, headingLevel (2-6), dir
    slots  : `panel-<value>` — the content of the section with that value
    emits  : update:modelValue (a string for `single`, a string[] for `multiple`)
-->
<script setup lang="ts">
import {
  AccordionContent,
  AccordionHeader,
  AccordionItem,
  AccordionRoot,
  AccordionTrigger,
} from 'reka-ui'
import { computed } from 'vue'
import { resolveDirection, type KitDirection } from '../utils/direction'

export type AccordionVariant = 'default' | 'flush'
export type AccordionSize = 'sm' | 'md'
export type AccordionValue = string | string[]
export interface AccordionItemSpec {
  value: string
  label: string
  disabled?: boolean
}

const props = withDefaults(
  defineProps<{
    items: AccordionItemSpec[]
    type?: 'single' | 'multiple'
    modelValue?: AccordionValue
    defaultValue?: AccordionValue
    /** `single` only: allow the open section to be closed again. */
    collapsible?: boolean
    variant?: AccordionVariant
    size?: AccordionSize
    /** The heading level the section titles are exposed as (keep the page outline valid). */
    headingLevel?: 2 | 3 | 4 | 5 | 6
    /** `horizontal` moves focus with Left/Right (mirrored under RTL) instead of Up/Down. */
    orientation?: 'vertical' | 'horizontal'
    dir?: KitDirection
  }>(),
  {
    type: 'single',
    modelValue: undefined,
    defaultValue: undefined,
    collapsible: true,
    variant: 'default',
    size: 'md',
    headingLevel: 3,
    orientation: 'vertical',
    dir: undefined,
  },
)

const emit = defineEmits<{ 'update:modelValue': [value: AccordionValue] }>()

const direction = computed(() => resolveDirection(props.dir))
const heading = computed(() => `h${props.headingLevel}`)
</script>

<template>
  <AccordionRoot
    class="aui-accordion"
    :class="[`aui-accordion--${variant}`, `aui-accordion--${size}`]"
    :type="type"
    :collapsible="collapsible"
    :model-value="modelValue"
    :default-value="defaultValue"
    :orientation="orientation"
    :dir="direction"
    @update:model-value="emit('update:modelValue', $event as AccordionValue)"
  >
    <AccordionItem
      v-for="item in items"
      :key="item.value"
      class="aui-accordion__item"
      :value="item.value"
      :disabled="item.disabled"
    >
      <AccordionHeader :as="heading" class="aui-accordion__header">
        <AccordionTrigger class="aui-accordion__trigger">
          <span class="aui-accordion__label">{{ item.label }}</span>
          <svg
            class="aui-accordion__chevron"
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
        </AccordionTrigger>
      </AccordionHeader>
      <AccordionContent class="aui-accordion__content">
        <div class="aui-accordion__panel">
          <slot :name="`panel-${item.value}`" />
        </div>
      </AccordionContent>
    </AccordionItem>
  </AccordionRoot>
</template>

<style scoped>
.aui-accordion {
  color: var(--aui-color-text);
  font-family: var(--aui-font-sans);
}

.aui-accordion--default {
  border: 1px solid var(--aui-color-border);
  border-radius: var(--aui-radius-md);
  background: var(--aui-color-surface);
}

.aui-accordion__item + .aui-accordion__item {
  border-top: 1px solid var(--aui-color-border);
}

.aui-accordion__header {
  margin: 0;
  font: inherit;
}

.aui-accordion__trigger {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--aui-space-3);
  width: 100%;
  padding: var(--aui-space-3) var(--aui-space-4);
  border: 0;
  background: transparent;
  color: inherit;
  font: inherit;
  font-size: var(--aui-text-base);
  font-weight: var(--aui-font-weight-medium);
  text-align: start;
  cursor: pointer;
}

.aui-accordion--sm .aui-accordion__trigger {
  padding: var(--aui-space-2) var(--aui-space-3);
  font-size: var(--aui-text-sm);
}

.aui-accordion--flush .aui-accordion__trigger {
  padding-inline: 0;
}

.aui-accordion__trigger:hover:not(:disabled) {
  background: var(--aui-color-surface-raised);
}

.aui-accordion__trigger:focus-visible {
  outline: var(--aui-focus-ring-width) solid var(--aui-color-focus-ring);
  outline-offset: -2px;
}

.aui-accordion__trigger:disabled {
  cursor: not-allowed;
  opacity: 0.5;
}

.aui-accordion__chevron {
  flex-shrink: 0;
  color: var(--aui-color-text-muted);
  transition: transform var(--aui-transition-fast);
}

.aui-accordion__trigger[data-state='open'] .aui-accordion__chevron {
  transform: rotate(180deg);
}

.aui-accordion__panel {
  padding: var(--aui-space-2) var(--aui-space-4) var(--aui-space-4);
  font-size: var(--aui-text-sm);
}

.aui-accordion--flush .aui-accordion__panel {
  padding-inline: 0;
}
</style>
