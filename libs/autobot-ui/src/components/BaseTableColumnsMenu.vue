<!--
  Copyright 2025-2026 mrveiss
  SPDX-License-Identifier: Apache-2.0

  BaseTableColumnsMenu -- the column-visibility menu of BaseTable (#17562). Internal to the
  table: a disclosure with one checkbox per hideable column. The kit holds no text, so the
  menu's name comes in as `label`.
-->
<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'

export interface ColumnsMenuItem {
  key: string
  label: string
  shown: boolean
}

defineProps<{ label: string; items: ColumnsMenuItem[] }>()
const emit = defineEmits<{ toggle: [key: string] }>()

const root = ref<HTMLDetailsElement | null>(null)

function close(): void {
  if (root.value) root.value.open = false
}

function onKeydown(event: KeyboardEvent): void {
  if (event.key !== 'Escape' || !root.value?.open) return
  close()
  root.value.querySelector('summary')?.focus()
}

function onOutside(event: MouseEvent): void {
  if (root.value?.open && !root.value.contains(event.target as Node)) close()
}

onMounted(() => document.addEventListener('mousedown', onOutside))
onBeforeUnmount(() => document.removeEventListener('mousedown', onOutside))
</script>

<template>
  <details ref="root" class="aui-columns" @keydown="onKeydown">
    <summary class="aui-columns__toggle">{{ label }}</summary>
    <ul class="aui-columns__list" role="group" :aria-label="label">
      <li v-for="item in items" :key="item.key">
        <label class="aui-columns__item">
          <input type="checkbox" class="aui-columns__checkbox" :checked="item.shown" @change="emit('toggle', item.key)" />
          {{ item.label }}
        </label>
      </li>
    </ul>
  </details>
</template>

<style scoped>
.aui-columns { margin-left: auto; position: relative; }
.aui-columns__toggle { cursor: pointer; }

.aui-columns__list {
  position: absolute;
  right: 0;
  z-index: 1;
  margin: var(--aui-space-1) 0 0;
  padding: var(--aui-space-2) var(--aui-space-3);
  list-style: none;
  background: var(--aui-color-surface);
  border: var(--aui-table-border);
  border-radius: var(--aui-radius-md);
}

.aui-columns__item { display: flex; align-items: center; gap: var(--aui-space-2); white-space: nowrap; }

.aui-columns__toggle:focus-visible,
.aui-columns__checkbox:focus-visible {
  outline: var(--aui-focus-ring-width) solid var(--aui-color-focus-ring);
  outline-offset: 2px;
}
</style>
