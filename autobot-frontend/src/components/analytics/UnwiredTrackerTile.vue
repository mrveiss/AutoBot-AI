<template>
  <!-- Issue #6871: Modules with zero production callers metric tile -->
  <div
    class="unwired-tracker-tile"
    :class="{ 'has-findings': count > 0 }"
    role="button"
    tabindex="0"
    :aria-label="`Unwired trackers: ${count} modules with zero production callers. Click to view details.`"
    @click="navigateToProblems"
    @keydown.enter="navigateToProblems"
    @keydown.space.prevent="navigateToProblems"
  >
    <!-- Header -->
    <div class="tile-header">
      <span class="tile-icon" aria-hidden="true">{{ count > 0 ? '🔗' : '✅' }}</span>
      <span class="tile-label">Unwired Trackers</span>
      <span v-if="loading" class="tile-loading" aria-label="Loading">…</span>
    </div>

    <!-- Count -->
    <div class="tile-count" :class="countClass">
      <span class="count-value">{{ count }}</span>
      <span class="count-unit">{{ count === 1 ? 'module' : 'modules' }}</span>
    </div>

    <!-- Sparkline (7 points, newest right) -->
    <div class="tile-sparkline" aria-hidden="true">
      <svg
        viewBox="0 0 70 24"
        class="sparkline-svg"
        preserveAspectRatio="none"
      >
        <polyline
          v-if="sparklinePoints.length > 0"
          :points="sparklinePoints"
          fill="none"
          :stroke="sparklineColor"
          stroke-width="1.5"
          stroke-linecap="round"
          stroke-linejoin="round"
        />
      </svg>
    </div>

    <!-- Footer hint -->
    <div class="tile-footer">
      <span class="footer-hint">{{ count > 0 ? 'Click to view →' : 'All wired in' }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * UnwiredTrackerTile
 *
 * Displays the count of modules with zero production callers alongside a
 * sparkline trend and click-through to the problems list filtered to
 * unwired-tracker findings.
 *
 * Issue #6871: Surface 'Modules with zero production callers' metric in the
 * Code Quality Dashboard.
 */
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { getCssVar } from '@/composables/useCssVars'

const props = withDefaults(
  defineProps<{
    /** Current count of unwired-tracker modules */
    count: number
    /** 7-point sparkline array (oldest → newest) */
    sparkline: number[]
    /** Whether data is still loading */
    loading?: boolean
    /** Optional route for click-through (defaults to /codebase/problems?type=...) */
    targetRoute?: string
  }>(),
  {
    loading: false,
    targetRoute: '/codebase/problems?type=code_smell_unwired_tracker',
  },
)

const router = useRouter()

/** CSS class for the count badge based on severity */
const countClass = computed(() => {
  if (props.count === 0) return 'count-ok'
  if (props.count <= 5) return 'count-low'
  if (props.count <= 20) return 'count-medium'
  return 'count-high'
})

/** SVG sparkline color matching count severity */
const sparklineColor = computed(() => {
  if (props.count === 0) return getCssVar('--color-success', '#22c55e')
  if (props.count <= 5) return getCssVar('--color-success', '#22c55e')
  if (props.count <= 20) return getCssVar('--color-warning', '#f59e0b')
  return getCssVar('--color-error', '#ef4444')
})

/**
 * Convert sparkline data array to SVG polyline points string.
 * Maps the 7 values to x=0..70, y=0..24 (inverted — higher count = lower y).
 */
const sparklinePoints = computed<string>(() => {
  const data = props.sparkline
  if (!data || data.length === 0) return ''
  const max = Math.max(...data, 1)
  const step = 70 / Math.max(data.length - 1, 1)
  return data
    .map((v, i) => {
      const x = Math.round(i * step * 10) / 10
      const y = Math.round((1 - v / max) * 20 * 10) / 10 + 2 // 2px top padding
      return `${x},${y}`
    })
    .join(' ')
})

function navigateToProblems(): void {
  router.push(props.targetRoute)
}
</script>

<style scoped>
/* Issue #6871: UnwiredTrackerTile — uses design tokens for theming */
.unwired-tracker-tile {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-2);
  padding: var(--spacing-4);
  background: var(--bg-card);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-xl);
  cursor: pointer;
  transition: var(--transition-all);
  user-select: none;
}

.unwired-tracker-tile:hover,
.unwired-tracker-tile:focus-visible {
  border-color: var(--color-info);
  transform: translateY(-2px);
  outline: 2px solid var(--color-info);
  outline-offset: 2px;
}

.unwired-tracker-tile.has-findings {
  border-color: var(--color-warning-border, var(--color-warning));
}

.unwired-tracker-tile.has-findings:hover,
.unwired-tracker-tile.has-findings:focus-visible {
  border-color: var(--color-warning);
}

/* Header */
.tile-header {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
}

.tile-icon {
  font-size: var(--text-lg);
  line-height: 1;
}

.tile-label {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  flex: 1;
}

.tile-loading {
  font-size: var(--text-sm);
  color: var(--text-tertiary);
  animation: blink 1s step-start infinite;
}

@keyframes blink {
  50% { opacity: 0; }
}

/* Count */
.tile-count {
  display: flex;
  align-items: baseline;
  gap: var(--spacing-1);
}

.count-value {
  font-size: var(--text-3xl);
  font-weight: var(--font-bold);
  line-height: var(--leading-none);
  transition: color var(--duration-300);
}

.count-unit {
  font-size: var(--text-sm);
  color: var(--text-muted);
}

/* Count severity colors */
.count-ok .count-value   { color: var(--color-success); }
.count-low .count-value  { color: var(--color-success); }
.count-medium .count-value { color: var(--color-warning); }
.count-high .count-value { color: var(--color-error); }

/* Sparkline */
.tile-sparkline {
  height: 24px;
  width: 100%;
}

.sparkline-svg {
  width: 100%;
  height: 100%;
}

/* Footer */
.tile-footer {
  margin-top: var(--spacing-1);
}

.footer-hint {
  font-size: var(--text-xs);
  color: var(--text-tertiary);
}

.unwired-tracker-tile:hover .footer-hint,
.unwired-tracker-tile:focus-visible .footer-hint {
  color: var(--color-info);
}
</style>
