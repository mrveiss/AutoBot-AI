<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * GrafanaDashboards - Full Grafana dashboard browser and viewer
 *
 * Provides a full-page Grafana integration with dashboard selection
 * and embedded viewing capabilities.
 */

import { ref, computed } from 'vue'
import GrafanaDashboard from '@/components/monitoring/GrafanaDashboard.vue'
import { getGrafanaUrl } from '@/config/ssot-config'

const grafanaUrl = getGrafanaUrl()

// Dashboard categories
interface Dashboard {
  id: string
  name: string
  description: string
  category: string
  icon: string
}

const dashboards: Dashboard[] = [
  // System Dashboards
  { id: 'system', name: 'System Metrics', description: 'CPU, Memory, Disk, Network', category: 'System', icon: 'M5 3v4M3 5h4M6 17v4m-2-2h4m5-16l2.286 6.857L21 12l-5.714 2.143L13 21l-2.286-6.857L5 12l5.714-2.143L13 3z' },
  { id: 'overview', name: 'Overview', description: 'High-level system overview', category: 'System', icon: 'M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z' },
  { id: 'nodes', name: 'Node Metrics', description: 'Per-node resource metrics', category: 'System', icon: 'M5 12h14M5 12a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v4a2 2 0 01-2 2M5 12a2 2 0 00-2 2v4a2 2 0 002 2h14a2 2 0 002-2v-4a2 2 0 00-2-2m-2-4h.01M17 16h.01' },

  // Hardware Dashboards
  { id: 'performance', name: 'GPU/NPU', description: 'Hardware acceleration metrics', category: 'Hardware', icon: 'M9 3v2m6-2v2M9 19v2m6-2v2M5 9H3m2 6H3m18-6h-2m2 6h-2M7 19h10a2 2 0 002-2V7a2 2 0 00-2-2H7a2 2 0 00-2 2v10a2 2 0 002 2zM9 9h6v6H9V9z' },

  // Service Dashboards
  { id: 'redis', name: 'Redis', description: 'Redis memory and performance', category: 'Services', icon: 'M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4' },
  { id: 'api-health', name: 'API Health', description: 'API latency and availability', category: 'Services', icon: 'M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z' },

  // Application Dashboards
  { id: 'workflow', name: 'Workflow', description: 'Task and workflow metrics', category: 'Application', icon: 'M4 5a1 1 0 011-1h14a1 1 0 011 1v2a1 1 0 01-1 1H5a1 1 0 01-1-1V5zM4 13a1 1 0 011-1h6a1 1 0 011 1v6a1 1 0 01-1 1H5a1 1 0 01-1-1v-6zM16 13a1 1 0 011-1h2a1 1 0 011 1v6a1 1 0 01-1 1h-2a1 1 0 01-1-1v-6z' },
  { id: 'errors', name: 'Errors', description: 'Error rates and tracking', category: 'Application', icon: 'M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z' },
]

// State
const selectedDashboard = ref<string>('system')
const selectedCategory = ref<string>('all')
const isFullscreen = ref(false)

// Categories
const categories = computed(() => {
  const cats = new Set(dashboards.map(d => d.category))
  return ['all', ...Array.from(cats)]
})

// Filtered dashboards
const filteredDashboards = computed(() => {
  if (selectedCategory.value === 'all') return dashboards
  return dashboards.filter(d => d.category === selectedCategory.value)
})

// Current dashboard info
const currentDashboard = computed(() => {
  return dashboards.find(d => d.id === selectedDashboard.value) ?? dashboards[0]
})

function selectDashboard(id: string) {
  selectedDashboard.value = id
}

function toggleFullscreen() {
  isFullscreen.value = !isFullscreen.value
}

function openInGrafana() {
  window.open(`${grafanaUrl}/d/${selectedDashboard.value}`, '_blank')
}
</script>

<template>
  <div :class="['p-6', { 'fixed inset-0 z-50 bg-white': isFullscreen }]">
    <!-- Header -->
    <div class="flex items-center justify-between mb-6">
      <div>
        <h2 class="text-xl font-bold text-gray-900">Grafana Dashboards</h2>
        <p class="text-sm text-gray-500 mt-1">{{ currentDashboard.name }} - {{ currentDashboard.description }}</p>
      </div>
      <div class="flex items-center gap-2">
        <button
          @click="toggleFullscreen"
          class="px-3 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 flex items-center gap-2"
        >
          <svg v-if="!isFullscreen" class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 8V4m0 0h4M4 4l5 5m11-1V4m0 0h-4m4 0l-5 5M4 16v4m0 0h4m-4 0l5-5m11 5l-5-5m5 5v-4m0 4h-4" />
          </svg>
          <svg v-else class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
          </svg>
          {{ isFullscreen ? 'Exit' : 'Fullscreen' }}
        </button>
        <button
          @click="openInGrafana"
          class="px-4 py-2 text-sm font-medium text-white bg-primary-600 rounded-lg hover:bg-primary-700 flex items-center gap-2"
        >
          <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
          </svg>
          Open in Grafana
        </button>
      </div>
    </div>

    <div :class="[isFullscreen ? 'flex gap-4 h-[calc(100vh-100px)]' : 'flex flex-col lg:flex-row gap-4']">
      <!-- Dashboard Selector Panel -->
      <div :class="[isFullscreen ? 'w-64 flex-shrink-0 overflow-y-auto' : 'lg:w-64']">
        <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-4">
          <!-- Category Filter -->
          <div class="mb-4">
            <label class="text-xs font-medium text-gray-500 uppercase tracking-wider">Category</label>
            <select
              v-model="selectedCategory"
              class="mt-1 w-full px-3 py-2 text-sm border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500"
            >
              <option v-for="cat in categories" :key="cat" :value="cat">
                {{ cat === 'all' ? 'All Categories' : cat }}
              </option>
            </select>
          </div>

          <!-- Dashboard List -->
          <div class="space-y-2">
            <button
              v-for="dash in filteredDashboards"
              :key="dash.id"
              @click="selectDashboard(dash.id)"
              :class="[
                'w-full px-3 py-2 text-left rounded-lg transition-colors flex items-start gap-3',
                selectedDashboard === dash.id
                  ? 'bg-primary-50 text-primary-700 border border-primary-200'
                  : 'hover:bg-gray-50 text-gray-700'
              ]"
            >
              <svg class="w-5 h-5 flex-shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" :d="dash.icon" />
              </svg>
              <div>
                <p class="text-sm font-medium">{{ dash.name }}</p>
                <p class="text-xs text-gray-500">{{ dash.description }}</p>
              </div>
            </button>
          </div>
        </div>
      </div>

      <!-- Dashboard Viewer -->
      <div :class="[isFullscreen ? 'flex-1' : 'flex-1 min-h-[600px]']">
        <div class="bg-white rounded-lg shadow-sm border border-gray-200 overflow-hidden h-full">
          <GrafanaDashboard
            :dashboard="(selectedDashboard as any)"
            :height="isFullscreen ? 'calc(100vh - 150px)' : 600"
            :showControls="true"
          />
        </div>
      </div>
    </div>
  </div>
</template>
