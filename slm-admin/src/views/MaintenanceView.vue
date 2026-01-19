<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

import { ref, computed } from 'vue'
import { useFleetStore } from '@/stores/fleet'
import { useSlmApi } from '@/composables/useSlmApi'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('MaintenanceView')
const fleetStore = useFleetStore()
const api = useSlmApi()

const nodes = computed(() => fleetStore.nodeList)
const maintenanceNodes = computed(() => nodes.value.filter(n => n.status === 'maintenance'))

const showScheduleDialog = ref(false)
const selectedDrainNode = ref<string | null>(null)
const selectedResumeNode = ref<string | null>(null)
const isDraining = ref(false)
const isResuming = ref(false)

async function handleDrainNode(nodeId: string): Promise<void> {
  if (!confirm(`Are you sure you want to drain node ${nodeId}? This will put it in maintenance mode.`)) {
    return
  }

  isDraining.value = true
  try {
    await api.drainNode(nodeId)
    await fleetStore.fetchNodes()
    selectedDrainNode.value = null
    logger.info('Node drained successfully:', nodeId)
  } catch (err) {
    logger.error('Failed to drain node:', err)
    alert('Failed to drain node. Please try again.')
  } finally {
    isDraining.value = false
  }
}

async function handleResumeNode(nodeId: string): Promise<void> {
  isResuming.value = true
  try {
    await api.resumeNode(nodeId)
    await fleetStore.fetchNodes()
    selectedResumeNode.value = null
    logger.info('Node resumed successfully:', nodeId)
  } catch (err) {
    logger.error('Failed to resume node:', err)
    alert('Failed to resume node. Please try again.')
  } finally {
    isResuming.value = false
  }
}
</script>

<template>
  <div class="p-6">
    <!-- Header -->
    <div class="flex items-center justify-between mb-6">
      <div>
        <h1 class="text-2xl font-bold text-gray-900">Maintenance</h1>
        <p class="text-sm text-gray-500 mt-1">
          Schedule maintenance windows and manage node availability
        </p>
      </div>
      <button
        @click="showScheduleDialog = true"
        class="btn btn-primary flex items-center gap-2"
      >
        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
        </svg>
        Schedule Maintenance
      </button>
    </div>

    <!-- Quick Actions -->
    <div class="card p-6 mb-6">
      <h2 class="text-lg font-semibold mb-4">Quick Actions</h2>
      <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div class="border border-gray-200 rounded-lg p-4">
          <h3 class="font-medium text-gray-900 mb-2">Drain Node</h3>
          <p class="text-sm text-gray-500 mb-3">
            Put a node into maintenance mode, making it unavailable for new workloads.
          </p>
          <select
            v-model="selectedDrainNode"
            class="input mb-2"
            :disabled="isDraining"
          >
            <option value="">Select a node...</option>
            <option
              v-for="node in nodes.filter(n => n.status !== 'maintenance')"
              :key="node.node_id"
              :value="node.node_id"
            >
              {{ node.hostname }} ({{ node.ip_address }})
            </option>
          </select>
          <button
            @click="selectedDrainNode && handleDrainNode(selectedDrainNode)"
            :disabled="!selectedDrainNode || isDraining"
            class="btn btn-secondary w-full"
          >
            {{ isDraining ? 'Draining...' : 'Drain Node' }}
          </button>
        </div>

        <div class="border border-gray-200 rounded-lg p-4">
          <h3 class="font-medium text-gray-900 mb-2">Resume Node</h3>
          <p class="text-sm text-gray-500 mb-3">
            Return a maintenance node to active service.
          </p>
          <select
            v-model="selectedResumeNode"
            class="input mb-2"
            :disabled="isResuming"
          >
            <option value="">Select a node...</option>
            <option
              v-for="node in maintenanceNodes"
              :key="node.node_id"
              :value="node.node_id"
            >
              {{ node.hostname }} ({{ node.ip_address }})
            </option>
          </select>
          <button
            @click="selectedResumeNode && handleResumeNode(selectedResumeNode)"
            :disabled="!selectedResumeNode || isResuming"
            class="btn btn-success w-full"
          >
            {{ isResuming ? 'Resuming...' : 'Resume Node' }}
          </button>
        </div>

        <div class="border border-gray-200 rounded-lg p-4">
          <h3 class="font-medium text-gray-900 mb-2">Fleet-Wide Maintenance</h3>
          <p class="text-sm text-gray-500 mb-3">
            Schedule maintenance across all nodes with rolling updates.
          </p>
          <button
            @click="showScheduleDialog = true"
            class="btn btn-primary w-full"
          >
            Schedule Window
          </button>
        </div>
      </div>
    </div>

    <!-- Scheduled Maintenance Windows -->
    <div class="card overflow-hidden">
      <div class="px-6 py-4 border-b border-gray-200">
        <h2 class="text-lg font-semibold">Scheduled Maintenance Windows</h2>
      </div>
      <div class="p-6 text-center text-gray-500">
        No maintenance windows scheduled.
      </div>
    </div>
  </div>
</template>
