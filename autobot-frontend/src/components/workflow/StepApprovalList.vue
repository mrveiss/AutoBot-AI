<!--
  Copyright 2025-2026 mrveiss
  SPDX-License-Identifier: Apache-2.0
  AutoBot - AI-Powered Automation Platform
  Author: mrveiss

  StepApprovalList: the StepApprovalCards in a bounded vertical scroll region (#21033), so
  tall prompts never push the approve / skip buttons out of reach. Rendered outside the
  loading / error / content switch, so the bound applies in every state.
-->
<template>
  <div v-if="steps.length" class="step-approval-list" data-testid="step-approval-list">
    <StepApprovalCard
      v-for="s in steps"
      :key="s.step_id"
      :step="s"
      :workflow-id="workflowId"
      :approve="approve"
      :skip="skip"
    />
  </div>
</template>

<script setup lang="ts">
import StepApprovalCard from '@/components/workflow/StepApprovalCard.vue'

type Props = InstanceType<typeof StepApprovalCard>['$props']

defineProps<{
  steps: Array<Props['step']>
  workflowId: string
  approve: Props['approve']
  skip: Props['skip']
}>()
</script>

<style scoped>
.step-approval-list {
  max-height: calc(var(--view-min-height) / 2);
  overflow-y: auto;
  scrollbar-width: thin;
  scrollbar-color: var(--scrollbar-thumb) var(--scrollbar-track);
}

.step-approval-list::-webkit-scrollbar {
  width: var(--scrollbar-width);
}

.step-approval-list::-webkit-scrollbar-track {
  background: var(--scrollbar-track);
}

.step-approval-list::-webkit-scrollbar-thumb {
  background: var(--scrollbar-thumb);
  border-radius: var(--scrollbar-thumb-radius);
}
</style>
