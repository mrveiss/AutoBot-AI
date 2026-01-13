<template>
  <div class="audit-filters">
    <div class="filter-row">
      <!-- Date Range Filter -->
      <div class="filter-group">
        <label for="date-range">Date Range</label>
        <select
          id="date-range"
          :value="filter.dateRange"
          @change="handleDateRangeChange"
        >
          <option value="today">Today</option>
          <option value="week">Last 7 Days</option>
          <option value="month">Last 30 Days</option>
          <option value="custom">Custom</option>
        </select>
      </div>

      <!-- Custom Date Inputs -->
      <template v-if="filter.dateRange === 'custom'">
        <div class="filter-group">
          <label for="start-date">Start Date</label>
          <input
            id="start-date"
            type="datetime-local"
            :value="filter.startDate"
            @input="handleStartDateChange"
          />
        </div>
        <div class="filter-group">
          <label for="end-date">End Date</label>
          <input
            id="end-date"
            type="datetime-local"
            :value="filter.endDate"
            @input="handleEndDateChange"
          />
        </div>
      </template>

      <!-- Operation Filter -->
      <div class="filter-group">
        <label for="operation">Operation</label>
        <select
          id="operation"
          :value="filter.operation || ''"
          @change="handleOperationChange"
        >
          <option value="">All Operations</option>
          <optgroup
            v-for="(ops, category) in operationCategories"
            :key="category"
            :label="category"
          >
            <option v-for="op in ops" :key="op" :value="op">
              {{ formatOperationName(op) }}
            </option>
          </optgroup>
        </select>
      </div>

      <!-- Result Filter -->
      <div class="filter-group">
        <label for="result">Result</label>
        <select
          id="result"
          :value="filter.result || ''"
          @change="handleResultChange"
        >
          <option value="">All Results</option>
          <option value="success">Success</option>
          <option value="denied">Denied</option>
          <option value="failed">Failed</option>
          <option value="error">Error</option>
        </select>
      </div>
    </div>

    <div class="filter-row">
      <!-- User Filter -->
      <div class="filter-group">
        <label for="user-id">User</label>
        <input
          id="user-id"
          type="text"
          :value="filter.userId || ''"
          placeholder="Filter by user..."
          @input="handleUserIdChange"
        />
      </div>

      <!-- Session Filter -->
      <div class="filter-group">
        <label for="session-id">Session</label>
        <input
          id="session-id"
          type="text"
          :value="filter.sessionId || ''"
          placeholder="Filter by session..."
          @input="handleSessionIdChange"
        />
      </div>

      <!-- VM Filter -->
      <div class="filter-group">
        <label for="vm-name">VM</label>
        <input
          id="vm-name"
          type="text"
          :value="filter.vmName || ''"
          placeholder="Filter by VM..."
          @input="handleVmNameChange"
        />
      </div>

      <!-- Limit -->
      <div class="filter-group filter-group-small">
        <label for="limit">Limit</label>
        <select
          id="limit"
          :value="filter.limit"
          @change="handleLimitChange"
        >
          <option :value="50">50</option>
          <option :value="100">100</option>
          <option :value="250">250</option>
          <option :value="500">500</option>
          <option :value="1000">1000</option>
        </select>
      </div>
    </div>

    <div class="filter-actions">
      <button class="btn btn-primary" @click="applyFilters">
        <i class="fas fa-search"></i>
        Apply Filters
      </button>
      <button class="btn btn-secondary" @click="resetFilters">
        <i class="fas fa-undo"></i>
        Reset
      </button>
      <button
        v-if="hasActiveFilters"
        class="btn btn-ghost"
        @click="clearFilters"
      >
        <i class="fas fa-times"></i>
        Clear All
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { AuditFilter, AuditResult } from '@/types/audit'

interface Props {
  filter: AuditFilter
  operationCategories: Record<string, string[]>
}

interface Emits {
  (e: 'update:filter', filter: Partial<AuditFilter>): void
  (e: 'apply'): void
  (e: 'reset'): void
}

const props = defineProps<Props>()
const emit = defineEmits<Emits>()

