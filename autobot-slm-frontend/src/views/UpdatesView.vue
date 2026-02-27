<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * UpdatesView - Tabbed container for Updates (Issue #1230)
 *
 * Consolidates System Updates and Code Sync into a single
 * tabbed view, following the existing AgentsView/:tab? pattern.
 *
 * Tabs:
 *   /updates/system    - Fleet system update management (Issue #840)
 *   /updates/code-sync - Code version sync across fleet (Issue #741)
 */

import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useCodeSync } from '@/composables/useCodeSync'
import SystemUpdatesTab from '@/views/SystemUpdatesTab.vue'
import CodeSyncView from '@/views/CodeSyncView.vue'

const route = useRoute()
const router = useRouter()
const codeSync = useCodeSync()

// Tab definitions
type UpdatesTab = 'system' | 'code-sync'

const tabs: { id: UpdatesTab; label: string }[] = [
  { id: 'system', label: 'System Updates' },
  { id: 'code-sync', label: 'Code Sync' },
]

function resolveTab(param: unknown): UpdatesTab {
  return param === 'code-sync' ? 'code-sync' : 'system'
}

const activeTab = computed(() => resolveTab(route.params.tab))

function navigateToTab(tab: UpdatesTab): void {
  router.push({ name: 'updates', params: { tab } })
}
</script>

<template>
  <div class="p-6 max-w-7xl mx-auto">
    <!-- Header -->
    <div class="mb-6">
      <h1 class="text-2xl font-bold text-gray-900">Updates</h1>
      <p class="text-sm text-gray-500 mt-1">
        Manage system updates and code deployments across the fleet
      </p>
    </div>

    <!-- Tab navigation -->
    <div class="border-b border-gray-200 mb-6">
      <nav class="flex gap-4">
        <button
          v-for="tab in tabs"
          :key="tab.id"
          @click="navigateToTab(tab.id)"
          :class="[
            'py-4 px-1 border-b-2 font-medium text-sm',
            activeTab === tab.id
              ? 'border-primary-500 text-primary-600'
              : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300',
          ]"
        >
          {{ tab.label }}
          <!-- Code sync outdated badge -->
          <span
            v-if="tab.id === 'code-sync' && codeSync.outdatedCount.value > 0"
            class="ml-2 inline-flex items-center justify-center w-5 h-5 text-xs font-bold text-white bg-yellow-500 rounded-full"
          >
            {{ codeSync.outdatedCount.value }}
          </span>
        </button>
      </nav>
    </div>

    <!-- Tab content -->
    <SystemUpdatesTab v-if="activeTab === 'system'" />
    <CodeSyncView v-else-if="activeTab === 'code-sync'" />
  </div>
</template>
