<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * SLODashboard - SLO management dashboard
 *
 * Displays SLO cards with compliance status, supports creation and deletion.
 * Issue #752 - Comprehensive performance monitoring.
 */

import { ref, onMounted } from 'vue'
import { usePerformanceMonitoring } from '@/composables/usePerformanceMonitoring'
import type { SLODefinition } from '@/composables/usePerformanceMonitoring'

const {
  slos,
  loading,
  error,
  fetchSLOs,
  createSLO,
  deleteSLO,
} = usePerformanceMonitoring()

// Modal state
const showCreateModal = ref(false)
const showDeleteConfirm = ref(false)
const deleteTarget = ref<SLODefinition | null>(null)

// Form state
const form = ref({
  name: '',
  description: '',
  target_percent: 99.9,
  metric_type: 'latency',
  threshold_value: 500,
  threshold_unit: 'ms',
  window_days: 30,
  node_id: '',
  enabled: true,
})

const metricTypeOptions = [
  { label: 'Latency', value: 'latency' },
  { label: 'Error Rate', value: 'error_rate' },
  { label: 'Throughput', value: 'throughput' },
  { label: 'Availability', value: 'availability' },
]

const thresholdUnitOptions = [
  { label: 'ms', value: 'ms' },
  { label: 's', value: 's' },
  { label: '%', value: '%' },
  { label: 'req/min', value: 'rpm' },
]

onMounted(() => {
  fetchSLOs()
})

/**
 * Determine SLO status badge based on compliance vs target.
 */
function sloStatusBadge(
  slo: SLODefinition
): { label: string; cls: string } {
  const compliance = slo.current_compliance ?? 0
  const target = slo.target_percent
  if (compliance >= target) {
    return { label: 'Met', cls: 'bg-green-100 text-green-700' }
  }
  if (compliance >= target - 1) {
    return { label: 'At Risk', cls: 'bg-amber-100 text-amber-700' }
  }
  return { label: 'Breached', cls: 'bg-red-100 text-red-700' }
}

/**
 * Get compliance bar color class.
 */
function complianceBarColor(slo: SLODefinition): string {
  const compliance = slo.current_compliance ?? 0
  const target = slo.target_percent
  if (compliance >= target) return 'bg-green-500'
  if (compliance >= target - 1) return 'bg-amber-500'
  return 'bg-red-500'
}

/**
 * Reset form to defaults.
 */
function resetForm(): void {
  form.value = {
    name: '',
    description: '',
    target_percent: 99.9,
    metric_type: 'latency',
    threshold_value: 500,
    threshold_unit: 'ms',
    window_days: 30,
    node_id: '',
    enabled: true,
  }
}

/**
 * Open create modal.
 */
function openCreateModal(): void {
  resetForm()
  showCreateModal.value = true
}

/**
 * Handle SLO creation form submission.
 */
async function handleCreate(): Promise<void> {
  const slo = {
    name: form.value.name,
    description: form.value.description || null,
    target_percent: form.value.target_percent,
    metric_type: form.value.metric_type,
    threshold_value: form.value.threshold_value,
    threshold_unit: form.value.threshold_unit,
    window_days: form.value.window_days,
    node_id: form.value.node_id || null,
    enabled: form.value.enabled,
  }
  const result = await createSLO(slo)
  if (result) {
    showCreateModal.value = false
    resetForm()
  }
}

/**
 * Prompt for SLO deletion confirmation.
 */
function confirmDelete(slo: SLODefinition): void {
  deleteTarget.value = slo
  showDeleteConfirm.value = true
}

/**
 * Execute SLO deletion.
 */
async function handleDelete(): Promise<void> {
  if (!deleteTarget.value) return
  await deleteSLO(deleteTarget.value.slo_id)
  showDeleteConfirm.value = false
  deleteTarget.value = null
}
</script>

