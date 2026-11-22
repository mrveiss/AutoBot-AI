<!--
  Copyright 2025-2026 mrveiss
  SPDX-License-Identifier: Apache-2.0

  NavItemIcon — the one renderer for a nav-registry icon (#18240). Header
  links, the mobile panel, the profile menu and the icon cluster all drew this
  same <svg> by hand; the registry (config/navItems.ts) carries the path data,
  this draws it. Decorative: the label or aria-label is always on the parent.
-->
<template>
  <svg
    :fill="item.iconStroke ? 'none' : 'currentColor'"
    :stroke="item.iconStroke ? 'currentColor' : undefined"
    :stroke-width="item.iconStroke ? '2' : undefined"
    stroke-linecap="round"
    stroke-linejoin="round"
    :viewBox="item.iconViewBox || '0 0 20 20'"
    xmlns="http://www.w3.org/2000/svg"
    aria-hidden="true"
    focusable="false"
  >
    <template v-if="item.iconPaths">
      <path v-for="(p, i) in item.iconPaths" :key="i" :d="p" :fill-rule="item.iconRule" :clip-rule="item.iconRule" />
    </template>
    <path v-else :d="item.icon" :fill-rule="item.iconRule" :clip-rule="item.iconRule" />
  </svg>
</template>

<script setup lang="ts">
import type { NavItem } from '@/config/navItems'

defineProps<{ item: Pick<NavItem, 'icon' | 'iconPaths' | 'iconRule' | 'iconStroke' | 'iconViewBox'> }>()
</script>
