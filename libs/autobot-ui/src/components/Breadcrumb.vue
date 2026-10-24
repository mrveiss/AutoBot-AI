<!--
  Copyright 2025-2026 mrveiss
  SPDX-License-Identifier: Apache-2.0
  Breadcrumb — the trail to the current page (#17563). One implementation for both apps;
  LlcBreadcrumb wraps it.
  Every item but the last is a link: rendered through `linkAs` (pass RouterLink; the kit never
  imports vue-router) with `to`, or as a plain `<a href>` when `linkAs` is omitted. The last
  item is the current page.
    props : items ({ label, to? }[]), label (names the nav landmark, translated by the app),
            linkAs (component used for linked items)
-->
<script setup lang="ts">
import type { Component } from 'vue'

export interface BreadcrumbItem {
  label: string
  to?: unknown
}

withDefaults(
  defineProps<{
    items: BreadcrumbItem[]
    label: string
    linkAs?: Component | string
  }>(),
  { linkAs: 'a' },
)

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
          v-if="item.to !== undefined && idx < items.length - 1"
          v-bind="linkProps(linkAs, item.to)"
          class="aui-breadcrumb__link"
        >{{ item.label }}</component>
        <span
          v-else
          class="aui-breadcrumb__current"
          :aria-current="idx === items.length - 1 ? 'page' : undefined"
        >{{ item.label }}</span>
        <span v-if="idx < items.length - 1" class="aui-breadcrumb__sep" aria-hidden="true">/</span>
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
  color: var(--aui-color-primary);
  text-decoration: none;
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
  color: var(--aui-color-text);
  font-weight: var(--aui-font-weight-semibold);
}

.aui-breadcrumb__sep {
  color: var(--aui-color-text-muted);
}
</style>
