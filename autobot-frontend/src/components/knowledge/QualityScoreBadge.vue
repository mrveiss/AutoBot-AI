<template>
  <span
    class="quality-badge"
    :class="qualityClass"
    :title="$t('knowledge.qualityScore.title', { score: (safeScore * 100).toFixed(0) })"
  >
    {{ (safeScore * 100).toFixed(0) }}%
  </span>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  score: number | null | undefined
}>()

const safeScore = computed(() => props.score ?? 0)

const qualityClass = computed(() => {
  if (safeScore.value >= 0.8) return 'quality-high'
  if (safeScore.value >= 0.5) return 'quality-medium'
  return 'quality-low'
})
</script>

<style scoped>
.quality-badge {
  display: inline-block;
  padding: var(--spacing-0-5) var(--spacing-2);
  border-radius: var(--radius-xs);
  font-size: var(--text-xs);
  font-weight: 600;
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
  letter-spacing: -0.02em;
  white-space: nowrap;
}

.quality-high {
  background: var(--color-success-bg);
  color: var(--color-success);
  border: 1px solid var(--color-success-border);
}

.quality-medium {
  background: var(--color-warning-bg);
  color: var(--color-warning);
  border: 1px solid var(--color-warning-border);
}

.quality-low {
  background: var(--color-error-bg);
  color: var(--color-error);
  border: 1px solid var(--color-error-border);
}
</style>
