<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * InfrastructureMonitor - VM and infrastructure monitoring dashboard
 *
 * Displays real-time status of all VMs, services, and infrastructure components.
 *
 * NOTE: This component is intentionally separate from SLM node management (#737).
 * - Purpose: Monitor fixed infrastructure VMs defined in SSOT config
 * - Data source: SSOT config (config.vm.*) + fleet store health data
 * - Role field: Human-readable description, NOT technical NodeRole
 *
 * For dynamic node management, see:
 * - FleetOverview.vue for SLM node management
 * - @/constants/node-roles.ts for role definitions
 * - @/utils/node-status.ts for shared status utilities
 */

import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useFleetStore } from '@/stores/fleet'
import { getConfig } from '@/config/ssot-config'
import { getStatusBgColor, getMetricColor as getSharedMetricColor } from '@/utils/node-status'

const fleetStore = useFleetStore()
const config = getConfig()

// Refresh interval
let refreshInterval: ReturnType<typeof setInterval> | null = null
const isRefreshing = ref(false)

// VM definitions from SSOT config
const vmNodes = computed(() => [
  { id: 'main', name: 'Main (WSL)', ip: config.vm.main, role: 'Backend API', port: config.port.backend },
  { id: 'frontend', name: 'Frontend', ip: config.vm.frontend, role: 'Web UI', port: config.port.frontend },
  { id: 'npu', name: 'NPU Worker', ip: config.vm.npu, role: 'AI Acceleration', port: 8081 },
  { id: 'redis', name: 'Redis Stack', ip: config.vm.redis, role: 'Data Layer', port: config.port.redis },
  { id: 'ai', name: 'AI Stack', ip: config.vm.ai, role: 'AI Processing', port: 8080 },
  { id: 'browser', name: 'Browser', ip: config.vm.browser, role: 'Playwright', port: 3000 },
  { id: 'slm', name: 'SLM Host', ip: config.vm.slm, role: 'Service Manager', port: config.port.slmApi },
])

// Combine VM definitions with fleet store data
const infrastructureNodes = computed(() => {
  return vmNodes.value.map(vm => {
    const fleetNode = fleetStore.nodeList.find(n => n.ip_address === vm.ip)
    return {
      ...vm,
      status: fleetNode?.status ?? 'unknown',
      cpu: fleetNode?.health?.cpu_percent ?? 0,
      memory: fleetNode?.health?.memory_percent ?? 0,
      disk: fleetNode?.health?.disk_percent ?? 0,
      lastSeen: fleetNode?.last_heartbeat ?? null,
      services: fleetNode?.health?.services ?? [],
    }
  })
})

// Summary stats
const summaryStats = computed(() => {
  const nodes = infrastructureNodes.value
  return {
    total: nodes.length,
    online: nodes.filter(n => n.status === 'healthy' || n.status === 'online').length,
    degraded: nodes.filter(n => n.status === 'degraded').length,
    offline: nodes.filter(n => n.status === 'offline' || n.status === 'unknown').length,
  }
})

// Status utilities - using shared functions from @/utils/node-status.ts
function getStatusColor(status: string): string {
  // Map to Tailwind classes used in this component
  const color = getStatusBgColor(status)
  // Convert bg-green-500 -> bg-success-500 for legacy compatibility
  return color.replace('bg-green-', 'bg-success-')
    .replace('bg-yellow-', 'bg-warning-')
    .replace('bg-red-', 'bg-danger-')
}

function getMetricColor(value: number): string {
  const color = getSharedMetricColor(value)
  // Convert text-green-500 -> text-success-500 for legacy compatibility
  return color.replace('text-green-', 'text-success-')
    .replace('text-yellow-', 'text-warning-')
    .replace('text-red-', 'text-danger-')
}

function formatLastSeen(timestamp: string | null): string {
  if (!timestamp) return 'Never'
  const date = new Date(timestamp)
  const now = new Date()
  const diffMs = now.getTime() - date.getTime()
  const diffMins = Math.floor(diffMs / 60000)
  if (diffMins < 1) return 'Just now'
  if (diffMins < 60) return `${diffMins}m ago`
  const diffHours = Math.floor(diffMins / 60)
  if (diffHours < 24) return `${diffHours}h ago`
  return date.toLocaleDateString()
}

async function refresh() {
  isRefreshing.value = true
  try {
    await fleetStore.fetchNodes()
  } finally {
    isRefreshing.value = false
  }
}

onMounted(() => {
  refresh()
  refreshInterval = setInterval(refresh, 30000)
})

onUnmounted(() => {
  if (refreshInterval) {
    clearInterval(refreshInterval)
  }
})
</script>

