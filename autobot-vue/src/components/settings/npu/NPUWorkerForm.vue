<template>
  <div class="worker-form">
    <!-- Error Alert -->
    <BaseAlert
      v-if="error"
      variant="error"
      :message="error"
    />

    <div class="form-group">
      <label class="form-label">Worker Name *</label>
      <input
        :value="modelValue.name"
        @input="updateField('name', ($event.target as HTMLInputElement).value)"
        type="text"
        class="form-input"
        placeholder="e.g., NPU-Worker-VM2"
        required
      />
    </div>

    <div class="form-row">
      <div class="form-group">
        <label class="form-label">Platform *</label>
        <select
          :value="modelValue.platform"
          @change="updateField('platform', ($event.target as HTMLSelectElement).value)"
          class="form-select"
        >
          <option value="linux">Linux</option>
          <option value="windows">Windows</option>
          <option value="macos">macOS</option>
        </select>
      </div>

      <div class="form-group">
        <label class="form-label">IP Address *</label>
        <input
          :value="modelValue.ip_address"
          @input="updateField('ip_address', ($event.target as HTMLInputElement).value)"
          type="text"
          class="form-input"
          :placeholder="defaultIp"
          required
        />
      </div>

      <div class="form-group">
        <label class="form-label">Port *</label>
        <input
          :value="modelValue.port"
          @input="updateField('port', parseInt(($event.target as HTMLInputElement).value) || 8081)"
          type="number"
          class="form-input"
          placeholder="8081"
          min="1"
          max="65535"
          required
        />
      </div>
    </div>

    <div class="form-row">
      <div class="form-group">
        <label class="form-label">Priority (1-10)</label>
        <input
          :value="modelValue.priority"
          @input="updateField('priority', parseInt(($event.target as HTMLInputElement).value) || 5)"
          type="number"
          class="form-input"
          min="1"
          max="10"
        />
        <p class="form-help">Higher priority workers receive tasks first</p>
      </div>

      <div class="form-group">
        <label class="form-label">Weight</label>
        <input
          :value="modelValue.weight"
          @input="updateField('weight', parseInt(($event.target as HTMLInputElement).value) || 1)"
          type="number"
          class="form-input"
          min="1"
          max="100"
        />
        <p class="form-help">Load balancing weight (higher = more tasks)</p>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss
/**
 * NPU Worker Form Component
 *
 * Form for adding/editing NPU worker configuration.
 * Extracted from NPUWorkersSettings.vue for better maintainability.
 *
 * Issue #184: Split oversized Vue components
 */

import BaseAlert from '@/components/ui/BaseAlert.vue'
import { NetworkConstants } from '@/constants/network'

interface WorkerForm {
  name: string
  platform: string
  ip_address: string
  port: number
  priority: number
  weight: number
}

interface Props {
  modelValue: WorkerForm
  error?: string | null
}

interface Emits {
  (e: 'update:modelValue', value: WorkerForm): void
}

const props = withDefaults(defineProps<Props>(), {
  error: null
})

const emit = defineEmits<Emits>()

const defaultIp = NetworkConstants.NPU_WORKER_VM_IP

const updateField = (field: keyof WorkerForm, value: string | number) => {
  emit('update:modelValue', {
    ...props.modelValue,
    [field]: value
  })
}
</script>

<style scoped>
.worker-form {
  @apply space-y-4;
}

.form-group {
  @apply flex flex-col;
}

.form-row {
  @apply grid grid-cols-1 md:grid-cols-3 gap-4;
}

.form-label {
  @apply text-sm font-medium text-gray-700 mb-1;
}

.form-input,
.form-select {
  @apply w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500;
}

.form-input:disabled,
.form-select:disabled {
  @apply bg-gray-100 cursor-not-allowed;
}

.form-help {
  @apply text-xs text-gray-500 mt-1;
}
</style>
