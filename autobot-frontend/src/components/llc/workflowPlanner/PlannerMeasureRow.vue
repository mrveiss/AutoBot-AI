<!-- Copyright 2025-2026 mrveiss -->
<!-- SPDX-License-Identifier: Apache-2.0 -->
<!--
  PlannerMeasureRow (#19938): one step's frequency (per week) and duration, with the source
  pill of what is stored. Saving sends the owner's numbers; the server decides the source.
-->
<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { BaseButton, BaseInput } from '@autobot/ui'
import PlannerSourcePill from './PlannerSourcePill.vue'
import type { Step, StepMetric } from '@/composables/llc/workflowPlanTypes'

const DURATION_UNITS = ['minutes', 'hours', 'days'] as const

interface Quantity {
  value: number
  unit: string
}

const props = defineProps<{ step: Step; metric?: StepMetric; busy: boolean }>()
const emit = defineEmits<{
  save: [stepKey: string, body: { frequency: Quantity; duration: Quantity }]
  clear: [stepKey: string]
}>()
const { t } = useI18n()

const frequency = ref(String(props.metric?.frequency.value ?? ''))
const duration = ref(String(props.metric?.duration.value ?? ''))
const unit = ref<string>(props.metric?.duration.unit ?? 'days')

const valid = () => Number(frequency.value) > 0 && Number(duration.value) > 0

function save() {
  if (!valid()) return
  emit('save', props.step.key, {
    frequency: { value: Number(frequency.value), unit: 'per_week' },
    duration: { value: Number(duration.value), unit: unit.value },
  })
}
</script>

<template>
  <li class="flex flex-wrap items-end gap-3 border-b border-autobot-border py-3" :data-testid="`measure-row-${step.key}`">
    <span class="min-w-40 flex-1 text-sm font-medium text-autobot-text-primary">{{ step.label }}</span>
    <PlannerSourcePill v-if="metric" :source="metric.duration.source" />
    <BaseInput v-model="frequency" size="sm" inputmode="numeric" :label="t('llc.workflowPlanner.measure.perWeek')" />
    <BaseInput v-model="duration" size="sm" inputmode="decimal" :label="t('llc.workflowPlanner.measure.duration')" />
    <select
      v-model="unit"
      class="rounded-md border border-autobot-border bg-autobot-bg-card px-2 py-1.5 text-sm text-autobot-text-primary"
      :aria-label="t('llc.workflowPlanner.measure.unit')"
    >
      <option v-for="u in DURATION_UNITS" :key="u" :value="u">{{ t(`llc.workflowPlanner.unit.${u}`) }}</option>
    </select>
    <BaseButton size="sm" :disabled="busy || !valid()" data-testid="measure-save" @click="save">
      {{ t('llc.workflowPlanner.measure.save') }}
    </BaseButton>
    <BaseButton v-if="metric" size="sm" variant="ghost" :disabled="busy" @click="emit('clear', step.key)">
      {{ t('llc.workflowPlanner.measure.clear') }}
    </BaseButton>
  </li>
</template>
