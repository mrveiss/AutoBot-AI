<!--
  Copyright 2025-2026 mrveiss
  SPDX-License-Identifier: Apache-2.0

  AppHeader — the application's top bar (#18240), split out of App.vue.
  Brand (the kit BrandMark, linking Home) · primary links · icon cluster ·
  profile menu · mobile drawer. The brand no longer opens System Status (that
  is a profile-menu item now); the health dot stays as a decorative overlay on
  the mark. It composes TopNavLinks, NavIconCluster, ProfileMenu and
  MobileNavPanel; the nav registry (config/navItems.ts) feeds all of them.
-->
<template>
  <header class="app-header relative z-30 min-h-14 border-b border-autobot-border bg-autobot-bg-secondary">
    <div class="mx-auto flex min-h-14 max-w-full items-center gap-2 px-4 sm:px-6 lg:px-8">
      <router-link
        to="/home"
        class="me-2 flex shrink-0 items-center gap-2.5 rounded-md py-1 pe-2 focus:outline-none focus-visible:ring-2 focus-visible:ring-autobot-primary"
        :aria-label="$t('nav.homeAria')"
        data-testid="app-brand"
      >
        <span class="relative inline-flex">
          <BrandMark :size="32" />
          <span
            class="absolute -end-1 -top-1 h-3 w-3 rounded-full border-2 border-autobot-bg-secondary"
            :class="statusDot[statusTone]"
            aria-hidden="true"
            data-testid="health-dot"
          ></span>
        </span>
        <span class="hidden text-lg font-semibold text-autobot-text-primary sm:block">AutoBot</span>
      </router-link>

      <TopNavLinks :items="navItems" />
      <span class="flex-1 lg:hidden" aria-hidden="true"></span>

      <div class="hidden sm:block"><NavIconCluster /></div>
      <ProfileMenu class="ms-2" @open-profile="emit('open-profile')" @open-status="emit('open-status')" />

      <button
        type="button"
        class="inline-flex items-center justify-center rounded p-2 text-autobot-text-primary hover:bg-autobot-bg-tertiary focus:outline-none focus-visible:ring-2 focus-visible:ring-autobot-primary lg:hidden"
        aria-controls="mobile-nav"
        :aria-expanded="showMobileNav"
        @click="showMobileNav = !showMobileNav"
      >
        <span class="sr-only">{{ $t('nav.openMainMenu') }}</span>
        <svg class="block h-6 w-6" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
          <path v-if="!showMobileNav" stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6h16M4 12h16M4 18h16" />
          <path v-else stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
        </svg>
      </button>
    </div>

    <!-- Minimal mode only (.only-min): says what is hidden and offers the way back -->
    <div
      class="only-min flex-wrap items-center gap-2 border-t border-autobot-border px-4 py-1 text-xs text-autobot-text-secondary sm:px-6 lg:px-8"
      data-testid="minimal-note"
    >
      <span>{{ $t('ui.minimalNote') }}</span>
      <button
        type="button"
        class="font-semibold text-autobot-text-link underline underline-offset-2 focus:outline-none focus-visible:ring-2 focus-visible:ring-autobot-primary"
        @click="showAllFeatures"
      >
        {{ $t('ui.minimalNoteAction') }}
      </button>
    </div>

    <MobileNavPanel
      :open="showMobileNav"
      :items="navItems"
      @close="showMobileNav = false"
      @open-profile="closeThen('open-profile')"
      @open-status="closeThen('open-status')"
    />
    <div v-if="showMobileNav" class="fixed inset-0 z-10 bg-black/25 lg:hidden" @click="showMobileNav = false"></div>
  </header>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { BrandMark } from '@autobot/ui'
import { filterByFeatureFlag, navItems as registry } from '@/config/navItems'
import { useUiMode, useUiModeAnnouncer } from '@/composables/useUiMode'
import { useInjectedSystemStatus, type StatusTone } from '@/composables/systemStatusContext'
import { useRuntimeFeaturesStore } from '@/stores/useRuntimeFeaturesStore'
import TopNavLinks from '@/components/layout/TopNavLinks.vue'
import NavIconCluster from '@/components/layout/NavIconCluster.vue'
import ProfileMenu from '@/components/layout/ProfileMenu.vue'
import MobileNavPanel from '@/components/layout/MobileNavPanel.vue'

const emit = defineEmits<{ 'open-profile': []; 'open-status': [] }>()

const runtimeFeatures = useRuntimeFeaturesStore()
const { statusTone } = useInjectedSystemStatus()
const showMobileNav = ref(false)

const statusDot: Record<StatusTone, string> = {
  success: 'bg-autobot-success',
  warning: 'bg-autobot-warning',
  error: 'bg-autobot-error animate-pulse',
}

// #10502: hide Company OS when the deployment has no PostgreSQL company mode --
// its endpoints return 503 there. The runtime flag fails closed until it loads.
const navItems = computed(() =>
  filterByFeatureFlag(registry).filter(
    (item) => item.to !== '/llc/select-company' || runtimeFeatures.companyOsEnabled,
  ),
)

const { setMode } = useUiMode()
const announceMode = useUiModeAnnouncer()

function showAllFeatures(): void {
  setMode('full')
  announceMode('full')
}

function closeThen(event: 'open-profile' | 'open-status'): void {
  showMobileNav.value = false
  if (event === 'open-profile') emit('open-profile')
  else emit('open-status')
}

function onDocumentClick(event: MouseEvent): void {
  const target = event.target as HTMLElement | null
  if (showMobileNav.value && target && !target.closest('#mobile-nav') && !target.closest('[aria-controls="mobile-nav"]')) {
    showMobileNav.value = false
  }
}

function onDocumentKeydown(event: KeyboardEvent): void {
  if (event.key === 'Escape' && showMobileNav.value) showMobileNav.value = false
}

onMounted(() => {
  document.addEventListener('click', onDocumentClick)
  document.addEventListener('keydown', onDocumentKeydown)
})
onBeforeUnmount(() => {
  document.removeEventListener('click', onDocumentClick)
  document.removeEventListener('keydown', onDocumentKeydown)
})
</script>
