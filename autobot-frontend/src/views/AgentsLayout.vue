<template>
  <div class="agents-layout flex flex-col h-full bg-autobot-bg-primary">
    <nav
      class="flex shrink-0 border-b border-autobot-border bg-autobot-bg-secondary px-4"
      :aria-label="$t('agent.nav.label')"
    >
      <router-link
        v-for="tab in tabs"
        :key="tab.to"
        :to="tab.to"
        :class="[
          'px-4 py-3 text-sm font-medium border-b-2 transition-colors duration-150 focus:outline-none focus:ring-2 focus:ring-autobot-primary',
          isActive(tab) ? activeClass : inactiveClass,
        ]"
        :aria-current="isActive(tab) ? 'page' : undefined"
      >
        <i :class="['fas', tab.icon, 'mr-2']" aria-hidden="true"></i>
        {{ $t(tab.labelKey) }}
      </router-link>
    </nav>

    <div class="flex-1 min-h-0 overflow-hidden">
      <router-view class="h-full" />
    </div>
  </div>
</template>

<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * AgentsLayout — tabbed shell for /agents/* routes (#6634).
 *
 * Three tabs (Registry, Activity, Heartbeat). Each tab is a separate route
 * so URLs stay bookmarkable and browser back/forward works. AgentRegistryView's
 * own internal Backend/Specialized/Settings tabs live inside the Registry tab
 * and are untouched.
 */

import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'

const route = useRoute()
const { t: _t } = useI18n() // ensure $t is available in template

interface AgentTab {
  to: string
  labelKey: string
  icon: string
}

const tabs: AgentTab[] = [
  { to: '/agents/registry', labelKey: 'agent.nav.registry', icon: 'fa-robot' },
  { to: '/agents/activity', labelKey: 'agent.nav.activity', icon: 'fa-journal-whills' },
  { to: '/agents/heartbeat', labelKey: 'agent.nav.heartbeat', icon: 'fa-heartbeat' },
]

const activeClass =
  'text-autobot-primary border-autobot-primary'
const inactiveClass =
  'text-autobot-text-secondary border-transparent hover:text-autobot-text-primary hover:border-autobot-border'

const isActive = (tab: AgentTab) => computed(() => route.path === tab.to).value
</script>