<template>
  <div class="p-6">
    <!-- Header -->
    <div class="flex items-center justify-between mb-6">
      <h2 class="text-xl font-bold text-gray-900">Infrastructure Monitor</h2>
      <button
        @click="refresh"
        :disabled="isRefreshing"
        class="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 disabled:opacity-50 flex items-center gap-2"
      >
        <svg
          class="w-4 h-4"
          :class="{ 'animate-spin': isRefreshing }"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
        </svg>
        {{ isRefreshing ? 'Refreshing...' : 'Refresh' }}
      </button>
    </div>

    <!-- Summary Cards -->
    <div class="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
      <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-4">
        <p class="text-sm text-gray-500">Total Nodes</p>
        <p class="text-2xl font-bold text-gray-900">{{ summaryStats.total }}</p>
      </div>
      <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-4">
        <p class="text-sm text-gray-500">Online</p>
        <p class="text-2xl font-bold text-success-600">{{ summaryStats.online }}</p>
      </div>
      <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-4">
        <p class="text-sm text-gray-500">Degraded</p>
        <p class="text-2xl font-bold text-warning-600">{{ summaryStats.degraded }}</p>
      </div>
      <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-4">
        <p class="text-sm text-gray-500">Offline</p>
        <p class="text-2xl font-bold text-danger-600">{{ summaryStats.offline }}</p>
      </div>
    </div>

    <!-- Infrastructure Grid -->
    <div class="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-4">
      <div
        v-for="node in infrastructureNodes"
        :key="node.id"
        class="bg-white rounded-lg shadow-sm border border-gray-200 p-4"
      >
        <!-- Node Header -->
        <div class="flex items-center justify-between mb-4">
          <div class="flex items-center gap-3">
            <div :class="['w-3 h-3 rounded-full', getStatusColor(node.status)]"></div>
            <div>
              <h3 class="font-semibold text-gray-900">{{ node.name }}</h3>
              <p class="text-xs text-gray-500">{{ node.ip }}:{{ node.port }}</p>
            </div>
          </div>
          <span class="px-2 py-1 text-xs font-medium bg-gray-100 text-gray-600 rounded">
            {{ node.role }}
          </span>
        </div>

        <!-- Metrics -->
        <div class="space-y-2 mb-4">
          <div class="flex items-center justify-between text-sm">
            <span class="text-gray-600">CPU</span>
            <div class="flex items-center gap-2">
              <div class="w-24 h-2 bg-gray-200 rounded-full overflow-hidden">
                <div
                  class="h-full rounded-full transition-all"
                  :class="{
                    'bg-success-500': node.cpu < 70,
                    'bg-warning-500': node.cpu >= 70 && node.cpu < 90,
                    'bg-danger-500': node.cpu >= 90
                  }"
                  :style="{ width: `${node.cpu}%` }"
                ></div>
              </div>
              <span :class="getMetricColor(node.cpu)" class="w-12 text-right">{{ node.cpu.toFixed(1) }}%</span>
            </div>
          </div>
          <div class="flex items-center justify-between text-sm">
            <span class="text-gray-600">Memory</span>
            <div class="flex items-center gap-2">
              <div class="w-24 h-2 bg-gray-200 rounded-full overflow-hidden">
                <div
                  class="h-full rounded-full transition-all"
                  :class="{
                    'bg-success-500': node.memory < 70,
                    'bg-warning-500': node.memory >= 70 && node.memory < 90,
                    'bg-danger-500': node.memory >= 90
                  }"
                  :style="{ width: `${node.memory}%` }"
                ></div>
              </div>
              <span :class="getMetricColor(node.memory)" class="w-12 text-right">{{ node.memory.toFixed(1) }}%</span>
            </div>
          </div>
          <div class="flex items-center justify-between text-sm">
            <span class="text-gray-600">Disk</span>
            <div class="flex items-center gap-2">
              <div class="w-24 h-2 bg-gray-200 rounded-full overflow-hidden">
                <div
                  class="h-full rounded-full transition-all"
                  :class="{
                    'bg-success-500': node.disk < 70,
                    'bg-warning-500': node.disk >= 70 && node.disk < 90,
                    'bg-danger-500': node.disk >= 90
                  }"
                  :style="{ width: `${node.disk}%` }"
                ></div>
              </div>
              <span :class="getMetricColor(node.disk)" class="w-12 text-right">{{ node.disk.toFixed(1) }}%</span>
            </div>
          </div>
        </div>

        <!-- Services -->
        <div v-if="node.services.length > 0" class="pt-3 border-t border-gray-100">
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

        <!-- Last Seen -->
        <div class="mt-3 pt-3 border-t border-gray-100 text-xs text-gray-400">
          Last seen: {{ formatLastSeen(node.lastSeen) }}
        </div>
      </div>
    </div>
  </div>
</template>
