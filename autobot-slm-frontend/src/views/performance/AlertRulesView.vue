<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * AlertRulesView - Performance alert rule management
 *
 * Displays alert rules in a table with create, edit, toggle, and delete actions.
 * Issue #752 - Comprehensive performance monitoring.
 */

import { ref, onMounted } from 'vue'
import { usePerformanceMonitoring } from '@/composables/usePerformanceMonitoring'
import type { AlertRule } from '@/composables/usePerformanceMonitoring'

const {
  alertRules,
  loading,
  error,
  fetchAlertRules,
  createAlertRule,
  updateAlertRule,
  deleteAlertRule,
} = usePerformanceMonitoring()

// Modal state
const showCreateModal = ref(false)
const showEditModal = ref(false)
const showDeleteConfirm = ref(false)
const editTarget = ref<AlertRule | null>(null)
const deleteTarget = ref<AlertRule | null>(null)

// Form state
const form = ref(getDefaultForm())

const metricTypeOptions = [
  { label: 'Latency', value: 'latency' },
  { label: 'Error Rate', value: 'error_rate' },
  { label: 'Throughput', value: 'throughput' },
  { label: 'CPU Usage', value: 'cpu_usage' },
  { label: 'Memory Usage', value: 'memory_usage' },
  { label: 'Disk Usage', value: 'disk_usage' },
]

const conditionOptions = [
  { label: 'Greater Than', value: 'gt' },
  { label: 'Greater or Equal', value: 'gte' },
  { label: 'Less Than', value: 'lt' },
  { label: 'Less or Equal', value: 'lte' },
  { label: 'Equals', value: 'eq' },
]

const severityOptions = [
  { label: 'Info', value: 'info' },
  { label: 'Warning', value: 'warning' },
  { label: 'Critical', value: 'critical' },
]

onMounted(() => {
  fetchAlertRules()
})

/**
 * Get default form values.
 */
function getDefaultForm() {
  return {
    name: '',
    description: '',
    metric_type: 'latency',
    condition: 'gt',
    threshold: 1000,
    duration_seconds: 60,
    severity: 'warning',
    node_id: '',
    enabled: true,
  }
}

/**
 * Reset form to defaults.
 */
function resetForm(): void {
  form.value = getDefaultForm()
}

/**
 * Get severity badge classes.
 */
function severityBadgeClass(severity: string): string {
  switch (severity) {
    case 'info': return 'bg-blue-100 text-blue-700'
    case 'warning': return 'bg-amber-100 text-amber-700'
    case 'critical': return 'bg-red-100 text-red-700'
    default: return 'bg-gray-100 text-gray-700'
  }
}

/**
 * Format condition for display.
 */
function formatCondition(condition: string): string {
  switch (condition) {
    case 'gt': return '>'
    case 'gte': return '>='
    case 'lt': return '<'
    case 'lte': return '<='
    case 'eq': return '='
    default: return condition
  }
}

/**
 * Format last triggered date.
 */
function formatLastTriggered(dateStr: string | null): string {
  if (!dateStr) return 'Never'
  return new Date(dateStr).toLocaleString()
}

/**
 * Open create modal.
 */
function openCreateModal(): void {
  resetForm()
  showCreateModal.value = true
}

/**
 * Open edit modal for a rule.
 */
function openEditModal(rule: AlertRule): void {
  editTarget.value = rule
  form.value = {
    name: rule.name,
    description: rule.description ?? '',
    metric_type: rule.metric_type,
    condition: rule.condition,
    threshold: rule.threshold,
    duration_seconds: rule.duration_seconds,
    severity: rule.severity,
    node_id: rule.node_id ?? '',
    enabled: rule.enabled,
  }
  showEditModal.value = true
}

/**
 * Handle create form submission.
 */
async function handleCreate(): Promise<void> {
  const rule = {
    name: form.value.name,
    description: form.value.description || null,
    metric_type: form.value.metric_type,
    condition: form.value.condition,
    threshold: form.value.threshold,
    duration_seconds: form.value.duration_seconds,
    severity: form.value.severity,
    node_id: form.value.node_id || null,
    enabled: form.value.enabled,
  }
  const result = await createAlertRule(rule)
  if (result) {
    showCreateModal.value = false
    resetForm()
  }
}

