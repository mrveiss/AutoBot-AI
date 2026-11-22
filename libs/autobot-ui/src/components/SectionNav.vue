<!--
  Copyright 2025-2026 mrveiss
  SPDX-License-Identifier: Apache-2.0

  SectionNav — the section sub-navigation (the Refined UI `.sub` sidebar, #18241).
  A titled column of sections, each a small uppercase label over a list of links.
  The kit holds no text and no router: the app passes translated labels, marks the
  active item, and supplies the link component (`linkAs`, e.g. RouterLink; each
  item's `to` is bound as `to` for a component and as `href` for a plain `<a>`).

    props : label (the nav's accessible name), title, sections, linkAs
    items : { id, label, to, active?, adv?, disabled?, class?, ariaLabel? }
    slots : icon ({ item }), trailing ({ item } - a count or badge), footer

  `adv` puts the app's `.adv` class on the item (or the section label), so Minimal mode
  hides it with the same rule as every other advanced control. The active item carries
  `aria-current="page"`. Tokens only; logical properties, so the bar flips under dir="rtl".
-->
<script setup lang="ts">
import type { Component } from 'vue'

export interface SectionNavItem {
  id: string
  label: string
  to: string
  active?: boolean
  /** Advanced-only: hidden in Minimal mode by the app's `.adv` rule. */
  adv?: boolean
  disabled?: boolean
  /** Extra class on the link. */
  class?: string
  /** Accessible name when the visible label is not enough. */
  ariaLabel?: string
}

export interface SectionNavSection {
  id: string
  /** Section heading; omit for an unlabelled group. */
  label?: string
  adv?: boolean
  items: SectionNavItem[]
}

const props = withDefaults(
  defineProps<{
    label: string
    title?: string
    sections: SectionNavSection[]
    linkAs?: string | Component
  }>(),
  { title: undefined, linkAs: 'a' },
)

function linkProps(item: SectionNavItem): Record<string, unknown> {
  const target = props.linkAs === 'a' ? { href: item.to } : { to: item.to }
  return {
    ...target,
    'aria-current': item.active ? 'page' : undefined,
    'aria-label': item.ariaLabel,
    'aria-disabled': item.disabled ? 'true' : undefined,
    tabindex: item.disabled ? -1 : undefined,
  }
}

const itemClass = (item: SectionNavItem) => [
  'aui-section-nav__link',
  { 'aui-section-nav__link--on': item.active, 'aui-section-nav__link--disabled': item.disabled, adv: item.adv },
  item.class,
]
</script>

<template>
  <nav class="aui-section-nav" :aria-label="label">
    <h2 v-if="title" class="aui-section-nav__title">{{ title }}</h2>
    <template v-for="section in sections" :key="section.id">
      <p v-if="section.label" :class="['aui-section-nav__sect', { adv: section.adv }]">{{ section.label }}</p>
      <ul class="aui-section-nav__list" :class="{ adv: section.adv && !section.label }">
        <li v-for="item in section.items" :key="item.id" class="aui-section-nav__li" :class="{ adv: item.adv }">
          <component :is="linkAs" v-bind="linkProps(item)" :class="itemClass(item)">
            <span v-if="$slots.icon" class="aui-section-nav__icon"><slot name="icon" :item="item" /></span>
            <span class="aui-section-nav__text">{{ item.label }}</span>
            <span v-if="$slots.trailing" class="aui-section-nav__trailing"><slot name="trailing" :item="item" /></span>
          </component>
        </li>
      </ul>
    </template>
    <div v-if="$slots.footer" class="aui-section-nav__footer"><slot name="footer" /></div>
  </nav>
</template>

<style scoped>
.aui-section-nav {
  display: flex;
  flex-direction: column;
  gap: 1px;
  box-sizing: border-box;
  padding: var(--aui-space-4) var(--aui-space-3);
  background: var(--aui-color-surface);
  border-inline-end: 1px solid var(--aui-color-border);
  font-family: var(--aui-font-sans);
}

.aui-section-nav__title {
  margin: 0 var(--aui-space-3) var(--aui-space-1);
  font-size: var(--aui-text-base);
  font-weight: var(--aui-font-weight-semibold);
  color: var(--aui-color-text);
}

.aui-section-nav__sect {
  margin: var(--aui-space-4) var(--aui-space-3) var(--aui-space-2);
  font-size: var(--aui-text-xs);
  font-weight: var(--aui-font-weight-semibold);
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--aui-color-text-muted);
}

.aui-section-nav__list {
  display: flex;
  flex-direction: column;
  gap: 1px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.aui-section-nav__link {
  display: flex;
  align-items: center;
  gap: var(--aui-space-3);
  min-block-size: var(--aui-space-6);
  padding: var(--aui-space-2) var(--aui-space-3);
  border-inline-start: 3px solid transparent;
  border-radius: var(--aui-radius-md);
  color: var(--aui-color-text-muted);
  font-size: var(--aui-text-sm);
  text-decoration: none;
  transition: background var(--aui-transition-fast), color var(--aui-transition-fast);
}

.aui-section-nav__link:hover {
  background: var(--aui-color-surface-sunken);
  color: var(--aui-color-text);
}

.aui-section-nav__link--on {
  background: var(--aui-color-surface-sunken);
  border-inline-start-color: var(--aui-color-primary);
  color: var(--aui-color-text);
  font-weight: var(--aui-font-weight-semibold);
}

.aui-section-nav__link:focus-visible {
  outline: var(--aui-focus-ring-width) solid var(--aui-color-focus-ring);
  outline-offset: 2px;
}

.aui-section-nav__link--disabled {
  opacity: 0.5;
  pointer-events: none;
}

.aui-section-nav__icon {
  display: inline-flex;
  flex: none;
}

.aui-section-nav__text {
  flex: 1;
  min-inline-size: 0;
}

.aui-section-nav__trailing {
  flex: none;
  margin-inline-start: auto;
}

.aui-section-nav__footer {
  margin: var(--aui-space-4) var(--aui-space-3) 0;
}
</style>
