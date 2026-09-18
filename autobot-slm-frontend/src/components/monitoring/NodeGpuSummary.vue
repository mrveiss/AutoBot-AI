<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * NodeGpuSummary - one node's GPUs from its latest heartbeat (#15226)
 *
 * Each state reads differently, and none of them renders as a measured zero:
 * - not reported: the node's agent predates GPU telemetry (#16280)
 * - none: the agent probed and found no GPU
 * - present, not monitored: the card is visible but its vendor tool could not read it
 * - measured: the first measured GPU's utilisation and VRAM, plus a count of the rest
 * and "unavailable" when the fleet's GPU read itself failed.
 */

import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import type { GPUNodeStatus } from '@/types/slm'

interface Props {
  status?: GPUNodeStatus
  unavailable?: boolean
}

const props = defineProps<Props>()
const { t } = useI18n()

const MB_PER_GB = 1024

function percent(value: number | null | undefined): string {
  return value == null ? t('monitoring.systemMonitor.gpuUnreadable') : `${Math.round(value)}%`
}

function tone(value: number | null | undefined): string {
  if (value == null) return 'text-gray-500'
  if (value >= 90) return 'text-danger-600'
  if (value >= 70) return 'text-warning-600'
  return 'text-success-600'
}

const summary = computed(() => {
  if (props.unavailable) return { text: t('monitoring.systemMonitor.gpuUnavailable'), tone: 'text-gray-400' }
  const status = props.status
  if (!status || status.state === 'not_reported') {
    return { text: t('monitoring.systemMonitor.gpuNotReported'), tone: 'text-gray-400' }
  }
  if (status.state === 'none') return { text: t('monitoring.systemMonitor.gpuNone'), tone: 'text-gray-500' }

  // The generated type marks devices optional (the schema gives it a default).
  const devices = status.devices ?? []
  const first = devices.find((device) => device.monitored)
  if (!first) {
    return {
      text: t('monitoring.systemMonitor.gpuUnmonitored', { count: devices.length }),
      tone: 'text-warning-600',
    }
  }
  const parts = [
    t('monitoring.systemMonitor.gpuMeasured', {
      name: first.name ?? first.device_type,
      utilization: percent(first.utilization_percent),
    }),
  ]
  if (first.memory_used_mb != null && first.memory_total_mb) {
    parts.push(
      t('monitoring.systemMonitor.gpuMemory', {
        used: (first.memory_used_mb / MB_PER_GB).toFixed(1),
        total: (first.memory_total_mb / MB_PER_GB).toFixed(1),
      }),
    )
  }
  if (devices.length > 1) {
    parts.push(t('monitoring.systemMonitor.gpuMore', { count: devices.length - 1 }))
  }
  return { text: parts.join(' · '), tone: tone(first.utilization_percent) }
})
</script>

<template>
  <div class="flex justify-between text-sm">
    <span class="text-gray-600">{{ t('monitoring.systemMonitor.gpu') }}</span>
    <span :class="summary.tone" data-testid="node-gpu-summary">{{ summary.text }}</span>
  </div>
</template>
