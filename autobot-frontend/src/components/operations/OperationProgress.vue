<!--
  AutoBot - AI-Powered Automation Platform
  Copyright (c) 2025 mrveiss
  Author: mrveiss

  Operation Progress Component
  Issue #591 - Long-Running Operations Tracker
-->
<template>
  <div class="operation-progress" :class="progressClasses">
    <!-- Progress bar -->
    <div class="progress-bar-container">
      <div
        class="progress-bar"
        :style="{ width: `${progress}%` }"
        :class="progressBarClasses"
      ></div>
    </div>

    <!-- Progress info -->
    <div class="progress-info" v-if="showInfo">
      <span class="progress-percentage">{{ progress }}%</span>
      <span class="progress-items" v-if="showItems">
        {{ processedItems }} / {{ estimatedItems }}
      </span>
    </div>

    <!-- Current step -->
    <div class="progress-step" v-if="currentStep && showStep">
      <i class="fas fa-cog fa-spin step-icon" v-if="isRunning"></i>
      <span class="step-text">{{ currentStep }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { OperationStatus } from '@/types/operations'

interface Props {
  progress: number
  status: OperationStatus
  processedItems?: number
  estimatedItems?: number
  currentStep?: string
  size?: 'small' | 'medium' | 'large'
  showInfo?: boolean
  showItems?: boolean
  showStep?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  processedItems: 0,
  estimatedItems: 0,
  currentStep: '',
  size: 'medium',
  showInfo: true,
  showItems: true,
  showStep: true
})

const isRunning = computed(() => props.status === 'running')

const progressClasses = computed(() => [
  `progress-${props.size}`,
  `status-${props.status}`
])

const progressBarClasses = computed(() => {
  switch (props.status) {
    case 'completed':
      return 'bg-green-500'
    case 'failed':
    case 'timeout':
      return 'bg-red-500'
    case 'cancelled':
      return 'bg-yellow-500'
    case 'paused':
      return 'bg-purple-500'
    case 'running':
      return 'bg-blue-500 animate-pulse'
    default:
      return 'bg-autobot-text-muted'
  }
})
</script>

<style scoped>
/* Issue #704: Migrated to CSS design tokens */
.operation-progress {
  width: 100%;
}

.progress-bar-container {
  width: 100%;
  background-color: var(--bg-tertiary);
  border-radius: var(--radius-full);
  overflow: hidden;
}

.progress-small .progress-bar-container {
  height: 4px;
}

.progress-medium .progress-bar-container {
  height: 8px;
}

.progress-large .progress-bar-container {
  height: 12px;
}

.progress-bar {
  height: 100%;
  transition: width var(--duration-300) var(--ease-in-out);
  border-radius: var(--radius-full);
}

.progress-info {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: var(--spacing-1);
  font-size: var(--text-xs);
  color: var(--text-secondary);
}

.progress-percentage {
  font-weight: var(--font-semibold);
}

.progress-items {
  color: var(--text-tertiary);
}

.progress-step {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  margin-top: var(--spacing-1-5);
  font-size: var(--text-xs);
  color: var(--text-secondary);
}

.step-icon {
  font-size: 0.625rem;
  color: var(--color-info);
}

.step-text {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* Status-specific styles */
.status-running .progress-percentage {
  color: var(--color-info);
}

.status-completed .progress-percentage {
  color: var(--color-success);
}

.status-failed .progress-percentage,
.status-timeout .progress-percentage {
  color: var(--color-error);
}

/* Tailwind-like utility classes */
.bg-green-500 {
  background-color: #22c55e;
}

.bg-red-500 {
  background-color: #ef4444;
}

.bg-yellow-500 {
  background-color: #eab308;
}

.bg-purple-500 {
  background-color: #a855f7;
}

.bg-blue-500 {
  background-color: #3b82f6;
}

.bg-autobot-text-muted {
  background-color: var(--text-muted, #9ca3af);
}

.animate-pulse {
  animation: pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite;
}

@keyframes pulse {
  0%, 100% {
    opacity: 1;
  }
  50% {
    opacity: 0.7;
  }
}
</style>
