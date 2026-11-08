<!--
  Copyright 2025-2026 mrveiss
  SPDX-License-Identifier: Apache-2.0

  WaitingForYou — what is waiting for the signed-in person to decide, whatever page started it
  (#20917). The rows come from the approvals store and each is one ApprovalEnvelope, the frame
  every approval surface shares. Removal proposals (destructive_action) stay with the cleanup
  panel, which shows them with the files they concern.
-->
<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import ApprovalEnvelope from '@/components/approvals/ApprovalEnvelope.vue'
import { useApprovalGatesStore } from '@/stores/useApprovalGatesStore'

const { t } = useI18n()
const store = useApprovalGatesStore()
const rows = computed(() => store.pending.filter((row) => row.approval_type !== 'destructive_action'))

function command(row: (typeof rows.value)[number]): string | null {
  const value = row.context?.command
  return typeof value === 'string' ? value : null
}
</script>

<template>
  <section v-if="rows.length > 0" class="space-y-3 mb-6" data-testid="waiting-for-you">
    <h3 class="text-lg font-semibold text-autobot-text-primary">{{ t('approvals.inbox.waitingForYou') }}</h3>
    <ApprovalEnvelope
      v-for="row in rows"
      :key="row.id"
      :title="row.title"
      :risk="row.risk_tier ?? undefined"
      :deciding="store.deciding.has(row.id)"
      :reject-label="row.source === 'workflow_step' ? t('approvals.inbox.skipStep') : undefined"
      @approve="store.decide(row.id, 'approve')"
      @reject="store.decide(row.id, 'reject')"
    >
      <p v-if="row.description" class="text-autobot-text-secondary">{{ row.description }}</p>
      <code v-if="command(row)" class="block mt-2 text-sm text-autobot-text-primary">{{ command(row) }}</code>
    </ApprovalEnvelope>
  </section>
</template>
