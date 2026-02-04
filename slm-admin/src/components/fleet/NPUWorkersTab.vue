// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

<script setup lang="ts">
/**
 * NPUWorkersTab - NPU Workers management as a Fleet tab
 *
 * Provides NPU worker management, status monitoring, and load balancing configuration.
 * NPU workers are fleet nodes with the 'npu-worker' role.
 *
 * Related to Issue #255 (Service Authentication) and Issue #729 (Layer Separation).
 */

import { ref, computed, onMounted, watch } from 'vue'
import { useFleetStore } from '@/stores/fleet'
import NPUNodeCard from './NPUNodeCard.vue'
import NPUDetailsPanel from './NPUDetailsPanel.vue'
import AssignNPURoleModal from './AssignNPURoleModal.vue'
import type { SLMNode, NPUNodeStatus, NPULoadBalancingStrategy } from '@/types/slm'

const fleetStore = useFleetStore()

// State
const loading = ref(false)
const error = ref<string | null>(null)
const selectedNpuNode = ref<SLMNode | null>(null)
const showAssignModal = ref(false)
const showLoadBalancingConfig = ref(false)

// Load balancing configuration
const loadBalancingStrategy = ref<NPULoadBalancingStrategy>('round-robin')

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
    await fleetStore.fetchAllNpuStatus()
    await fleetStore.fetchNpuLoadBalancing()

    if (fleetStore.npuLoadBalancingConfig) {
      loadBalancingStrategy.value = fleetStore.npuLoadBalancingConfig.strategy
    }
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

async function updateLoadBalancing(): Promise<void> {
  try {
    await fleetStore.updateNpuLoadBalancing({
      strategy: loadBalancingStrategy.value,
      modelAffinity: fleetStore.npuLoadBalancingConfig?.modelAffinity || {},
    })
    showLoadBalancingConfig.value = false
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Failed to update load balancing'
  }
}

// Load data on mount
onMounted(() => {
  refreshAll()
})

// Watch for node list changes
watch(() => fleetStore.nodeList, () => {
  // Refresh NPU status when node list changes
  fleetStore.fetchAllNpuStatus()
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

    <!-- Actions Bar -->
    <div class="flex items-center justify-between mb-6">
      <div class="flex items-center gap-3">
        <button
          @click="showAssignModal = true"
          :disabled="nonNpuNodes.length === 0"
          class="px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
        >
          <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4" />
          </svg>
          Assign NPU Role
        </button>

        <button
          @click="showLoadBalancingConfig = !showLoadBalancingConfig"
          class="px-4 py-2 bg-white border border-gray-300 text-gray-700 rounded-lg hover:bg-gray-50 transition-colors flex items-center gap-2"
        >
          <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
          </svg>
          Load Balancing
        </button>
      </div>

      <button
        @click="refreshAll"
        :disabled="loading"
        class="px-4 py-2 bg-white border border-gray-300 text-gray-700 rounded-lg hover:bg-gray-50 transition-colors flex items-center gap-2"
      >
        <svg
          :class="['w-4 h-4', loading ? 'animate-spin' : '']"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
        </svg>
        {{ loading ? 'Refreshing...' : 'Refresh All' }}
      </button>
    </div>

    <!-- Load Balancing Config Panel -->
    <div v-if="showLoadBalancingConfig" class="bg-white rounded-lg shadow-sm border border-gray-200 p-6 mb-6">
      <h3 class="text-lg font-semibold text-gray-900 mb-4">Load Balancing Configuration</h3>
      <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div>
          <label class="block text-sm font-medium text-gray-700 mb-2">Strategy</label>
          <select
            v-model="loadBalancingStrategy"
            class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
          >
            <option value="round-robin">Round Robin</option>
            <option value="least-loaded">Least Loaded</option>
            <option value="model-affinity">Model Affinity</option>
          </select>
          <p class="text-xs text-gray-500 mt-1">
            <template v-if="loadBalancingStrategy === 'round-robin'">
              Distribute requests evenly across all NPU nodes
            </template>
            <template v-else-if="loadBalancingStrategy === 'least-loaded'">
              Route requests to the node with lowest utilization
            </template>
            <template v-else>
              Route requests based on which node has the model loaded
            </template>
          </p>
        </div>
        <div class="flex items-end">
          <button
            @click="updateLoadBalancing"
            class="px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition-colors"
          >
            Save Configuration
          </button>
        </div>
      </div>
    </div>

    <!-- Error Message -->
    <div v-if="error" class="mb-6 p-4 bg-red-50 border border-red-200 rounded-lg text-red-700">
      {{ error }}
    </div>

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

    <!-- Details Panel -->
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
