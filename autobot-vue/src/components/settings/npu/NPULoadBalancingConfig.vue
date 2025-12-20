<template>
  <div class="config-section">
    <h4 class="section-title">
      <i class="fas fa-balance-scale mr-2"></i>
      Load Balancing Configuration
    </h4>
    <div class="config-grid">
      <div class="config-item">
        <label class="config-label">Strategy</label>
        <select
          :value="modelValue.strategy"
          @change="updateField('strategy', ($event.target as HTMLSelectElement).value)"
          class="config-select"
        >
          <option value="round-robin">Round Robin</option>
          <option value="least-loaded">Least Loaded</option>
          <option value="weighted">Weighted</option>
          <option value="priority">Priority Based</option>
        </select>
        <p class="config-help">Distribution strategy for task allocation</p>
      </div>
      <div class="config-item">
        <label class="config-label">Health Check Interval</label>
        <input
          :value="modelValue.health_check_interval"
          @input="updateField('health_check_interval', parseInt(($event.target as HTMLInputElement).value) || 30)"
          type="number"
          min="5"
          max="300"
          class="config-input"
        />
        <p class="config-help">Seconds between health checks</p>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss
/**
 * NPU Load Balancing Config Component
 *
 * Configuration panel for NPU worker load balancing.
 * Extracted from NPUWorkersSettings.vue for better maintainability.
 *
 * Issue #184: Split oversized Vue components
 */

interface LoadBalancingConfig {
  strategy: string
  health_check_interval: number
}

interface Props {
  modelValue: LoadBalancingConfig
}

interface Emits {
  (e: 'update:modelValue', value: LoadBalancingConfig): void
  (e: 'change'): void
}

const props = defineProps<Props>()
const emit = defineEmits<Emits>()

const updateField = (field: keyof LoadBalancingConfig, value: string | number) => {
  emit('update:modelValue', {
    ...props.modelValue,
    [field]: value
  })
  emit('change')
}
</script>

<style scoped>
.config-section {
  @apply bg-gray-50 rounded-lg p-4 mb-6;
}

.section-title {
  @apply text-lg font-semibold text-gray-800 mb-4 flex items-center;
}

.config-grid {
  @apply grid grid-cols-1 md:grid-cols-2 gap-4;
}

.config-item {
  @apply flex flex-col;
}

.config-label {
  @apply text-sm font-medium text-gray-700 mb-1;
}

.config-input,
.config-select {
  @apply w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500;
}

.config-help {
  @apply text-xs text-gray-500 mt-1;
}
</style>
