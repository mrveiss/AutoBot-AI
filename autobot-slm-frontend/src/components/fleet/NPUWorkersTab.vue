// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

<script setup lang="ts">
/**
 * NPUWorkersTab - NPU Workers management as a Fleet tab
 *
 * Provides NPU worker management with sub-tab navigation:
 * Overview, Monitor, Performance, Load Balancing.
 *
 * Related to Issue #255 (Service Authentication), enhanced in Issue #590.
 */

import { ref, computed, onMounted, watch } from 'vue'
import { useFleetStore } from '@/stores/fleet'
import NPUNodeCard from './NPUNodeCard.vue'
import NPUDetailsPanel from './NPUDetailsPanel.vue'
import AssignNPURoleModal from './AssignNPURoleModal.vue'
import NPUWorkerMonitor from './NPUWorkerMonitor.vue'
import NPUPerformanceMetrics from './NPUPerformanceMetrics.vue'
import LoadBalancingView from './LoadBalancingView.vue'
import NPUWorkersSettings from '@/views/settings/admin/NPUWorkersSettings.vue'
import type { SLMNode } from '@/types/slm'

const fleetStore = useFleetStore()

// Sub-tab navigation (Issue #590)
type SubTab = 'overview' | 'monitor' | 'performance' | 'load-balancing' | 'worker-registry'
const activeTab = ref<SubTab>('overview')

const tabs: { key: SubTab; label: string }[] = [
  { key: 'overview', label: 'Overview' },
  { key: 'monitor', label: 'Monitor' },
  { key: 'performance', label: 'Performance' },
  { key: 'load-balancing', label: 'Load Balancing' },
  { key: 'worker-registry', label: 'Worker Registry' },
]

// State
const loading = ref(false)
const error = ref<string | null>(null)
const selectedNpuNode = ref<SLMNode | null>(null)
const showAssignModal = ref(false)

// Computed
const npuNodes = computed(() => fleetStore.npuNodes)
const nonNpuNodes = computed(() => fleetStore.nonNpuNodes)

const totalModels = computed(() => {
  let count = 0
  for (const node of npuNodes.value) {
    const status = fleetStore.getNpuStatus(node.node_id)
    if (status?.capabilities?.models) {
      count += status.capabilities.models.length
    }
  }
  return count
})

const avgUtilization = computed(() => {
  const nodes = npuNodes.value
  if (nodes.length === 0) return 0

  let total = 0
  let counted = 0
  for (const node of nodes) {
    const status = fleetStore.getNpuStatus(node.node_id)
    if (status?.capabilities?.utilization !== undefined) {
      total += status.capabilities.utilization
      counted++
    }
  }
  return counted > 0 ? Math.round(total / counted) : 0
})

const healthyNpuNodes = computed(() => {
  return npuNodes.value.filter(n =>
    n.status === 'online' || n.status === 'healthy'
  ).length
})

// Methods
async function refreshAll(): Promise<void> {
  loading.value = true
  error.value = null

  try {
    await fleetStore.fetchNodes()
    await fleetStore.fetchNpuNodes()
    await fleetStore.fetchNpuLoadBalancing()
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Failed to refresh NPU status'
  } finally {
    loading.value = false
  }
}

function selectNode(node: SLMNode): void {
  selectedNpuNode.value = node
}

function closeDetailsPanel(): void {
  selectedNpuNode.value = null
}

async function handleRoleAssigned(): Promise<void> {
  showAssignModal.value = false
  await refreshAll()
}

// Load data on mount
onMounted(() => {
  refreshAll()
})

// Watch for node list changes
watch(() => fleetStore.nodeList, () => {
  fleetStore.fetchNpuNodes()
}, { deep: true })
</script>

