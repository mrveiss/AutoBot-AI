<!--
  Copyright 2025-2026 mrveiss
  SPDX-License-Identifier: Apache-2.0

  BaseBadge — small status/label pill. Token-only styling; used by both apps
  for statuses, counts, and tags. See BaseButton.vue for the kit rules.
-->
<script setup lang="ts">
export type BadgeVariant = 'neutral' | 'primary' | 'success' | 'warning' | 'danger' | 'info'
export type BadgeSize = 'sm' | 'md'

withDefaults(
  defineProps<{
    variant?: BadgeVariant
    size?: BadgeSize
  }>(),
  {
    variant: 'neutral',
    size: 'md',
  },
)
</script>

<template>
  <span :class="['aui-badge', `aui-badge--${variant}`, `aui-badge--${size}`]">
    <slot />
  </span>
</template>

<style scoped>
.aui-badge {
  display: inline-flex;
  align-items: center;
  gap: var(--aui-space-1);
  border-radius: var(--aui-radius-full);
  font-family: var(--aui-font-sans);
  font-weight: var(--aui-font-weight-medium);
  line-height: 1;
  white-space: nowrap;
}

.aui-badge--sm {
  padding: 0.125rem var(--aui-space-2);
  font-size: var(--aui-text-xs);
}
.aui-badge--md {
  padding: var(--aui-space-1) var(--aui-space-3);
  font-size: var(--aui-text-sm);
}

.aui-badge--neutral {
  background-color: var(--aui-color-surface-sunken);
  color: var(--aui-color-text-muted);
}
.aui-badge--primary {
  background-color: var(--aui-color-primary);
  color: var(--aui-color-primary-contrast);
}
.aui-badge--success {
  background-color: var(--aui-color-success);
  color: var(--aui-color-success-contrast);
}
.aui-badge--warning {
  background-color: var(--aui-color-warning);
  color: var(--aui-color-warning-contrast);
}
.aui-badge--danger {
  background-color: var(--aui-color-danger);
  color: var(--aui-color-danger-contrast);
}
.aui-badge--info {
  background-color: var(--aui-color-info);
  color: var(--aui-color-info-contrast);
}
</style>
