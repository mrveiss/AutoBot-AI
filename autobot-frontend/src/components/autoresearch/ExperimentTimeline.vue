<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->

<script setup lang="ts">
import { computed } from 'vue'
import type { Experiment } from '@/composables/useAutoResearch'
import ApprovalCard from './ApprovalCard.vue'

const props = defineProps<{
  experiments: Experiment[]
  pendingApprovals: Array<{
    session_id: string
    experiment_id: string
    details: Record<string, unknown>
  }>
}>()

const emit = defineEmits<{
  approve: [sessionId: string, experimentId: string]
  reject: [sessionId: string, experimentId: string]
}>()

const stateColors: Record<string, string> = {
  pending: 'bg-neutral-400',
  running: 'bg-blue-500',
  completed: 'bg-green-500',
  failed: 'bg-red-500',
  kept: 'bg-emerald-600',
  discarded: 'bg-orange-500',
}

const sortedExperiments = computed(() =>
  [...props.experiments].sort((a, b) => b.created_at - a.created_at),
)

function formatTime(timestamp: number): string {
  return new Date(timestamp * 1000).toLocaleString()
}

function getApproval(experimentId: string) {
  return props.pendingApprovals.find((a) => a.experiment_id === experimentId)
}
</script>

<template>
  <div class="space-y-3">
    <div v-if="sortedExperiments.length === 0" class="py-8 text-center text-autobot-text-muted">
      No experiments yet
    </div>

    <div
      v-for="exp in sortedExperiments"
      :key="exp.id"
      class="rounded-lg border border-autobot-border p-4"
    >
      <div class="mb-2 flex items-center justify-between">
        <div class="flex items-center gap-2">
          <span
            :class="stateColors[exp.state] ?? 'bg-neutral-400'"
            class="inline-block h-2 w-2 rounded-full"
          ></span>
          <span class="text-sm font-medium capitalize">{{ exp.state }}</span>
        </div>
        <span class="text-xs text-autobot-text-muted">{{ formatTime(exp.created_at) }}</span>
      </div>

      <p class="mb-2 text-sm text-autobot-text-secondary">
        {{ exp.hypothesis || 'No hypothesis' }}
      </p>

      <div v-if="exp.result" class="flex gap-4 text-xs text-autobot-text-muted">
        <span v-if="exp.result.val_bpb != null">
          val_bpb: <span class="font-mono">{{ exp.result.val_bpb.toFixed(4) }}</span>
        </span>
        <span v-if="exp.result.wall_time_seconds > 0">
          {{ exp.result.wall_time_seconds.toFixed(0) }}s
        </span>
        <span v-if="exp.result.tokens_per_second != null">
          {{ exp.result.tokens_per_second.toFixed(0) }} tok/s
        </span>
      </div>

      <!-- Inline approval card -->
      <ApprovalCard
        v-if="getApproval(exp.id)"
        :approval="{
          sessionId: getApproval(exp.id)!.session_id,
          experimentId: exp.id,
          metrics: exp.result
            ? {
                baseline_val_bpb: exp.baseline_val_bpb ?? undefined,
                result_val_bpb: exp.result.val_bpb ?? undefined,
              }
            : undefined,
        }"
        class="mt-3"
        @approve="(sid: string, eid: string) => emit('approve', sid, eid)"
        @reject="(sid: string, eid: string) => emit('reject', sid, eid)"
      />
    </div>
  </div>
</template>