/**
 * Handle edit form submission.
 */
async function handleEdit(): Promise<void> {
  if (!editTarget.value) return
  const updates = {
    name: form.value.name,
    description: form.value.description || null,
    metric_type: form.value.metric_type,
    condition: form.value.condition,
    threshold: form.value.threshold,
    duration_seconds: form.value.duration_seconds,
    severity: form.value.severity,
    node_id: form.value.node_id || null,
    enabled: form.value.enabled,
  }
  const result = await updateAlertRule(editTarget.value.rule_id, updates)
  if (result) {
    showEditModal.value = false
    editTarget.value = null
    resetForm()
  }
}

/**
 * Toggle rule enabled state.
 */
async function toggleEnabled(rule: AlertRule): Promise<void> {
  await updateAlertRule(rule.rule_id, { enabled: !rule.enabled })
}

/**
 * Prompt for rule deletion confirmation.
 */
function confirmDelete(rule: AlertRule): void {
  deleteTarget.value = rule
  showDeleteConfirm.value = true
}

/**
 * Execute rule deletion.
 */
async function handleDelete(): Promise<void> {
  if (!deleteTarget.value) return
  await deleteAlertRule(deleteTarget.value.rule_id)
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
        <h2 class="text-lg font-semibold text-gray-900">Alert Rules</h2>
        <p class="text-sm text-gray-500">
          {{ alertRules.length }} rule{{ alertRules.length !== 1 ? 's' : '' }} configured
        </p>
      </div>
      <button
        @click="openCreateModal"
        class="flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-primary-600 rounded-lg hover:bg-primary-700 transition-colors"
      >
        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4" />
        </svg>
        Create Rule
      </button>
    </div>

    <!-- Rules Table -->
    <div class="bg-white rounded-lg shadow-sm border border-gray-200">
      <div v-if="alertRules.length === 0 && !loading" class="p-8 text-center text-gray-400">
        No alert rules configured. Create one to start monitoring.
      </div>
      <div v-else class="overflow-x-auto">
        <table class="min-w-full divide-y divide-gray-200">
          <thead class="bg-gray-50">
            <tr>
              <th class="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Name</th>
              <th class="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Metric</th>
              <th class="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Condition</th>
              <th class="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Severity</th>
              <th class="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Enabled</th>
              <th class="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Last Triggered</th>
              <th class="px-4 py-2 text-right text-xs font-medium text-gray-500 uppercase">Actions</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-gray-200">
            <tr v-for="rule in alertRules" :key="rule.rule_id" class="hover:bg-gray-50">
              <td class="px-4 py-3">
                <div class="text-sm font-medium text-gray-900">{{ rule.name }}</div>
                <div v-if="rule.description" class="text-xs text-gray-500">
                  {{ rule.description }}
                </div>
              </td>
              <td class="px-4 py-3 text-sm text-gray-600 capitalize">
                {{ rule.metric_type.replace('_', ' ') }}
              </td>
              <td class="px-4 py-3 text-sm font-mono text-gray-700">
                {{ formatCondition(rule.condition) }} {{ rule.threshold }}
                <span class="text-gray-400 text-xs">
                  ({{ rule.duration_seconds }}s)
                </span>
              </td>
              <td class="px-4 py-3">
                <span
                  :class="[
                    'px-2 py-0.5 text-xs font-medium rounded-full capitalize',
                    severityBadgeClass(rule.severity)
                  ]"
                >
                  {{ rule.severity }}
                </span>
              </td>
              <td class="px-4 py-3">
                <button
                  @click="toggleEnabled(rule)"
                  :class="[
                    'relative inline-flex h-5 w-9 items-center rounded-full transition-colors',
                    rule.enabled ? 'bg-green-500' : 'bg-gray-300'
                  ]"
                  :title="rule.enabled ? 'Disable' : 'Enable'"
                >
                  <span
                    :class="[
                      'inline-block h-3.5 w-3.5 rounded-full bg-white transition-transform',
                      rule.enabled ? 'translate-x-4.5' : 'translate-x-0.5'
                    ]"
                  ></span>
                </button>
              </td>
              <td class="px-4 py-3 text-sm text-gray-500 whitespace-nowrap">
                {{ formatLastTriggered(rule.last_triggered) }}
              </td>
              <td class="px-4 py-3 text-right">
                <div class="flex items-center justify-end gap-2">
                  <button
                    @click="openEditModal(rule)"
                    class="text-xs text-primary-600 hover:text-primary-800 transition-colors"
                  >
                    Edit
                  </button>
                  <button
                    @click="confirmDelete(rule)"
                    class="text-xs text-red-600 hover:text-red-800 transition-colors"
                  >
                    Delete
                  </button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Create/Edit Rule Modal -->
    <transition
      enter-active-class="transition ease-out duration-200"
      enter-from-class="opacity-0"
      enter-to-class="opacity-100"
      leave-active-class="transition ease-in duration-150"
      leave-from-class="opacity-100"
      leave-to-class="opacity-0"
    >
      <div
        v-if="showCreateModal || showEditModal"
        class="fixed inset-0 z-50 flex items-center justify-center"
      >
        <div
          class="fixed inset-0 bg-black bg-opacity-50"
          @click="showCreateModal = false; showEditModal = false"
        ></div>
        <div class="relative bg-white rounded-lg shadow-xl w-full max-w-lg mx-4 p-6">
          <h3 class="text-lg font-semibold text-gray-900 mb-4">
            {{ showEditModal ? 'Edit Alert Rule' : 'Create Alert Rule' }}
          </h3>
          <form
            @submit.prevent="showEditModal ? handleEdit() : handleCreate()"
            class="space-y-4"
          >
            <div>
              <label class="block text-sm font-medium text-gray-700 mb-1">Name</label>
              <input
                v-model="form.name"
                type="text"
                required
                class="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"
                placeholder="High Latency Alert"
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
              <div>
                <label class="block text-sm font-medium text-gray-700 mb-1">Condition</label>
                <select
                  v-model="form.condition"
                  class="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"
                >
                  <option v-for="opt in conditionOptions" :key="opt.value" :value="opt.value">
                    {{ opt.label }}
                  </option>
                </select>
              </div>
            </div>
            <div class="grid grid-cols-3 gap-4">
              <div>
                <label class="block text-sm font-medium text-gray-700 mb-1">Threshold</label>
                <input
                  v-model.number="form.threshold"
                  type="number"
                  step="any"
                  required
                  class="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"
                />
              </div>
              <div>
                <label class="block text-sm font-medium text-gray-700 mb-1">Duration (s)</label>
                <input
                  v-model.number="form.duration_seconds"
                  type="number"
                  min="1"
                  required
                  class="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"
                />
              </div>
              <div>
                <label class="block text-sm font-medium text-gray-700 mb-1">Severity</label>
                <select
                  v-model="form.severity"
                  class="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"
                >
                  <option v-for="opt in severityOptions" :key="opt.value" :value="opt.value">
                    {{ opt.label }}
                  </option>
                </select>
              </div>
            </div>
            <div>
              <label class="block text-sm font-medium text-gray-700 mb-1">Node ID (optional)</label>
              <input
                v-model="form.node_id"
                type="text"
                class="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"
                placeholder="Leave empty for all nodes"
              />
            </div>
            <div class="flex items-center gap-2">
              <input
                v-model="form.enabled"
                type="checkbox"
                id="rule-enabled"
                class="rounded border-gray-300"
              />
              <label for="rule-enabled" class="text-sm text-gray-700">Enabled</label>
            </div>
            <div class="flex justify-end gap-3 pt-2">
              <button
                type="button"
                @click="showCreateModal = false; showEditModal = false"
                class="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50"
              >
                Cancel
              </button>
              <button
                type="submit"
                :disabled="!form.name || loading"
                class="px-4 py-2 text-sm font-medium text-white bg-primary-600 rounded-lg hover:bg-primary-700 disabled:opacity-50"
              >
                {{ showEditModal ? 'Save' : 'Create' }}
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
          <h3 class="text-lg font-semibold text-gray-900 mb-2">Delete Alert Rule</h3>
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
