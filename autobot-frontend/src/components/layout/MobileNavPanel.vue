<!--
  Copyright 2025-2026 mrveiss
  SPDX-License-Identifier: Apache-2.0

  MobileNavPanel — the below-lg navigation drawer (#18240). It renders the
  SAME registry the desktop header does (primary links, the icon-cluster
  entries, settings/tools, admin) -- no copy of the items. Advanced entries
  carry `.adv`, so Minimal mode hides them here too. The SLM text link is gone:
  Platform admin is a registry entry like the rest.
-->
<template>
  <Transition
    enter-active-class="transition duration-300 ease-out"
    enter-from-class="transform -translate-y-full opacity-0"
    enter-to-class="transform translate-y-0 opacity-100"
    leave-active-class="transition duration-200 ease-out"
    leave-from-class="transform translate-y-0 opacity-100"
    leave-to-class="transform -translate-y-full opacity-0"
  >
    <div
      v-show="open"
      id="mobile-nav"
      class="absolute left-0 right-0 top-full z-50 border-b border-autobot-border bg-autobot-bg-secondary shadow-lg lg:hidden"
    >
      <div class="max-h-[calc(100vh-3.5rem)] space-y-2 overflow-y-auto px-4 py-3">
        <div class="sm:hidden"><UiModeToggle /></div>
        <template v-for="row in rows" :key="row.item.labelKey">
          <a
            v-if="row.href"
            :href="row.href"
            target="_blank"
            rel="noopener noreferrer"
            :class="[rowClass, { adv: row.item.adv }]"
            @click="emit('close')"
          >
            <NavItemIcon :item="row.item" class="h-4 w-4 shrink-0" />
            <span>{{ $t(row.item.labelKey) }}</span>
          </a>
          <router-link
            v-else
            :to="row.to ?? '/'"
            :class="[rowClass, { adv: row.item.adv }, activeClass(row.to)]"
            @click="emit('close')"
          >
            <NavItemIcon :item="row.item" class="h-4 w-4 shrink-0" />
            <span>{{ $t(row.item.labelKey) }}</span>
          </router-link>
        </template>

        <div class="mt-1 border-t border-autobot-border pt-2">
          <p :class="headingClass">{{ $t('nav.settingsAndTools') }}</p>
          <router-link v-for="item in toolItems" :key="item.to" :to="item.to" :class="[rowClass, activeClass(item.to)]" @click="emit('close')">
            <NavItemIcon :item="item" class="h-4 w-4 shrink-0" />
            <span>{{ $t(item.labelKey) }}</span>
          </router-link>
        </div>

        <div v-if="userStore.isAdmin" class="mt-1 border-t border-autobot-border pt-2">
          <p :class="headingClass">{{ $t('nav.adminPanel') }}</p>
          <router-link v-for="item in adminMenuItems" :key="item.to" :to="item.to" :class="[rowClass, activeClass(item.to)]" @click="emit('close')">
            <NavItemIcon :item="item" class="h-4 w-4 shrink-0" />
            <span>{{ $t(item.labelKey) }}</span>
          </router-link>
        </div>

        <div class="mt-1 border-t border-autobot-border pt-2">
          <button v-if="userStore.isAuthenticated" type="button" :class="rowClass" @click="emit('open-profile')">
            <span>{{ $t('nav.profileSettings') }}</span>
          </button>
          <button type="button" :class="rowClass" @click="emit('open-status')">
            <span>{{ $t('nav.systemStatus') }}</span>
          </button>
          <router-link to="/about" :class="rowClass" @click="emit('close')">
            <span>{{ $t('nav.about') }}</span>
          </router-link>
        </div>
      </div>
    </div>
  </Transition>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import {
  adminMenuItems,
  filterByFeatureFlag,
  navIconItems,
  profileMenuItems,
  type NavItem,
} from '@/config/navItems'
import { useUserStore } from '@/stores/useUserStore'
import UiModeToggle from '@/components/layout/UiModeToggle.vue'
import NavItemIcon from '@/components/layout/NavItemIcon.vue'

const props = defineProps<{ open: boolean; items: NavItem[] }>()
const emit = defineEmits<{ close: []; 'open-profile': []; 'open-status': [] }>()

const route = useRoute()
const userStore = useUserStore()

const rowClass =
  'flex w-full items-center gap-2 rounded-md px-3 py-2 text-start text-sm font-medium text-autobot-text-primary transition-colors duration-200 hover:bg-autobot-bg-tertiary'
const headingClass = 'px-3 py-1 text-[10px] font-semibold uppercase tracking-wider text-autobot-text-secondary'

const toolItems = computed(() => filterByFeatureFlag(profileMenuItems))
const clusterItems = computed(() =>
  navIconItems.filter((item) => item.requires !== 'serviceManagement' || userStore.hasServiceManagement),
)
const rows = computed(() => [
  ...props.items.map((item) => ({ item, to: item.to as string | undefined, href: null as string | null })),
  ...clusterItems.value.map((item) => ({ item, to: item.to, href: item.href?.() ?? null })),
])

const activeClass = (to?: string): string =>
  to && route.path.startsWith(to) ? 'bg-autobot-primary text-autobot-text-inverse' : ''
</script>
