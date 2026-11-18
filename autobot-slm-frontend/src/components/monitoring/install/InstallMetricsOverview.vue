<!--
  Copyright 2025-2026 mrveiss
  SPDX-License-Identifier: Apache-2.0

  InstallMetricsOverview (#19484): the host, GPU and NPU figures of one install-metrics reading
  (InstallMetrics). Pure display. A figure is what the main backend reported or "Not reported":
  a section that failed to read, a field the route left out, and a device that is not present
  all read as not reported, never as 0.
-->
<template>
  <div class="flex flex-col gap-4">
    <BaseCard :title="t(`${NS}.system.title`)" data-testid="slm-install-system">
      <dl class="m-0 grid grid-cols-[repeat(auto-fit,minmax(11rem,1fr))] gap-4">
        <div v-for="stat in systemStats" :key="stat.key" :data-testid="`slm-install-stat-${stat.key}`">
          <dt class="text-sm text-(--aui-color-text-muted)">{{ t(`${NS}.stat.${stat.key}`) }}</dt>
          <dd class="m-0 text-lg font-semibold tabular-nums">{{ stat.value }}</dd>
        </div>
      </dl>
      <p class="m-0 mt-3 text-sm text-(--aui-color-text-muted)">{{ t(`${NS}.readAt`, { time: formatFleetDateTime(readAt) }) }}</p>
    </BaseCard>

    <div class="grid gap-4 md:grid-cols-2">
      <BaseCard :title="t(`${NS}.gpu.title`)" data-testid="slm-install-gpu">
        <p v-if="gpuAbsent" class="m-0 text-(--aui-color-text-muted)" role="status" data-testid="slm-install-gpu-absent">{{ t(`${NS}.gpu.absent`) }}</p>
        <dl v-else class="m-0 grid grid-cols-[repeat(auto-fit,minmax(9rem,1fr))] gap-4">
          <div v-for="stat in gpuStats" :key="stat.key" :data-testid="`slm-install-stat-${stat.key}`">
            <dt class="text-sm text-(--aui-color-text-muted)">{{ t(`${NS}.stat.${stat.key}`) }}</dt>
            <dd class="m-0 text-lg font-semibold tabular-nums">{{ stat.value }}</dd>
          </div>
        </dl>
      </BaseCard>

      <BaseCard :title="t(`${NS}.npu.title`)" data-testid="slm-install-npu">
        <p v-if="npuAbsent" class="m-0 text-(--aui-color-text-muted)" role="status" data-testid="slm-install-npu-absent">{{ t(`${NS}.npu.absent`) }}</p>
        <dl v-else class="m-0 grid grid-cols-[repeat(auto-fit,minmax(9rem,1fr))] gap-4">
          <div v-for="stat in npuStats" :key="stat.key" :data-testid="`slm-install-stat-${stat.key}`">
            <dt class="text-sm text-(--aui-color-text-muted)">{{ t(`${NS}.stat.${stat.key}`) }}</dt>
            <dd class="m-0 text-lg font-semibold tabular-nums">{{ stat.value }}</dd>
          </div>
        </dl>
      </BaseCard>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { BaseCard } from '@autobot/ui'
import { formatFleetDateTime } from '@/composables/useTimezone'
import { analysisMeasured, type InstallMetricsReading } from '@/composables/useInstallMetricsApi'

interface Stat { key: string; value: string | number }

const NS = 'monitoring.installMetrics'
const props = defineProps<{ reading: InstallMetricsReading; readAt: string }>()
const { t } = useI18n()

const notReported = (): string => t(`${NS}.notReported`)
const num = (value: number | null | undefined): string | number => (typeof value === 'number' && Number.isFinite(value) ? value : notReported())
const percent = (value: number | null | undefined): string =>
  typeof value === 'number' && Number.isFinite(value) ? t(`${NS}.percent`, { value: value.toFixed(1) }) : notReported()
const text = (value: string | null | undefined): string => (value ? value : notReported())

const dashboard = computed(() => (props.reading.dashboard.ok ? props.reading.dashboard.data : null))
const gpu = computed(() => (props.reading.gpu.ok ? props.reading.gpu.data : null))
const npu = computed(() => (props.reading.npu.ok ? props.reading.npu.data : null))

const systemStats = computed<Stat[]>(() => {
  const sys = dashboard.value?.system
  // The route attaches a default analysis even when nothing was measured; that is not a figure.
  const analysis = analysisMeasured(dashboard.value?.analysis) ? dashboard.value?.analysis : null
  return [
    { key: 'cpu', value: percent(sys?.cpu_usage_percent) },
    { key: 'memory', value: percent(sys?.memory_usage_percent) },
    { key: 'overallHealth', value: text(analysis?.overall_health) },
    { key: 'performanceScore', value: num(analysis?.performance_score) },
  ]
})

/** Present only when the read succeeded and the backend says there is no such device. */
const gpuAbsent = computed(() => gpu.value !== null && !gpu.value.available)
const npuAbsent = computed(() => npu.value !== null && !npu.value.available)

const gpuStats = computed<Stat[]>(() => [
  { key: 'gpuName', value: text(gpu.value?.name) },
  { key: 'gpuUtilization', value: percent(gpu.value?.utilization_percent) },
  { key: 'gpuMemory', value: percent(gpu.value?.memory_utilization_percent) },
  { key: 'gpuTemperature', value: typeof gpu.value?.temperature_celsius === 'number' ? t(`${NS}.celsius`, { n: gpu.value.temperature_celsius }) : notReported() },
  { key: 'gpuPower', value: typeof gpu.value?.power_watts === 'number' ? t(`${NS}.watts`, { n: gpu.value.power_watts }) : notReported() },
])

const npuStats = computed<Stat[]>(() => [
  { key: 'npuUtilization', value: percent(npu.value?.utilization_percent) },
  { key: 'npuAcceleration', value: num(npu.value?.acceleration_ratio) },
  { key: 'npuInferences', value: num(npu.value?.inference_count) },
])
</script>
