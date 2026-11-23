<!--
  Copyright 2025-2026 mrveiss
  SPDX-License-Identifier: Apache-2.0

  EmptyState — canonical "nothing here yet" block. Both apps currently hand-roll
  this per view; this is the shared version. Token-only styling.

  Title/description accept props OR slots (apps pass translated strings via
  their own i18n — the kit hardcodes no user-facing text). Slots: icon, title,
  description, actions. `compact` tightens the spacing for in-panel use (#14776,
  promoted from the main app's fork).
-->
<script setup lang="ts">
defineProps<{
  title?: string
  description?: string
  compact?: boolean
}>()
</script>

<template>
  <div data-slot="empty" class="aui-empty" :class="{ 'aui-empty--compact': compact }" role="status">
    <div v-if="$slots.icon" data-slot="empty-icon" class="aui-empty__icon" aria-hidden="true">
      <slot name="icon" />
    </div>
    <p v-if="$slots.title || title" data-slot="empty-title" class="aui-empty__title">
      <slot name="title">{{ title }}</slot>
    </p>
    <p v-if="$slots.description || description" data-slot="empty-description" class="aui-empty__description">
      <slot name="description">{{ description }}</slot>
    </p>
    <div v-if="$slots.actions" data-slot="empty-actions" class="aui-empty__actions">
      <slot name="actions" />
    </div>
  </div>
</template>

<style scoped>
[data-slot="empty"] {
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  gap: var(--aui-space-3);
  padding: var(--aui-space-6) var(--aui-space-4);
  font-family: var(--aui-font-sans);
  color: var(--aui-color-text-muted);
}

.aui-empty--compact {
  gap: var(--aui-space-2);
  padding: var(--aui-space-4) var(--aui-space-3);
}

[data-slot="empty-icon"] {
  font-size: var(--aui-text-lg);
  color: var(--aui-color-text-muted);
}

[data-slot="empty-title"] {
  margin: 0;
  font-size: var(--aui-text-lg);
  font-weight: var(--aui-font-weight-semibold);
  color: var(--aui-color-text);
}

[data-slot="empty-description"] {
  margin: 0;
  max-width: 42ch;
  font-size: var(--aui-text-sm);
}

[data-slot="empty-actions"] {
  margin-top: var(--aui-space-2);
  display: flex;
  gap: var(--aui-space-2);
}
</style>
