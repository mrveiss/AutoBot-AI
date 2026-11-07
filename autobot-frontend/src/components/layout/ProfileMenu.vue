<!--
  Copyright 2025-2026 mrveiss
  SPDX-License-Identifier: Apache-2.0

  ProfileMenu — the avatar button and its dropdown (#18240, GH#8748). Items:
  Profile settings, System status (the brand mark no longer opens it), the
  registry's settings/tools and admin entries, About. Extracted from App.vue;
  behaviour is unchanged apart from the System status item.
-->
<template>
  <div v-if="userStore.isAuthenticated" ref="triggerRef" class="relative hidden sm:block">
    <BaseTooltip :text="$t('nav.profileSettings')" placement="left">
      <template #default="{ describedby }">
        <button
          type="button"
          class="flex h-9 w-9 items-center justify-center rounded-full bg-autobot-primary text-xs font-semibold text-autobot-text-inverse transition-opacity duration-150 hover:opacity-90 focus:outline-none focus-visible:ring-2 focus-visible:ring-autobot-primary focus-visible:ring-offset-2"
          :aria-label="$t('nav.profileMenu')"
          :aria-describedby="describedby"
          :aria-expanded="open"
          aria-haspopup="menu"
          data-testid="profile-menu-trigger"
          @click="open = !open"
        >
          {{ initial }}
        </button>
      </template>
    </BaseTooltip>

    <Teleport to="body">
      <div
        v-if="open"
        ref="menuRef"
        :style="menuStyle"
        class="fixed z-50 min-w-48 rounded-md border border-autobot-border bg-autobot-bg-secondary py-1 shadow-lg"
        role="menu"
        :aria-label="$t('nav.profileMenu')"
      >
        <p class="truncate px-3 py-1 text-xs text-autobot-text-secondary">{{ displayUsername || $t('nav.profile') }}</p>
        <button type="button" role="menuitem" :class="rowClass" @click="pick('open-profile')">
          <span>{{ $t('nav.profileSettings') }}</span>
        </button>
        <button type="button" role="menuitem" :class="rowClass" data-testid="profile-menu-status" @click="pick('open-status')">
          <span>{{ $t('nav.systemStatus') }}</span>
        </button>

        <hr class="my-1 border-autobot-border" />
        <p :class="headingClass">{{ $t('nav.settingsAndTools') }}</p>
        <router-link v-for="item in toolItems" :key="item.to" :to="item.to" role="menuitem" :class="rowClass" @click="open = false">
          <NavItemIcon :item="item" class="h-4 w-4 shrink-0" />
          <span>{{ $t(item.labelKey) }}</span>
        </router-link>

        <template v-if="userStore.isAdmin">
          <hr class="my-1 border-autobot-border" />
          <p :class="headingClass">{{ $t('nav.adminPanel') }}</p>
          <router-link v-for="item in adminMenuItems" :key="item.to" :to="item.to" role="menuitem" :class="rowClass" @click="open = false">
            <NavItemIcon :item="item" class="h-4 w-4 shrink-0" />
            <span>{{ $t(item.labelKey) }}</span>
          </router-link>
        </template>

        <hr class="my-1 border-autobot-border" />
        <router-link to="/about" role="menuitem" :class="rowClass" @click="open = false">
          <span>{{ $t('nav.about') }}</span>
        </router-link>
      </div>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { BaseTooltip } from '@autobot/ui'
import { adminMenuItems, filterByFeatureFlag, profileMenuItems } from '@/config/navItems'
import { useUserStore } from '@/stores/useUserStore'
import NavItemIcon from '@/components/layout/NavItemIcon.vue'

const emit = defineEmits<{ 'open-profile': []; 'open-status': [] }>()

const userStore = useUserStore()
const open = ref(false)
const triggerRef = ref<HTMLElement | null>(null)
const menuRef = ref<HTMLElement | null>(null)
const menuStyle = ref<Record<string, string>>({})

const rowClass =
  'flex w-full items-center gap-2 px-3 py-2 text-start text-sm text-autobot-text-primary transition-colors duration-150 hover:bg-autobot-bg-tertiary'
const headingClass = 'px-3 py-1 text-[10px] font-semibold uppercase tracking-wider text-autobot-text-secondary'

const toolItems = computed(() => filterByFeatureFlag(profileMenuItems))

// Issue #973: guard against a Promise being rendered as the username
const displayUsername = computed(() => {
  const username = userStore.currentUser?.username
  return typeof username === 'string' ? username : null
})
const initial = computed(() => displayUsername.value?.charAt(0)?.toUpperCase() || 'U')

function pick(event: 'open-profile' | 'open-status'): void {
  open.value = false
  if (event === 'open-profile') emit('open-profile')
  else emit('open-status')
}

function position(): void {
  if (!triggerRef.value) return
  const rect = triggerRef.value.getBoundingClientRect()
  const width = menuRef.value?.getBoundingClientRect().width || 192
  const left = window.innerWidth - rect.left < width ? rect.right - width : rect.left
  menuStyle.value = { top: `${rect.bottom + 4}px`, left: `${Math.max(0, left)}px` }
}

function onClickOutside(event: MouseEvent): void {
  const target = event.target as Node
  if (!triggerRef.value?.contains(target) && !menuRef.value?.contains(target)) open.value = false
}

watch(open, async (isOpen) => {
  if (!isOpen) {
    document.removeEventListener('click', onClickOutside, true)
    return
  }
  position()
  await nextTick()
  position()
  document.addEventListener('click', onClickOutside, true)
})

onBeforeUnmount(() => document.removeEventListener('click', onClickOutside, true))
</script>
