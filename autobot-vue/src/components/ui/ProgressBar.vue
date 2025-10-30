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
  margin-bottom: 4px;
  font-size: 0.875rem;
}

.progress-text {
  color: #374151;
  font-weight: 500;
}

.progress-percentage {
  color: #6b7280;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}

.progress-bar {
  background: #f3f4f6;
  overflow: hidden;
  position: relative;
}

.progress-bar.progress-xs { height: 2px; }
.progress-bar.progress-sm { height: 4px; }
.progress-bar.progress-md { height: 8px; }
.progress-bar.progress-lg { height: 12px; }

.progress-rounded .progress-bar {
  border-radius: 9999px;
}

.progress-fill {
  height: 100%;
  transition: width 0.3s ease-in-out;
  position: relative;
  overflow: hidden;
}

.progress-fill-default { background: #3b82f6; }
.progress-fill-success { background: #10b981; }
.progress-fill-warning { background: #f59e0b; }
.progress-fill-error { background: #ef4444; }
.progress-fill-info { background: #06b6d4; }

.progress-fill-complete {
  background: #10b981 !important;
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
    rgba(255, 255, 255, 0.3) 50%,
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
  margin-top: 4px;
  font-size: 0.75rem;
  color: #6b7280;
}

.progress-stats {
  font-variant-numeric: tabular-nums;
}

.progress-eta {
  font-weight: 500;
}

/* Compact layout adjustments */
.progress-compact .progress-label {
  margin-bottom: 0;
  margin-right: 12px;
  flex-shrink: 0;
}

.progress-compact .progress-bar {
  flex: 1;
}

.progress-compact .progress-details {
  margin-top: 0;
  margin-left: 12px;
  flex-shrink: 0;
}

/* Responsive */
@media (max-width: 640px) {
  .progress-label {
    flex-direction: column;
    align-items: flex-start;
    gap: 2px;
  }
  
  .progress-details {
    flex-direction: column;
    align-items: flex-start;
    gap: 2px;
  }
}
</style>