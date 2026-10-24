<!--
  Copyright 2025-2026 mrveiss
  SPDX-License-Identifier: Apache-2.0

  BaseAccordion — stacked sections that expand and collapse (#14779), on Reka UI's Accordion.

  Reka supplies the WAI-ARIA accordion pattern: each header is a heading wrapping a button
  with aria-expanded / aria-controls, the panel is a region labelled by it, and Arrow / Home
  / End move between headers (mirrored in RTL). The kit adds the token styling and a list
  API. The kit ships no text; item labels come in translated.

    props : modelValue (v-model: the open value for type single, the open values for
            multiple), items ({ value, label, disabled? }[]), type (single | multiple),
            collapsible (single only: the open item can close), level (heading level of
            each header, 2-6; default 3), dir (ltr | rtl; defaults to the document's)
    slots : label ({ item, open }: the header content), panel ({ item }: the item's content)
    emits : update:modelValue
-->
<script setup lang="ts">
import { toRef } from 'vue'
import { AccordionContent, AccordionHeader, AccordionItem, AccordionRoot, AccordionTrigger } from 'reka-ui'
import { useDocumentDirection, type Direction } from '../composables/useDocumentDirection'

export interface AccordionEntry {
  value: string
  label: string
  disabled?: boolean
}

const props = withDefaults(
  defineProps<{
    modelValue?: string | string[]
    items: AccordionEntry[]
    type?: 'single' | 'multiple'
    collapsible?: boolean
    level?: 2 | 3 | 4 | 5 | 6
    dir?: Direction
  }>(),
  { modelValue: undefined, type: 'single', collapsible: true, level: 3, dir: undefined },
)

const emit = defineEmits<{ 'update:modelValue': [value: string | string[] | undefined] }>()
const direction = useDocumentDirection(toRef(props, 'dir'))

function isOpen(value: string): boolean {
  const open = props.modelValue
  return Array.isArray(open) ? open.includes(value) : open === value
}
</script>

<template>
  <AccordionRoot
    class="aui-accordion"
    :type="type"
    :collapsible="collapsible"
    :model-value="modelValue"
    :dir="direction"
    @update:model-value="emit('update:modelValue', $event as string | string[] | undefined)"
  >
    <AccordionItem
      v-for="item in items"
      :key="item.value"
      class="aui-accordion__item"
      :value="item.value"
      :disabled="item.disabled"
    >
      <AccordionHeader class="aui-accordion__header" :as="`h${level}`">
        <AccordionTrigger class="aui-accordion__trigger">
          <span class="aui-accordion__label">
            <slot name="label" :item="item" :open="isOpen(item.value)">{{ item.label }}</slot>
          </span>
          <svg class="aui-accordion__chevron" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
            <path d="M6 9l6 6 6-6" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" />
          </svg>
        </AccordionTrigger>
      </AccordionHeader>
      <AccordionContent class="aui-accordion__panel">
        <div class="aui-accordion__body"><slot name="panel" :item="item" /></div>
      </AccordionContent>
    </AccordionItem>
  </AccordionRoot>
</template>

<style scoped>
.aui-accordion {
  border: 1px solid var(--aui-color-border);
  border-radius: var(--aui-radius-md);
  background: var(--aui-color-surface);
}

.aui-accordion__item + .aui-accordion__item {
  border-top: 1px solid var(--aui-color-border);
}

.aui-accordion__header {
  margin: 0;
  font-size: inherit;
}

.aui-accordion__trigger {
  display: flex;
  width: 100%;
  align-items: center;
  justify-content: space-between;
  gap: var(--aui-space-3);
  padding: var(--aui-space-3) var(--aui-space-4);
  border: none;
  background: none;
  color: var(--aui-color-text);
  font: inherit;
  font-size: var(--aui-text-sm);
  font-weight: var(--aui-font-weight-medium);
  text-align: start;
  cursor: pointer;
}

.aui-accordion__trigger:hover:not([data-disabled]) {
  background: var(--aui-color-surface-raised);
}

.aui-accordion__trigger[data-disabled] {
  opacity: 0.5;
  cursor: not-allowed;
}

.aui-accordion__trigger:focus-visible {
  outline: var(--aui-focus-ring-width) solid var(--aui-color-focus-ring);
  outline-offset: -2px;
}

.aui-accordion__chevron {
  width: 1rem;
  height: 1rem;
  flex-shrink: 0;
  color: var(--aui-color-text-muted);
  transition: transform var(--aui-transition-fast);
}

.aui-accordion__trigger[data-state='open'] .aui-accordion__chevron {
  transform: rotate(180deg);
}

.aui-accordion__body {
  padding: 0 var(--aui-space-4) var(--aui-space-4);
  color: var(--aui-color-text);
  font-size: var(--aui-text-sm);
}

@media (prefers-reduced-motion: reduce) {
  .aui-accordion__chevron {
    transition: none;
  }
}
</style>
