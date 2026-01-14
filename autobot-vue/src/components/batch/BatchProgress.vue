<!--
  AutoBot - AI-Powered Automation Platform
  Copyright (c) 2025 mrveiss
  Author: mrveiss

  Batch Progress Component - Progress bar for batch jobs
  Issue #584 - Batch Processing Manager
-->
<template>
  <div class="batch-progress" :class="progressClasses">
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
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { BatchJobStatus } from '@/types/batch-processing'

interface Props {
  progress: number
  status: BatchJobStatus
  size?: 'small' | 'medium' | 'large'
  showInfo?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  size: 'medium',
  showInfo: true
})

const progressClasses = computed(() => [
  `progress-${props.size}`,
  `status-${props.status}`
])

const progressBarClasses = computed(() => {
  switch (props.status) {
    case 'completed':
      return 'bg-green-500'
    case 'failed':
      return 'bg-red-500'
    case 'cancelled':
      return 'bg-yellow-500'
    case 'running':
      return 'bg-blue-500 animate-pulse'
    default:
      return 'bg-gray-400'
  }
})
</script>

<style scoped>
.batch-progress {
  width: 100%;
}

.progress-bar-container {
  width: 100%;
  background-color: var(--blue-gray-200);
  border-radius: 9999px;
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
  transition: width 0.3s ease-in-out;
  border-radius: 9999px;
}

.progress-info {
  display: flex;
  justify-content: flex-end;
  margin-top: 0.25rem;
  font-size: 0.75rem;
  color: var(--blue-gray-600);
}

.progress-percentage {
  font-weight: 600;
}

/* Status-specific styles */
.status-running .progress-percentage {
  color: #2563eb;
}

.status-completed .progress-percentage {
  color: #16a34a;
}

.status-failed .progress-percentage {
  color: #dc2626;
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

.bg-blue-500 {
  background-color: #3b82f6;
}

.bg-gray-400 {
  background-color: #9ca3af;
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
