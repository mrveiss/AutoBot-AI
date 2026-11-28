<!--
  Copyright 2025-2026 mrveiss
  SPDX-License-Identifier: Apache-2.0

  SectionShell — the section layout: a SectionNav sub-sidebar beside the routed content, with the
  mobile drawer (#18241, #22019). Below the 768px breakpoint the sidebar becomes a toggled
  drawer with a backdrop, and a click on a nav link closes it. The kit holds no text and no
  storage: the app passes the toggle labels and owns `v-model:open` (and persists it if it wants).

    props : navLabel, title, sections, linkAs (as SectionNav), openLabel, closeLabel, open
    slots : default (the content), icon / trailing / nav-footer (as SectionNav), toggle-icon ({ open })
    emits : update:open
-->
<script setup lang="ts">
import type { Component } from 'vue'
import BaseButton from './BaseButton.vue'
import SectionNav from './SectionNav.vue'
import type { SectionNavSection } from './SectionNav.vue'

const props = withDefaults(
  defineProps<{
    navLabel: string
    title?: string
    sections: SectionNavSection[]
    linkAs?: string | Component
    openLabel: string
    closeLabel: string
    open?: boolean
  }>(),
  { title: undefined, linkAs: 'a', open: false },
)

const emit = defineEmits<{ 'update:open': [open: boolean] }>()

const MOBILE_MAX_WIDTH = 768

function onNavClick(e: Event) {
  const onLink = (e.target as HTMLElement).closest('a')
  if (onLink && props.open && window.innerWidth <= MOBILE_MAX_WIDTH) emit('update:open', false)
}
</script>

<template>
  <div class="aui-section-shell">
    <div v-if="open" class="aui-section-shell__overlay" aria-hidden="true" @click="emit('update:open', false)" />

    <aside class="aui-section-shell__sidebar" :class="{ 'aui-section-shell__sidebar--open': open }">
      <BaseButton
        variant="ghost"
        size="sm"
        class="aui-section-shell__toggle"
        :aria-label="open ? closeLabel : openLabel"
        :aria-expanded="open"
        @click="emit('update:open', !open)"
      >
        <slot name="toggle-icon" :open="open" />
      </BaseButton>
      <SectionNav
        class="aui-section-shell__nav"
        :label="navLabel"
        :title="title"
        :sections="sections"
        :link-as="linkAs"
        @click="onNavClick"
      >
        <template v-if="$slots.icon" #icon="{ item }"><slot name="icon" :item="item" /></template>
        <template v-if="$slots.trailing" #trailing="{ item }"><slot name="trailing" :item="item" /></template>
        <template v-if="$slots['nav-footer']" #footer><slot name="nav-footer" /></template>
      </SectionNav>
    </aside>

    <main class="aui-section-shell__content"><slot /></main>
  </div>
</template>

<style scoped>
.aui-section-shell {
  contain: layout style paint;
  display: flex;
  min-block-size: 0;
}

.aui-section-shell__sidebar {
  inline-size: var(--aui-section-nav-width);
  min-inline-size: var(--aui-section-nav-width);
  display: flex;
  flex-direction: column;
  overflow-y: auto;
  background: var(--aui-color-surface);
  border-inline-end: 1px solid var(--aui-color-border);
}

.aui-section-shell__nav {
  flex: 1;
  border-inline-end: 0;
}

.aui-section-shell__content {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-inline-size: 0;
  overflow-x: hidden;
  overflow-y: auto;
}

.aui-section-shell__toggle,
.aui-section-shell__overlay {
  display: none;
}

@media (max-width: 768px) {
  .aui-section-shell {
    flex-direction: column;
    position: relative;
  }

  .aui-section-shell__sidebar {
    inline-size: 100%;
    min-inline-size: 100%;
    border-inline-end: 0;
    border-block-end: 1px solid var(--aui-color-border);
    position: relative;
    z-index: var(--aui-z-raised);
  }

  .aui-section-shell__toggle {
    display: inline-flex;
    align-self: flex-start;
    margin: var(--aui-space-2);
  }

  .aui-section-shell__sidebar:not(.aui-section-shell__sidebar--open) .aui-section-shell__nav {
    display: none;
  }

  .aui-section-shell__sidebar--open {
    position: fixed;
    inset-block: 0;
    inset-inline-start: 0;
    inline-size: 80vw;
    max-inline-size: 320px;
    min-inline-size: 0;
    z-index: var(--aui-z-modal);
  }

  .aui-section-shell__overlay {
    display: block;
    position: fixed;
    inset: 0;
    background: var(--aui-color-overlay);
    z-index: var(--aui-z-dropdown);
  }
}
</style>