<template>
  <div>
    <!-- Summary Stats -->
    <div class="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
      <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-4">
        <div class="flex items-center gap-3">
          <div class="p-2 bg-blue-100 rounded-lg">
            <svg class="w-5 h-5 text-blue-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 3v2m6-2v2M9 19v2m6-2v2M5 9H3m2 6H3m18-6h-2m2 6h-2M7 19h10a2 2 0 002-2V7a2 2 0 00-2-2H7a2 2 0 00-2 2v10a2 2 0 002 2zM9 9h6v6H9V9z" />
            </svg>
          </div>
          <div>
            <p class="text-sm text-gray-500">NPU Nodes</p>
            <p class="text-2xl font-semibold text-gray-900">{{ npuNodes.length }}</p>
          </div>
        </div>
      </div>

      <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-4">
        <div class="flex items-center gap-3">
          <div class="p-2 bg-green-100 rounded-lg">
            <svg class="w-5 h-5 text-green-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          </div>
          <div>
            <p class="text-sm text-gray-500">Healthy</p>
            <p class="text-2xl font-semibold text-gray-900">{{ healthyNpuNodes }}</p>
          </div>
        </div>
      </div>

      <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-4">
        <div class="flex items-center gap-3">
          <div class="p-2 bg-purple-100 rounded-lg">
            <svg class="w-5 h-5 text-purple-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19.428 15.428a2 2 0 00-1.022-.547l-2.387-.477a6 6 0 00-3.86.517l-.318.158a6 6 0 01-3.86.517L6.05 15.21a2 2 0 00-1.806.547M8 4h8l-1 1v5.172a2 2 0 00.586 1.414l5 5c1.26 1.26.367 3.414-1.415 3.414H4.828c-1.782 0-2.674-2.154-1.414-3.414l5-5A2 2 0 009 10.172V5L8 4z" />
            </svg>
          </div>
          <div>
            <p class="text-sm text-gray-500">Total Models</p>
            <p class="text-2xl font-semibold text-gray-900">{{ totalModels }}</p>
          </div>
        </div>
      </div>

      <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-4">
        <div class="flex items-center gap-3">
          <div class="p-2 bg-orange-100 rounded-lg">
            <svg class="w-5 h-5 text-orange-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z" />
            </svg>
          </div>
          <div>
            <p class="text-sm text-gray-500">Avg Utilization</p>
            <p class="text-2xl font-semibold text-gray-900">{{ avgUtilization }}%</p>
          </div>
        </div>
      </div>
    </div>

    <!-- Sub-Tab Navigation (Issue #590) -->
    <div class="flex items-center justify-between mb-6">
      <div class="flex border-b border-gray-200">
        <button
          v-for="tab in tabs"
          :key="tab.key"
          @click="activeTab = tab.key"
          :class="[
            'px-4 py-2 text-sm font-medium border-b-2 transition-colors -mb-px',
            activeTab === tab.key
              ? 'border-primary-600 text-primary-600'
              : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300',
          ]"
        >
          {{ tab.label }}
        </button>
      </div>

      <div class="flex items-center gap-3">
        <button
          v-if="activeTab === 'overview'"
          @click="showAssignModal = true"
          :disabled="nonNpuNodes.length === 0"
          class="px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2 text-sm"
        >
          <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4" />
          </svg>
          Assign NPU Role
        </button>

        <button
          @click="refreshAll"
          :disabled="loading"
          class="px-4 py-2 bg-white border border-gray-300 text-gray-700 rounded-lg hover:bg-gray-50 transition-colors flex items-center gap-2 text-sm"
        >
          <svg
            :class="['w-4 h-4', loading ? 'animate-spin' : '']"
            fill="none" stroke="currentColor" viewBox="0 0 24 24"
          >
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
          </svg>
          {{ loading ? 'Refreshing...' : 'Refresh' }}
        </button>
      </div>
    </div>

    <!-- Error Message -->
    <div v-if="error" class="mb-6 p-4 bg-red-50 border border-red-200 rounded-lg text-red-700">
      {{ error }}
    </div>

    <!-- Tab Content -->

    <!-- Overview Tab (original content) -->
    <template v-if="activeTab === 'overview'">
      <!-- Empty State -->
      <div v-if="npuNodes.length === 0 && !loading" class="bg-white rounded-lg shadow-sm border border-gray-200 p-12 text-center">
        <div class="mx-auto w-16 h-16 bg-gray-100 rounded-full flex items-center justify-center mb-4">
          <svg class="w-8 h-8 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 3v2m6-2v2M9 19v2m6-2v2M5 9H3m2 6H3m18-6h-2m2 6h-2M7 19h10a2 2 0 002-2V7a2 2 0 00-2-2H7a2 2 0 00-2 2v10a2 2 0 002 2zM9 9h6v6H9V9z" />
          </svg>
        </div>
        <h3 class="text-lg font-medium text-gray-900 mb-2">No NPU Workers</h3>
        <p class="text-gray-500 mb-4">
          Assign the NPU Worker role to a node to enable hardware-accelerated AI inference.
        </p>
        <button
          @click="showAssignModal = true"
          :disabled="nonNpuNodes.length === 0"
          class="px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition-colors disabled:opacity-50"
        >
          Assign NPU Role
        </button>
      </div>

      <!-- NPU Nodes Grid -->
      <div v-else class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        <NPUNodeCard
          v-for="node in npuNodes"
          :key="node.node_id"
          :node="node"
          :npu-status="fleetStore.getNpuStatus(node.node_id)"
          @select="selectNode(node)"
        />
      </div>
    </template>

    <!-- Monitor Tab (Issue #590) -->
    <NPUWorkerMonitor
      v-if="activeTab === 'monitor'"
      @select-node="selectNode"
    />

    <!-- Performance Tab (Issue #590) -->
    <NPUPerformanceMetrics v-if="activeTab === 'performance'" />

    <!-- Load Balancing Tab (Issue #590) -->
    <LoadBalancingView v-if="activeTab === 'load-balancing'" />

    <!-- Worker Registry Tab — CRUD + Windows pairing (consolidated from Settings) -->
    <NPUWorkersSettings v-if="activeTab === 'worker-registry'" />

    <!-- Details Panel (shared across tabs) -->
    <NPUDetailsPanel
      v-if="selectedNpuNode"
      :node="selectedNpuNode"
      :npu-status="fleetStore.getNpuStatus(selectedNpuNode.node_id)"
      @close="closeDetailsPanel"
      @refresh="refreshAll"
    />

    <!-- Assign Role Modal -->
    <AssignNPURoleModal
      v-model:visible="showAssignModal"
      :available-nodes="nonNpuNodes"
      @assigned="handleRoleAssigned"
    />
  </div>
</template>
