<!--
  AutoBot - AI-Powered Automation Platform
  Copyright (c) 2025 mrveiss
  Author: mrveiss

  Batch Filters Component - Filter controls for batch jobs
  Issue #584 - Batch Processing Manager
-->
<template>
  <div class="batch-filters">
    <!-- Status filter -->
    <div class="filter-group">
      <label class="filter-label">Status</label>
      <select
        v-model="localStatus"
        class="filter-select"
        @change="emitFilter"
      >
        <option :value="undefined">All Statuses</option>
        <option
          v-for="status in statuses"
          :key="status"
          :value="status"
        >
          {{ BATCH_STATUS_CONFIG[status].label }}
        </option>
      </select>
    </div>

    <!-- Type filter -->
    <div class="filter-group">
      <label class="filter-label">Type</label>
      <select
        v-model="localType"
        class="filter-select"
        @change="emitFilter"
      >
        <option :value="undefined">All Types</option>
        <option
          v-for="(label, type) in BATCH_TYPE_LABELS"
          :key="type"
          :value="type"
        >
          {{ label }}
        </option>
      </select>
    </div>

    <!-- Limit filter -->
    <div class="filter-group">
      <label class="filter-label">Show</label>
      <select
        v-model.number="localLimit"
        class="filter-select"
        @change="emitFilter"
      >
        <option :value="25">25</option>
        <option :value="50">50</option>
        <option :value="100">100</option>
        <option :value="250">250</option>
      </select>
    </div>

    <!-- Clear filters button -->
    <button
      class="clear-filters-btn"
      @click="clearFilters"
      :disabled="!hasActiveFilters"
    >
      <i class="fas fa-times"></i>
      Clear
    </button>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import type { BatchJobsFilter, BatchJobStatus, BatchJobType } from '@/types/batch-processing'
import { BATCH_STATUS_CONFIG, BATCH_TYPE_LABELS } from '@/types/batch-processing'

interface Props {
  filter: BatchJobsFilter
}

const props = defineProps<Props>()

const emit = defineEmits<{
  'update:filter': [filter: BatchJobsFilter]
  clear: []
}>()

// All available statuses
const statuses: BatchJobStatus[] = [
  'pending',
  'running',
  'completed',
  'failed',
  'cancelled'
]

// Local filter state
const localStatus = ref<BatchJobStatus | undefined>(props.filter.status)
const localType = ref<BatchJobType | undefined>(props.filter.job_type)
const localLimit = ref(props.filter.limit || 50)

// Watch for external filter changes
watch(() => props.filter, (newFilter) => {
  localStatus.value = newFilter.status
  localType.value = newFilter.job_type
  localLimit.value = newFilter.limit || 50
}, { deep: true })

// Check if any filters are active
const hasActiveFilters = computed(() =>
  localStatus.value !== undefined ||
  localType.value !== undefined ||
  localLimit.value !== 50
)

// Emit filter changes
function emitFilter() {
  emit('update:filter', {
    status: localStatus.value,
    job_type: localType.value,
    limit: localLimit.value
  })
}

// Clear all filters
function clearFilters() {
  localStatus.value = undefined
  localType.value = undefined
  localLimit.value = 50
  emit('clear')
}
</script>

<style scoped>
.batch-filters {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  gap: 1rem;
  padding: 1rem;
  background-color: var(--blue-gray-50);
  border-radius: 0.5rem;
  border: 1px solid var(--blue-gray-200);
}

.filter-group {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.filter-label {
  font-size: 0.75rem;
  font-weight: 500;
  color: var(--blue-gray-600);
}

.filter-select {
  padding: 0.5rem 2rem 0.5rem 0.75rem;
  font-size: 0.875rem;
  border: 1px solid var(--blue-gray-300);
  border-radius: 0.375rem;
  background-color: white;
  color: var(--blue-gray-700);
  cursor: pointer;
  appearance: none;
  background-image: url("data:image/svg+xml,%3csvg xmlns='http://www.w3.org/2000/svg' fill='none' viewBox='0 0 20 20'%3e%3cpath stroke='%236b7280' stroke-linecap='round' stroke-linejoin='round' stroke-width='1.5' d='M6 8l4 4 4-4'/%3e%3c/svg%3e");
  background-position: right 0.5rem center;
  background-repeat: no-repeat;
  background-size: 1.5em 1.5em;
}

.filter-select:hover {
  border-color: var(--blue-gray-400);
}

.filter-select:focus {
  outline: none;
  border-color: var(--blue-500);
  box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.2);
}

.clear-filters-btn {
  display: flex;
  align-items: center;
  gap: 0.375rem;
  padding: 0.5rem 0.75rem;
  font-size: 0.875rem;
  font-weight: 500;
  color: var(--blue-gray-600);
  background-color: white;
  border: 1px solid var(--blue-gray-300);
  border-radius: 0.375rem;
  cursor: pointer;
  transition: all 0.2s;
}

.clear-filters-btn:hover:not(:disabled) {
  background-color: var(--blue-gray-100);
  border-color: var(--blue-gray-400);
}

.clear-filters-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* Responsive */
@media (max-width: 640px) {
  .batch-filters {
    flex-direction: column;
    align-items: stretch;
  }

  .filter-group {
    width: 100%;
  }

  .filter-select {
    width: 100%;
  }

  .clear-filters-btn {
    width: 100%;
    justify-content: center;
  }
}
</style>