<template>
  <div class="p-6">
    <!-- Error Banner -->
    <div
      v-if="error"
      class="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm"
    >
      {{ error }}
    </div>

    <!-- Header -->
    <div class="flex items-center justify-between mb-6">
      <div>
        <h2 class="text-lg font-semibold text-gray-900">Service Level Objectives</h2>
        <p class="text-sm text-gray-500">{{ slos.length }} SLO{{ slos.length !== 1 ? 's' : '' }} defined</p>
      </div>
      <button
        @click="openCreateModal"
        class="flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-primary-600 rounded-lg hover:bg-primary-700 transition-colors"
      >
        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4" />
        </svg>
        Create SLO
      </button>
    </div>

    <!-- SLO Cards -->
    <div v-if="slos.length === 0 && !loading" class="text-center text-gray-400 py-12">
      No SLOs defined. Create one to start tracking service level objectives.
    </div>
    <div v-else class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
      <div
        v-for="slo in slos"
        :key="slo.slo_id"
        class="bg-white rounded-lg shadow-sm border border-gray-200 p-4"
      >
        <div class="flex items-start justify-between mb-3">
          <div>
            <h3 class="text-sm font-semibold text-gray-900">{{ slo.name }}</h3>
            <p v-if="slo.description" class="text-xs text-gray-500 mt-0.5">
              {{ slo.description }}
            </p>
          </div>
          <span
            :class="[
              'px-2 py-0.5 text-xs font-medium rounded-full',
              sloStatusBadge(slo).cls
            ]"
          >
            {{ sloStatusBadge(slo).label }}
          </span>
        </div>

        <!-- Compliance Bar -->
        <div class="mb-3">
          <div class="flex items-center justify-between text-xs mb-1">
            <span class="text-gray-500">Compliance</span>
            <span class="font-medium text-gray-700">
              {{ (slo.current_compliance ?? 0).toFixed(1) }}% / {{ slo.target_percent }}%
            </span>
          </div>
          <div class="w-full bg-gray-200 rounded-full h-2 relative">
            <div
              :class="['h-2 rounded-full transition-all', complianceBarColor(slo)]"
              :style="{ width: `${Math.min(slo.current_compliance ?? 0, 100)}%` }"
            ></div>
            <!-- Target indicator line -->
            <div
              class="absolute top-0 h-2 w-0.5 bg-gray-700"
              :style="{ left: `${Math.min(slo.target_percent, 100)}%` }"
              :title="`Target: ${slo.target_percent}%`"
            ></div>
          </div>
        </div>

        <!-- Metadata -->
        <div class="grid grid-cols-2 gap-2 text-xs text-gray-500 mb-3">
          <div>
            <span class="text-gray-400">Metric:</span>
            <span class="ml-1 capitalize">{{ slo.metric_type }}</span>
          </div>
          <div>
            <span class="text-gray-400">Threshold:</span>
            <span class="ml-1">{{ slo.threshold_value }}{{ slo.threshold_unit }}</span>
          </div>
          <div>
            <span class="text-gray-400">Window:</span>
            <span class="ml-1">{{ slo.window_days }}d</span>
          </div>
          <div v-if="slo.node_id">
            <span class="text-gray-400">Node:</span>
            <span class="ml-1">{{ slo.node_id }}</span>
          </div>
        </div>

        <!-- Actions -->
        <div class="flex justify-end">
          <button
            @click="confirmDelete(slo)"
            class="text-xs text-red-600 hover:text-red-800 transition-colors"
          >
            Delete
          </button>
        </div>
      </div>
    </div>

    <!-- Create SLO Modal -->
    <transition
      enter-active-class="transition ease-out duration-200"
      enter-from-class="opacity-0"
      enter-to-class="opacity-100"
      leave-active-class="transition ease-in duration-150"
      leave-from-class="opacity-100"
      leave-to-class="opacity-0"
    >
      <div v-if="showCreateModal" class="fixed inset-0 z-50 flex items-center justify-center">
        <div class="fixed inset-0 bg-black bg-opacity-50" @click="showCreateModal = false"></div>
        <div class="relative bg-white rounded-lg shadow-xl w-full max-w-lg mx-4 p-6">
          <h3 class="text-lg font-semibold text-gray-900 mb-4">Create SLO</h3>
          <form @submit.prevent="handleCreate" class="space-y-4">
            <div>
              <label class="block text-sm font-medium text-gray-700 mb-1">Name</label>
              <input
                v-model="form.name"
                type="text"
                required
                class="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"
                placeholder="API Response Time SLO"
              />
            </div>
            <div>
              <label class="block text-sm font-medium text-gray-700 mb-1">Description</label>
              <input
                v-model="form.description"
                type="text"
                class="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"
                placeholder="Optional description"
              />
            </div>
            <div class="grid grid-cols-2 gap-4">
              <div>
                <label class="block text-sm font-medium text-gray-700 mb-1">Target %</label>
                <input
                  v-model.number="form.target_percent"
                  type="number"
                  step="0.1"
                  min="0"
                  max="100"
                  required
                  class="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"
                />
              </div>
              <div>
                <label class="block text-sm font-medium text-gray-700 mb-1">Metric Type</label>
                <select
                  v-model="form.metric_type"
                  class="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"
                >
                  <option v-for="opt in metricTypeOptions" :key="opt.value" :value="opt.value">
                    {{ opt.label }}
                  </option>
                </select>
              </div>
            </div>
            <div class="grid grid-cols-3 gap-4">
              <div>
                <label class="block text-sm font-medium text-gray-700 mb-1">Threshold</label>
                <input
                  v-model.number="form.threshold_value"
                  type="number"
                  step="1"
                  required
                  class="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"
                />
              </div>
              <div>
                <label class="block text-sm font-medium text-gray-700 mb-1">Unit</label>
                <select
                  v-model="form.threshold_unit"
                  class="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"
                >
                  <option v-for="opt in thresholdUnitOptions" :key="opt.value" :value="opt.value">
                    {{ opt.label }}
                  </option>
                </select>
              </div>
              <div>
                <label class="block text-sm font-medium text-gray-700 mb-1">Window (days)</label>
                <input
                  v-model.number="form.window_days"
                  type="number"
                  min="1"
                  required
                  class="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"
                />
              </div>
            </div>
            <div>
              <label class="block text-sm font-medium text-gray-700 mb-1">Node ID (optional)</label>
              <input
                v-model="form.node_id"
                type="text"
                class="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"
                placeholder="Leave empty for global"
              />
            </div>
            <div class="flex items-center gap-2">
              <input
                v-model="form.enabled"
                type="checkbox"
                id="slo-enabled"
                class="rounded border-gray-300"
              />
              <label for="slo-enabled" class="text-sm text-gray-700">Enabled</label>
            </div>
            <div class="flex justify-end gap-3 pt-2">
              <button
                type="button"
                @click="showCreateModal = false"
                class="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50"
              >
                Cancel
              </button>
              <button
                type="submit"
                :disabled="!form.name || loading"
                class="px-4 py-2 text-sm font-medium text-white bg-primary-600 rounded-lg hover:bg-primary-700 disabled:opacity-50"
              >
                Create
              </button>
            </div>
          </form>
        </div>
      </div>
    </transition>

    <!-- Delete Confirmation Modal -->
    <transition
      enter-active-class="transition ease-out duration-200"
      enter-from-class="opacity-0"
      enter-to-class="opacity-100"
      leave-active-class="transition ease-in duration-150"
      leave-from-class="opacity-100"
      leave-to-class="opacity-0"
    >
      <div v-if="showDeleteConfirm" class="fixed inset-0 z-50 flex items-center justify-center">
        <div class="fixed inset-0 bg-black bg-opacity-50" @click="showDeleteConfirm = false"></div>
        <div class="relative bg-white rounded-lg shadow-xl w-full max-w-sm mx-4 p-6">
          <h3 class="text-lg font-semibold text-gray-900 mb-2">Delete SLO</h3>
          <p class="text-sm text-gray-600 mb-4">
            Are you sure you want to delete
            <span class="font-medium">"{{ deleteTarget?.name }}"</span>?
            This action cannot be undone.
          </p>
          <div class="flex justify-end gap-3">
            <button
              @click="showDeleteConfirm = false"
              class="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50"
            >
              Cancel
            </button>
            <button
              @click="handleDelete"
              :disabled="loading"
              class="px-4 py-2 text-sm font-medium text-white bg-red-600 rounded-lg hover:bg-red-700 disabled:opacity-50"
            >
              Delete
            </button>
          </div>
        </div>
      </div>
    </transition>
  </div>
</template>
