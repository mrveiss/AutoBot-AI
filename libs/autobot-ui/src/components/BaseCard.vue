<!--
  Copyright 2025-2026 mrveiss
  SPDX-License-Identifier: Apache-2.0

  BaseCard — surface container with optional header/footer. Token-only styling;
  the default content panel for both apps. See BaseButton.vue for kit rules.

  Slots: header (optional), default (body), footer (optional).
-->
<script setup lang="ts">
withDefaults(
  defineProps<{
    /** Remove body padding (e.g. to hold a flush table). */
    flush?: boolean
  }>(),
  {
    flush: false,
  },
)
</script>

<template>
  <section class="aui-card">
    <header v-if="$slots.header" class="aui-card__header">
      <slot name="header" />
    </header>
    <div :class="['aui-card__body', { 'aui-card__body--flush': flush }]">
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

.aui-card__header {
  padding: var(--aui-space-4) var(--aui-space-5);
  border-bottom: 1px solid var(--aui-color-border);
  font-weight: var(--aui-font-weight-semibold);
}

.aui-card__body {
  padding: var(--aui-space-5);
}
.aui-card__body--flush {
  padding: 0;
}

.aui-card__footer {
  padding: var(--aui-space-4) var(--aui-space-5);
  border-top: 1px solid var(--aui-color-border);
}
</style>
