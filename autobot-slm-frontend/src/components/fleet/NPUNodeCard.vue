// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

<script setup lang="ts">
/**
 * NPUNodeCard - Displays an individual NPU worker node
 *
 * Shows node status, device type, loaded models, and utilization.
 *
 * Related to Issue #255 (NPU Fleet Integration).
 */

import { computed } from 'vue'
import type { SLMNode, NPUNodeStatus } from '@/types/slm'

const props = defineProps<{
  node: SLMNode
  npuStatus?: NPUNodeStatus
}>()

const emit = defineEmits<{
  select: []
}>()

const statusColor = computed(() => {
  switch (props.node.status) {
    case 'online':
    case 'healthy':
      return 'bg-green-100 text-green-800'
    case 'degraded':
      return 'bg-yellow-100 text-yellow-800'
    case 'offline':
    case 'error':
    case 'unhealthy':
      return 'bg-red-100 text-red-800'
    default:
      return 'bg-gray-100 text-gray-800'
  }
})

const deviceTypeLabel = computed(() => {
  if (!props.npuStatus?.capabilities?.deviceType) return 'Unknown'
  switch (props.npuStatus.capabilities.deviceType) {
    case 'intel-npu':
      return 'Intel NPU'
    case 'nvidia-gpu':
      return 'NVIDIA GPU'
    case 'amd-gpu':
      return 'AMD GPU'
    default:
      return props.npuStatus.capabilities.deviceType
  }
})

const deviceTypeColor = computed(() => {
  if (!props.npuStatus?.capabilities?.deviceType) return 'bg-gray-100 text-gray-600'
  switch (props.npuStatus.capabilities.deviceType) {
    case 'intel-npu':
      return 'bg-blue-100 text-blue-700'
    case 'nvidia-gpu':
      return 'bg-green-100 text-green-700'
    case 'amd-gpu':
      return 'bg-red-100 text-red-700'
    default:
      return 'bg-gray-100 text-gray-600'
  }
})

const utilizationColor = computed(() => {
  const util = props.npuStatus?.capabilities?.utilization ?? 0
  if (util >= 80) return 'bg-red-500'
  if (util >= 60) return 'bg-yellow-500'
  return 'bg-green-500'
})

const modelsCount = computed(() => {
  return props.npuStatus?.capabilities?.models?.length ?? 0
})

const loadedModelsCount = computed(() => {
  return props.npuStatus?.loadedModels?.length ?? 0
})

const utilization = computed(() => {
  return props.npuStatus?.capabilities?.utilization ?? 0
})

const detectionStatus = computed(() => {
  if (!props.npuStatus) return 'pending'
  return props.npuStatus.detectionStatus
})
</script>

<template>
  <div
    @click="emit('select')"
    class="bg-white rounded-lg shadow-sm border border-gray-200 p-4 cursor-pointer hover:shadow-md hover:border-primary-300 transition-all"
  >
    <!-- Header -->
    <div class="flex items-start justify-between mb-3">
      <div>
        <h3 class="font-medium text-gray-900">{{ node.hostname }}</h3>
        <p class="text-sm text-gray-500">{{ node.ip_address }}</p>
      </div>
      <span :class="['px-2 py-1 rounded-full text-xs font-medium', statusColor]">
        {{ node.status }}
      </span>
    </div>

    <!-- Device Type Badge -->
    <div class="mb-3">
      <span :class="['px-2 py-1 rounded text-xs font-medium', deviceTypeColor]">
        {{ deviceTypeLabel }}
      </span>
      <span
        v-if="detectionStatus === 'pending'"
        class="ml-2 px-2 py-1 rounded text-xs font-medium bg-yellow-100 text-yellow-700"
      >
        Detecting...
      </span>
      <span
        v-else-if="detectionStatus === 'failed'"
        class="ml-2 px-2 py-1 rounded text-xs font-medium bg-red-100 text-red-700"
      >
        Detection Failed
      </span>
    </div>

    <!-- Stats -->
    <div class="grid grid-cols-2 gap-3 mb-3">
      <div class="text-center p-2 bg-gray-50 rounded">
        <p class="text-lg font-semibold text-gray-900">{{ loadedModelsCount }}/{{ modelsCount }}</p>
        <p class="text-xs text-gray-500">Models Loaded</p>
      </div>
      <div class="text-center p-2 bg-gray-50 rounded">
        <p class="text-lg font-semibold text-gray-900">{{ npuStatus?.queueDepth ?? 0 }}</p>
        <p class="text-xs text-gray-500">Queue Depth</p>
      </div>
    </div>

    <!-- Utilization Bar -->
    <div>
      <div class="flex items-center justify-between text-xs text-gray-500 mb-1">
        <span>Utilization</span>
        <span>{{ utilization }}%</span>
      </div>
      <div class="w-full h-2 bg-gray-200 rounded-full overflow-hidden">
        <div
          :class="['h-full transition-all', utilizationColor]"
          :style="{ width: `${utilization}%` }"
        />
      </div>
    </div>

    <!-- Memory Info -->
    <div v-if="npuStatus?.capabilities?.memoryGB" class="mt-3 text-xs text-gray-500">
      {{ npuStatus.capabilities.memoryGB }} GB Memory |
      Max {{ npuStatus.capabilities.maxConcurrent }} concurrent
    </div>
  </div>
</template>
