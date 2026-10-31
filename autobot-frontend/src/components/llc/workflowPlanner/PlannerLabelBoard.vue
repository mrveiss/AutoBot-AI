<!-- Copyright 2025-2026 mrveiss -->
<!-- SPDX-License-Identifier: Apache-2.0 -->
<!--
  PlannerLabelBoard (#19938): steps 4 and 5. The chosen step is broken into sub-steps and each is
  labelled AI, Automation or By Hand. The label colours come from design tokens and are always
  paired with the label's text, so colour is never the only signal. By Hand stays with people:
  the owner confirms they have read that list before the plan can move on.
-->
<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { BaseButton, BaseInput } from '@autobot/ui'
import {
  breakdownWith,
  edgeCasesFor,
  LABEL_COLOR_VAR,
  LABELS,
  subStepsFor,
  type BreakdownBody,
  type Label,
  type Plan,
} from '@/composables/llc/workflowPlanTypes'

const props = defineProps<{ plan: Plan; busy: boolean }>()
const emit = defineEmits<{
  breakdown: [stepKey: string, body: BreakdownBody]
  classify: [subStepKey: string, label: Label | null]
  acknowledge: []
}>()
const { t } = useI18n()

const newSub = ref('')
const stepKey = computed(() => props.plan.one_number?.step_key ?? '')
const subs = computed(() => subStepsFor(props.plan, stepKey.value))
const cases = computed(() => edgeCasesFor(props.plan, stepKey.value))
const unlabelled = computed(() => subs.value.filter((s) => !s.classification))
const byHandCount = computed(
  () => subs.value.filter((s) => s.classification === 'by_hand').length + cases.value.filter((c) => c.classification === 'by_hand').length,
)

function column(label: Label) {
  return subs.value.filter((s) => s.classification === label)
}

function addSub() {
  const label = newSub.value.trim()
  if (!label || !stepKey.value) return
  emit('breakdown', stepKey.value, breakdownWith(props.plan, stepKey.value, label))
  newSub.value = ''
}
</script>

<template>
  <section :aria-label="t('llc.workflowPlanner.steps.label')">
    <p v-if="!stepKey" class="text-sm text-autobot-text-muted" data-testid="label-needs-number">{{ t('llc.workflowPlanner.label.needNumber') }}</p>
    <template v-else>
      <div class="mb-3 flex flex-wrap items-end gap-3">
        <BaseInput v-model="newSub" size="sm" :label="t('llc.workflowPlanner.label.subStep')" />
        <BaseButton size="sm" variant="secondary" :disabled="busy || !newSub.trim()" data-testid="add-sub-step" @click="addSub">
          {{ t('llc.workflowPlanner.label.addSubStep') }}
        </BaseButton>
      </div>

      <ul v-if="unlabelled.length" class="mb-3" data-testid="unlabelled">
        <li v-for="s in unlabelled" :key="s.key" class="flex flex-wrap items-center gap-2 py-1 text-sm text-autobot-text-primary">
          <span class="flex-1">{{ s.label }}</span>
          <BaseButton v-for="l in LABELS" :key="l" size="xs" variant="outline" :disabled="busy" :data-testid="`classify-${s.key}-${l}`" @click="emit('classify', s.key, l)">
            {{ t(`llc.workflowPlanner.labels.${l}`) }}
          </BaseButton>
        </li>
      </ul>

      <div class="grid gap-3 md:grid-cols-3">
        <div v-for="l in LABELS" :key="l" class="rounded-md border border-autobot-border p-3" :data-testid="`column-${l}`">
          <h4 class="mb-2 border-l-4 pl-2 text-sm font-semibold text-autobot-text-primary" :style="{ borderColor: LABEL_COLOR_VAR[l] }">{{ t(`llc.workflowPlanner.labels.${l}`) }}</h4>
          <ul>
            <li v-for="s in column(l)" :key="s.key" class="flex items-center gap-2 py-1 text-sm text-autobot-text-secondary">
              <span class="flex-1">{{ s.label }}</span>
              <BaseButton size="xs" variant="ghost" :disabled="busy" @click="emit('classify', s.key, null)">{{ t('llc.workflowPlanner.label.unlabel') }}</BaseButton>
            </li>
            <li v-for="c in cases.filter((e) => e.classification === l)" :key="c.key" class="py-1 text-sm italic text-autobot-text-muted">
              {{ t('llc.workflowPlanner.label.edgeCase', { text: c.description }) }}
            </li>
          </ul>
        </div>
      </div>

      <div v-if="byHandCount" class="mt-3 flex items-center gap-3 text-sm text-autobot-text-secondary">
        <span>{{ t('llc.workflowPlanner.label.byHandNote') }}</span>
        <BaseButton size="sm" :disabled="busy || !!plan.by_hand_acknowledged_at" data-testid="ack-by-hand" @click="emit('acknowledge')">
          {{ plan.by_hand_acknowledged_at ? t('llc.workflowPlanner.label.acknowledged') : t('llc.workflowPlanner.label.acknowledge') }}
        </BaseButton>
      </div>
    </template>
  </section>
</template>
