<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->

<script setup lang="ts">
import { ref } from 'vue'
import type { ExperimentInsight } from '@/composables/useAutoResearch'

defineProps<{
  insights: ExperimentInsight[]
}>()

const emit = defineEmits<{
  search: [query: string]
}>()

const searchQuery = ref('')

function handleSearch() {
  if (searchQuery.value.trim()) {
    emit('search', searchQuery.value.trim())
  }
}

function confidenceColor(confidence: number): string {
  if (confidence >= 0.8) return 'text-green-600 dark:text-green-400'
  if (confidence >= 0.5) return 'text-amber-600 dark:text-amber-400'
  return 'text-red-600 dark:text-red-400'
}
</script>

<template>
  <div>
    <h3 class="mb-3 text-lg font-semibold">Experiment Insights</h3>

    <!-- Search -->
    <div class="mb-4 flex gap-2">
      <input
        v-model="searchQuery"
        placeholder="Search insights..."
        class="flex-1 rounded-md border px-3 py-1.5 text-sm"
        @keyup.enter="handleSearch"
      />
      <button
        class="rounded-md bg-blue-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-blue-700"
        @click="handleSearch"
      >
        Search
      </button>
    </div>

    <!-- Insights list -->
    <div v-if="insights.length === 0" class="py-4 text-center text-sm text-autobot-text-muted">
      No insights yet. Run experiments and trigger synthesis.
    </div>

    <div v-else class="space-y-2">
      <div
        v-for="insight in insights"
        :key="insight.id"
        class="rounded-md border p-3"
      >
        <div class="mb-1 flex items-center justify-between">
          <span :class="confidenceColor(insight.confidence)" class="text-xs font-medium">
            {{ (insight.confidence * 100).toFixed(0) }}% confidence
          </span>
          <span class="text-xs text-autobot-text-muted">
            {{ insight.related_hyperparams.join(', ') }}
          </span>
        </div>
        <p class="text-sm text-autobot-text-secondary">
          {{ insight.statement }}
        </p>
        <div class="mt-1 text-xs text-autobot-text-muted">
          Based on {{ insight.supporting_experiments.length }} experiment(s)
        </div>
      </div>
    </div>
  </div>
</template>