const hasActiveFilters = computed(() => {
  return (
    props.filter.operation !== null ||
    props.filter.result !== null ||
    props.filter.userId !== null ||
    props.filter.sessionId !== null ||
    props.filter.vmName !== null ||
    props.filter.dateRange === 'custom'
  )
})

function formatOperationName(operation: string): string {
  return operation
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (char) => char.toUpperCase())
}

function handleDateRangeChange(event: Event) {
  const target = event.target as HTMLSelectElement
  emit('update:filter', {
    dateRange: target.value as AuditFilter['dateRange']
  })
}

function handleStartDateChange(event: Event) {
  const target = event.target as HTMLInputElement
  emit('update:filter', { startDate: target.value || null })
}

function handleEndDateChange(event: Event) {
  const target = event.target as HTMLInputElement
  emit('update:filter', { endDate: target.value || null })
}

function handleOperationChange(event: Event) {
  const target = event.target as HTMLSelectElement
  emit('update:filter', { operation: target.value || null })
}

function handleResultChange(event: Event) {
  const target = event.target as HTMLSelectElement
  emit('update:filter', {
    result: (target.value as AuditResult) || null
  })
}

function handleUserIdChange(event: Event) {
  const target = event.target as HTMLInputElement
  emit('update:filter', { userId: target.value || null })
}

function handleSessionIdChange(event: Event) {
  const target = event.target as HTMLInputElement
  emit('update:filter', { sessionId: target.value || null })
}

function handleVmNameChange(event: Event) {
  const target = event.target as HTMLInputElement
  emit('update:filter', { vmName: target.value || null })
}

function handleLimitChange(event: Event) {
  const target = event.target as HTMLSelectElement
  emit('update:filter', { limit: parseInt(target.value) })
}

function applyFilters() {
  emit('apply')
}

function resetFilters() {
  emit('reset')
}

function clearFilters() {
  emit('update:filter', {
    operation: null,
    result: null,
    userId: null,
    sessionId: null,
    vmName: null,
    dateRange: 'today',
    startDate: null,
    endDate: null
  })
  emit('apply')
}
</script>

<style scoped>
.audit-filters {
  background: var(--bg-card);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-lg);
  padding: var(--spacing-4);
  margin-bottom: var(--spacing-4);
}

.filter-row {
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-4);
  margin-bottom: var(--spacing-4);
}

.filter-row:last-of-type {
  margin-bottom: var(--spacing-4);
}

.filter-group {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-1);
  min-width: 150px;
  flex: 1;
}

.filter-group-small {
  flex: 0 0 100px;
  min-width: 80px;
}

.filter-group label {
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
  color: var(--text-secondary);
}

.filter-group input,
.filter-group select {
  padding: var(--spacing-2) var(--spacing-3);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-default);
  font-size: var(--text-sm);
  background: var(--bg-input);
  color: var(--text-primary);
  transition: border-color var(--duration-200) var(--ease-in-out);
}

.filter-group input:focus,
.filter-group select:focus {
  outline: none;
  border-color: var(--color-primary);
  box-shadow: var(--ring-primary);
}

.filter-actions {
  display: flex;
  gap: var(--spacing-2);
  padding-top: var(--spacing-3);
  border-top: 1px solid var(--border-subtle);
}

.btn {
  display: inline-flex;
  align-items: center;
  gap: var(--spacing-2);
  padding: var(--spacing-2) var(--spacing-4);
  border-radius: var(--radius-default);
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
  cursor: pointer;
  transition: all var(--duration-200) var(--ease-in-out);
  border: none;
}

.btn-primary {
  background: var(--color-primary);
  color: white;
}

.btn-primary:hover {
  background: var(--color-primary-hover);
}

.btn-secondary {
  background: var(--bg-secondary);
  color: var(--text-primary);
  border: 1px solid var(--border-default);
}

.btn-secondary:hover {
  background: var(--bg-hover);
}

.btn-ghost {
  background: transparent;
  color: var(--text-secondary);
}

.btn-ghost:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}

@media (max-width: 768px) {
  .filter-row {
    flex-direction: column;
  }

  .filter-group {
    min-width: 100%;
  }

  .filter-group-small {
    flex: 1;
  }

  .filter-actions {
    flex-wrap: wrap;
  }

  .btn {
    flex: 1;
    justify-content: center;
  }
}
</style>
