<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->

<script setup lang="ts">
import { onMounted, onUnmounted } from 'vue'
import { useAutoResearch } from '@/composables/useAutoResearch'
import ExperimentTimeline from '@/components/autoresearch/ExperimentTimeline.vue'
import PromptOptimizerPanel from '@/components/autoresearch/PromptOptimizerPanel.vue'
import InsightsPanel from '@/components/autoresearch/InsightsPanel.vue'

const {
  experiments,
  stats,
  loading,
  optimizerStatus,
  variants,
  pendingApprovals,
  insights,
  fetchExperiments,
  fetchStats,
  fetchPendingApprovals,
  fetchInsights,
  startOptimization,
  cancelOptimization,
  scoreVariant,
  approveExperiment,
  rejectExperiment,
  searchInsights,
  startPolling,
  stopPolling,
} = useAutoResearch()

onMounted(async () => {
  await Promise.all([
    fetchExperiments(),
    fetchStats(),
    fetchPendingApprovals(),
    fetchInsights(),
  ])
  startPolling(15000)
})

onUnmounted(() => {
  stopPolling()
})

async function handleStartOptimization(agentName: string, maxRounds: number) {
  await startOptimization(agentName, maxRounds)
}

async function handleScoreVariant(variantId: string, score: number, comment: string) {
  if (optimizerStatus.value) {
    await scoreVariant(variantId, optimizerStatus.value.id, score, comment)
  }
}

async function handleApprove(sessionId: string, experimentId: string) {
  await approveExperiment(sessionId, experimentId)
}

async function handleReject(sessionId: string, experimentId: string) {
  await rejectExperiment(sessionId, experimentId)
}
</script>

<template>
  <div class="mx-auto max-w-7xl space-y-6 p-6 view-container">
    <h1 class="text-2xl font-bold">Experiment Dashboard</h1>

    <!-- Stats Header -->
    <div v-if="stats" class="grid grid-cols-2 gap-4 sm:grid-cols-4">
      <div class="rounded-lg border p-4">
        <div class="text-2xl font-bold">{{ stats.total_experiments }}</div>
        <div class="text-sm text-autobot-text-muted">Total Experiments</div>
      </div>
      <div class="rounded-lg border p-4">
        <div class="text-2xl font-bold text-emerald-600">{{ stats.kept }}</div>
        <div class="text-sm text-autobot-text-muted">Kept</div>
      </div>
      <div class="rounded-lg border p-4">
        <div class="text-2xl font-bold text-orange-600">{{ stats.discarded }}</div>
        <div class="text-sm text-autobot-text-muted">Discarded</div>
      </div>
      <div class="rounded-lg border p-4">
        <div class="text-2xl font-bold font-mono">
          {{ stats.best_val_bpb?.toFixed(4) ?? '---' }}
        </div>
        <div class="text-sm text-autobot-text-muted">Best val_bpb</div>
      </div>
    </div>

    <!-- Loading indicator -->
    <div v-if="loading" class="py-4 text-center text-autobot-text-muted">
      Loading experiments...
    </div>

    <!-- Main content grid -->
    <div class="grid gap-6 lg:grid-cols-3">
      <!-- Timeline (2/3 width) -->
      <div class="lg:col-span-2">
        <h2 class="mb-3 text-lg font-semibold">Experiment Timeline</h2>
        <ExperimentTimeline
          :experiments="experiments"
          :pending-approvals="pendingApprovals"
          @approve="handleApprove"
          @reject="handleReject"
        />
      </div>

      <!-- Right sidebar (1/3 width) -->
      <div class="space-y-6">
        <PromptOptimizerPanel
          :session="optimizerStatus"
          :variants="variants"
          @start="handleStartOptimization"
          @cancel="cancelOptimization"
          @score-variant="handleScoreVariant"
        />

        <InsightsPanel
          :insights="insights"
          @search="searchInsights"
        />
      </div>
    </div>
  </div>
</template>
