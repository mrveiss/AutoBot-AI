<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->

<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import ApprovalEnvelope from '@/components/approvals/ApprovalEnvelope.vue'

interface ApprovalDetails {
  sessionId: string
  experimentId: string
  topic?: string
  iteration?: number
  metrics?: {
    baseline_val_bpb?: number
    result_val_bpb?: number
    improvement?: number
    improvement_pct?: number
  }
}

const props = defineProps<{
  approval: ApprovalDetails
}>()

const emit = defineEmits<{
  approve: [sessionId: string, experimentId: string]
  reject: [sessionId: string, experimentId: string]
}>()

const { t } = useI18n()
const deciding = ref(false)

async function handleApprove() {
  deciding.value = true
  emit('approve', props.approval.sessionId, props.approval.experimentId)
}

async function handleReject() {
  deciding.value = true
  emit('reject', props.approval.sessionId, props.approval.experimentId)
}
</script>

<template>
  <ApprovalEnvelope
    :title="t('research.approval.title')"
    :deciding="deciding"
    @approve="handleApprove"
    @reject="handleReject"
  >
    <div v-if="approval.metrics" class="grid grid-cols-2 gap-2 text-sm">
      <div>
        <span class="text-autobot-text-muted">{{ t('research.approval.baseline') }}</span>
        <span class="ml-1 font-mono">{{ approval.metrics.baseline_val_bpb?.toFixed(4) ?? '---' }}</span>
      </div>
      <div>
        <span class="text-autobot-text-muted">{{ t('research.approval.result') }}</span>
        <span class="ml-1 font-mono">{{ approval.metrics.result_val_bpb?.toFixed(4) ?? '---' }}</span>
      </div>
      <div v-if="approval.metrics.improvement_pct != null" class="col-span-2">
        <span class="text-autobot-text-muted">{{ t('research.approval.improvement') }}</span>
        <span class="ml-1 font-mono text-autobot-success">
          {{ approval.metrics.improvement_pct.toFixed(2) }}%
        </span>
      </div>
    </div>
  </ApprovalEnvelope>
</template>
