<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->

<script setup lang="ts">
import { computed } from 'vue'
import type { Experiment } from '@/composables/useAutoResearch'

const props = defineProps<{
  experiment: Experiment
}>()

const stateLabel: Record<string, string> = {
  pending: 'Pending',
  running: 'Running',
  completed: 'Completed',
  failed: 'Failed',
  kept: 'Kept',
  discarded: 'Discarded',
}

const stateBadgeClass = computed(() => {
  const classes: Record<string, string> = {
    pending: 'bg-neutral-100 text-neutral-600',
    running: 'bg-blue-100 text-blue-700',
    completed: 'bg-green-100 text-green-700',
    failed: 'bg-red-100 text-red-700',
    kept: 'bg-emerald-100 text-emerald-700',
    discarded: 'bg-orange-100 text-orange-700',
  }
  return classes[props.experiment.state] ?? 'bg-neutral-100 text-neutral-600'
})
</script>

<template>
  <div class="flex items-center gap-3 rounded-md border p-3 text-sm dark:border-neutral-700">
    <span
      :class="stateBadgeClass"
      class="rounded-full px-2 py-0.5 text-xs font-medium"
    >
      {{ stateLabel[experiment.state] ?? experiment.state }}
    </span>

    <span class="flex-1 truncate text-neutral-700 dark:text-neutral-300">
      {{ experiment.hypothesis || 'AutoResearch experiment' }}
    </span>

    <span
      v-if="experiment.result?.val_bpb != null"
      class="font-mono text-xs text-neutral-500"
    >
      {{ experiment.result.val_bpb.toFixed(4) }}
    </span>

    <router-link
      to="/experiments"
      class="text-xs text-blue-600 hover:underline dark:text-blue-400"
    >
      Details
    </router-link>
  </div>
</template>
