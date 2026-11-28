<!--
  Copyright 2025-2026 mrveiss
  SPDX-License-Identifier: Apache-2.0

  InstallMetricsFindings (#19484): the service health, alerts and optimization recommendations of
  one install-metrics reading (InstallMetrics). Pure display. A section that failed to read says
  so ("Not reported"); it is never drawn as an empty list.
-->
<template>
  <div class="flex flex-col gap-4">
    <BaseCard :title="t(`${NS}.services.title`)" data-testid="slm-install-services">
      <p v-if="!reading.services.ok" class="m-0 text-(--aui-color-text-muted)" role="status" data-testid="slm-install-services-unread">{{ t(`${NS}.notReported`) }}</p>
      <template v-else>
        <p class="m-0 mb-3 text-sm text-(--aui-color-text-muted)" data-testid="slm-install-services-summary">
          {{ serviceSummary }}
        </p>
        <BaseTable
          :columns="serviceColumns" :rows="serviceRows" row-key="name" :aria-label="t(`${NS}.services.title`)"
          :empty-title="t(`${NS}.services.empty`)" data-testid="slm-install-services-table"
        />
      </template>
    </BaseCard>

    <div class="grid gap-4 md:grid-cols-2">
      <BaseCard :title="t(`${NS}.alerts.title`)" data-testid="slm-install-alerts">
        <p v-if="!reading.alerts.ok" class="m-0 text-(--aui-color-text-muted)" role="status" data-testid="slm-install-alerts-unread">{{ t(`${NS}.notReported`) }}</p>
        <p v-else-if="alertList.length === 0" class="m-0 text-(--aui-color-text-muted)" role="status" data-testid="slm-install-alerts-empty">{{ t(`${NS}.alerts.empty`) }}</p>
        <ul v-else class="m-0 flex list-none flex-col gap-3 p-0">
          <li v-for="(a, i) in alertList" :key="`${a.category}:${a.message}:${i}`" class="flex flex-col gap-1" data-testid="slm-install-alert">
            <span class="flex items-center gap-2">
              <BaseBadge :variant="SEVERITY_VARIANT[a.severity] ?? 'neutral'" size="sm" tone="solid">{{ word('severity', a.severity) }}</BaseBadge>
              <strong>{{ a.category }}</strong>
            </span>
            <span class="text-(--aui-color-text-muted)">{{ a.message }}</span>
          </li>
        </ul>
      </BaseCard>

      <BaseCard :title="t(`${NS}.recommendations.title`)" data-testid="slm-install-recommendations">
        <p v-if="!reading.recommendations.ok" class="m-0 text-(--aui-color-text-muted)" role="status" data-testid="slm-install-recommendations-unread">{{ t(`${NS}.notReported`) }}</p>
        <p v-else-if="recommendations.length === 0" class="m-0 text-(--aui-color-text-muted)" role="status" data-testid="slm-install-recommendations-empty">{{ t(`${NS}.recommendations.empty`) }}</p>
        <ul v-else class="m-0 flex list-none flex-col gap-3 p-0">
          <li v-for="(r, i) in recommendations" :key="`${r.category}:${r.recommendation}:${i}`" class="flex flex-col gap-1" data-testid="slm-install-recommendation">
            <span class="flex items-center gap-2">
              <BaseBadge :variant="PRIORITY_VARIANT[r.priority] ?? 'neutral'" size="sm" tone="solid">{{ word('priority', r.priority) }}</BaseBadge>
              <strong>{{ r.category }}</strong>
            </span>
            <span class="text-(--aui-color-text-muted)">{{ r.recommendation }}</span>
            <span class="text-sm">{{ t(`${NS}.recommendations.action`, { action: r.action }) }}</span>
          </li>
        </ul>
      </BaseCard>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { BaseBadge, BaseCard, BaseTable, type BadgeVariant, type BaseTableColumn, type OptimizationRecommendation, type PerformanceAlert, type ServicesSummary } from '@autobot/ui'
import type { InstallMetricsReading } from '@/composables/useInstallMetricsApi'

const NS = 'monitoring.installMetrics'
const props = defineProps<{ reading: InstallMetricsReading }>()
const { t, te } = useI18n()

const SEVERITY_VARIANT: Record<string, BadgeVariant> = { critical: 'error', high: 'error', warning: 'warning', info: 'info' }
const PRIORITY_VARIANT: Record<string, BadgeVariant> = { high: 'error', medium: 'warning', low: 'neutral' }

const services = computed<ServicesSummary | null>(() => (props.reading.services.ok ? props.reading.services.data : null))
const alertList = computed<PerformanceAlert[]>(() => (props.reading.alerts.ok ? props.reading.alerts.data.alerts ?? [] : []))
const serviceSummary = computed(() =>
  services.value
    ? t(`${NS}.services.summary`, { healthy: services.value.healthy_services, total: services.value.total_services, status: word('health', services.value.overall_status) })
    : '',
)
const recommendations = computed<OptimizationRecommendation[]>(() => (props.reading.recommendations.ok ? props.reading.recommendations.data : []))

const serviceColumns = computed<BaseTableColumn[]>(() => [
  { key: 'name', label: t(`${NS}.services.col.name`) },
  { key: 'status', label: t(`${NS}.services.col.status`) },
  { key: 'endpoint', label: t(`${NS}.services.col.endpoint`) },
  { key: 'response', label: t(`${NS}.services.col.response`), numeric: true },
  { key: 'score', label: t(`${NS}.services.col.score`), numeric: true },
  { key: 'uptime', label: t(`${NS}.services.col.uptime`), numeric: true },
])

const serviceRows = computed(() =>
  (services.value?.services ?? []).map((s) => ({
    name: s.name,
    status: word('status', s.status),
    endpoint: `${s.host}:${s.port}`,
    response: typeof s.response_time_ms === 'number' ? t(`${NS}.ms`, { n: s.response_time_ms.toFixed(0) }) : t(`${NS}.notReported`),
    score: typeof s.health_score === 'number' ? s.health_score : t(`${NS}.notReported`),
    uptime: typeof s.uptime_hours === 'number' ? t(`${NS}.hours`, { n: s.uptime_hours.toFixed(1) }) : t(`${NS}.notReported`),
  })),
)

/** The backend's own word when this screen has no translation for it. */
function word(group: string, value: string): string {
  const key = `${NS}.${group}.${value}`
  return te(key) ? t(key) : value
}
</script>
