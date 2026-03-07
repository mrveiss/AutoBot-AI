<template>
  <div class="audit-filters">
    <div class="filter-row">
      <!-- Date Range Filter -->
      <div class="filter-group">
        <label for="date-range">{{ $t('audit.filters.dateRange') }}</label>
        <select
          id="date-range"
          :value="filter.dateRange"
          @change="handleDateRangeChange"
        >
          <option value="today">{{ $t('audit.filters.today') }}</option>
          <option value="week">{{ $t('audit.filters.last7Days') }}</option>
          <option value="month">{{ $t('audit.filters.last30Days') }}</option>
          <option value="custom">{{ $t('audit.filters.custom') }}</option>
        </select>
      </div>

      <!-- Custom Date Inputs -->
      <template v-if="filter.dateRange === 'custom'">
        <div class="filter-group">
          <label for="start-date">{{ $t('audit.filters.startDate') }}</label>
          <input
            id="start-date"
            type="datetime-local"
            :value="filter.startDate"
            @input="handleStartDateChange"
          />
        </div>
        <div class="filter-group">
          <label for="end-date">{{ $t('audit.filters.endDate') }}</label>
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
        <label for="operation">{{ $t('audit.filters.operation') }}</label>
        <select
          id="operation"
          :value="filter.operation || ''"
          @change="handleOperationChange"
        >
          <option value="">{{ $t('audit.filters.allOperations') }}</option>
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
        <label for="result">{{ $t('audit.filters.result') }}</label>
        <select
          id="result"
          :value="filter.result || ''"
          @change="handleResultChange"
        >
          <option value="">{{ $t('audit.filters.allResults') }}</option>
          <option value="success">{{ $t('audit.filters.success') }}</option>
          <option value="denied">{{ $t('audit.filters.denied') }}</option>
          <option value="failed">{{ $t('audit.filters.failed') }}</option>
          <option value="error">{{ $t('audit.filters.error') }}</option>
        </select>
      </div>
    </div>

    <div class="filter-row">
      <!-- User Filter -->
      <div class="filter-group">
        <label for="user-id">{{ $t('audit.filters.user') }}</label>
        <input
          id="user-id"
          type="text"
          :value="filter.userId || ''"
          :placeholder="$t('audit.filters.userPlaceholder')"
          @input="handleUserIdChange"
        />
      </div>

      <!-- Session Filter -->
      <div class="filter-group">
        <label for="session-id">{{ $t('audit.filters.session') }}</label>
        <input
          id="session-id"
          type="text"
          :value="filter.sessionId || ''"
          :placeholder="$t('audit.filters.sessionPlaceholder')"
          @input="handleSessionIdChange"
        />
      </div>

      <!-- VM Filter -->
      <div class="filter-group">
        <label for="vm-name">{{ $t('audit.filters.vm') }}</label>
        <input
          id="vm-name"
          type="text"
          :value="filter.vmName || ''"
          :placeholder="$t('audit.filters.vmPlaceholder')"
          @input="handleVmNameChange"
        />
      </div>

      <!-- Limit -->
      <div class="filter-group filter-group-small">
        <label for="limit">{{ $t('audit.filters.limit') }}</label>
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
        {{ $t('audit.filters.applyFilters') }}
      </button>
      <button class="btn btn-secondary" @click="resetFilters">
        <i class="fas fa-undo"></i>
        {{ $t('audit.filters.reset') }}
      </button>
      <button
        v-if="hasActiveFilters"
        class="btn btn-ghost"
        @click="clearFilters"
      >
        <i class="fas fa-times"></i>
        {{ $t('audit.filters.clearAll') }}
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
