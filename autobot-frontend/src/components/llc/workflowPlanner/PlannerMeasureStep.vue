<!-- Copyright 2025-2026 mrveiss -->
<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- PlannerMeasureStep (#19938): step 2, how often and how long, per step. -->
<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { EmptyState } from '@autobot/ui'
import PlannerMeasureRow from './PlannerMeasureRow.vue'
import { metricFor, type Plan } from '@/composables/llc/workflowPlanTypes'

defineProps<{ plan: Plan; busy: boolean }>()
const emit = defineEmits<{
  save: [stepKey: string, body: unknown]
  clear: [stepKey: string]
}>()
const { t } = useI18n()
</script>

<template>
  <section :aria-label="t('llc.workflowPlanner.steps.measure')">
    <p class="mb-2 text-sm text-autobot-text-secondary">{{ t('llc.workflowPlanner.measure.hint') }}</p>
    <EmptyState v-if="!(plan.steps ?? []).length" :title="t('llc.workflowPlanner.measure.needSteps')" />
    <ul v-else>
      <PlannerMeasureRow
        v-for="step in plan.steps"
        :key="step.key"
        :step="step"
        :metric="metricFor(plan, step.key)"
        :busy="busy"
        @save="(k, b) => emit('save', k, b)"
        @clear="(k) => emit('clear', k)"
      />
    </ul>
  </section>
</template>
