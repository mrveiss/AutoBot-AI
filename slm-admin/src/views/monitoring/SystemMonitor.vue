<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * SystemMonitor - Grafana-based system metrics display with service details
 *
 * Shows embedded Grafana dashboards for all VMs with option to view
 * detailed service health information.
 */

import { ref, computed } from 'vue'
import GrafanaDashboard from '@/components/monitoring/GrafanaDashboard.vue'
import { useFleetStore } from '@/stores/fleet'
import { usePrometheusMetrics } from '@/composables/usePrometheusMetrics'
import { getGrafanaUrl } from '@/config/ssot-config'

const fleetStore = useFleetStore()
const grafanaUrl = getGrafanaUrl()

const {
  gpuDetails,
  npuDetails,
  cpuUsage,
  memoryUsage,
  diskUsage,
  systemHealth,
} = usePrometheusMetrics({ autoFetch: true, pollInterval: 30000 })

// View mode toggle
const viewMode = ref<'grafana' | 'details'>('grafana')

// Dashboard selector
type DashboardType = 'overview' | 'system' | 'performance' | 'nodes' | 'redis' | 'api-health'
const activeDashboard = ref<DashboardType>('system')

const dashboards: { id: DashboardType; name: string; icon: string }[] = [
  { id: 'system', name: 'System Metrics', icon: 'M5 3v4M3 5h4M6 17v4m-2-2h4m5-16l2.286 6.857L21 12l-5.714 2.143L13 21l-2.286-6.857L5 12l5.714-2.143L13 3z' },
  { id: 'overview', name: 'Overview', icon: 'M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z' },
  { id: 'performance', name: 'GPU/NPU', icon: 'M9 3v2m6-2v2M9 19v2m6-2v2M5 9H3m2 6H3m18-6h-2m2 6h-2M7 19h10a2 2 0 002-2V7a2 2 0 00-2-2H7a2 2 0 00-2 2v10a2 2 0 002 2zM9 9h6v6H9V9z' },
  { id: 'nodes', name: 'Node Metrics', icon: 'M5 12h14M5 12a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v4a2 2 0 01-2 2M5 12a2 2 0 00-2 2v4a2 2 0 002 2h14a2 2 0 002-2v-4a2 2 0 00-2-2m-2-4h.01M17 16h.01' },
  { id: 'redis', name: 'Redis', icon: 'M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4' },
  { id: 'api-health', name: 'API Health', icon: 'M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z' },
]

// Node metrics from fleet store
const nodeMetrics = computed(() => {
  return fleetStore.nodeList.map(node => ({
    ...node,
    cpu: node.health?.cpu_percent ?? 0,
    memory: node.health?.memory_percent ?? 0,
    disk: node.health?.disk_percent ?? 0,
    services: node.health?.services ?? [],
  }))
})

function getStatusColor(status: string): string {
  switch (status) {
    case 'healthy': return 'bg-success-500'
    case 'degraded': return 'bg-warning-500'
    case 'unhealthy': return 'bg-danger-500'
    case 'offline': return 'bg-gray-400'
    default: return 'bg-gray-400'
  }
}

function getMetricColor(value: number): string {
  if (value >= 90) return 'text-danger-500'
  if (value >= 70) return 'text-warning-500'
  return 'text-success-500'
}
</script>

