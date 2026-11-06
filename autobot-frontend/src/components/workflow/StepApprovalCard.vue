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
  } finally {
    deciding.value = false
  }
}
</script>

<template>
  <ApprovalEnvelope
    class="step-approval-card"
    icon="clock"
    :title="t('workflow.builder.stepApprovalTitle')"
    :risk="step.risk_tier ?? undefined"
    :approve-label="t('workflow.runner.approve')"
    :reject-label="t('workflow.builder.stepApprovalSkip')"
    :deciding="deciding"
    @approve="decide(approve)"
    @reject="decide(skip)"
  >
    <p class="step-approval-description">{{ step.description }}</p>
    <code class="step-approval-command">{{ step.command }}</code>
  </ApprovalEnvelope>
</template>

<style scoped>
.step-approval-card { margin: var(--spacing-3) 0; }
.step-approval-description { margin: var(--spacing-0) var(--spacing-0) var(--spacing-2); color: var(--text-primary); }
.step-approval-command { display: block; padding: var(--spacing-2); background: var(--bg-tertiary); border-radius: var(--radius-default); color: var(--text-secondary); overflow-x: auto; }
</style>
