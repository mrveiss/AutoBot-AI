<!--
  Copyright 2025-2026 mrveiss
  SPDX-License-Identifier: Apache-2.0

  StepApprovalCard — the persistent prompt for a workflow step the executor has parked
  in `waiting_approval` (#17677). It is the shared ApprovalEnvelope (#13421) filled with
  the step; it is not a second approval UI. The card owns no state about whether the step
  is still waiting: the parent renders it from the server's step status, so it survives a
  reload or a missed socket frame and leaves only when the status does. `approve` / `skip`
  are the owner's answer calls; the card holds `deciding` while one is in flight so a
  second click cannot send the decision twice.
-->
<script lang="ts">
/** Answers a waiting step; resolves once the owner has sent the decision. */
export type StepAnswer = (workflowId: string, stepId: string) => Promise<unknown>
</script>

<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import ApprovalEnvelope from '@/components/approvals/ApprovalEnvelope.vue'
import type { WorkflowStep } from '@/composables/useWorkflowBuilder'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('StepApprovalCard')

const props = defineProps<{
  step: WorkflowStep
  workflowId: string
  approve: StepAnswer
  skip: StepAnswer
}>()

const { t } = useI18n()
const deciding = ref(false)

async function decide(answer: StepAnswer): Promise<void> {
  if (deciding.value) return
  deciding.value = true
  try {
    await answer(props.workflowId, props.step.step_id)
  } catch (error) {
    // The owner reports the failure to the user; the step is still waiting, so the card stays.
    logger.error('Step answer rejected:', error)
  } finally {
    deciding.value = false
  }
}
</script>

<template>
  <div class="my-3" role="region" aria-live="polite" :aria-label="t('workflow.builder.stepApprovalTitle')">
    <ApprovalEnvelope
      icon="clock"
      :title="t('workflow.builder.stepApprovalTitle')"
      :risk="step.risk_tier ?? undefined"
      :approve-label="t('workflow.runner.approve')"
      :reject-label="t('workflow.builder.stepApprovalSkip')"
      :deciding="deciding"
      @approve="decide(approve)"
      @reject="decide(skip)"
    >
      <p class="mb-2">{{ step.description }}</p>
      <code class="block overflow-x-auto">{{ step.command }}</code>
    </ApprovalEnvelope>
  </div>
</template>
