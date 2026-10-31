<!-- Copyright 2025-2026 mrveiss -->
<!-- SPDX-License-Identifier: Apache-2.0 -->
<!--
  WorkflowPlanDetail (#19938): one plan, steps 1 to 4 of the flow. The status is the server's;
  this view never computes one. Approval and conversion are not built yet (#19936), so a plan in
  those statuses is shown read-only with an honest not-available note, never as a broken page.
-->
<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { BaseAlert, BaseBadge, BaseButton, useToast } from '@autobot/ui'
import PlannerMapStep from './PlannerMapStep.vue'
import PlannerMeasureStep from './PlannerMeasureStep.vue'
import PlannerOneNumberStep from './PlannerOneNumberStep.vue'
import PlannerLabelBoard from './PlannerLabelBoard.vue'
import { describeApiError } from '@/composables/llc/apiErrorMessage'
import { isActiveStatus, STATUS_ORDER, type GateResponse, type Plan } from '@/composables/llc/workflowPlanTypes'
import type { WorkflowPlansApi } from '@/composables/llc/useWorkflowPlans'

const STEPS = ['map', 'measure', 'oneNumber', 'label'] as const
type StepId = (typeof STEPS)[number]

const props = defineProps<{ planKey: string; api: WorkflowPlansApi }>()
const emit = defineEmits<{ back: [] }>()
const { t } = useI18n()
const { showToast } = useToast()

const plan = ref<Plan | null>(null)
const gate = ref<GateResponse | null>(null)
const warnings = ref<string[]>([])
const loadError = ref('')
const busy = ref(false)
const step = ref<StepId>('map')
const editable = computed(() => !!plan.value && isActiveStatus(plan.value.status))

async function refreshGate() {
  gate.value = await props.api.gate(props.planKey)
}

async function load() {
  loadError.value = ''
  try {
    plan.value = await props.api.get(props.planKey)
    await refreshGate()
  } catch (err: unknown) {
    loadError.value = describeApiError(err, t('llc.workflowPlanner.loadFailed'))
  }
}

/** One write at a time: the server returns the whole plan, which replaces the local copy. */
async function run(call: () => Promise<Plan>) {
  if (busy.value) return
  busy.value = true
  try {
    plan.value = await call()
    await refreshGate()
  } catch (err: unknown) {
    showToast(describeApiError(err, t('llc.workflowPlanner.saveFailed')), 'error')
  } finally {
    busy.value = false
  }
}

const saveMap = (body: Parameters<WorkflowPlansApi['putMap']>[1]) =>
  run(async () => {
    const res = await props.api.putMap(props.planKey, body)
    warnings.value = res.validation.warnings
    return res.plan
  })

onMounted(load)
</script>

<template>
  <div data-testid="plan-detail">
    <div class="mb-3 flex items-center gap-3">
      <BaseButton size="sm" variant="ghost" data-testid="plan-back" @click="emit('back')">{{ t('llc.workflowPlanner.back') }}</BaseButton>
      <h3 v-if="plan" class="text-lg font-semibold text-autobot-text-primary">{{ plan.name }}</h3>
    </div>

    <BaseAlert v-if="loadError" variant="error" :message="loadError" data-testid="plan-load-error" />
    <p v-else-if="!plan" role="status" class="py-6 text-center text-autobot-text-muted" data-testid="plan-loading">{{ t('llc.workflowPlanner.loading') }}</p>

    <template v-else>
      <ol class="mb-3 flex flex-wrap gap-2" :aria-label="t('llc.workflowPlanner.statusFlow')">
        <li v-for="s in STATUS_ORDER" :key="s">
          <BaseBadge :variant="s === plan.status ? 'primary' : 'neutral'" :tone="s === plan.status ? 'solid' : 'subtle'" size="sm" :label="t(`llc.workflowPlanner.status.${s}`)" :data-testid="`status-${s}`" />
        </li>
      </ol>

      <BaseAlert v-if="!editable" variant="info" :message="t('llc.workflowPlanner.statusNotAvailable', { status: t(`llc.workflowPlanner.status.${plan.status}`) })" data-testid="status-not-available" />

      <div class="mb-3 flex flex-wrap gap-2" role="tablist">
        <BaseButton v-for="(s, i) in STEPS" :key="s" size="sm" :variant="step === s ? 'primary' : 'outline'" role="tab" :aria-selected="step === s" :data-testid="`step-${s}`" @click="step = s">
          {{ i + 1 }} {{ t(`llc.workflowPlanner.steps.${s}`) }}
        </BaseButton>
        <BaseButton size="sm" variant="outline" disabled data-testid="step-convert" :title="t('llc.workflowPlanner.convertNotAvailable')">
          5 {{ t('llc.workflowPlanner.steps.convert') }}
        </BaseButton>
      </div>

      <fieldset :disabled="!editable" class="border-0 p-0">
        <PlannerMapStep v-if="step === 'map'" :plan="plan" :busy="busy" :warnings="warnings" @map="saveMap" @wait-note="(k, n) => run(() => api.setWaitNote(planKey, k, n))" />
        <PlannerMeasureStep v-else-if="step === 'measure'" :plan="plan" :busy="busy" @save="(k, b) => run(() => api.putMetric(planKey, k, b))" @clear="(k) => run(() => api.deleteMetric(planKey, k))" />
        <PlannerOneNumberStep v-else-if="step === 'oneNumber'" :plan="plan" :busy="busy" @save="(b) => run(() => api.putOneNumber(planKey, b))" />
        <PlannerLabelBoard v-else :plan="plan" :busy="busy" @breakdown="(k, b) => run(() => api.putBreakdown(planKey, k, b))" @classify="(k, l) => run(() => api.classifySubStep(planKey, k, l))" @acknowledge="run(() => api.acknowledgeByHand(planKey))" />
      </fieldset>

      <div v-if="gate?.missing.length" class="mt-4" data-testid="gate-missing">
        <h4 class="text-sm font-semibold text-autobot-text-primary">{{ t('llc.workflowPlanner.gate.missing') }}</h4>
        <ul class="text-sm text-autobot-text-secondary">
          <li v-for="m in gate.missing" :key="`${m.gate}-${m.step ?? ''}-${m.message}`">{{ m.message }}</li>
        </ul>
      </div>
    </template>
  </div>
</template>
