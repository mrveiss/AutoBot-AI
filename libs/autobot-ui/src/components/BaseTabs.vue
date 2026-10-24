<!--
  Copyright 2025-2026 mrveiss
  SPDX-License-Identifier: Apache-2.0

  BaseTabs — a tab bar with its panels (#14779), on Reka UI's Tabs primitive.

  Reka supplies the WAI-ARIA tabs pattern: roving tabindex, Arrow / Home / End (mirrored in
  RTL), aria-selected / aria-controls / aria-labelledby. The kit adds the token styling and
  the API derived from the user app's useTabs call sites (ChatTabs, ProfileModal,
  KnowledgeHealth, ...): a list of tabs and one panel per tab. The kit ships no text; tab
  labels and the list's accessible name come in translated.

    props : modelValue (v-model, the active tab's value), tabs ({ value, label, disabled? }[]),
            label (names the tablist), orientation (horizontal | vertical),
            activation (automatic: focus selects | manual: Enter / Space selects),
            dir (ltr | rtl; defaults to the document's)
    slots : tab ({ tab, selected }: the trigger content, e.g. an icon or a count),
            panel ({ tab }: the content of each tab's panel)
    emits : update:modelValue
-->
<script setup lang="ts">
import { toRef } from 'vue'
import { TabsContent, TabsList, TabsRoot, TabsTrigger } from 'reka-ui'
import { useDocumentDirection, type Direction } from '../composables/useDocumentDirection'

export interface TabItem {
  value: string
  label: string
  disabled?: boolean
}

const props = withDefaults(
  defineProps<{
    modelValue: string
    tabs: TabItem[]
    label: string
    orientation?: 'horizontal' | 'vertical'
    activation?: 'automatic' | 'manual'
    dir?: Direction
  }>(),
  { orientation: 'horizontal', activation: 'automatic', dir: undefined },
)

const emit = defineEmits<{ 'update:modelValue': [value: string] }>()
const direction = useDocumentDirection(toRef(props, 'dir'))

function onUpdate(value: string | number) {
  emit('update:modelValue', String(value))
}
</script>

<template>
  <TabsRoot
    class="aui-tabs"
    :class="`aui-tabs--${orientation}`"
    :model-value="modelValue"
    :orientation="orientation"
    :activation-mode="activation"
    :dir="direction"
    @update:model-value="onUpdate"
  >
    <TabsList class="aui-tabs__list" :aria-label="label">
      <TabsTrigger
        v-for="tab in tabs"
        :key="tab.value"
        class="aui-tabs__tab"
        :value="tab.value"
        :disabled="tab.disabled"
      >
        <slot name="tab" :tab="tab" :selected="tab.value === modelValue">{{ tab.label }}</slot>
      </TabsTrigger>
    </TabsList>
    <TabsContent v-for="tab in tabs" :key="tab.value" class="aui-tabs__panel" :value="tab.value">
      <slot name="panel" :tab="tab" />
    </TabsContent>
  </TabsRoot>
</template>

<style scoped>
.aui-tabs--vertical {
  display: flex;
  gap: var(--aui-space-4);
}

.aui-tabs__list {
  display: flex;
  gap: var(--aui-space-1);
  border-bottom: 1px solid var(--aui-color-border);
  overflow-x: auto;
}

.aui-tabs--vertical .aui-tabs__list {
  flex-direction: column;
  border-bottom: none;
  border-inline-end: 1px solid var(--aui-color-border);
  overflow-x: visible;
}

.aui-tabs__tab {
  display: inline-flex;
  align-items: center;
  gap: var(--aui-space-2);
  padding: var(--aui-space-2) var(--aui-space-4);
  margin-bottom: -1px;
  border: none;
  border-bottom: 2px solid transparent;
  background: none;
  color: var(--aui-color-text-muted);
  font: inherit;
  font-size: var(--aui-text-sm);
  font-weight: var(--aui-font-weight-medium);
  white-space: nowrap;
  cursor: pointer;
  transition: color var(--aui-transition-fast), border-color var(--aui-transition-fast);
}

.aui-tabs--vertical .aui-tabs__tab {
  margin-bottom: 0;
  margin-inline-end: -1px;
  border-bottom: none;
  border-inline-end: 2px solid transparent;
  justify-content: flex-start;
}

.aui-tabs__tab:hover:not([data-disabled]) {
  color: var(--aui-color-text);
}

.aui-tabs__tab[data-state='active'] {
  color: var(--aui-color-primary);
  border-color: var(--aui-color-primary);
}

.aui-tabs__tab[data-disabled] {
  opacity: 0.5;
  cursor: not-allowed;
}

.aui-tabs__tab:focus-visible {
  outline: var(--aui-focus-ring-width) solid var(--aui-color-focus-ring);
  outline-offset: -2px;
  border-radius: var(--aui-radius-sm);
}

.aui-tabs__panel {
  padding-top: var(--aui-space-4);
}

.aui-tabs--vertical .aui-tabs__panel {
  flex: 1;
  padding-top: 0;
}

.aui-tabs__panel:focus-visible {
  outline: var(--aui-focus-ring-width) solid var(--aui-color-focus-ring);
  outline-offset: 2px;
}

@media (prefers-reduced-motion: reduce) {
  .aui-tabs__tab {
    transition: none;
  }
}
</style>
