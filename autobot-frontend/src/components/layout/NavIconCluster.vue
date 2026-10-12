<!--
  Copyright 2025-2026 mrveiss
  SPDX-License-Identifier: Apache-2.0

  NavIconCluster — the icon-only controls on the header's right (#18240):
  Secrets, Preferences, the Minimal/Full toggle, Platform admin. The entries
  come from the nav registry (navIconItems); every icon carries an i18n
  aria-label and a kit tooltip. Platform admin is the SLM console: a new tab,
  shown only to roles with service.management. Advanced entries carry `.adv`
  so Minimal mode hides them (assets/css/components.css).
-->
<template>
  <div class="flex items-center gap-0.5" data-testid="nav-icon-cluster">
    <template v-for="item in leading" :key="item.labelKey">
      <NavIconLink :item="item" />
    </template>
    <UiModeToggle />
    <template v-for="item in trailing" :key="item.labelKey">
      <NavIconLink :item="item" />
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { navIconItems } from '@/config/navItems'
import { useUserStore } from '@/stores/useUserStore'
import UiModeToggle from '@/components/layout/UiModeToggle.vue'
import NavIconLink from '@/components/layout/NavIconLink.vue'

const userStore = useUserStore()

const allowed = computed(() =>
  navIconItems.filter((item) => item.requires !== 'serviceManagement' || userStore.hasServiceManagement),
)
const leading = computed(() => allowed.value.filter((item) => !item.afterToggle))
const trailing = computed(() => allowed.value.filter((item) => item.afterToggle))
</script>
