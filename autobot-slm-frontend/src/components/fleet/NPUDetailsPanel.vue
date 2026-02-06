// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

<script setup lang="ts">
/**
 * NPUDetailsPanel - Slide-out panel for NPU node details
 *
 * Shows full model list, performance metrics, and management actions.
 *
 * Related to Issue #255 (NPU Fleet Integration).
 */

import { ref, computed } from 'vue'
import { useFleetStore } from '@/stores/fleet'
import type { SLMNode, NPUNodeStatus } from '@/types/slm'

const props = defineProps<{
  node: SLMNode
  npuStatus?: NPUNodeStatus
}>()

const emit = defineEmits<{
  close: []
  refresh: []
}>()

const fleetStore = useFleetStore()
const loading = ref(false)
const error = ref<string | null>(null)

const deviceTypeLabel = computed(() => {
  if (!props.npuStatus?.capabilities?.deviceType) return 'Unknown Device'
  switch (props.npuStatus.capabilities.deviceType) {
    case 'intel-npu':
      return 'Intel Neural Processing Unit'
    case 'nvidia-gpu':
      return 'NVIDIA Graphics Processing Unit'
    case 'amd-gpu':
      return 'AMD Graphics Processing Unit'
    default:
      return props.npuStatus.capabilities.deviceType
  }
})

const lastHealthCheck = computed(() => {
  if (!props.npuStatus?.lastHealthCheck) return 'Never'
  return new Date(props.npuStatus.lastHealthCheck).toLocaleString()
})

const availableModels = computed(() => {
  return props.npuStatus?.capabilities?.models ?? []
})

const loadedModels = computed(() => {
  return props.npuStatus?.loadedModels ?? []
})

async function removeNpuRole(): Promise<void> {
  if (!confirm(`Remove NPU Worker role from ${props.node.hostname}?`)) {
    return
  }

  loading.value = true
  error.value = null

  try {
    await fleetStore.removeNpuRole(props.node.node_id)
    emit('close')
    emit('refresh')
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Failed to remove NPU role'
  } finally {
    loading.value = false
  }
}

