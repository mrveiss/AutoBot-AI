<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<!-- Author: mrveiss -->
<!-- Issue #772 - Code Intelligence Health Score Gauge -->

<template>
  <div class="health-score-gauge">
    <div class="gauge-container">
      <svg viewBox="0 0 120 80" class="gauge-svg">
        <!-- Background arc -->
        <path
          :d="backgroundArc"
          fill="none"
          stroke="var(--bg-tertiary)"
          stroke-width="12"
          stroke-linecap="round"
        />
        <!-- Score arc -->
        <path
          :d="scoreArc"
          fill="none"
          :stroke="scoreColor"
          stroke-width="12"
          stroke-linecap="round"
          class="score-arc"
        />
      </svg>
      <div class="score-display">
        <span class="score-value">{{ score }}</span>
        <span class="score-grade" :style="{ color: scoreColor }">{{ grade }}</span>
      </div>
    </div>
    <div class="gauge-label">{{ label }}</div>
    <div v-if="statusMessage" class="status-message">{{ statusMessage }}</div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  score: number
  grade: string
  label: string
  statusMessage?: string
}>()

const scoreColor = computed(() => {
  if (props.score >= 90) return 'var(--chart-green)'
  if (props.score >= 80) return 'var(--color-info-dark)'
  if (props.score >= 70) return 'var(--chart-yellow, #f59e0b)'
  if (props.score >= 50) return 'var(--chart-orange, #f97316)'
  return 'var(--chart-red, #ef4444)'
})

// SVG arc calculations
const radius = 50
const centerX = 60
const centerY = 70

function polarToCartesian(angle: number) {
  const radians = (angle - 180) * Math.PI / 180
  return {
    x: centerX + radius * Math.cos(radians),
    y: centerY + radius * Math.sin(radians)
  }
}

const backgroundArc = computed(() => {
  const start = polarToCartesian(0)
  const end = polarToCartesian(180)
  return `M ${start.x} ${start.y} A ${radius} ${radius} 0 0 1 ${end.x} ${end.y}`
})

const scoreArc = computed(() => {
  const scoreAngle = (props.score / 100) * 180
  const start = polarToCartesian(0)
  const end = polarToCartesian(scoreAngle)
  const largeArc = scoreAngle > 90 ? 1 : 0
  return `M ${start.x} ${start.y} A ${radius} ${radius} 0 ${largeArc} 1 ${end.x} ${end.y}`
})
</script>

<style scoped>
.health-score-gauge {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: var(--spacing-4);
}

.gauge-container {
  position: relative;
  width: 120px;
  height: 80px;
}

.gauge-svg {
  width: 100%;
  height: 100%;
}

.score-arc {
  transition: stroke-dasharray 0.5s ease;
}

.score-display {
  position: absolute;
  bottom: 0;
  left: 50%;
  transform: translateX(-50%);
  text-align: center;
}

.score-value {
  font-size: 1.5rem;
  font-weight: var(--font-semibold);
  color: var(--text-primary);
}

.score-grade {
  display: block;
  font-size: 0.875rem;
  font-weight: var(--font-medium);
}

.gauge-label {
  margin-top: var(--spacing-2);
  font-size: 0.875rem;
  color: var(--text-secondary);
  font-weight: var(--font-medium);
}

.status-message {
  margin-top: var(--spacing-1);
  font-size: 0.75rem;
  color: var(--text-tertiary);
  text-align: center;
  max-width: 150px;
}
</style>
