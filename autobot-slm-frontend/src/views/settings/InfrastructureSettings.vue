<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * InfrastructureSettings - Infrastructure overview and configuration
 *
 * Provides an overview of all infrastructure components with links
 * to detailed management in the Nodes settings.
 */

import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useFleetStore } from '@/stores/fleet'
import config from '@/config/ssot-config'

const router = useRouter()
const fleetStore = useFleetStore()

const loading = ref(false)
const error = ref<string | null>(null)

// Infrastructure status summary
const infrastructureStatus = computed(() => {
  const nodes = fleetStore.nodeList
  return {
    total: nodes.length,
    online: nodes.filter(n => n.status === 'online').length,
    offline: nodes.filter(n => n.status === 'offline' || n.status === 'error').length,
    pending: nodes.filter(n => n.status === 'pending' || n.status === 'enrolling').length,
  }
})

// VM configuration from SSOT
const vmConfig = computed(() => config.vm)
const portConfig = computed(() => config.port)

// Service endpoints
const endpoints = computed(() => [
  {
    name: 'Main Backend',
    ip: vmConfig.value.main,
    port: portConfig.value.backend,
    status: 'primary',
    description: 'FastAPI backend API server',
  },
  {
    name: 'Frontend Server',
    ip: vmConfig.value.frontend,
    port: portConfig.value.frontend,
    status: 'primary',
    description: 'Vue.js development server',
  },
  {
    name: 'SLM Admin',
    ip: vmConfig.value.slm,
    port: portConfig.value.slmApi,
    status: 'primary',
    description: 'Service Lifecycle Manager',
  },
  {
    name: 'NPU Worker',
    ip: vmConfig.value.npu,
    port: 8081,
    status: 'secondary',
    description: 'Intel OpenVINO acceleration',
  },
  {
    name: 'Redis Stack',
    ip: vmConfig.value.redis,
    port: portConfig.value.redis,
    status: 'primary',
    description: 'Data layer and caching',
  },
  {
    name: 'AI Stack',
    ip: vmConfig.value.ai,
    port: 8080,
    status: 'secondary',
    description: 'LLM and AI processing',
  },
  {
    name: 'Browser Automation',
    ip: vmConfig.value.browser,
    port: 3000,
    status: 'secondary',
    description: 'Playwright automation server',
  },
  {
    name: 'Grafana',
    ip: vmConfig.value.slm,
    port: portConfig.value.grafana,
    status: 'monitoring',
    description: 'Metrics visualization',
  },
  {
    name: 'Prometheus',
    ip: vmConfig.value.slm,
    port: portConfig.value.prometheus,
    status: 'monitoring',
    description: 'Metrics collection',
  },
])

function navigateToNodes() {
  router.push('/settings/nodes')
}

function getStatusClass(status: string): string {
  switch (status) {
    case 'primary': return 'bg-primary-100 text-primary-700 border-primary-200'
    case 'secondary': return 'bg-blue-100 text-blue-700 border-blue-200'
    case 'monitoring': return 'bg-purple-100 text-purple-700 border-purple-200'
    default: return 'bg-gray-100 text-gray-700 border-gray-200'
  }
}

onMounted(async () => {
  loading.value = true
  try {
    await fleetStore.fetchNodes()
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Failed to load fleet data'
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <div class="p-6">
    <!-- Loading -->
    <div v-if="loading" class="flex items-center justify-center py-8">
      <svg class="animate-spin w-8 h-8 text-primary-600" fill="none" viewBox="0 0 24 24">
        <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
        <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
      </svg>
    </div>

    <template v-else>
      <!-- Error -->
      <div v-if="error" class="mb-4 p-4 bg-red-50 border border-red-200 rounded-lg text-red-700">
        {{ error }}
      </div>

      <!-- Status Summary Cards -->
      <div class="grid grid-cols-4 gap-4 mb-6">
        <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-4">
          <p class="text-sm text-gray-500">Total Nodes</p>
          <p class="text-3xl font-bold text-gray-900">{{ infrastructureStatus.total }}</p>
        </div>
        <div class="bg-white rounded-lg shadow-sm border border-green-200 p-4">
          <p class="text-sm text-green-600">Online</p>
          <p class="text-3xl font-bold text-green-700">{{ infrastructureStatus.online }}</p>
        </div>
        <div class="bg-white rounded-lg shadow-sm border border-red-200 p-4">
          <p class="text-sm text-red-600">Offline</p>
          <p class="text-3xl font-bold text-red-700">{{ infrastructureStatus.offline }}</p>
        </div>
        <div class="bg-white rounded-lg shadow-sm border border-yellow-200 p-4">
          <p class="text-sm text-yellow-600">Pending</p>
          <p class="text-3xl font-bold text-yellow-700">{{ infrastructureStatus.pending }}</p>
        </div>
      </div>

      <!-- Quick Actions -->
      <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-4 mb-6">
        <div class="flex items-center justify-between">
          <div>
            <h3 class="font-semibold text-gray-900">Node Management</h3>
            <p class="text-sm text-gray-500">Add, remove, and configure infrastructure nodes</p>
          </div>
          <button
            @click="navigateToNodes"
            class="px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition-colors flex items-center gap-2"
          >
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 12h14M5 12a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v4a2 2 0 01-2 2M5 12a2 2 0 00-2 2v4a2 2 0 002 2h14a2 2 0 002-2v-4a2 2 0 00-2-2" />
            </svg>
            Manage Nodes
          </button>
        </div>
      </div>

      <!-- Service Endpoints -->
      <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
        <h2 class="text-lg font-semibold mb-4">Service Endpoints</h2>
        <p class="text-sm text-gray-500 mb-6">
          Configured infrastructure endpoints from SSOT configuration
        </p>

        <div class="grid gap-3">
          <div
            v-for="endpoint in endpoints"
            :key="endpoint.name"
            class="flex items-center justify-between p-4 bg-gray-50 rounded-lg border border-gray-100"
          >
            <div class="flex items-center gap-4">
              <div
                :class="[
                  'px-2 py-1 text-xs font-medium rounded border',
                  getStatusClass(endpoint.status)
                ]"
              >
                {{ endpoint.status.toUpperCase() }}
              </div>
              <div>
                <p class="font-medium text-gray-900">{{ endpoint.name }}</p>
                <p class="text-sm text-gray-500">{{ endpoint.description }}</p>
              </div>
            </div>
            <div class="text-right">
              <p class="font-mono text-sm text-gray-700">{{ endpoint.ip }}:{{ endpoint.port }}</p>
              <p class="text-xs text-gray-400">{{ config.httpProtocol }}://{{ endpoint.ip }}:{{ endpoint.port }}</p>
            </div>
          </div>
        </div>
      </div>

      <!-- Configuration Note -->
      <div class="mt-6 p-4 bg-blue-50 border border-blue-200 rounded-lg">
        <div class="flex items-start gap-3">
          <svg class="w-5 h-5 text-blue-500 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          <div>
            <p class="text-sm font-medium text-blue-800">Configuration Source</p>
            <p class="text-sm text-blue-600 mt-1">
              These endpoints are configured in <code class="bg-blue-100 px-1 rounded">src/config/ssot-config.ts</code>.
              For detailed node management including enrollment, updates, and certificate management, use the
              <button @click="navigateToNodes" class="underline hover:text-blue-800">Nodes settings</button>.
            </p>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>
