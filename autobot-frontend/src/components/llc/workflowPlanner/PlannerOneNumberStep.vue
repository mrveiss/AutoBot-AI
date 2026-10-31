<!-- Copyright 2025-2026 mrveiss -->
<!-- SPDX-License-Identifier: Apache-2.0 -->
<!--
  PlannerOneNumberStep (#19938): step 3, pick the one number. Candidates are the measured steps,
  ranked by how often they happen times how long they wait; the owner decides. The baseline is
  the step's measured duration and keeps its source pill.
-->
<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { BaseButton, BaseInput, EmptyState } from '@autobot/ui'
import PlannerSourcePill from './PlannerSourcePill.vue'
import type { OneNumberBody, Plan, StepMetric } from '@/composables/llc/workflowPlanTypes'

const RETURN_KINDS = ['hours_back', 'more_yeses', 'money_sooner'] as const

const props = defineProps<{ plan: Plan; busy: boolean }>()
const emit = defineEmits<{ save: [body: OneNumberBody] }>()
const { t } = useI18n()

const candidates = computed(() =>
  [...(props.plan.step_metrics ?? [])].sort(
    (a, b) => b.frequency.value * b.duration.value - a.frequency.value * a.duration.value,
  ),
)
const chosen = ref(props.plan.one_number?.step_key ?? '')
const title = ref(props.plan.one_number?.title ?? '')
const returnKind = ref<(typeof RETURN_KINDS)[number]>(props.plan.one_number?.return_kind ?? 'more_yeses')
const target = ref(String(props.plan.one_number?.target_value ?? ''))
const metric = computed<StepMetric | undefined>(() => candidates.value.find((c) => c.step_key === chosen.value))

function stepLabel(key: string): string {
  return (props.plan.steps ?? []).find((s) => s.key === key)?.label ?? key
}

function save() {
  const m = metric.value
  if (!m || !title.value.trim()) return
  const body: OneNumberBody = {
    title: title.value.trim(),
    step_key: m.step_key,
    return_kind: returnKind.value,
    direction: 'down',
    unit: m.duration.unit,
    baseline_value: m.duration.value,
    target_value: target.value === '' ? null : Number(target.value),
  }
  emit('save', body)
}
</script>

<template>
  <section :aria-label="t('llc.workflowPlanner.steps.oneNumber')">
    <EmptyState v-if="!candidates.length" :title="t('llc.workflowPlanner.oneNumber.needMetrics')" />
    <template v-else>
      <p class="mb-2 text-sm text-autobot-text-secondary">{{ t('llc.workflowPlanner.oneNumber.hint') }}</p>
      <label v-for="c in candidates" :key="c.step_key" class="flex items-center gap-3 py-1 text-sm text-autobot-text-primary">
        <input v-model="chosen" type="radio" name="one-number-step" :value="c.step_key" />
        <span class="flex-1">{{ stepLabel(c.step_key) }}</span>
        <span>{{ t('llc.workflowPlanner.oneNumber.rate', { freq: c.frequency.value, dur: c.duration.value, unit: t(`llc.workflowPlanner.unit.${c.duration.unit}`) }) }}</span>
        <PlannerSourcePill :source="c.duration.source" />
      </label>
      <div class="mt-3 flex flex-wrap items-end gap-3">
        <BaseInput v-model="title" size="sm" :label="t('llc.workflowPlanner.oneNumber.title')" />
        <select v-model="returnKind" class="rounded-md border border-autobot-border bg-autobot-bg-card px-2 py-1.5 text-sm text-autobot-text-primary" :aria-label="t('llc.workflowPlanner.oneNumber.returnKind')">
          <option v-for="k in RETURN_KINDS" :key="k" :value="k">{{ t(`llc.workflowPlanner.returnKind.${k}`) }}</option>
        </select>
        <BaseInput v-model="target" size="sm" inputmode="decimal" :label="t('llc.workflowPlanner.oneNumber.target')" />
        <BaseButton size="sm" :disabled="busy || !metric || !title.trim()" data-testid="one-number-save" @click="save">
          {{ t('llc.workflowPlanner.oneNumber.save') }}
        </BaseButton>
      </div>
    </template>
  </section>
</template>
