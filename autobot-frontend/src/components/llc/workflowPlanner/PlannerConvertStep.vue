<!-- Copyright 2025-2026 mrveiss -->
<!-- SPDX-License-Identifier: Apache-2.0 -->
<!--
  PlannerConvertStep (#19938, spec 7.5): gates G1-G7, preview, approve, convert. The plan's phase
  is read from the stored plan (`convertPhase`). The owner confirms approval through the shared
  confirm dialog, then the server records who approved. A refused step is never an empty screen:
  a 404 is "not available", a 409 re-reads the gate list so the missing criteria are on screen,
  and anything else shows the server's reason.
-->
<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { BaseAlert, BaseButton } from '@autobot/ui'
import PlannerGateList from './PlannerGateList.vue'
import PlannerConversionSummary from './PlannerConversionSummary.vue'
import { useConfirmDialog } from '@/composables/useConfirmDialog'
import { describeApiError } from '@/composables/llc/apiErrorMessage'
import { approvalBlockers, classifyConvertError, convertPhase, conversionErrors, type ConvertFailure } from '@/composables/llc/workflowPlanGate'
import type { GateResponse, Plan } from '@/composables/llc/workflowPlanTypes'
import type { WorkflowPlansApi } from '@/composables/llc/useWorkflowPlans'

const props = defineProps<{ plan: Plan; gate: GateResponse | null; api: WorkflowPlansApi; stale?: boolean }>()
const emit = defineEmits<{ changed: [plan?: Plan] }>()
const { t } = useI18n()
const { confirm } = useConfirmDialog()

const working = ref(false)
const failure = ref<{ kind: ConvertFailure; message: string } | null>(null)
const phase = computed(() => convertPhase(props.plan))
const conversion = computed(() => props.plan.conversion ?? null)
const blockers = computed(() => approvalBlockers(props.plan.status, props.gate))
const canApprove = computed(() => conversionErrors(props.plan).length === 0 && blockers.value.length === 0 && !props.stale)
const failedProposals = computed(() => (conversion.value?.ai_line_proposals ?? []).some((p) => p.outcome === 'failed'))

/** One call at a time. A returned plan replaces the local copy; a refusal leaves the plan and re-reads the gate. */
async function act(call: () => Promise<unknown>, failedKey: string) {
  if (working.value) return
  working.value = true
  failure.value = null
  try {
    const res = (await call()) as Plan | undefined
    emit('changed', res && 'status' in res && 'key' in res ? res : undefined)
  } catch (err: unknown) {
    const kind = classifyConvertError(err)
    failure.value = { kind, message: kind === 'error' ? describeApiError(err, t(failedKey)) : t(`llc.workflowPlanner.convert.${kind}`) }
    emit('changed')
  } finally {
    working.value = false
  }
}

const preview = () => act(() => props.api.previewConversion(props.plan.key), 'llc.workflowPlanner.convert.previewFailed')
const create = () => act(() => props.api.convert(props.plan.key), 'llc.workflowPlanner.convert.convertFailed')
const retry = () => act(() => props.api.retryAiLineProposals(props.plan.key), 'llc.workflowPlanner.convert.retryFailed')

async function approve() {
  if (!canApprove.value) return
  const ok = await confirm({ title: t('llc.workflowPlanner.convert.approveTitle'), message: t('llc.workflowPlanner.convert.approveMessage') })
  if (ok) await act(() => props.api.approve(props.plan.key), 'llc.workflowPlanner.convert.approveFailed')
}
</script>

<template>
  <div data-testid="convert-step" :data-phase="phase">
    <h4 class="mb-2 text-sm font-semibold text-autobot-text-primary">{{ t('llc.workflowPlanner.gate.title') }}</h4>
    <PlannerGateList v-if="gate" :status="plan.status" :gate="gate" />

    <BaseAlert v-if="failure" class="my-3" :variant="failure.kind === 'unavailable' ? 'info' : 'error'" :message="failure.message" :data-testid="`convert-${failure.kind}`" />

    <div class="my-4">
      <PlannerConversionSummary v-if="conversion && phase !== 'not_ready'" :plan="plan" :conversion="conversion" />
      <p v-else-if="phase === 'not_ready'" class="text-sm text-autobot-text-muted" data-testid="convert-not-ready">{{ t('llc.workflowPlanner.convert.notReady') }}</p>
    </div>

    <p v-if="plan.approved_at" class="mb-2 text-sm text-autobot-text-secondary" data-testid="approved-by">
      {{ t('llc.workflowPlanner.convert.approvedBy', { by: plan.approved_by ?? '-', at: plan.approved_at }) }}
    </p>

    <div v-if="phase === 'previewed' && blockers.length" class="mb-3 text-sm text-autobot-text-secondary" data-testid="approve-blockers">
      <p class="font-semibold">{{ t('llc.workflowPlanner.convert.approveBlocked') }}</p>
      <ul>
        <li v-for="b in blockers" :key="b.id" :data-testid="`approve-blocker-${b.id}`">{{ b.id }}: {{ b.messages.join('; ') }}</li>
      </ul>
    </div>

    <div class="flex flex-wrap gap-2">
      <BaseButton v-if="phase === 'needs_preview' || phase === 'previewed'" size="sm" variant="outline" :disabled="stale" :loading="working" data-testid="convert-preview" @click="preview">
        {{ t(phase === 'previewed' ? 'llc.workflowPlanner.convert.previewAgain' : 'llc.workflowPlanner.convert.preview') }}
      </BaseButton>
      <BaseButton v-if="phase === 'previewed'" size="sm" :disabled="working || !canApprove" data-testid="convert-approve" @click="approve">
        {{ t('llc.workflowPlanner.convert.approve') }}
      </BaseButton>
      <BaseButton v-if="phase === 'approved'" size="sm" :disabled="stale" :loading="working" data-testid="convert-create" @click="create">
        {{ t('llc.workflowPlanner.convert.create') }}
      </BaseButton>
      <BaseButton v-if="phase === 'converted' && failedProposals" size="sm" variant="outline" :loading="working" data-testid="convert-retry" @click="retry">
        {{ t('llc.workflowPlanner.convert.retry') }}
      </BaseButton>
    </div>
  </div>
</template>
