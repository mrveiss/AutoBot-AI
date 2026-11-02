<!--
  Copyright 2025-2026 mrveiss
  SPDX-License-Identifier: Apache-2.0

  ValidationOverview (#18278): the headline figures and the metric groups of one validation
  report (ValidationDashboard). Pure display; the report is read by the screen.
-->
<template>
  <BaseCard :title="t(`${NS}.overview.title`)" data-testid="slm-validation-overview">
    <dl class="m-0 grid grid-cols-[repeat(auto-fit,minmax(11rem,1fr))] gap-4">
      <div v-for="stat in stats" :key="stat.key" :data-testid="`slm-validation-stat-${stat.key}`">
        <dt class="text-sm text-(--aui-color-text-muted)">{{ t(`${NS}.stat.${stat.key}`) }}</dt>
        <dd class="m-0 text-lg font-semibold tabular-nums">{{ stat.value }}</dd>
      </div>
    </dl>
    <p class="m-0 mt-3 flex flex-wrap items-center gap-2 text-sm text-(--aui-color-text-muted)">
      <span>{{ t(`${NS}.overview.measures`) }}</span>
      <BaseBadge variant="neutral" size="sm" monospace data-testid="slm-validation-measures">{{ report.system_overview.measures }}</BaseBadge>
      <span v-if="readAt">{{ t(`${NS}.overview.readAt`, { time: formatFleetDateTime(readAt) }) }}</span>
    </p>
  </BaseCard>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { BaseBadge, BaseCard } from '@autobot/ui'
import { formatFleetDateTime } from '@/composables/useTimezone'
import type { ValidationDashboardStatus, ValidationReport } from '@/composables/useValidationDashboardApi'

const NS = 'monitoring.validationDashboard'
const props = defineProps<{ report: ValidationReport; service: ValidationDashboardStatus | null; readAt: string }>()
const { t, te } = useI18n()

const percent = (value: number): string => t(`${NS}.percent`, { value: value.toFixed(1) })
const yesNo = (value: boolean): string => t(`${NS}.${value ? 'yes' : 'no'}`)
/** The generator's own word when this screen has no translation for it. */
const health = (value: string): string => (te(`${NS}.health.${value}`) ? t(`${NS}.health.${value}`) : value)

const stats = computed(() => {
  const { system_overview: o, metrics: m, progression_status: p } = props.report
  const rows: { key: string; value: string | number }[] = [
    { key: 'maturity', value: percent(o.overall_maturity) },
    { key: 'health', value: health(o.system_health) },
    { key: 'phases', value: t(`${NS}.outOf`, { done: o.completed_phases, total: o.total_phases }) },
    { key: 'capabilities', value: o.active_capabilities },
    { key: 'averageCompletion', value: percent(m.completion_statistics.average_completion) },
    { key: 'minCompletion', value: percent(m.completion_statistics.min_completion) },
    { key: 'maxCompletion', value: percent(m.completion_statistics.max_completion) },
    { key: 'above50', value: m.completion_statistics.phases_above_50 },
    { key: 'above90', value: m.completion_statistics.phases_above_90 },
    { key: 'stage', value: m.system_maturity.development_stage },
    { key: 'validationScore', value: m.quality_indicators.validation_score },
    { key: 'errorRate', value: m.quality_indicators.error_rate },
    { key: 'recentChanges', value: m.quality_indicators.recent_changes },
    { key: 'velocity', value: m.progression_metrics.progression_velocity },
    { key: 'canProgress', value: yesNo(p.can_progress) },
    { key: 'blocked', value: p.blocked_phases.length },
  ]
  const s = props.service
  if (s?.refresh_interval != null) rows.push({ key: 'refreshInterval', value: t(`${NS}.seconds`, { n: s.refresh_interval }) })
  if (s?.data_retention_days != null) rows.push({ key: 'retention', value: t(`${NS}.days`, { n: s.data_retention_days }) })
  return rows
})
</script>
