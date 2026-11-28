<!--
  Copyright 2025-2026 mrveiss
  SPDX-License-Identifier: Apache-2.0
  Breadcrumb — the trail to the current page (#17563). One implementation for both apps;
  LlcBreadcrumb wraps it.
  Every item but the last is a link: rendered through `linkAs` (pass RouterLink; the kit never
  imports vue-router) with `to`, or as a plain `<a href>` when `linkAs` is omitted. The last
  item is the current page. An item with `selectable` and no `to` is a button that emits
  `select` with its index, for trails that navigate by handler rather than by route (the
  file browser's path, the knowledge browser's root).
    props : items ({ label, to?, selectable? }[]), label (names the nav landmark, translated by
            the app), linkAs (component used for linked items)
    slots : item ({ item, index }: the label content, e.g. an icon before it), separator
    emits : select (index)
-->
<script setup lang="ts">
import type { Component } from 'vue'

export interface BreadcrumbItem {
  label: string
  to?: unknown
  selectable?: boolean
}

const props = withDefaults(
  defineProps<{
    items: BreadcrumbItem[]
    label: string
    linkAs?: Component | string
  }>(),
  { linkAs: 'a' },
)

defineEmits<{ select: [index: number] }>()

const isCurrent = (index: number) => index === props.items.length - 1

function linkProps(linkAs: Component | string, to: unknown) {
  return typeof linkAs === 'string' ? { href: to } : { to }
}
</script>

<template>
  <nav class="aui-breadcrumb" :aria-label="label">
    <ol class="aui-breadcrumb__list">
      <li v-for="(item, idx) in items" :key="idx" class="aui-breadcrumb__item">
        <component
          :is="linkAs"
          v-if="item.to !== undefined && !isCurrent(idx)"
          v-bind="linkProps(linkAs, item.to)"
          class="aui-breadcrumb__link"
        ><slot name="item" :item="item" :index="idx">{{ item.label }}</slot></component>
        <button
          v-else-if="item.selectable && !isCurrent(idx)"
          type="button"
          class="aui-breadcrumb__link aui-breadcrumb__button"
          @click="$emit('select', idx)"
        ><slot name="item" :item="item" :index="idx">{{ item.label }}</slot></button>
        <span
          v-else
          class="aui-breadcrumb__current"
          :aria-current="isCurrent(idx) ? 'page' : undefined"
        ><slot name="item" :item="item" :index="idx">{{ item.label }}</slot></span>
        <span v-if="!isCurrent(idx)" class="aui-breadcrumb__sep" aria-hidden="true">
          <slot name="separator">/</slot>
        </span>
      </li>
    </ol>
  </nav>
</template>

<style scoped>
.aui-breadcrumb__list {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--aui-space-2);
  margin: 0;
  padding: 0;
  list-style: none;
  font-size: var(--aui-text-sm);
}

.aui-breadcrumb__item {
  display: inline-flex;
  align-items: center;
  gap: var(--aui-space-2);
  white-space: nowrap;
}

.aui-breadcrumb__link {
  display: inline-flex;
  align-items: center;
  gap: var(--aui-space-1);
  color: var(--aui-color-primary);
  text-decoration: none;
}

.aui-breadcrumb__button {
  padding: 0;
  border: none;
  background: none;
  font: inherit;
  cursor: pointer;
}

.aui-breadcrumb__link:hover {
  text-decoration: underline;
}

.aui-breadcrumb__link:focus-visible {
  outline: var(--aui-focus-ring-width) solid var(--aui-color-focus-ring);
  outline-offset: 2px;
  border-radius: var(--aui-radius-sm);
}

.aui-breadcrumb__current {
  display: inline-flex;
  align-items: center;
  gap: var(--aui-space-1);
  color: var(--aui-color-text);
  font-weight: var(--aui-font-weight-semibold);
}

.aui-breadcrumb__sep {
  color: var(--aui-color-text-muted);
}
</style>