<template>
  <div class="p-6">
    <!-- Header -->
    <div class="flex items-center justify-between mb-6">
      <h2 class="text-xl font-bold text-gray-900">System Monitoring</h2>
      <div class="flex gap-2">
        <button
          @click="viewMode = 'grafana'"
          :class="[
            'px-4 py-2 text-sm font-medium rounded-lg transition-colors flex items-center gap-2',
            viewMode === 'grafana'
              ? 'bg-primary-600 text-white'
              : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
          ]"
        >
          <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
          </svg>
          Metrics Dashboards
        </button>
        <button
          @click="viewMode = 'details'"
          :class="[
            'px-4 py-2 text-sm font-medium rounded-lg transition-colors flex items-center gap-2',
            viewMode === 'details'
              ? 'bg-primary-600 text-white'
              : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
          ]"
        >
          <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6h16M4 10h16M4 14h16M4 18h16" />
          </svg>
          Service Details
        </button>
      </div>
    </div>

    <!-- Grafana View -->
    <div v-if="viewMode === 'grafana'" class="space-y-4">
      <!-- Dashboard Tabs -->
      <div class="flex flex-wrap gap-2">
        <button
          v-for="dash in dashboards"
          :key="dash.id"
          @click="activeDashboard = dash.id"
          :class="[
            'px-4 py-2 text-sm font-medium rounded-lg transition-colors flex items-center gap-2',
            activeDashboard === dash.id
              ? 'bg-gray-900 text-white'
              : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
          ]"
        >
          <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" :d="dash.icon" />
          </svg>
          {{ dash.name }}
        </button>
      </div>

      <!-- Dashboard Container -->
      <div class="bg-white rounded-lg shadow-sm border border-gray-200 overflow-hidden min-h-[600px]">
        <GrafanaDashboard
          :dashboard="activeDashboard"
          :height="600"
          :showControls="true"
        />
      </div>
    </div>

    <!-- Details View -->
    <div v-else class="space-y-6">
      <!-- Summary Cards -->
      <div class="grid grid-cols-1 md:grid-cols-4 gap-4">
        <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-4">
          <p class="text-sm text-gray-500">CPU Usage</p>
          <p class="text-2xl font-bold" :class="getMetricColor(cpuUsage)">{{ cpuUsage.toFixed(1) }}%</p>
        </div>
        <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-4">
          <p class="text-sm text-gray-500">Memory Usage</p>
          <p class="text-2xl font-bold" :class="getMetricColor(memoryUsage)">{{ memoryUsage.toFixed(1) }}%</p>
        </div>
        <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-4">
          <p class="text-sm text-gray-500">Disk Usage</p>
          <p class="text-2xl font-bold" :class="getMetricColor(diskUsage)">{{ diskUsage.toFixed(1) }}%</p>
        </div>
        <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-4">
          <p class="text-sm text-gray-500">System Health</p>
          <p class="text-2xl font-bold capitalize" :class="{
            'text-success-600': systemHealth === 'healthy',
            'text-warning-600': systemHealth === 'degraded',
            'text-danger-600': systemHealth === 'unhealthy' || systemHealth === 'critical',
            'text-gray-400': systemHealth === 'unknown',
          }">{{ systemHealth }}</p>
        </div>
      </div>

      <!-- Node Grid -->
      <div class="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-4">
        <div
          v-for="node in nodeMetrics"
          :key="node.node_id"
          class="bg-white rounded-lg shadow-sm border border-gray-200 p-4"
        >
          <div class="flex items-center gap-3 mb-4">
            <div :class="['w-3 h-3 rounded-full', getStatusColor(node.status)]"></div>
            <div>
              <h3 class="font-semibold text-gray-900">{{ node.hostname }}</h3>
              <p class="text-xs text-gray-500">{{ node.ip_address }}</p>
            </div>
          </div>

          <div class="space-y-2">
            <div class="flex justify-between text-sm">
              <span class="text-gray-600">CPU</span>
              <span :class="getMetricColor(node.cpu)">{{ node.cpu.toFixed(1) }}%</span>
            </div>
            <div class="flex justify-between text-sm">
              <span class="text-gray-600">Memory</span>
              <span :class="getMetricColor(node.memory)">{{ node.memory.toFixed(1) }}%</span>
            </div>
            <div class="flex justify-between text-sm">
              <span class="text-gray-600">Disk</span>
              <span :class="getMetricColor(node.disk)">{{ node.disk.toFixed(1) }}%</span>
            </div>
          </div>

          <div v-if="node.services.length > 0" class="mt-4 pt-3 border-t border-gray-100">
            <p class="text-xs text-gray-500 mb-2">Services</p>
            <div class="flex flex-wrap gap-1">
              <span
                v-for="service in node.services"
                :key="service.name"
                class="inline-flex items-center gap-1 px-2 py-0.5 text-xs bg-gray-100 rounded-full"
              >
                <span :class="['w-1.5 h-1.5 rounded-full', getStatusColor(service.status)]"></span>
                {{ service.name }}
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
