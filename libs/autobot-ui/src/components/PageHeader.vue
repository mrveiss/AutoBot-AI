<!--
  Copyright 2025-2026 mrveiss
  SPDX-License-Identifier: Apache-2.0
  PageHeader — the title row at the top of a page or a feature panel (#17563).
  Its API comes from the headers it replaces (chat, analytics, file browser, terminal,
  knowledge browser): an optional leading control or icon, a title with an optional subtitle,
  an actions row on the right, and an optional toolbar row under them (path navigation,
  filters, search). The kit ships no text: the title and subtitle come in translated.
    props : title, subtitle, level (heading level, 1-6; default 1)
    slots : breadcrumb, leading, title (rich title content), subtitle, actions,
            default (the toolbar row under the title)
-->
<script setup lang="ts">
import { computed, useSlots } from 'vue'

const props = withDefaults(
  defineProps<{
    title?: string
    subtitle?: string
    level?: 1 | 2 | 3 | 4 | 5 | 6
  }>(),
  { title: undefined, subtitle: undefined, level: 1 },
)

const slots = useSlots()
const heading = computed(() => `h${props.level}`)
const hasTitle = computed(() => !!(props.title || slots.title))
const hasSubtitle = computed(() => !!(props.subtitle || slots.subtitle))
</script>

<template>
  <header class="aui-page-header">
    <div v-if="$slots.breadcrumb" class="aui-page-header__breadcrumb">
      <slot name="breadcrumb" />
    </div>
    <div v-if="hasTitle || $slots.leading || $slots.actions" class="aui-page-header__row">
      <div class="aui-page-header__start">
        <slot name="leading" />
        <div v-if="hasTitle" class="aui-page-header__text">
          <component :is="heading" class="aui-page-header__title">
            <slot name="title">{{ title }}</slot>
          </component>
          <p v-if="hasSubtitle" class="aui-page-header__subtitle">
            <slot name="subtitle">{{ subtitle }}</slot>
          </p>
        </div>
      </div>
      <div v-if="$slots.actions" class="aui-page-header__actions">
        <slot name="actions" />
      </div>
    </div>
    <div v-if="$slots.default" class="aui-page-header__toolbar">
      <slot />
    </div>
  </header>
</template>

<style scoped>
.aui-page-header {
  display: flex;
  flex-direction: column;
  gap: var(--aui-space-3);
  padding: var(--aui-space-4) var(--aui-space-6);
  border-bottom: 1px solid var(--aui-color-border);
  background: var(--aui-color-surface);
}

.aui-page-header__row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--aui-space-3);
  flex-wrap: wrap;
}

.aui-page-header__start {
  display: flex;
  align-items: center;
  gap: var(--aui-space-3);
  min-width: 0;
}

.aui-page-header__text {
  min-width: 0;
}

.aui-page-header__title {
  display: flex;
  align-items: center;
  gap: var(--aui-space-2);
  margin: 0;
  color: var(--aui-color-text);
  font-size: var(--aui-text-lg);
  font-weight: var(--aui-font-weight-semibold);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.aui-page-header__subtitle {
  margin: 0;
  color: var(--aui-color-text-muted);
  font-size: var(--aui-text-sm);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.aui-page-header__actions {
  display: flex;
  align-items: center;
  gap: var(--aui-space-2);
  flex-shrink: 0;
  flex-wrap: wrap;
}

.aui-page-header__toolbar {
  display: flex;
  align-items: center;
  gap: var(--aui-space-3);
  flex-wrap: wrap;
}
</style>
