<!--
  Copyright 2025-2026 mrveiss
  SPDX-License-Identifier: Apache-2.0

  EmptyState — canonical "nothing here yet" block. Both apps currently hand-roll
  this per view; this is the shared version. Token-only styling.

  Title/description accept props OR slots (apps pass translated strings via
  their own i18n — the kit hardcodes no user-facing text). Slots: icon, title,
  description, actions.
-->
<script setup lang="ts">
defineProps<{
  title?: string
  description?: string
}>()
</script>

<template>
  <div class="aui-empty" role="status">
    <div v-if="$slots.icon" class="aui-empty__icon" aria-hidden="true">
      <slot name="icon" />
    </div>
    <p v-if="$slots.title || title" class="aui-empty__title">
      <slot name="title">{{ title }}</slot>
    </p>
    <p v-if="$slots.description || description" class="aui-empty__description">
      <slot name="description">{{ description }}</slot>
    </p>
    <div v-if="$slots.actions" class="aui-empty__actions">
      <slot name="actions" />
    </div>
  </div>
</template>

<style scoped>
.aui-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  gap: var(--aui-space-3);
  padding: var(--aui-space-6) var(--aui-space-4);
  font-family: var(--aui-font-sans);
  color: var(--aui-color-text-muted);
}

.aui-empty__icon {
  font-size: var(--aui-text-lg);
  color: var(--aui-color-text-muted);
}

.aui-empty__title {
  margin: 0;
  font-size: var(--aui-text-lg);
  font-weight: var(--aui-font-weight-semibold);
  color: var(--aui-color-text);
}

.aui-empty__description {
  margin: 0;
  max-width: 42ch;
  font-size: var(--aui-text-sm);
}

.aui-empty__actions {
  margin-top: var(--aui-space-2);
  display: flex;
  gap: var(--aui-space-2);
}
</style>