async function refreshStatus(): Promise<void> {
  loading.value = true
  error.value = null

  try {
    await fleetStore.fetchNpuStatus(props.node.node_id)
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Failed to refresh NPU status'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="fixed inset-0 z-50 overflow-hidden">
    <!-- Backdrop -->
    <div
      class="absolute inset-0 bg-gray-500 bg-opacity-50 transition-opacity"
      @click="emit('close')"
    />

    <!-- Panel -->
    <div class="absolute inset-y-0 right-0 max-w-lg w-full bg-white shadow-xl">
      <div class="h-full flex flex-col">
        <!-- Header -->
        <div class="px-6 py-4 border-b border-gray-200 flex items-center justify-between">
          <div>
            <h2 class="text-lg font-semibold text-gray-900">{{ node.hostname }}</h2>
            <p class="text-sm text-gray-500">{{ node.ip_address }}</p>
          </div>
          <button
            @click="emit('close')"
            class="p-2 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-lg transition-colors"
          >
            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <!-- Content -->
        <div class="flex-1 overflow-y-auto p-6 space-y-6">
          <!-- Error Message -->
          <div v-if="error" class="p-4 bg-red-50 border border-red-200 rounded-lg text-red-700">
            {{ error }}
          </div>

          <!-- Device Info -->
          <div class="bg-gray-50 rounded-lg p-4">
            <h3 class="text-sm font-medium text-gray-700 mb-3">Device Information</h3>
            <dl class="space-y-2">
              <div class="flex justify-between">
                <dt class="text-sm text-gray-500">Device Type</dt>
                <dd class="text-sm font-medium text-gray-900">{{ deviceTypeLabel }}</dd>
              </div>
              <div class="flex justify-between">
                <dt class="text-sm text-gray-500">Memory</dt>
                <dd class="text-sm font-medium text-gray-900">
                  {{ npuStatus?.capabilities?.memoryGB ?? 'N/A' }} GB
                </dd>
              </div>
              <div class="flex justify-between">
                <dt class="text-sm text-gray-500">Max Concurrent</dt>
                <dd class="text-sm font-medium text-gray-900">
                  {{ npuStatus?.capabilities?.maxConcurrent ?? 'N/A' }}
                </dd>
              </div>
              <div class="flex justify-between">
                <dt class="text-sm text-gray-500">Last Health Check</dt>
                <dd class="text-sm font-medium text-gray-900">{{ lastHealthCheck }}</dd>
              </div>
              <div class="flex justify-between">
                <dt class="text-sm text-gray-500">Detection Status</dt>
                <dd class="text-sm font-medium">
                  <span
                    v-if="npuStatus?.detectionStatus === 'detected'"
                    class="text-green-600"
                  >
                    Detected
                  </span>
                  <span
                    v-else-if="npuStatus?.detectionStatus === 'pending'"
                    class="text-yellow-600"
                  >
                    Pending
                  </span>
                  <span
                    v-else-if="npuStatus?.detectionStatus === 'failed'"
                    class="text-red-600"
                  >
                    Failed
                  </span>
                  <span v-else class="text-gray-600">Unknown</span>
                </dd>
              </div>
            </dl>
          </div>

          <!-- Utilization -->
          <div>
            <h3 class="text-sm font-medium text-gray-700 mb-3">Current Utilization</h3>
            <div class="flex items-center gap-4">
              <div class="flex-1">
                <div class="w-full h-4 bg-gray-200 rounded-full overflow-hidden">
                  <div
                    class="h-full bg-primary-500 transition-all"
                    :style="{ width: `${npuStatus?.capabilities?.utilization ?? 0}%` }"
                  />
                </div>
              </div>
              <span class="text-lg font-semibold text-gray-900">
                {{ npuStatus?.capabilities?.utilization ?? 0 }}%
              </span>
            </div>
            <p class="text-xs text-gray-500 mt-2">
              Queue Depth: {{ npuStatus?.queueDepth ?? 0 }} requests
            </p>
          </div>

          <!-- Available Models -->
          <div>
            <h3 class="text-sm font-medium text-gray-700 mb-3">
              Available Models ({{ availableModels.length }})
            </h3>
            <div v-if="availableModels.length === 0" class="text-sm text-gray-500">
              No models detected
            </div>
            <ul v-else class="space-y-2">
              <li
                v-for="model in availableModels"
                :key="model"
                class="flex items-center justify-between p-2 bg-gray-50 rounded"
              >
                <span class="text-sm text-gray-900">{{ model }}</span>
                <span
                  v-if="loadedModels.includes(model)"
                  class="px-2 py-0.5 bg-green-100 text-green-700 text-xs rounded"
                >
                  Loaded
                </span>
                <span
                  v-else
                  class="px-2 py-0.5 bg-gray-100 text-gray-600 text-xs rounded"
                >
                  Available
                </span>
              </li>
            </ul>
          </div>

          <!-- Detection Error -->
          <div v-if="npuStatus?.detectionError" class="bg-red-50 rounded-lg p-4">
            <h3 class="text-sm font-medium text-red-700 mb-2">Detection Error</h3>
            <p class="text-sm text-red-600">{{ npuStatus.detectionError }}</p>
          </div>
        </div>

        <!-- Footer Actions -->
        <div class="px-6 py-4 border-t border-gray-200 flex items-center justify-between">
          <button
            @click="removeNpuRole"
            :disabled="loading"
            class="px-4 py-2 text-red-600 hover:bg-red-50 rounded-lg transition-colors disabled:opacity-50"
          >
            Remove NPU Role
          </button>
          <button
            @click="refreshStatus"
            :disabled="loading"
            class="px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition-colors disabled:opacity-50 flex items-center gap-2"
          >
            <svg
              v-if="loading"
              class="animate-spin w-4 h-4"
              fill="none"
              viewBox="0 0 24 24"
            >
              <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
              <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
            {{ loading ? 'Refreshing...' : 'Refresh Status' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
