<!--
  Copyright 2025-2026 mrveiss
  SPDX-License-Identifier: Apache-2.0

  ValidationDashboard -- SLM > Monitoring > Validation, admin only (#18278). The system
  validation report from the main backend's /validation-dashboard routes: overview, metrics,
  per-phase status, alerts, recommendations and trends, all from the one /report read, plus the
  admin action that rebuilds the server-rendered HTML dashboard (POST /generate).

  Four states are said apart, never folded into "nothing": reading, not available (the report
  generator is not installed on the backend), failed, and read-but-empty. A phase that publishes
  no score reads "Not scored", never 0%.
-->
<template>
  <div class="flex flex-col gap-4 p-4 text-(--aui-color-text)" data-testid="slm-validation">
    <header class="flex flex-wrap items-baseline gap-3">
      <h2 class="m-0 text-xl font-semibold">{{ t('monitoring.validationDashboard.title') }}</h2>
      <p class="m-0 text-(--aui-color-text-muted)">{{ t('monitoring.validationDashboard.subtitle') }}</p>
      <div class="ms-auto flex items-center gap-2">
        <BaseButton variant="secondary" size="sm" :loading="state === 'loading'" data-testid="slm-validation-refresh" @click="load">
          {{ t('monitoring.validationDashboard.refresh') }}
        </BaseButton>
        <BaseButton
          size="sm" :loading="generating" :disabled="state === 'unavailable'" data-testid="slm-validation-generate" @click="generate"
        >{{ t('monitoring.validationDashboard.generate') }}</BaseButton>
      </div>
    </header>

    <BaseAlert v-if="generateOutcome === 'started'" variant="success" data-testid="slm-validation-generate-started" :message="t('monitoring.validationDashboard.generateStarted')" />
    <BaseAlert v-else-if="generateOutcome === 'failed'" variant="error" data-testid="slm-validation-generate-failed" :message="generateError" />

    <p v-if="state === 'loading'" role="status" class="m-0 flex items-center gap-2 text-(--aui-color-text-muted)" data-testid="slm-validation-loading">
      <BaseSpinner size="sm" />{{ t('monitoring.validationDashboard.loading') }}
    </p>
    <BaseAlert
      v-else-if="state === 'unavailable'" variant="warning" data-testid="slm-validation-unavailable"
      :title="t('monitoring.validationDashboard.unavailableTitle')" :message="t('monitoring.validationDashboard.unavailableBody')"
    />
    <BaseAlert
      v-else-if="state === 'error'" variant="error" data-testid="slm-validation-error"
      :title="t('monitoring.validationDashboard.errorTitle')" :message="errorText"
    />
    <EmptyState
      v-else-if="!hasData" data-testid="slm-validation-empty"
      :title="t('monitoring.validationDashboard.emptyTitle')" :description="t('monitoring.validationDashboard.emptyBody')"
    />

    <template v-else-if="report">
      <ValidationOverview :report="report" :service="service" :read-at="readAt" />

      <BaseCard :title="t('monitoring.validationDashboard.phases.title')">
        <BaseTable
          :columns="phaseColumns" :rows="phaseRows" row-key="name" :aria-label="t('monitoring.validationDashboard.phases.title')"
          :empty-title="t('monitoring.validationDashboard.phases.empty')" data-testid="slm-validation-phases"
        />
      </BaseCard>

      <ValidationFindings :alerts="report.alerts" :recommendations="report.recommendations" />

      <BaseCard :title="t('monitoring.validationDashboard.trends.title')">
        <BaseAlert variant="info" :message="t('monitoring.validationDashboard.trends.note')" data-testid="slm-validation-trends-note" />
        <BaseTable
          :columns="trendColumns" :rows="trendRows" row-key="series" :aria-label="t('monitoring.validationDashboard.trends.title')"
          :empty-title="t('monitoring.validationDashboard.trends.empty')" data-testid="slm-validation-trends"
        />
      </BaseCard>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { BaseAlert, BaseButton, BaseCard, BaseSpinner, BaseTable, EmptyState, type BaseTableColumn } from '@autobot/ui'
import { autobotApiErrorMessage } from '@/composables/autobotApiError'
import {
  isValidationGeneratorUnavailable,
  useValidationDashboardApi,
  type ValidationDashboardStatus,
  type ValidationReport,
} from '@/composables/useValidationDashboardApi'
import ValidationFindings from '@/components/monitoring/validation/ValidationFindings.vue'
import ValidationOverview from '@/components/monitoring/validation/ValidationOverview.vue'

type LoadState = 'loading' | 'ready' | 'unavailable' | 'error'
type GenerateOutcome = 'idle' | 'started' | 'failed'

const NS = 'monitoring.validationDashboard'
const { t } = useI18n()
const api = useValidationDashboardApi()

const state = ref<LoadState>('loading')
const errorText = ref('')
const service = ref<ValidationDashboardStatus | null>(null)
const report = ref<ValidationReport | null>(null)
const readAt = ref('')
const generating = ref(false)
const generateOutcome = ref<GenerateOutcome>('idle')
const generateError = ref('')

/** Read but empty: the route answered and there is no phase to show. */
const hasData = computed(() => (report.value?.phase_details.length ?? 0) > 0)

const phaseColumns = computed<BaseTableColumn[]>(() => [
  { key: 'display_name', label: t(`${NS}.phases.col.phase`) },
  { key: 'status', label: t(`${NS}.phases.col.status`) },
  { key: 'completion', label: t(`${NS}.phases.col.completion`), numeric: true },
  { key: 'requirements', label: t(`${NS}.phases.col.requirements`), numeric: true },
  { key: 'missing_count', label: t(`${NS}.phases.col.missing`), numeric: true },
  { key: 'verified_by', label: t(`${NS}.phases.col.verifiedBy`), wrap: true },
])

const phaseRows = computed(() =>
  (report.value?.phase_details ?? []).map((p) => ({
    name: p.name,
    display_name: p.display_name,
    status: p.status,
    completion: p.completion_percentage === null ? t(`${NS}.phases.notScored`) : t(`${NS}.percent`, { value: p.completion_percentage.toFixed(1) }),
    requirements: `${p.requirements_met}/${p.total_requirements}`,
    missing_count: p.missing_count,
    verified_by: p.authoritative_gates.length > 0 ? p.authoritative_gates.join(', ') : '—',
  })),
)

const trendColumns = computed<BaseTableColumn[]>(() => [
  { key: 'label', label: t(`${NS}.trends.col.series`) },
  { key: 'points', label: t(`${NS}.trends.col.points`), numeric: true },
  { key: 'first', label: t(`${NS}.trends.col.first`), numeric: true },
  { key: 'latest', label: t(`${NS}.trends.col.latest`), numeric: true },
])

/** Each series the generator sent, with its first and last value; none when it sent `{}`. */
const trendRows = computed(() => {
  const trends = report.value?.trends ?? {}
  const series: [string, number[]][] = [
    ['maturity_trend', (trends.maturity_trend ?? []).map((p) => p.value)],
    ['phase_completion_trend', (trends.phase_completion_trend ?? []).map((p) => p.completed_phases)],
    ['capability_growth', (trends.capability_growth ?? []).map((p) => p.capabilities)],
  ]
  return series
    .filter(([, values]) => values.length > 0)
    .map(([key, values]) => ({ series: key, label: t(`${NS}.trends.series.${key}`), points: values.length, first: values[0], latest: values[values.length - 1] }))
})

async function load(): Promise<void> {
  state.value = 'loading'
  try {
    service.value = await api.getStatus()
    report.value = await api.getReport()
    readAt.value = new Date().toISOString()
    state.value = 'ready'
  } catch (e) {
    errorText.value = autobotApiErrorMessage(e, t(`${NS}.errorBody`))
    state.value = isValidationGeneratorUnavailable(e) ? 'unavailable' : 'error'
  }
}

async function generate(): Promise<void> {
  generating.value = true
  generateOutcome.value = 'idle'
  try {
    await api.generate()
    generateOutcome.value = 'started'
  } catch (e) {
    generateError.value = autobotApiErrorMessage(e, t(`${NS}.generateFailed`))
    generateOutcome.value = 'failed'
  } finally {
    generating.value = false
  }
}

onMounted(load)
</script>
