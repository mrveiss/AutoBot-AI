<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025-2026 mrveiss -->
<!-- Author: mrveiss -->
<!--
  LlcBreadcrumb (GH#9628) — horizontal breadcrumb trail for the LLC
  Portfolio → Program → Project browser views. Each item renders as a
  RouterLink when `to` is provided, otherwise as plain (current) text.
-->
<script setup lang="ts">
import type { RouteLocationRaw } from 'vue-router'

export interface BreadcrumbItem {
  label: string
  to?: RouteLocationRaw
}

defineProps<{
  items: BreadcrumbItem[]
}>()
</script>

<template>
  <nav class="llc-breadcrumb" aria-label="Breadcrumb">
    <template v-for="(item, idx) in items" :key="idx">
      <RouterLink v-if="item.to" :to="item.to" class="crumb crumb-link">
        {{ item.label }}
      </RouterLink>
      <span v-else class="crumb crumb-current" aria-current="page">
        {{ item.label }}
      </span>
      <span v-if="idx < items.length - 1" class="crumb-sep" aria-hidden="true">/</span>
    </template>
  </nav>
</template>

<style scoped>
.llc-breadcrumb {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.875rem;
  margin-bottom: 1rem;
}

.crumb {
  white-space: nowrap;
}

.crumb-link {
  color: var(--color-accent-text, var(--color-accent, #c4651a));
  text-decoration: none;
}

.crumb-link:hover {
  text-decoration: underline;
}

.crumb-current {
  color: var(--color-text-primary, #111827);
  font-weight: 600;
}

.crumb-sep {
  color: var(--color-text-secondary, #9ca3af);
}
</style>
