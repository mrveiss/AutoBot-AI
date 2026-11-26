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
import { BaseAlert, BaseModal } from '@autobot/ui'

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
    return { label: 'Met', cls: 'bg-autobot-pill-ok-bg text-autobot-pill-ok-fg' }
  }
  if (compliance >= target - 1) {
    return { label: 'At Risk', cls: 'bg-autobot-pill-warn-bg text-autobot-pill-warn-fg' }
  }
  return { label: 'Breached', cls: 'bg-autobot-pill-bad-bg text-autobot-pill-bad-fg' }
}

/**
 * Get compliance bar color class.
 */
function complianceBarColor(slo: SLODefinition): string {
  const compliance = slo.current_compliance ?? 0
  const target = slo.target_percent
  if (compliance >= target) return 'bg-autobot-dot-ok'
  if (compliance >= target - 1) return 'bg-autobot-dot-warn'
  return 'bg-autobot-dot-bad'
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
    <BaseAlert v-if="error" variant="error" class="mb-4" :message="error" />

    <!-- Header -->
    <div class="flex items-center justify-between mb-6">
      <div>
        <h2 class="text-lg font-semibold text-autobot-text-primary">{{ $t('performance.sLODashboard.serviceLevelObjectives') }}</h2>
        <p class="text-sm text-autobot-text-tertiary">{{ $t('performance.sLODashboard.countSLOPluralDefined', { count: slos.length, plural: slos.length !== 1 ? 's' : '' }) }}</p>
      </div>
      <button
        @click="openCreateModal"
        class="flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-primary-600 rounded-lg hover:bg-primary-700 transition-colors"
      >
        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4" />
        </svg>
        {{ $t('performance.sLODashboard.createSLO') }}
      </button>
    </div>

    <!-- SLO Cards -->
    <div v-if="slos.length === 0 && !loading" class="text-center text-autobot-text-tertiary py-12">
      {{ $t('performance.sLODashboard.noSLOsDefinedCreate') }}
    </div>
    <div v-else class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
      <div
        v-for="slo in slos"
        :key="slo.slo_id"
        class="bg-white rounded-lg shadow-xs border border-autobot-border p-4"
      >
        <div class="flex items-start justify-between mb-3">
          <div>
            <h3 class="text-sm font-semibold text-autobot-text-primary">{{ slo.name }}</h3>
            <p v-if="slo.description" class="text-xs text-autobot-text-tertiary mt-0.5">
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
            <span class="text-autobot-text-tertiary">{{ $t('performance.sLODashboard.compliance') }}</span>
            <span class="font-medium text-autobot-text-secondary">
              {{ (slo.current_compliance ?? 0).toFixed(1) }}% / {{ slo.target_percent }}%
            </span>
          </div>
          <div class="w-full bg-autobot-bg-active rounded-full h-2 relative">
            <div
              :class="['h-2 rounded-full transition-all', complianceBarColor(slo)]"
              :style="{ width: `${Math.min(slo.current_compliance ?? 0, 100)}%` }"
            ></div>
            <!-- Target indicator line -->
            <div
              class="absolute top-0 h-2 w-0.5 bg-autobot-bg-hover outline outline-1 outline-autobot-text-primary"
              :style="{ left: `${Math.min(slo.target_percent, 100)}%` }"
              :title="$t('performance.sLODashboard.targetPercentTitle', { percent: slo.target_percent })"
            ></div>
          </div>
        </div>

        <!-- Metadata -->
        <div class="grid grid-cols-2 gap-2 text-xs text-autobot-text-tertiary mb-3">
          <div>
            <span class="text-autobot-text-tertiary">{{ $t('performance.sLODashboard.metric') }}</span>
            <span class="ml-1 capitalize">{{ slo.metric_type }}</span>
          </div>
          <div>
            <span class="text-autobot-text-tertiary">{{ $t('performance.sLODashboard.threshold') }}</span>
            <span class="ml-1">{{ slo.threshold_value }}{{ slo.threshold_unit }}</span>
          </div>
          <div>
            <span class="text-autobot-text-tertiary">{{ $t('performance.sLODashboard.window') }}</span>
            <span class="ml-1">{{ slo.window_days }}d</span>
          </div>
          <div v-if="slo.node_id">
            <span class="text-autobot-text-tertiary">{{ $t('performance.sLODashboard.node') }}</span>
            <span class="ml-1">{{ slo.node_id }}</span>
          </div>
        </div>

        <!-- Actions -->
        <div class="flex justify-end">
          <button
            @click="confirmDelete(slo)"
            class="text-xs text-autobot-error hover:bg-autobot-pill-bad-bg hover:text-autobot-pill-bad-fg transition-colors"
          >
            {{ $t('performance.sLODashboard.delete') }}
          </button>
        </div>
      </div>
    </div>

    <!-- Create SLO Modal -->
    <BaseModal
      v-model="showCreateModal"
      :title="$t('performance.sLODashboard.createSLO')"
      width="32rem"
      :close-label="$t('ui.modal.closeDialog')"
    >
      <form id="slo-create-form" @submit.prevent="handleCreate" class="space-y-4">
        <div>
          <label class="block text-sm font-medium text-autobot-text-secondary mb-1">{{ $t('performance.sLODashboard.name') }}</label>
          <input
            v-model="form.name"
            type="text"
            required
            class="w-full border border-autobot-border-strong rounded-lg px-3 py-2 text-sm"
            :placeholder="$t('performance.sLODashboard.aPIResponseTimeSLO')"
          />
        </div>
        <div>
          <label class="block text-sm font-medium text-autobot-text-secondary mb-1">{{ $t('performance.sLODashboard.description') }}</label>
          <input
            v-model="form.description"
            type="text"
            class="w-full border border-autobot-border-strong rounded-lg px-3 py-2 text-sm"
            :placeholder="$t('performance.sLODashboard.optionalDescription')"
          />
        </div>
        <div class="grid grid-cols-2 gap-4">
          <div>
            <label class="block text-sm font-medium text-autobot-text-secondary mb-1">{{ $t('performance.sLODashboard.target') }}</label>
            <input
              v-model.number="form.target_percent"
              type="number"
              step="0.1"
              min="0"
              max="100"
              required
              class="w-full border border-autobot-border-strong rounded-lg px-3 py-2 text-sm"
            />
          </div>
          <div>
            <label class="block text-sm font-medium text-autobot-text-secondary mb-1">{{ $t('performance.sLODashboard.metricType') }}</label>
            <select
              v-model="form.metric_type"
              class="w-full border border-autobot-border-strong rounded-lg px-3 py-2 text-sm"
            >
              <option v-for="opt in metricTypeOptions" :key="opt.value" :value="opt.value">
                {{ opt.label }}
              </option>
            </select>
          </div>
        </div>
        <div class="grid grid-cols-3 gap-4">
          <div>
            <label class="block text-sm font-medium text-autobot-text-secondary mb-1">{{ $t('performance.sLODashboard.threshold1') }}</label>
            <input
              v-model.number="form.threshold_value"
              type="number"
              step="1"
              required
              class="w-full border border-autobot-border-strong rounded-lg px-3 py-2 text-sm"
            />
          </div>
          <div>
            <label class="block text-sm font-medium text-autobot-text-secondary mb-1">{{ $t('performance.sLODashboard.unit') }}</label>
            <select
              v-model="form.threshold_unit"
              class="w-full border border-autobot-border-strong rounded-lg px-3 py-2 text-sm"
            >
              <option v-for="opt in thresholdUnitOptions" :key="opt.value" :value="opt.value">
                {{ opt.label }}
              </option>
            </select>
          </div>
          <div>
            <label class="block text-sm font-medium text-autobot-text-secondary mb-1">{{ $t('performance.sLODashboard.windowDays') }}</label>
            <input
              v-model.number="form.window_days"
              type="number"
              min="1"
              required
              class="w-full border border-autobot-border-strong rounded-lg px-3 py-2 text-sm"
            />
          </div>
        </div>
        <div>
          <label class="block text-sm font-medium text-autobot-text-secondary mb-1">{{ $t('performance.sLODashboard.nodeIDOptional') }}</label>
          <input
            v-model="form.node_id"
            type="text"
            class="w-full border border-autobot-border-strong rounded-lg px-3 py-2 text-sm"
            :placeholder="$t('performance.sLODashboard.leaveEmptyForGlobal')"
          />
        </div>
        <div class="flex items-center gap-2">
          <input
            v-model="form.enabled"
            type="checkbox"
            id="slo-enabled"
            class="rounded-sm border-autobot-border-strong"
          />
          <label for="slo-enabled" class="text-sm text-autobot-text-secondary">{{ $t('performance.sLODashboard.enabled') }}</label>
        </div>
      </form>
      <template #actions>
        <div class="flex justify-end gap-3">
          <button
            type="button"
            @click="showCreateModal = false"
            class="px-4 py-2 text-sm font-medium text-autobot-text-secondary bg-white border border-autobot-border-strong rounded-lg hover:bg-autobot-bg-hover"
          >
            {{ $t('performance.sLODashboard.cancel') }}
          </button>
          <button
            type="submit"
            form="slo-create-form"
            :disabled="!form.name || loading"
            class="px-4 py-2 text-sm font-medium text-white bg-primary-600 rounded-lg hover:bg-primary-700 disabled:opacity-50"
          >
            {{ $t('performance.sLODashboard.create') }}
          </button>
        </div>
      </template>
    </BaseModal>

    <!-- Delete Confirmation Modal -->
    <BaseModal
      v-model="showDeleteConfirm"
      :title="$t('performance.sLODashboard.deleteSLO')"
      size="sm"
      :close-label="$t('ui.modal.closeDialog')"
    >
      <p class="text-sm text-autobot-text-secondary">
        {{ $t('performance.sLODashboard.areYouSureYou') }}
        <span class="font-medium">"{{ deleteTarget?.name }}"</span>{{ $t('performance.sLODashboard.thisActionCannotBe') }}
      </p>
      <template #actions>
        <button
          @click="showDeleteConfirm = false"
          class="px-4 py-2 text-sm font-medium text-autobot-text-secondary bg-white border border-autobot-border-strong rounded-lg hover:bg-autobot-bg-hover"
        >
          {{ $t('performance.sLODashboard.cancel') }}
        </button>
        <button
          @click="handleDelete"
          :disabled="loading"
          class="px-4 py-2 text-sm font-medium text-(--text-on-error) bg-autobot-error-solid rounded-lg hover:bg-(--color-error-solid-hover) disabled:opacity-50"
        >
          {{ $t('performance.sLODashboard.delete') }}
        </button>
      </template>
    </BaseModal>
  </div>
</template>
