<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * SettingsView - Layout wrapper for settings subsections
 *
 * Provides navigation tabs for settings sub-routes and displays
 * the active sub-view via router-view.
 *
 * Issue #754: Added ARIA tablist/tab roles, aria-selected,
 * aria-current, accessible error/success messages.
 */

import { computed, ref, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'

const route = useRoute()
const router = useRouter()

const error = ref<string | null>(null)
const success = ref<string | null>(null)

// Navigation tabs for settings sub-routes (all SLM settings - Issue #729)
const tabs = [
  { id: 'general', name: 'General', path: '/settings/general', icon: 'M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z M15 12a3 3 0 11-6 0 3 3 0 016 0z' },
  // Issue #737: Nodes tab removed - consolidated to Fleet Overview
  // Issue #786: Infrastructure tab removed - consolidated to Fleet Overview /fleet/infrastructure
  // { id: 'nodes', name: 'Nodes', path: '/settings/nodes', icon: '...' },
  { id: 'monitoring', name: 'Monitoring', path: '/settings/monitoring', icon: 'M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z' },
  { id: 'notifications', name: 'Notifications', path: '/settings/notifications', icon: 'M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9' },
  { id: 'security', name: 'Security', path: '/settings/security', icon: 'M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z' },
  { id: 'api', name: 'API', path: '/settings/api', icon: 'M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4' },
  { id: 'backend', name: 'Backend', path: '/settings/backend', icon: 'M5 12h14M5 12a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v4a2 2 0 01-2 2M5 12a2 2 0 00-2 2v4a2 2 0 002 2h14a2 2 0 002-2v-4a2 2 0 00-2-2' },
  // Migrated from main AutoBot frontend - Issue #729
  { id: 'users', name: 'Users', path: '/settings/admin/users', icon: 'M12 4.354a4 4 0 110 5.292M15 21H3v-1a6 6 0 0112 0v1zm0 0h6v-1a6 6 0 00-9-5.197M13 7a4 4 0 11-8 0 4 4 0 018 0z' },
  { id: 'cache', name: 'Cache', path: '/settings/admin/cache', icon: 'M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4m0 5c0 2.21-3.582 4-8 4s-8-1.79-8-4' },
  { id: 'prompts', name: 'Prompts', path: '/settings/admin/prompts', icon: 'M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z' },
  { id: 'personality', name: 'Personality', path: '/settings/admin/personality', icon: 'M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z' },
  { id: 'log-forwarding', name: 'Log Forwarding', path: '/settings/admin/log-forwarding', icon: 'M12 19l9 2-9-18-9 18 9-2zm0 0v-8' },
  // Issue: NPU Workers consolidated to Fleet Overview /fleet/npu (Worker Registry sub-tab)
]

// Get active tab based on current route
const activeTab = computed(() => {
  const path = route.path
  const tab = tabs.find(t => path.startsWith(t.path))
  return tab?.id ?? 'general'
})

function navigateTo(path: string) {
  router.push(path)
}


onMounted(() => {
  // If we're at /settings exactly, redirect to /settings/general
  if (route.path === '/settings' || route.path === '/settings/') {
    router.replace('/settings/general')
  }
})
</script>

<template>
  <div class="h-full flex flex-col overflow-hidden bg-gray-50">
    <!-- Header -->
    <div class="bg-white border-b border-gray-200 px-6 py-4">
      <div class="flex items-center justify-between">
        <div class="flex items-center gap-4">
          <h1 class="text-2xl font-bold text-gray-900">Settings</h1>
          <p class="text-sm text-gray-500">Configure system settings and infrastructure</p>
        </div>
      </div>

      <!-- Tab Navigation -->
      <div
        class="flex gap-1 mt-4 -mb-4 overflow-x-auto"
        role="tablist"
        aria-label="Settings sections"
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
          {{ tab.name }}
        </button>
      </div>
    </div>

    <!-- Messages -->
    <div v-if="error" class="mx-6 mt-4 p-4 bg-red-50 border border-red-200 rounded-lg text-red-700" role="alert">
      {{ error }}
    </div>
    <div v-if="success" class="mx-6 mt-4 p-4 bg-green-50 border border-green-200 rounded-lg text-green-700" role="status">
      {{ success }}
    </div>

    <!-- Content Area -->
    <div class="flex-1 overflow-auto">
      <router-view />
    </div>
  </div>
</template>
