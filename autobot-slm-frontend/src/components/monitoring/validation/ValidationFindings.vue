<!--
  Copyright 2025-2026 mrveiss
  SPDX-License-Identifier: Apache-2.0

  ValidationFindings (#18278): the alerts and the recommendations of one validation report,
  each with its count by level, and each said as empty when the report has none.
-->
<template>
  <div class="grid gap-4 md:grid-cols-2">
    <BaseCard :title="t(`${NS}.alerts.title`, { n: alerts.length })" data-testid="slm-validation-alerts">
      <p v-if="alerts.length === 0" class="m-0 text-(--aui-color-text-muted)" role="status" data-testid="slm-validation-alerts-empty">
        {{ t(`${NS}.alerts.empty`) }}
      </p>
      <ul v-else class="m-0 flex list-none flex-col gap-3 p-0">
        <li v-for="(a, i) in alerts" :key="`${a.level}:${a.title}:${i}`" class="flex flex-col gap-1" data-testid="slm-validation-alert">
          <span class="flex items-center gap-2">
            <BaseBadge :variant="ALERT_VARIANT[a.level] ?? 'neutral'" size="sm" tone="solid">{{ level(`alerts.level`, a.level) }}</BaseBadge>
            <strong>{{ a.title }}</strong>
          </span>
          <span class="text-(--aui-color-text-muted)">{{ a.message }}</span>
        </li>
      </ul>
    </BaseCard>

    <BaseCard :title="t(`${NS}.recommendations.title`, { n: recommendations.length })" data-testid="slm-validation-recommendations">
      <p v-if="recommendations.length === 0" class="m-0 text-(--aui-color-text-muted)" role="status" data-testid="slm-validation-recommendations-empty">
        {{ t(`${NS}.recommendations.empty`) }}
      </p>
      <ul v-else class="m-0 flex list-none flex-col gap-3 p-0">
        <li v-for="(r, i) in recommendations" :key="`${r.type}:${r.title}:${i}`" class="flex flex-col gap-1" data-testid="slm-validation-recommendation">
          <span class="flex items-center gap-2">
            <BaseBadge :variant="URGENCY_VARIANT[r.urgency] ?? 'neutral'" size="sm" tone="solid">{{ level(`recommendations.urgency`, r.urgency) }}</BaseBadge>
            <strong>{{ r.title }}</strong>
          </span>
          <span class="text-(--aui-color-text-muted)">{{ r.description }}</span>
          <span class="text-sm">{{ t(`${NS}.recommendations.action`, { action: r.action }) }}</span>
        </li>
      </ul>
    </BaseCard>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { BaseBadge, BaseCard, type BadgeVariant } from '@autobot/ui'
import type { ValidationAlert, ValidationRecommendation } from '@/composables/useValidationDashboardApi'

defineProps<{ alerts: ValidationAlert[]; recommendations: ValidationRecommendation[] }>()

const NS = 'monitoring.validationDashboard'
const { t, te } = useI18n()

const ALERT_VARIANT: Record<string, BadgeVariant> = { critical: 'error', warning: 'warning', info: 'info' }
const URGENCY_VARIANT: Record<string, BadgeVariant> = { high: 'error', medium: 'warning', low: 'neutral', info: 'info' }

/** The generator's own word when this screen has no translation for it. */
function level(group: string, value: string): string {
  const key = `${NS}.${group}.${value}`
  return te(key) ? t(key) : value
}
</script>
