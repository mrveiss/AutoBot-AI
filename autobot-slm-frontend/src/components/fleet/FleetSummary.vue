<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

import { computed } from 'vue'
import { useFleetStore } from '@/stores/fleet'

const fleetStore = useFleetStore()
const summary = computed(() => fleetStore.fleetSummary)

const stats = computed(() => [
  {
    label: 'Total Nodes',
    value: summary.value.total_nodes,
    icon: 'server',
    color: 'text-gray-600',
    bgColor: 'bg-gray-100',
  },
  {
    label: 'Healthy',
    value: summary.value.healthy_nodes,
    icon: 'check',
    color: 'text-success-600',
    bgColor: 'bg-green-100',
  },
  {
    label: 'Degraded',
    value: summary.value.degraded_nodes,
    icon: 'warning',
    color: 'text-warning-600',
    bgColor: 'bg-yellow-100',
  },
  {
    label: 'Unhealthy',
    value: summary.value.unhealthy_nodes,
    icon: 'error',
    color: 'text-danger-600',
    bgColor: 'bg-red-100',
  },
  {
    label: 'Need Updates',
    value: fleetStore.nodesNeedingUpdates,
    icon: 'update',
    color: 'text-amber-600',
    bgColor: 'bg-amber-100',
  },
])
</script>

<template>
  <div class="grid grid-cols-2 md:grid-cols-5 gap-4">
    <div
      v-for="stat in stats"
      :key="stat.label"
      class="card p-4"
    >
      <div class="flex items-center gap-3">
        <div :class="['p-2 rounded-lg', stat.bgColor]">
          <!-- Server icon -->
          <svg v-if="stat.icon === 'server'" :class="['w-5 h-5', stat.color]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 12h14M5 12a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v4a2 2 0 01-2 2M5 12a2 2 0 00-2 2v4a2 2 0 002 2h14a2 2 0 002-2v-4a2 2 0 00-2-2m-2-4h.01M17 16h.01" />
          </svg>
          <!-- Check icon -->
          <svg v-else-if="stat.icon === 'check'" :class="['w-5 h-5', stat.color]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          <!-- Warning icon -->
          <svg v-else-if="stat.icon === 'warning'" :class="['w-5 h-5', stat.color]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
          </svg>
          <!-- Error icon -->
          <svg v-else-if="stat.icon === 'error'" :class="['w-5 h-5', stat.color]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 14l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2m7-2a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          <!-- Update icon (#682) -->
          <svg v-else-if="stat.icon === 'update'" :class="['w-5 h-5', stat.color]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
          </svg>
        </div>
        <div>
          <p class="text-2xl font-bold text-gray-900">{{ stat.value }}</p>
          <p class="text-sm text-gray-500">{{ stat.label }}</p>
        </div>
      </div>
    </div>
  </div>
</template>
