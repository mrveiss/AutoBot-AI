<!--
  Copyright 2025-2026 mrveiss
  SPDX-License-Identifier: Apache-2.0

  BaseTabs — a tabbed panel set on the kit tokens (#14779).

  The behaviour (tablist/tab/tabpanel roles, aria-selected, aria-controls, roving focus,
  Arrow/Home/End keys, RTL arrow direction) comes from the headless Reka UI tabs; this
  wrapper only supplies the structure and the `--aui-*` styling. The kit holds no strings:
  `label` names the tablist and every tab's text comes from `items[].label`, translated by
  the app.

    props  : items, label, modelValue (v-model) | defaultValue, variant (underline | pill),
             size (sm | md), orientation, activationMode, dir, listOnly
    slots  : `panel-<value>` — the content of the tab with that value;
             `icon` — scoped by `{ item }`, rendered before each tab's text
    item   : `class` reaches the trigger; `id` and `controls` replace the trigger's generated
             id and aria-controls (for a panel the caller owns, see `listOnly`)
    listOnly: renders the tablist only. The caller owns the tabpanel (it is routed content, not
             a slot), so the kit emits no `tabpanel` of its own.
    emits  : update:modelValue
-->
<script setup lang="ts">
import { computed, ref } from 'vue'
import { TabsContent, TabsList, TabsRoot, TabsTrigger } from 'reka-ui'
import { resolveDirection, type KitDirection } from '../utils/direction'

export type TabsVariant = 'underline' | 'pill'
export type TabsSize = 'sm' | 'md'
export interface TabItem {
  value: string
  label: string
  disabled?: boolean
  /** Extra class on this tab's trigger (e.g. a ui-mode class). */
  class?: string
  /** Replaces the trigger's generated id. */
  id?: string
  /** Replaces the trigger's aria-controls: the id of a tabpanel the caller owns. */
  controls?: string
}

const props = withDefaults(
  defineProps<{
    items: TabItem[]
    /** Accessible name of the tablist (translated by the app). */
    label: string
    modelValue?: string
    defaultValue?: string
    variant?: TabsVariant
    size?: TabsSize
    orientation?: 'horizontal' | 'vertical'
    /** `automatic` selects a tab as it takes focus; `manual` waits for Enter or Space. */
    activationMode?: 'automatic' | 'manual'
    dir?: KitDirection
    /** Render the tablist only; the caller supplies the `role="tabpanel"`. */
    listOnly?: boolean
  }>(),
  {
    modelValue: undefined,
    defaultValue: undefined,
    variant: 'underline',
    size: 'md',
    orientation: 'horizontal',
    activationMode: 'automatic',
    dir: undefined,
    listOnly: false,
  },
)

const emit = defineEmits<{ 'update:modelValue': [value: string] }>()

const direction = computed(() => resolveDirection(props.dir))
// Uncontrolled use keeps the chosen tab here, so items that arrive after mount still get a
// selection and a default never lands on a disabled first item (#20382).
const chosen = ref(props.defaultValue)
const active = computed(() => {
  if (props.modelValue !== undefined) return props.modelValue
  const kept = props.items.some((item) => item.value === chosen.value)
  return kept ? chosen.value : props.items.find((item) => !item.disabled)?.value
})

/** Overrides for the generated id / aria-controls; a list-only trigger controls no kit panel. */
function triggerAttrs(item: TabItem): Record<string, string | undefined> {
  const attrs: Record<string, string | undefined> = {}
  if (item.id !== undefined) attrs.id = item.id
  if (item.controls !== undefined || props.listOnly) attrs['aria-controls'] = item.controls
  return attrs
}

function onSelect(value: string | number): void {
  chosen.value = String(value)
  emit('update:modelValue', chosen.value)
}
</script>

<template>
  <TabsRoot
    class="aui-tabs"
    :class="[`aui-tabs--${variant}`, `aui-tabs--${size}`, `aui-tabs--${orientation}`]"
    :model-value="active"
    :orientation="orientation"
    :activation-mode="activationMode"
    :dir="direction"
    @update:model-value="onSelect"
  >
    <TabsList class="aui-tabs__list" :aria-label="label">
      <!-- as-child: Reka merges its roles and roving focus onto this button, and the button's own
           id / aria-controls win -- which is how an item names a panel the caller owns. -->
      <TabsTrigger v-for="item in items" :key="item.value" :value="item.value" :disabled="item.disabled" as-child>
        <button
          type="button"
          class="aui-tabs__trigger"
          :class="item.class"
          v-bind="triggerAttrs(item)"
        >
          <slot name="icon" :item="item" />
          {{ item.label }}
        </button>
      </TabsTrigger>
    </TabsList>
    <TabsContent
      v-for="item in listOnly ? [] : items"
      :key="item.value"
      class="aui-tabs__panel"
      :value="item.value"
    >
      <slot :name="`panel-${item.value}`" />
    </TabsContent>
  </TabsRoot>
</template>

<style scoped>
.aui-tabs {
  display: flex;
  flex-direction: column;
  gap: var(--aui-space-3);
  color: var(--aui-color-text);
  font-family: var(--aui-font-sans);
}

.aui-tabs--vertical {
  flex-direction: row;
}

.aui-tabs__list {
  display: flex;
  flex-shrink: 0;
  gap: var(--aui-space-1);
}

.aui-tabs--vertical .aui-tabs__list {
  flex-direction: column;
}

.aui-tabs--underline.aui-tabs--horizontal .aui-tabs__list {
  border-bottom: 1px solid var(--aui-color-border);
}

.aui-tabs--underline.aui-tabs--vertical .aui-tabs__list {
  border-inline-end: 1px solid var(--aui-color-border);
}

.aui-tabs__trigger {
  display: inline-flex;
  align-items: center;
  gap: var(--aui-space-2);
  --aui-tabs-pad-y: var(--aui-space-2);
  --aui-tabs-pad-x: var(--aui-space-4);
  padding: var(--aui-tabs-pad-y) var(--aui-tabs-pad-x);
  border: 0;
  background: transparent;
  color: var(--aui-color-text-muted);
  font: inherit;
  font-size: var(--aui-text-sm);
  font-weight: var(--aui-font-weight-medium);
  cursor: pointer;
  transition: color var(--aui-transition-fast), background-color var(--aui-transition-fast);
}

.aui-tabs--sm .aui-tabs__trigger {
  display: inline-flex;
  align-items: center;
  gap: var(--aui-space-2);
  --aui-tabs-pad-y: var(--aui-space-1);
  --aui-tabs-pad-x: var(--aui-space-3);
  font-size: var(--aui-text-xs);
}

.aui-tabs__trigger:hover:not(:disabled) {
  color: var(--aui-color-text);
}

.aui-tabs__trigger[data-state='active'] {
  color: var(--aui-color-primary);
}

.aui-tabs--underline.aui-tabs--horizontal .aui-tabs__trigger {
  margin-bottom: -1px;
  border-bottom: 2px solid transparent;
}

.aui-tabs--underline.aui-tabs--horizontal .aui-tabs__trigger[data-state='active'] {
  border-bottom-color: var(--aui-color-primary);
}

.aui-tabs--underline.aui-tabs--vertical .aui-tabs__trigger {
  margin-inline-end: -1px;
  border-inline-end: 2px solid transparent;
  text-align: start;
}

.aui-tabs--underline.aui-tabs--vertical .aui-tabs__trigger[data-state='active'] {
  border-inline-end-color: var(--aui-color-primary);
}

.aui-tabs--pill .aui-tabs__trigger {
  border-radius: var(--aui-radius-md);
}

.aui-tabs--pill .aui-tabs__trigger[data-state='active'] {
  background: var(--aui-color-primary);
  color: var(--aui-color-primary-contrast);
}

.aui-tabs__trigger:focus-visible,
.aui-tabs__panel:focus-visible {
  outline: var(--aui-focus-ring-width) solid var(--aui-color-focus-ring);
  outline-offset: 2px;
}

.aui-tabs__trigger:disabled {
  cursor: not-allowed;
  opacity: 0.5;
}

.aui-tabs__panel {
  flex: 1;
  min-width: 0;
}
</style>
