<!--
  Copyright 2025-2026 mrveiss
  SPDX-License-Identifier: Apache-2.0

  BaseCard — the one card / panel container for both apps (#14776, #14778).
  Token-only styling.

  It is the union of the kit card and the main app's retired BaseCard and
  BasePanel (owner decision, step-3 plan S5): a `variant` for the frame, a
  `size` for the text scale, an optional title/subtitle header with an
  `actions` area, and a body that can scroll. The defaults (variant
  "default", size "md") are the kit card as it was, so existing consumers do
  not change.

  Slots: header (replaces the title block), actions (right of the header),
  default (body), footer.
-->
<script setup lang="ts">
export type CardVariant = 'default' | 'bordered' | 'elevated' | 'flat' | 'dark'
export type CardSize = 'sm' | 'md' | 'lg'

withDefaults(
  defineProps<{
    variant?: CardVariant
    size?: CardSize
    title?: string
    subtitle?: string
    /** Remove body padding (e.g. to hold a flush table). */
    flush?: boolean
    /** Let the body scroll when something constrains the card's height. */
    scrollable?: boolean
  }>(),
  {
    variant: 'default',
    size: 'md',
    title: undefined,
    subtitle: undefined,
    flush: false,
    scrollable: false,
  },
)
</script>

<template>
  <section :class="['aui-card', `aui-card--${variant}`, `aui-card--${size}`]">
    <header v-if="$slots.header || title || $slots.actions" class="aui-card__header">
      <div class="aui-card__heading">
        <slot name="header">
          <h3 v-if="title" class="aui-card__title">{{ title }}</h3>
          <p v-if="subtitle" class="aui-card__subtitle">{{ subtitle }}</p>
        </slot>
      </div>
      <div v-if="$slots.actions" class="aui-card__actions">
        <slot name="actions" />
      </div>
    </header>
    <div :class="['aui-card__body', { 'aui-card__body--flush': flush, 'aui-card__body--scroll': scrollable }]">
      <slot />
    </div>
    <footer v-if="$slots.footer" class="aui-card__footer">
      <slot name="footer" />
    </footer>
  </section>
</template>

<style scoped>
.aui-card {
  display: flex;
  flex-direction: column;
  background-color: var(--aui-color-surface);
  border: 1px solid var(--aui-color-border);
  border-radius: var(--aui-radius-lg);
  box-shadow: var(--aui-shadow-sm);
  color: var(--aui-color-text);
  font-family: var(--aui-font-sans);
}

/* Frames. "default" is the original kit card. */
.aui-card--bordered {
  border: 2px solid var(--aui-color-border-strong);
  box-shadow: none;
}
/* The design system draws no shadows: "elevated" is a raised surface with a strong border. */
.aui-card--elevated {
  background-color: var(--aui-color-surface-raised);
  border-color: var(--aui-color-border-strong);
  box-shadow: none;
}
.aui-card--flat {
  background-color: var(--aui-color-surface-sunken);
  border-color: transparent;
  box-shadow: none;
}
.aui-card--dark {
  background-color: var(--aui-color-surface-sunken);
  box-shadow: none;
}
.aui-card--dark .aui-card__footer {
  background-color: var(--aui-color-surface-raised);
}

/* Text scale. "md" inherits, as the original kit card did. */
.aui-card--sm {
  font-size: var(--aui-text-sm);
}
.aui-card--lg {
  font-size: var(--aui-text-lg);
}

.aui-card__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--aui-space-3);
  padding: var(--aui-space-4) var(--aui-space-5);
  border-bottom: 1px solid var(--aui-color-border);
  font-weight: var(--aui-font-weight-semibold);
}
.aui-card__heading {
  min-width: 0;
}
.aui-card__title {
  margin: 0;
  font-size: var(--aui-text-lg);
  font-weight: var(--aui-font-weight-semibold);
}
.aui-card__subtitle {
  margin: var(--aui-space-1) 0 0;
  color: var(--aui-color-text-muted);
  font-size: var(--aui-text-sm);
  font-weight: normal;
}
.aui-card__actions {
  display: flex;
  align-items: center;
  gap: var(--aui-space-2);
  flex-shrink: 0;
}

.aui-card__body {
  padding: var(--aui-space-5);
}
.aui-card__body--flush {
  padding: 0;
}
.aui-card__body--scroll {
  overflow-y: auto;
}

.aui-card__footer {
  padding: var(--aui-space-4) var(--aui-space-5);
  border-top: 1px solid var(--aui-color-border);
}
</style>
