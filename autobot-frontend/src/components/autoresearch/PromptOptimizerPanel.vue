<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->

<script setup lang="ts">
import { ref } from 'vue'
import type { OptimizationSession, PromptVariant } from '@/composables/useAutoResearch'

defineProps<{
  session: OptimizationSession | null
  variants: PromptVariant[]
}>()

const emit = defineEmits<{
  start: [agentName: string, maxRounds: number]
  cancel: []
  scoreVariant: [variantId: string, score: number, comment: string]
}>()

const agentName = ref('autoresearch_hypothesis')
const maxRounds = ref(3)
const reviewScore = ref(5)
const reviewComment = ref('')
const reviewingVariantId = ref<string | null>(null)

function handleStart() {
  emit('start', agentName.value, maxRounds.value)
}

function submitScore(variantId: string) {
  emit('scoreVariant', variantId, reviewScore.value, reviewComment.value)
  reviewingVariantId.value = null
  reviewScore.value = 5
  reviewComment.value = ''
}
</script>

<template>
  <div>
    <h3 class="mb-3 text-lg font-semibold">Prompt Optimizer</h3>

    <!-- Start/Cancel controls -->
    <div v-if="!session" class="mb-4 flex items-end gap-3">
      <div>
        <label class="mb-1 block text-xs text-neutral-500">Target Agent</label>
        <input
          v-model="agentName"
          class="rounded-md border px-3 py-1.5 text-sm dark:border-neutral-600 dark:bg-neutral-800"
        />
      </div>
      <div>
        <label class="mb-1 block text-xs text-neutral-500">Max Rounds</label>
        <input
          v-model.number="maxRounds"
          type="number"
          min="1"
          max="10"
          class="w-20 rounded-md border px-3 py-1.5 text-sm dark:border-neutral-600 dark:bg-neutral-800"
        />
      </div>
      <button
        class="rounded-md bg-blue-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-blue-700"
        @click="handleStart"
      >
        Start Optimization
      </button>
    </div>

    <div v-else class="mb-4">
      <div class="flex items-center gap-3">
        <span class="text-sm">
          Status: <span class="font-medium capitalize">{{ session.status }}</span>
        </span>
        <span class="text-sm text-neutral-500">
          Round {{ session.rounds_completed }}/{{ session.max_rounds }}
        </span>
        <button
          v-if="session.status === 'running'"
          class="rounded-md bg-red-600 px-3 py-1 text-sm text-white hover:bg-red-700"
          @click="emit('cancel')"
        >
          Cancel
        </button>
      </div>
      <div v-if="session.best_variant" class="mt-2 text-sm text-green-600 dark:text-green-400">
        Best score: {{ session.best_variant.final_score.toFixed(3) }}
      </div>
    </div>

    <!-- Variant list -->
    <div v-if="variants.length > 0" class="space-y-2">
      <div
        v-for="variant in variants"
        :key="variant.id"
        class="rounded-md border p-3 text-sm dark:border-neutral-700"
      >
        <div class="mb-1 flex items-center justify-between">
          <span class="font-mono text-xs text-neutral-500">{{ variant.id.slice(0, 8) }}</span>
          <span class="font-medium">Score: {{ variant.final_score.toFixed(3) }}</span>
        </div>
        <p class="mb-2 text-neutral-600 dark:text-neutral-400">
          {{ variant.prompt_text.slice(0, 200) }}{{ variant.prompt_text.length > 200 ? '...' : '' }}
        </p>

        <!-- Human review form -->
        <div v-if="reviewingVariantId === variant.id" class="mt-2 flex items-end gap-2">
          <input
            v-model.number="reviewScore"
            type="number"
            min="0"
            max="10"
            class="w-16 rounded border px-2 py-1 text-sm dark:border-neutral-600 dark:bg-neutral-800"
          />
          <input
            v-model="reviewComment"
            placeholder="Comment..."
            class="flex-1 rounded border px-2 py-1 text-sm dark:border-neutral-600 dark:bg-neutral-800"
          />
          <button
            class="rounded bg-green-600 px-3 py-1 text-sm text-white"
            @click="submitScore(variant.id)"
          >
            Submit
          </button>
        </div>
        <button
          v-else
          class="mt-1 text-xs text-blue-600 hover:underline dark:text-blue-400"
          @click="reviewingVariantId = variant.id"
        >
          Review
        </button>
      </div>
    </div>
  </div>
</template>
