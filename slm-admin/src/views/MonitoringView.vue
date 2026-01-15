<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * MonitoringView - Layout wrapper for monitoring subsections
 *
 * Provides navigation tabs for monitoring sub-routes and displays
 * the active sub-view via router-view.
 */

import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useFleetStore } from '@/stores/fleet'
import { usePrometheusMetrics } from '@/composables/usePrometheusMetrics'

const route = useRoute()
const router = useRouter()
const fleetStore = useFleetStore()

const {
  systemHealth,
  activeAlertCount,
} = usePrometheusMetrics({ autoFetch: true, pollInterval: 30000 })

// Navigation tabs for monitoring sub-routes
const tabs = [
  { id: 'system', name: 'System', path: '/monitoring/system', icon: 'M5 3v4M3 5h4M6 17v4m-2-2h4m5-16l2.286 6.857L21 12l-5.714 2.143L13 21l-2.286-6.857L5 12l5.714-2.143L13 3z' },
  { id: 'infrastructure', name: 'Infrastructure', path: '/monitoring/infrastructure', icon: 'M5 12h14M5 12a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v4a2 2 0 01-2 2M5 12a2 2 0 00-2 2v4a2 2 0 002 2h14a2 2 0 002-2v-4a2 2 0 00-2-2m-2-4h.01M17 16h.01' },
  { id: 'logs', name: 'Logs', path: '/monitoring/logs', icon: 'M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z' },
  { id: 'dashboards', name: 'Dashboards', path: '/monitoring/dashboards', icon: 'M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z' },
  { id: 'alerts', name: 'Alerts', path: '/monitoring/alerts', icon: 'M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9' },
  { id: 'errors', name: 'Errors', path: '/monitoring/errors', icon: 'M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z' },
]

// Get active tab based on current route
const activeTab = computed(() => {
  const path = route.path
  const tab = tabs.find(t => path.startsWith(t.path))
  return tab?.id ?? 'system'
})

// Check if there are critical alerts
const hasCriticalAlerts = computed(() => activeAlertCount.value > 0)

function navigateTo(path: string) {
  router.push(path)
}

function getStatusColor(status: string): string {
  switch (status) {
    case 'healthy': return 'bg-success-500'
    case 'degraded': return 'bg-warning-500'
    case 'unhealthy':
    case 'critical': return 'bg-danger-500'
    default: return 'bg-gray-400'
  }
}
</script>

<template>
  <div class="h-full flex flex-col overflow-hidden bg-gray-50">
    <!-- Header -->
    <div class="bg-white border-b border-gray-200 px-6 py-4">
      <div class="flex items-center justify-between">
        <div class="flex items-center gap-4">
          <h1 class="text-2xl font-bold text-gray-900">Monitoring</h1>
          <div class="flex items-center gap-2">
            <span
              :class="['w-2.5 h-2.5 rounded-full', getStatusColor(systemHealth)]"
            ></span>
            <span class="text-sm text-gray-600 capitalize">{{ systemHealth }}</span>
          </div>
        </div>

        <!-- Quick Stats -->
        <div class="flex items-center gap-4 text-sm">
          <div class="flex items-center gap-2 text-gray-600">
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 12h14M5 12a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v4a2 2 0 01-2 2M5 12a2 2 0 00-2 2v4a2 2 0 002 2h14a2 2 0 002-2v-4a2 2 0 00-2-2" />
            </svg>
            <span>{{ fleetStore.nodeList.length }} Nodes</span>
          </div>
          <div v-if="hasCriticalAlerts" class="flex items-center gap-2 text-danger-600">
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
            <span>{{ activeAlertCount }} Alert{{ activeAlertCount !== 1 ? 's' : '' }}</span>
          </div>
        </div>
      </div>

      <!-- Tab Navigation -->
      <div class="flex gap-1 mt-4 -mb-4 overflow-x-auto">
        <button
          v-for="tab in tabs"
          :key="tab.id"
          @click="navigateTo(tab.path)"
          :class="[
            'px-4 py-2.5 text-sm font-medium rounded-t-lg transition-colors flex items-center gap-2 whitespace-nowrap',
            activeTab === tab.id
              ? 'bg-gray-50 text-primary-600 border-t border-x border-gray-200 -mb-px'
              : 'text-gray-600 hover:text-gray-900 hover:bg-gray-100'
          ]"
        >
          <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" :d="tab.icon" />
          </svg>
          {{ tab.name }}
          <span
            v-if="tab.id === 'alerts' && activeAlertCount > 0"
            class="px-1.5 py-0.5 text-xs font-bold bg-danger-500 text-white rounded-full"
          >
            {{ activeAlertCount }}
          </span>
        </button>
      </div>
    </div>

    <!-- Content Area -->
    <div class="flex-1 overflow-auto">
      <router-view />
    </div>
  </div>
</template>
