<!--
  Copyright 2025-2026 mrveiss
  SPDX-License-Identifier: Apache-2.0
  PageHeader — the title row at the top of a page or a feature panel (#17563).
  Its API comes from the headers it replaces (chat, analytics, file browser, terminal,
  knowledge browser): an optional leading control or icon, a title with an optional subtitle,
  an actions row on the right, and an optional toolbar row under them (path navigation,
  filters, search). The kit ships no text: the title and subtitle come in translated.
    props : title, subtitle, level (heading level, 1-6; default 1),
            size (title size: sm | md | lg | xl; default lg; the level stays semantic)
    slots : breadcrumb, leading, eyebrow (a short line ABOVE the title), title (rich title content),
            subtitle, actions, default (the toolbar row under the title)
  A surface that needs its own chrome (the terminal window) sets these on the root rather than
  overriding the rules: --aui-page-header-bg, --aui-page-header-border, --aui-page-header-py,
  --aui-page-header-px, --aui-page-header-title-color.
-->
<script setup lang="ts">
import { computed, useSlots } from 'vue'

const props = withDefaults(
  defineProps<{
    title?: string
    subtitle?: string
    level?: 1 | 2 | 3 | 4 | 5 | 6
    size?: 'sm' | 'md' | 'lg' | 'xl'
  }>(),
  { title: undefined, subtitle: undefined, level: 1, size: 'lg' },
)

// useSlots() is not reactive, so these are plain functions the render calls each time;
// a computed would cache a slot the parent adds or removes later.
const slots = useSlots()
const heading = computed(() => `h${props.level}`)
const hasTitle = () => !!(props.title || slots.title)
const hasSubtitle = () => !!(props.subtitle || slots.subtitle)
</script>

<template>
  <header data-slot="page-header" class="aui-page-header">
    <div v-if="$slots.breadcrumb" data-slot="page-header-breadcrumb" class="aui-page-header__breadcrumb">
      <slot name="breadcrumb" />
    </div>
    <div v-if="hasTitle() || $slots.leading || $slots.actions" data-slot="page-header-row" class="aui-page-header__row">
      <div data-slot="page-header-start" class="aui-page-header__start">
        <slot name="leading" />
        <div v-if="hasTitle()" data-slot="page-header-text" class="aui-page-header__text">
          <p v-if="$slots.eyebrow" data-slot="page-header-eyebrow" class="aui-page-header__eyebrow"><slot name="eyebrow" /></p>
          <component :is="heading" data-slot="page-header-title" class="aui-page-header__title" :class="`aui-page-header__title--${size}`">
            <span data-slot="page-header-title-text" class="aui-page-header__title-text"><slot name="title">{{ title }}</slot></span>
          </component>
          <p v-if="hasSubtitle()" data-slot="page-header-subtitle" class="aui-page-header__subtitle">
            <slot name="subtitle">{{ subtitle }}</slot>
          </p>
        </div>
      </div>
      <div v-if="$slots.actions" data-slot="page-header-actions" class="aui-page-header__actions">
        <slot name="actions" />
      </div>
    </div>
    <div v-if="$slots.default" data-slot="page-header-toolbar" class="aui-page-header__toolbar">
      <slot />
    </div>
  </header>
</template>

<style scoped>
[data-slot="page-header"] {
  display: flex;
  flex-direction: column;
  gap: var(--aui-space-3);
  padding: var(--aui-page-header-py, var(--aui-space-4)) var(--aui-page-header-px, var(--aui-space-6));
  border-bottom: 1px solid var(--aui-page-header-border, var(--aui-color-border));
  background: var(--aui-page-header-bg, var(--aui-color-surface));
}

[data-slot="page-header-row"] {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--aui-space-3);
  flex-wrap: wrap;
}

[data-slot="page-header-start"] {
  display: flex;
  align-items: center;
  gap: var(--aui-space-3);
  min-width: 0;
}

[data-slot="page-header-text"] {
  min-width: 0;
}

[data-slot="page-header-title"] {
  display: flex;
  align-items: center;
  gap: var(--aui-space-2);
  margin: 0;
  color: var(--aui-page-header-title-color, var(--aui-color-text));
  font-weight: var(--aui-font-weight-semibold);
}

/* text-overflow applies to this flex item (blockified), not to the flex row around it */
[data-slot="page-header-title-text"] {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.aui-page-header__title--sm {
  font-size: var(--aui-text-sm);
}

.aui-page-header__title--md {
  font-size: var(--aui-text-base);
}

.aui-page-header__title--lg {
  font-size: var(--aui-text-lg);
}

.aui-page-header__title--xl {
  font-size: var(--aui-text-xl);
}

[data-slot="page-header-eyebrow"] {
  margin: 0 0 var(--aui-space-1);
  color: var(--aui-color-text-muted);
  font-size: var(--aui-text-sm);
}
[data-slot="page-header-subtitle"] {
  margin: 0;
  color: var(--aui-color-text-muted);
  font-size: var(--aui-text-sm);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

[data-slot="page-header-actions"] {
  display: flex;
  align-items: center;
  gap: var(--aui-space-2);
  flex-shrink: 0;
  flex-wrap: wrap;
}

[data-slot="page-header-toolbar"] {
  display: flex;
  align-items: center;
  gap: var(--aui-space-3);
  flex-wrap: wrap;
}
</style>
