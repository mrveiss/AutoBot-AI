<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

import { computed } from 'vue'
import { useFleetStore } from '@/stores/fleet'
import NodeCard from '@/components/fleet/NodeCard.vue'
import FleetSummary from '@/components/fleet/FleetSummary.vue'

const fleetStore = useFleetStore()

const nodes = computed(() => fleetStore.nodeList)
const isLoading = computed(() => fleetStore.isLoading)

async function refreshFleet(): Promise<void> {
  await fleetStore.fetchNodes()
}
</script>

<template>
  <div class="p-6">
    <!-- Header -->
    <div class="flex items-center justify-between mb-6">
      <div>
        <h1 class="text-2xl font-bold text-gray-900">Fleet Overview</h1>
        <p class="text-sm text-gray-500 mt-1">
          Real-time health status of all managed nodes
        </p>
      </div>
      <button
        @click="refreshFleet"
        :disabled="isLoading"
        class="btn btn-primary flex items-center gap-2"
      >
        <svg
          :class="['w-4 h-4', isLoading ? 'animate-spin' : '']"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            stroke-linecap="round"
            stroke-linejoin="round"
            stroke-width="2"
            d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
          />
        </svg>
        Refresh
      </button>
    </div>

    <!-- Fleet Summary -->
    <FleetSummary class="mb-6" />

    <!-- Node Grid -->
    <div v-if="nodes.length > 0" class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
      <NodeCard
        v-for="node in nodes"
        :key="node.node_id"
        :node="node"
      />
    </div>

    <!-- Empty State -->
    <div v-else-if="!isLoading" class="card p-12 text-center">
      <svg class="w-16 h-16 mx-auto text-gray-400 mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 12h14M5 12a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v4a2 2 0 01-2 2M5 12a2 2 0 00-2 2v4a2 2 0 002 2h14a2 2 0 002-2v-4a2 2 0 00-2-2m-2-4h.01M17 16h.01" />
      </svg>
      <h3 class="text-lg font-medium text-gray-900 mb-2">No nodes registered</h3>
      <p class="text-gray-500 mb-4">
        Deploy an SLM agent to start managing your infrastructure.
      </p>
      <button
        @click="$router.push('/deployments')"
        class="btn btn-primary"
      >
        Go to Deployments
      </button>
    </div>

    <!-- Loading State -->
    <div v-if="isLoading" class="flex items-center justify-center py-12">
      <div class="animate-spin w-8 h-8 border-4 border-primary-600 border-t-transparent rounded-full"></div>
    </div>
  </div>
</template>
