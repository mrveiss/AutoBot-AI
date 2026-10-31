<!--
  Copyright 2025-2026 mrveiss
  SPDX-License-Identifier: Apache-2.0

  BaseDropdownMenu — an action menu opened from a trigger, on the kit tokens (#14779).

  The behaviour (aria-haspopup/aria-expanded on the trigger, role="menu"/"menuitem", focus
  moved into the menu, Arrow/Home/End/typeahead, Escape to close and return focus, RTL
  submenu and arrow direction, collision-aware positioning, portalling) comes from the
  headless Reka UI menu. This wrapper supplies the structure and the `--aui-*` styling. The
  kit holds no strings: every item label is `items[].label`, translated by the app.

    props  : items, open (v-model, optional), size (sm | md), side, align, dir
    slots  : `trigger` — one focusable element (receives the trigger behaviour);
             `item` — optional custom row content, scoped `{ item }`
    emits  : select (the chosen item's key), update:open

  Unscoped styles on purpose: the menu is portalled out of this component's subtree, and a
  scoped style does not reliably reach the inner positioned element. Every class is `aui-menu`.
-->
<script setup lang="ts">
import {
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuPortal,
  DropdownMenuRoot,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from 'reka-ui'
import { computed } from 'vue'
import { resolveDirection, type KitDirection } from '../utils/direction'

export type MenuSize = 'sm' | 'md'
export type MenuItemVariant = 'default' | 'danger'
export interface MenuItem {
  key: string
  label: string
  disabled?: boolean
  variant?: MenuItemVariant
  /** Draw a separator above this item. */
  separatorBefore?: boolean
}

const props = withDefaults(
  defineProps<{
    items: MenuItem[]
    open?: boolean
    size?: MenuSize
    side?: 'top' | 'right' | 'bottom' | 'left'
    align?: 'start' | 'center' | 'end'
    dir?: KitDirection
  }>(),
  { open: undefined, size: 'md', side: 'bottom', align: 'start', dir: undefined },
)

const emit = defineEmits<{
  select: [key: string]
  'update:open': [open: boolean]
}>()

const direction = computed(() => resolveDirection(props.dir))
</script>

<template>
  <DropdownMenuRoot
    :open="open"
    :dir="direction"
    @update:open="emit('update:open', $event)"
  >
    <DropdownMenuTrigger as-child>
      <slot name="trigger" />
    </DropdownMenuTrigger>
    <DropdownMenuPortal>
      <DropdownMenuContent
        class="aui-menu"
        :class="`aui-menu--${size}`"
        :side="side"
        :align="align"
        :side-offset="4"
      >
        <template v-for="item in items" :key="item.key">
          <DropdownMenuSeparator v-if="item.separatorBefore" class="aui-menu__separator" />
          <DropdownMenuItem
            class="aui-menu__item"
            :class="`aui-menu__item--${item.variant ?? 'default'}`"
            :disabled="item.disabled"
            @select="emit('select', item.key)"
          >
            <slot name="item" :item="item">{{ item.label }}</slot>
          </DropdownMenuItem>
        </template>
      </DropdownMenuContent>
    </DropdownMenuPortal>
  </DropdownMenuRoot>
</template>

<style>
.aui-menu {
  z-index: var(--aui-z-dropdown);
  min-width: 10rem;
  padding: var(--aui-space-1);
  border: 1px solid var(--aui-color-border);
  border-radius: var(--aui-radius-md);
  background: var(--aui-color-surface);
  box-shadow: var(--aui-shadow-md);
  color: var(--aui-color-text);
  font-family: var(--aui-font-sans);
  font-size: var(--aui-text-sm);
}

.aui-menu--sm {
  font-size: var(--aui-text-xs);
}

.aui-menu__item {
  display: flex;
  align-items: center;
  padding: var(--aui-space-2) var(--aui-space-3);
  border-radius: var(--aui-radius-sm);
  outline: none;
  cursor: pointer;
  user-select: none;
}

.aui-menu--sm .aui-menu__item {
  padding: var(--aui-space-1) var(--aui-space-2);
}

.aui-menu__item[data-highlighted] {
  background: var(--aui-color-surface-raised);
}

.aui-menu__item:focus-visible {
  outline: var(--aui-focus-ring-width) solid var(--aui-color-focus-ring);
  outline-offset: -2px;
}

.aui-menu__item--danger {
  color: var(--aui-color-error);
}

.aui-menu__item[data-disabled] {
  cursor: not-allowed;
  opacity: 0.5;
}

.aui-menu__separator {
  height: 1px;
  margin: var(--aui-space-1) 0;
  background: var(--aui-color-border);
}
</style>
