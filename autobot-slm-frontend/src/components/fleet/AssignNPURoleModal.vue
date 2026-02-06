// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

<script setup lang="ts">
/**
 * AssignNPURoleModal - Modal for assigning NPU Worker role to nodes
 *
 * Allows selecting a node and assigning the npu-worker role with auto-detection.
 *
 * Related to Issue #255 (NPU Fleet Integration).
 */

import { ref, computed } from 'vue'
import { useFleetStore } from '@/stores/fleet'
import type { SLMNode } from '@/types/slm'

const props = defineProps<{
  visible: boolean
  availableNodes: SLMNode[]
}>()

const emit = defineEmits<{
  'update:visible': [value: boolean]
  assigned: []
}>()

const fleetStore = useFleetStore()
const selectedNodeId = ref<string>('')
const loading = ref(false)
const error = ref<string | null>(null)

const selectedNode = computed(() => {
  if (!selectedNodeId.value) return null
  return props.availableNodes.find(n => n.node_id === selectedNodeId.value) || null
})

const eligibleNodes = computed(() => {
  // Filter to nodes that are online and don't already have npu-worker role
  return props.availableNodes.filter(n =>
    (n.status === 'online' || n.status === 'healthy') &&
    !n.roles.includes('npu-worker')
  )
})

function close(): void {
  emit('update:visible', false)
  selectedNodeId.value = ''
  error.value = null
}

async function assignRole(): Promise<void> {
  if (!selectedNodeId.value) {
    error.value = 'Please select a node'
    return
  }

  loading.value = true
  error.value = null

  try {
    await fleetStore.assignNpuRole(selectedNodeId.value)
    emit('assigned')
    close()
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Failed to assign NPU role'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div v-if="visible" class="fixed inset-0 z-50 overflow-y-auto">
    <!-- Backdrop -->
    <div
      class="fixed inset-0 bg-gray-500 bg-opacity-50 transition-opacity"
      @click="close"
    />

    <!-- Modal -->
    <div class="flex min-h-full items-center justify-center p-4">
      <div class="relative bg-white rounded-lg shadow-xl max-w-md w-full">
        <!-- Header -->
        <div class="px-6 py-4 border-b border-gray-200">
          <h2 class="text-lg font-semibold text-gray-900">Assign NPU Worker Role</h2>
          <p class="text-sm text-gray-500 mt-1">
            Select a node to enable NPU acceleration capabilities
          </p>
        </div>

        <!-- Content -->
        <div class="p-6 space-y-4">
          <!-- Error Message -->
          <div v-if="error" class="p-4 bg-red-50 border border-red-200 rounded-lg text-red-700">
            {{ error }}
          </div>

          <!-- Node Selection -->
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-2">
              Select Node
            </label>
            <select
              v-model="selectedNodeId"
              class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
            >
              <option value="">-- Select a node --</option>
              <option
                v-for="node in eligibleNodes"
                :key="node.node_id"
                :value="node.node_id"
              >
                {{ node.hostname }} ({{ node.ip_address }})
              </option>
            </select>
          </div>

          <!-- Selected Node Info -->
          <div v-if="selectedNode" class="bg-gray-50 rounded-lg p-4">
            <h4 class="text-sm font-medium text-gray-700 mb-2">Node Details</h4>
            <dl class="space-y-1 text-sm">
              <div class="flex justify-between">
                <dt class="text-gray-500">Hostname</dt>
                <dd class="text-gray-900">{{ selectedNode.hostname }}</dd>
              </div>
              <div class="flex justify-between">
                <dt class="text-gray-500">IP Address</dt>
                <dd class="text-gray-900">{{ selectedNode.ip_address }}</dd>
              </div>
              <div class="flex justify-between">
                <dt class="text-gray-500">Status</dt>
                <dd class="text-gray-900">{{ selectedNode.status }}</dd>
              </div>
              <div class="flex justify-between">
                <dt class="text-gray-500">Current Roles</dt>
                <dd class="text-gray-900">
                  {{ selectedNode.roles.length > 0 ? selectedNode.roles.join(', ') : 'None' }}
                </dd>
              </div>
            </dl>
          </div>

          <!-- Info Box -->
          <div class="flex items-start gap-3 p-4 bg-blue-50 rounded-lg">
            <svg class="w-5 h-5 text-blue-600 flex-shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            <div class="text-sm text-blue-700">
              <p class="font-medium">Auto-Detection</p>
              <p class="mt-1">
                After assigning the role, the system will automatically detect NPU capabilities
                including device type, available models, and memory capacity.
              </p>
            </div>
          </div>

          <!-- No Eligible Nodes Warning -->
          <div v-if="eligibleNodes.length === 0" class="flex items-start gap-3 p-4 bg-yellow-50 rounded-lg">
            <svg class="w-5 h-5 text-yellow-600 flex-shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
            <div class="text-sm text-yellow-700">
              <p class="font-medium">No Eligible Nodes</p>
              <p class="mt-1">
                All available nodes either already have the NPU Worker role or are offline.
                Ensure nodes are online before assigning roles.
              </p>
            </div>
          </div>
        </div>

        <!-- Footer -->
        <div class="px-6 py-4 border-t border-gray-200 flex items-center justify-end gap-3">
          <button
            @click="close"
            class="px-4 py-2 text-gray-700 hover:bg-gray-100 rounded-lg transition-colors"
          >
            Cancel
          </button>
          <button
            @click="assignRole"
            :disabled="loading || !selectedNodeId"
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
            {{ loading ? 'Assigning...' : 'Assign NPU Role' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
