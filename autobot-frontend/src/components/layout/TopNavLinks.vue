<!--
  Copyright 2025-2026 mrveiss
  SPDX-License-Identifier: Apache-2.0

  TopNavLinks — the header's primary link rail (#18240): Home, Chat,
  Knowledge, Company OS, Analytics. The active link is a 2px underline in the
  accent colour. Entries come from the nav registry. Advanced links are
  filtered out in Minimal mode here, in script, because the overflow
  measurement counts DOM links -- a CSS-hidden one would still take a slot.
  Entries flagged `overflow` (Automation) and any link that does not fit go to
  the shared NavOverflowMenu.
-->
<template>
  <nav id="navigation" class="hidden min-w-0 flex-1 lg:block" role="navigation" :aria-label="$t('nav.mainNavigation')">
    <div ref="railRef" class="flex items-center gap-1">
      <router-link
        v-for="item in visibleItems"
        :key="item.to"
        :to="item.to"
        data-nav-item
        :aria-current="isActive(item.to) ? 'page' : undefined"
        :class="isActive(item.to)
          ? 'border-autobot-accent text-autobot-text-primary'
          : 'border-transparent text-autobot-text-secondary hover:bg-autobot-bg-tertiary hover:text-autobot-text-primary'"
        class="inline-flex h-14 shrink-0 items-center gap-1.5 border-b-2 px-3 text-sm font-medium transition-colors duration-150 focus:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-autobot-primary"
      >
        <NavItemIcon :item="item" class="h-4 w-4" />
        <span>{{ $t(item.labelKey) }}</span>
      </router-link>
      <NavOverflowMenu v-if="overflowItems.length > 0" :items="overflowItems" />
    </div>
  </nav>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute } from 'vue-router'
import type { NavItem } from '@/config/navItems'
import { useNavOverflow } from '@/composables/useNavOverflow'
import { useUiMode } from '@/composables/useUiMode'
import NavItemIcon from '@/components/layout/NavItemIcon.vue'
import NavOverflowMenu from '@/components/layout/NavOverflowMenu.vue'

const props = defineProps<{ items: NavItem[] }>()

const route = useRoute()
const { uiMode } = useUiMode()
const railRef = ref<HTMLElement | null>(null)

const inMode = computed(() => props.items.filter((item) => !(item.adv && uiMode.value === 'minimal')))
const rail = computed(() => inMode.value.filter((item) => !item.overflow))
const pinned = computed(() => inMode.value.filter((item) => item.overflow))

const { visibleCount } = useNavOverflow(railRef, computed(() => rail.value.length))
const visibleItems = computed(() => rail.value.slice(0, visibleCount.value))
const overflowItems = computed(() => [...rail.value.slice(visibleCount.value), ...pinned.value])

const isActive = (to: string): boolean => route.path.startsWith(to)
</script>
