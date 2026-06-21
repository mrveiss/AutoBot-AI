<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025-2026 mrveiss -->
<!-- Author: mrveiss -->
<!--
  Sparkline (GH#10232) — a tiny inline SVG trend line for card metrics
  (e.g. project velocity history). Renders nothing when fewer than two points
  are available, so cards stay clean for new/empty projects.
-->
<template>
  <svg
    v-if="points.length >= 2"
    class="sparkline"
    :width="width"
    :height="height"
    :viewBox="`0 0 ${width} ${height}`"
    role="img"
    :aria-label="ariaLabel"
    preserveAspectRatio="none"
  >
    <polyline :points="polyline" fill="none" :stroke="stroke" stroke-width="1.5" stroke-linejoin="round" />
  </svg>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(
  defineProps<{
    points: number[]
    width?: number
    height?: number
    stroke?: string
    ariaLabel?: string
  }>(),
  {
    width: 96,
    height: 24,
    stroke: 'var(--color-accent, #c4651a)',
    ariaLabel: 'trend',
  },
)

// Map the values into SVG coordinates, normalising the y-axis to the observed
// min/max so a flat series renders as a centred horizontal line (no divide-by-zero).
const polyline = computed<string>(() => {
  const vals = props.points
  const min = Math.min(...vals)
  const max = Math.max(...vals)
  const span = max - min || 1
  const stepX = props.width / (vals.length - 1)
  const pad = 2
  const usableH = props.height - pad * 2
  return vals
    .map((v, i) => {
      const x = i * stepX
      const y = pad + usableH - ((v - min) / span) * usableH
      return `${x.toFixed(1)},${y.toFixed(1)}`
    })
    .join(' ')
})
</script>

<style scoped>
.sparkline {
  display: block;
}
</style>
