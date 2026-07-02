<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->

<script setup lang="ts">
import { ref } from 'vue'

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
  <div class="rounded-lg border border-amber-200 bg-amber-50 p-4 dark:border-amber-800 dark:bg-amber-950">
    <div class="mb-2 flex items-center gap-2">
      <span class="inline-block h-2 w-2 rounded-full bg-amber-500"></span>
      <span class="text-sm font-medium text-amber-800 dark:text-amber-200">
        Approval Required
      </span>
    </div>

    <div v-if="approval.metrics" class="mb-3 grid grid-cols-2 gap-2 text-sm">
      <div>
        <span class="text-autobot-text-muted">Baseline val_bpb:</span>
        <span class="ml-1 font-mono">{{ approval.metrics.baseline_val_bpb?.toFixed(4) ?? '---' }}</span>
      </div>
      <div>
        <span class="text-autobot-text-muted">Result val_bpb:</span>
        <span class="ml-1 font-mono">{{ approval.metrics.result_val_bpb?.toFixed(4) ?? '---' }}</span>
      </div>
      <div v-if="approval.metrics.improvement_pct != null" class="col-span-2">
        <span class="text-autobot-text-muted">Improvement:</span>
        <span class="ml-1 font-mono text-green-600 dark:text-green-400">
          {{ approval.metrics.improvement_pct.toFixed(2) }}%
        </span>
      </div>
    </div>

    <div class="flex gap-2">
      <button
        :disabled="deciding"
        class="rounded-md bg-green-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-green-700 disabled:opacity-50"
        @click="handleApprove"
      >
        Approve
      </button>
      <button
        :disabled="deciding"
        class="rounded-md bg-red-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-red-700 disabled:opacity-50"
        @click="handleReject"
      >
        Reject
      </button>
    </div>
  </div>
</template>
