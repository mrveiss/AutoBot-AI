<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * TabbedRouteLayout - header + ARIA tablist + router-view shell
 *
 * The one layout behind every "section with route-backed tabs" view
 * (MonitoringView, PerformanceView). Each view passes its tabs, title and
 * poller; header status goes in the `title-extra` slot, the right-hand header
 * content in `header-end`, and per-tab decoration in `tab-badge`.
 *
 * `nested` renders the secondary form for a layout inside another one (#19851).
 *
 * Issue #754: ARIA tablist/tab roles, aria-selected, accessible labels.
 */

import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { PollingPausedAlert, type UsePollingJobReturn } from '@autobot/ui'
import { registerWithOuterNotice, useRoutePausedNotice } from '@/composables/monitoringPollContext'
import { useRoute, useRouter } from 'vue-router'

export interface LayoutTab {
  id: string
  label: string
  path: string
  /** SVG path data for the tab icon */
  icon: string
}

const props = defineProps<{
  title: string
  tabsLabel: string
  tabs: LayoutTab[]
  /** Tab highlighted when the route matches none of `tabs` */
  defaultTab: string
  poller: UsePollingJobReturn<void>
  /**
   * Secondary layout inside another TabbedRouteLayout's content area: only the sub-tab
   * bar (with `header-end`), the paused notice and the router-view. No page shell,
   * no <h1>, no full-height wrapper, so the outer layout keeps the one page scroll.
   */
  nested?: boolean
}>()

const { t } = useI18n()
const route = useRoute()
const router = useRouter()

// Outer layout shows the one paused notice for its own and nested pollers (#19851)
const notice = props.nested ? null : useRoutePausedNotice(props.poller)
const hasOuterNotice = props.nested && registerWithOuterNotice(props.poller)

const activeTab = computed(() => {
  const tab = props.tabs.find(tb => route.path.startsWith(tb.path))
  return tab?.id ?? props.defaultTab
})

function navigateTo(path: string): void {
  router.push(path)
}
</script>

<template>
  <div :class="nested ? undefined : 'h-full flex flex-col overflow-hidden bg-gray-50'">
    <PollingPausedAlert v-if="notice" :poller="notice.alertSource" :message="t('common.polling.paused')" :retry-label="t('common.polling.retry')" class="mx-6 mt-4" @retry="notice.retry" />
    <PollingPausedAlert v-else-if="!hasOuterNotice" :poller="poller" :message="t('common.polling.paused')" :retry-label="t('common.polling.retry')" class="mx-6 mt-4" @retry="poller.start('')" />
    <!-- Header -->
    <div :class="['bg-white border-b border-gray-200 px-6', nested ? 'py-2' : 'py-4']">
      <div :class="['flex items-center', nested ? 'justify-end' : 'justify-between']">
        <div v-if="!nested" class="flex items-center gap-4">
          <h1 class="text-2xl font-bold text-gray-900">{{ title }}</h1>
          <slot name="title-extra" />
        </div>
        <slot name="header-end" />
      </div>

      <!-- Tab Navigation -->
      <div
        :class="['flex gap-1 overflow-x-auto', nested ? 'mt-2 -mb-2' : 'mt-4 -mb-4']"
        role="tablist"
        :aria-label="tabsLabel"
      >
        <button
          v-for="tab in tabs"
          :key="tab.id"
          @click="navigateTo(tab.path)"
          role="tab"
          :aria-selected="activeTab === tab.id"
          :aria-current="activeTab === tab.id ? 'page' : undefined"
          :class="[
            'px-4 py-2.5 text-sm font-medium rounded-t-lg transition-colors flex items-center gap-2 whitespace-nowrap',
            activeTab === tab.id
              ? 'bg-gray-50 text-primary-600 border-t border-x border-gray-200 -mb-px'
              : 'text-gray-600 hover:text-gray-900 hover:bg-gray-100'
          ]"
        >
          <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" :d="tab.icon" />
          </svg>
          {{ tab.label }}
          <slot name="tab-badge" :tab="tab" />
        </button>
      </div>
    </div>

    <!-- Content Area -->
    <div :class="nested ? undefined : 'flex-1 overflow-auto'">
      <router-view />
    </div>
  </div>
</template>
