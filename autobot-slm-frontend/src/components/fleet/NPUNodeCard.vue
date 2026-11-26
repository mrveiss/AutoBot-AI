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
      return 'bg-autobot-pill-ok-bg text-autobot-pill-ok-fg'
    case 'degraded':
      return 'bg-autobot-pill-warn-bg text-autobot-pill-warn-fg'
    case 'offline':
    case 'error':
      return 'bg-autobot-pill-bad-bg text-autobot-pill-bad-fg'
    default:
      return 'bg-autobot-bg-tertiary text-autobot-text-primary'
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
  if (!props.npuStatus?.capabilities?.deviceType) return 'bg-autobot-bg-tertiary text-autobot-text-secondary'
  switch (props.npuStatus.capabilities.deviceType) {
    case 'intel-npu':
      return 'bg-autobot-pill-info-bg text-autobot-pill-info-fg'
    case 'nvidia-gpu':
      return 'bg-autobot-pill-ok-bg text-autobot-pill-ok-fg'
    case 'amd-gpu':
      return 'bg-autobot-pill-bad-bg text-autobot-pill-bad-fg'
    default:
      return 'bg-autobot-bg-tertiary text-autobot-text-secondary'
  }
})

const utilizationColor = computed(() => {
  const util = props.npuStatus?.capabilities?.utilization ?? 0
  if (util >= 80) return 'bg-autobot-dot-bad'
  if (util >= 60) return 'bg-autobot-dot-warn'
  return 'bg-autobot-dot-ok'
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
    class="bg-white rounded-lg shadow-xs border border-autobot-border p-4 cursor-pointer hover:shadow-md hover:border-primary-300 transition-all"
  >
    <!-- Header -->
    <div class="flex items-start justify-between mb-3">
      <div>
        <h3 class="font-medium text-autobot-text-primary">{{ node.hostname }}</h3>
        <p class="text-sm text-autobot-text-tertiary">{{ node.ip_address }}</p>
      </div>
      <span :class="['px-2 py-1 rounded-full text-xs font-medium', statusColor]">
        {{ node.status }}
      </span>
    </div>

    <!-- Device Type Badge -->
    <div class="mb-3">
      <span :class="['px-2 py-1 rounded-sm text-xs font-medium', deviceTypeColor]">
        {{ deviceTypeLabel }}
      </span>
      <span
        v-if="detectionStatus === 'pending'"
        class="ml-2 px-2 py-1 rounded-sm text-xs font-medium bg-autobot-pill-warn-bg text-autobot-pill-warn-fg"
      >
        {{ $t('fleet.nPUNodeCard.detecting') }}
      </span>
      <span
        v-else-if="detectionStatus === 'failed'"
        class="ml-2 px-2 py-1 rounded-sm text-xs font-medium bg-autobot-pill-bad-bg text-autobot-pill-bad-fg"
      >
        {{ $t('fleet.nPUNodeCard.detectionFailed') }}
      </span>
    </div>

    <!-- Stats -->
    <div class="grid grid-cols-2 gap-3 mb-3">
      <div class="text-center p-2 bg-autobot-bg-secondary rounded-sm">
        <p class="text-lg font-semibold text-autobot-text-primary">{{ loadedModelsCount }}/{{ modelsCount }}</p>
        <p class="text-xs text-autobot-text-tertiary">{{ $t('fleet.nPUNodeCard.modelsLoaded') }}</p>
      </div>
      <div class="text-center p-2 bg-autobot-bg-secondary rounded-sm">
        <p class="text-lg font-semibold text-autobot-text-primary">{{ npuStatus?.queueDepth ?? 0 }}</p>
        <p class="text-xs text-autobot-text-tertiary">{{ $t('fleet.nPUNodeCard.queueDepth') }}</p>
      </div>
    </div>

    <!-- Utilization Bar -->
    <div>
      <div class="flex items-center justify-between text-xs text-autobot-text-tertiary mb-1">
        <span>{{ $t('fleet.nPUNodeCard.utilization') }}</span>
        <span>{{ utilization }}%</span>
      </div>
      <div class="w-full h-2 bg-autobot-bg-active rounded-full overflow-hidden">
        <div
          :class="['h-full transition-all', utilizationColor]"
          :style="{ width: `${utilization}%` }"
        />
      </div>
    </div>

    <!-- Memory Info -->
    <div v-if="npuStatus?.capabilities?.memoryGB" class="mt-3 text-xs text-autobot-text-tertiary">{{ $t('fleet.nPUNodeCard.value0GBMemoryMaxValue1Concurrent', { value0: npuStatus.capabilities.memoryGB, value1: npuStatus.capabilities.maxConcurrent }) }}</div>
  </div>
</template>
