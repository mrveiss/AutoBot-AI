<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

import { ref } from 'vue'

const activeDashboard = ref('overview')

const dashboards = [
  { id: 'overview', name: 'System Overview', url: 'http://172.16.168.20:3000/d/system-overview' },
  { id: 'nodes', name: 'Node Metrics', url: 'http://172.16.168.20:3000/d/node-metrics' },
  { id: 'services', name: 'Service Health', url: 'http://172.16.168.20:3000/d/service-health' },
  { id: 'redis', name: 'Redis Metrics', url: 'http://172.16.168.20:3000/d/redis-metrics' },
]

const currentDashboard = ref(dashboards[0])

function selectDashboard(dashboard: typeof dashboards[0]): void {
  currentDashboard.value = dashboard
  activeDashboard.value = dashboard.id
}
</script>

<template>
  <div class="p-6 h-full flex flex-col">
    <!-- Header -->
    <div class="flex items-center justify-between mb-4">
      <div>
        <h1 class="text-2xl font-bold text-gray-900">Monitoring</h1>
        <p class="text-sm text-gray-500 mt-1">
          Grafana dashboards and system metrics
        </p>
      </div>
      <a
        :href="currentDashboard.url"
        target="_blank"
        class="btn btn-secondary flex items-center gap-2"
      >
        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
        </svg>
        Open in Grafana
      </a>
    </div>

    <!-- Dashboard Selector -->
    <div class="flex gap-2 mb-4">
      <button
        v-for="dashboard in dashboards"
        :key="dashboard.id"
        @click="selectDashboard(dashboard)"
        :class="[
          'px-4 py-2 text-sm font-medium rounded-lg transition-colors',
          activeDashboard === dashboard.id
            ? 'bg-primary-600 text-white'
            : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
        ]"
      >
        {{ dashboard.name }}
      </button>
    </div>

    <!-- Grafana Iframe -->
    <div class="card flex-1 overflow-hidden">
      <iframe
        :src="currentDashboard.url + '?kiosk=1&theme=light'"
        class="w-full h-full border-0"
        allow="fullscreen"
      ></iframe>
    </div>
  </div>
</template>
