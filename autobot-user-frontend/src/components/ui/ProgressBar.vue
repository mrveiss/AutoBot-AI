<template>
  <div class="progress-container" :class="containerClass">
    <div v-if="showLabel || $slots.label" class="progress-label">
      <slot name="label">
        <span class="progress-text">{{ label }}</span>
        <span v-if="showPercentage" class="progress-percentage">{{ Math.round(progress) }}%</span>
      </slot>
    </div>

    <div class="progress-bar" :class="barClass">
      <div
        class="progress-fill"
        :class="fillClass"
        :style="progressStyle"
      >
        <div v-if="animated" class="progress-animation"></div>
      </div>
    </div>

    <div v-if="showDetails || $slots.details" class="progress-details">
      <slot name="details">
        <span v-if="current && total" class="progress-stats">
          {{ formatSize(current) }} / {{ formatSize(total) }}
        </span>
        <span v-if="eta" class="progress-eta">
          {{ formatTime(eta) }} remaining
        </span>
      </slot>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { formatFileSize } from '@/utils/formatHelpers'

interface Props {
  progress: number // 0-100
  variant?: 'default' | 'success' | 'warning' | 'error' | 'info'
  size?: 'xs' | 'sm' | 'md' | 'lg'
  animated?: boolean
  indeterminate?: boolean
  label?: string
  showLabel?: boolean
  showPercentage?: boolean
  showDetails?: boolean
  current?: number
  total?: number
  eta?: number // estimated time remaining in seconds
  rounded?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  variant: 'default',
  size: 'md',
  animated: true,
  indeterminate: false,
  showLabel: false,
  showPercentage: true,
  showDetails: false,
  rounded: true
})

const containerClass = computed(() => ({
  'progress-compact': !props.showLabel && !props.showDetails,
  'progress-rounded': props.rounded
}))

const barClass = computed(() => ({
  [`progress-${props.size}`]: true,
  'progress-indeterminate': props.indeterminate
}))

const fillClass = computed(() => ({
  [`progress-fill-${props.variant}`]: true,
  'progress-fill-animated': props.animated,
  'progress-fill-complete': props.progress >= 100
}))

const progressStyle = computed(() => {
  if (props.indeterminate) {
    return {}
  }

  return {
    width: `${Math.min(Math.max(props.progress, 0), 100)}%`,
    transition: props.animated ? 'width 0.3s ease-in-out' : 'none'
  }
})

// Utility functions
// Use shared file size formatting utility
const formatSize = formatFileSize

const formatTime = (seconds: number): string => {
  if (seconds < 60) return `${Math.round(seconds)}s`
  if (seconds < 3600) return `${Math.round(seconds / 60)}m ${Math.round(seconds % 60)}s`
  return `${Math.round(seconds / 3600)}h ${Math.round((seconds % 3600) / 60)}m`
}
</script>

<style scoped>
/* Issue #704: Migrated to CSS design tokens */
.progress-container {
  width: 100%;
}

.progress-container.progress-compact {
  display: flex;
  align-items: center;
}

.progress-label {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--spacing-1);
  font-size: var(--text-sm);
}

.progress-text {
  color: var(--text-primary);
  font-weight: var(--font-medium);
}

.progress-percentage {
  color: var(--text-secondary);
  font-weight: var(--font-semibold);
  font-variant-numeric: tabular-nums;
}

.progress-bar {
  background: var(--bg-tertiary);
  overflow: hidden;
  position: relative;
}

.progress-bar.progress-xs { height: 2px; }
.progress-bar.progress-sm { height: 4px; }
.progress-bar.progress-md { height: 8px; }
.progress-bar.progress-lg { height: 12px; }

.progress-rounded .progress-bar {
  border-radius: var(--radius-full);
}

.progress-fill {
  height: 100%;
  transition: width var(--duration-300) var(--ease-in-out);
  position: relative;
  overflow: hidden;
}

.progress-fill-default { background: var(--color-primary); }
.progress-fill-success { background: var(--color-success); }
.progress-fill-warning { background: var(--color-warning); }
.progress-fill-error { background: var(--color-error); }
.progress-fill-info { background: var(--color-info); }

.progress-fill-complete {
  background: var(--color-success) !important;
}

.progress-animation {
  position: absolute;
  top: 0;
  left: 0;
  bottom: 0;
  right: 0;
  background: linear-gradient(
    to right,
    transparent 0%,
    var(--bg-primary-transparent) 50%,
    transparent 100%
  );
  animation: progress-shimmer 2s infinite;
}

@keyframes progress-shimmer {
  0% { transform: translateX(-100%); }
  100% { transform: translateX(100%); }
}

/* Indeterminate progress */
.progress-indeterminate .progress-fill {
  width: 30% !important;
  animation: progress-indeterminate 1.5s ease-in-out infinite;
}

@keyframes progress-indeterminate {
  0% {
    transform: translateX(-100%);
  }
  50% {
    transform: translateX(100%);
  }
  100% {
    transform: translateX(300%);
  }
}

.progress-details {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: var(--spacing-1);
  font-size: var(--text-xs);
  color: var(--text-secondary);
}

.progress-stats {
  font-variant-numeric: tabular-nums;
}

.progress-eta {
  font-weight: var(--font-medium);
}

/* Compact layout adjustments */
.progress-compact .progress-label {
  margin-bottom: 0;
  margin-right: var(--spacing-3);
  flex-shrink: 0;
}

.progress-compact .progress-bar {
  flex: 1;
}

.progress-compact .progress-details {
  margin-top: 0;
  margin-left: var(--spacing-3);
  flex-shrink: 0;
}

/* Responsive */
@media (max-width: 640px) {
  .progress-label {
    flex-direction: column;
    align-items: flex-start;
    gap: var(--spacing-0-5);
  }

  .progress-details {
    flex-direction: column;
    align-items: flex-start;
    gap: var(--spacing-0-5);
  }
}
</style>
