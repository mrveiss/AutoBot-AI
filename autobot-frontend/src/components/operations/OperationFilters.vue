<!--
  AutoBot - AI-Powered Automation Platform
  Copyright (c) 2025 mrveiss
  Author: mrveiss

  Operation Filters Component
  Issue #591 - Long-Running Operations Tracker
-->
<template>
  <div class="operation-filters">
    <!-- Status filter -->
    <div class="filter-group">
      <label class="filter-label">{{ $t('operations.filters.statusLabel') }}</label>
      <select
        v-model="localStatus"
        class="filter-select"
        @change="emitFilter"
      >
        <option :value="undefined">{{ $t('operations.filters.allStatuses') }}</option>
        <option
          v-for="status in statuses"
          :key="status"
          :value="status"
        >
          {{ STATUS_CONFIG[status].label }}
        </option>
      </select>
    </div>

    <!-- Type filter -->
    <div class="filter-group">
      <label class="filter-label">{{ $t('operations.filters.typeLabel') }}</label>
      <select
        v-model="localType"
        class="filter-select"
        @change="emitFilter"
      >
        <option :value="undefined">{{ $t('operations.filters.allTypes') }}</option>
        <option
          v-for="(label, type) in OPERATION_TYPE_LABELS"
          :key="type"
          :value="type"
        >
          {{ label }}
        </option>
      </select>
    </div>

    <!-- Limit filter -->
    <div class="filter-group">
      <label class="filter-label">{{ $t('operations.filters.showLabel') }}</label>
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
      <Icon name="times" />
      {{ $t('operations.filters.clear') }}
    </button>
  </div>
</template>

<script setup lang="ts">
import Icon from '@/components/ui/Icon.vue'
import { ref, computed, watch } from 'vue'
import type { OperationsFilter, OperationStatus, OperationType } from '@/types/operations'
import { STATUS_CONFIG, OPERATION_TYPE_LABELS } from '@/types/operations'


interface Props {
  filter: OperationsFilter
}

const props = defineProps<Props>()

const emit = defineEmits<{
  'update:filter': [filter: OperationsFilter]
  clear: []
}>()

// All available statuses
const statuses: OperationStatus[] = [
  'pending',
  'running',
  'completed',
  'failed',
  'timeout',
  'cancelled',
  'paused'
]

// Local filter state
const localStatus = ref<OperationStatus | undefined>(props.filter.status)
const localType = ref<OperationType | undefined>(props.filter.operation_type)
const localLimit = ref(props.filter.limit || 50)

// Watch for external filter changes
watch(() => props.filter, (newFilter) => {
  localStatus.value = newFilter.status
  localType.value = newFilter.operation_type
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
    operation_type: localType.value,
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
.operation-filters {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  gap: var(--spacing-4);
  padding: var(--spacing-4);
  background-color: var(--bg-secondary);
  border-radius: var(--radius-lg);
  border: 1px solid var(--border-default);
}

.filter-group {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-1);
}

.filter-label {
  font-size: var(--text-xs);
  font-weight: 500;
  color: var(--text-secondary);
}

.filter-select {
  padding: var(--spacing-2) var(--spacing-8) var(--spacing-2) var(--spacing-3);
  font-size: var(--text-sm);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  background-color: var(--bg-input);
  color: var(--text-primary);
  cursor: pointer;
  appearance: none;
  background-image: url("data:image/svg+xml,%3csvg xmlns='http://www.w3.org/2000/svg' fill='none' viewBox='0 0 20 20'%3e%3cpath stroke='%236b7280' stroke-linecap='round' stroke-linejoin='round' stroke-width='1.5' d='M6 8l4 4 4-4'/%3e%3c/svg%3e");
  background-position: right 0.5rem center;
  background-repeat: no-repeat;
  background-size: 1.5em 1.5em;
}

.filter-select:hover {
  border-color: var(--border-strong);
}

.filter-select:focus {
  outline: none;
  border-color: var(--color-primary);
  box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.2);
}
.filter-select:focus-visible {
  outline: 2px solid var(--color-primary);
  outline-offset: 2px;
}

.clear-filters-btn {
  display: flex;
  align-items: center;
  gap: var(--spacing-1-5);
  padding: var(--spacing-2) var(--spacing-3);
  font-size: var(--text-sm);
  font-weight: 500;
  color: var(--text-secondary);
  background-color: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: all var(--duration-200);
}

.clear-filters-btn:hover:not(:disabled) {
  background-color: var(--bg-hover);
  border-color: var(--border-strong);
}

.clear-filters-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* Responsive */
@media (max-width: 640px) {
  .operation-filters {
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
