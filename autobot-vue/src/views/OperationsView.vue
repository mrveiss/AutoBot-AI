<!--
  AutoBot - AI-Powered Automation Platform
  Copyright (c) 2025 mrveiss
  Author: mrveiss

  Operations View - Long-Running Operations Dashboard
  Issue #591 - Long-Running Operations Tracker
-->
<template>
  <div class="operations-view">
    <!-- Header -->
    <div class="view-header">
      <div class="header-title">
        <i class="fas fa-tasks header-icon"></i>
        <h1>Operations</h1>
      </div>
      <div class="header-actions">
        <button class="refresh-btn" @click="handleRefresh" :disabled="loading">
          <i class="fas fa-sync-alt" :class="{ 'fa-spin': loading }"></i>
          Refresh
        </button>
        <div class="polling-toggle">
          <label class="toggle-label">
            <input type="checkbox" v-model="autoRefresh" @change="togglePolling" />
            <span class="toggle-text">Auto-refresh</span>
          </label>
        </div>
      </div>
    </div>

    <!-- Stats cards -->
    <div class="stats-grid">
      <div class="stat-card">
        <div class="stat-icon active">
          <i class="fas fa-spinner"></i>
        </div>
        <div class="stat-info">
          <span class="stat-value">{{ activeCount }}</span>
          <span class="stat-label">Active</span>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-icon completed">
          <i class="fas fa-check-circle"></i>
        </div>
        <div class="stat-info">
          <span class="stat-value">{{ completedCount }}</span>
          <span class="stat-label">Completed</span>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-icon failed">
          <i class="fas fa-times-circle"></i>
        </div>
        <div class="stat-info">
          <span class="stat-value">{{ failedCount }}</span>
          <span class="stat-label">Failed</span>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-icon total">
          <i class="fas fa-list"></i>
        </div>
        <div class="stat-info">
          <span class="stat-value">{{ totalCount }}</span>
          <span class="stat-label">Total</span>
        </div>
      </div>
    </div>

    <!-- Service health indicator -->
    <div class="health-indicator" :class="healthClass" v-if="healthStatus">
      <i :class="healthIcon"></i>
      <span>{{ healthMessage }}</span>
    </div>

    <!-- Filters -->
    <OperationFilters
      :filter="filter"
      @update:filter="handleFilterUpdate"
      @clear="handleClearFilter"
    />

    <!-- Main content area -->
    <div class="content-area">
      <!-- Operations list -->
      <div class="list-panel">
        <OperationsList
          :operations="operations"
          :total-count="totalCount"
          :loading="loading"
          :selected-id="selectedOperation?.operation_id"
          @select="handleSelect"
          @cancel="handleCancel"
          @resume="handleResume"
        />
      </div>

      <!-- Detail panel -->
      <div class="detail-panel" v-if="selectedOperation">
        <OperationDetail
          :operation="selectedOperation"
          @close="selectedOperation = null"
          @cancel="handleCancel"
          @resume="handleResume"
          @refresh="handleRefreshOperation"
        />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useOperationsState } from '@/composables/useOperationsApi'
import { createLogger } from '@/utils/debugUtils'
import OperationFilters from '@/components/operations/OperationFilters.vue'
import OperationsList from '@/components/operations/OperationsList.vue'
import OperationDetail from '@/components/operations/OperationDetail.vue'
import type { Operation, OperationsFilter } from '@/types/operations'

const logger = createLogger('OperationsView')

const {
  operations,
  totalCount,
  activeCount,
  completedCount,
  failedCount,
  loading,
  selectedOperation,
  healthStatus,
  filter,
  isPolling,
  loadOperations,
  refreshOperation,
  cancelOperation,
  resumeOperation,
  checkHealth,
  setFilter,
  clearFilter,
  selectOperation,
  startPolling,
  stopPolling
} = useOperationsState()

const autoRefresh = ref(false)

// Health status computed properties
const healthClass = computed(() => {
  if (!healthStatus.value) return 'health-unknown'
  switch (healthStatus.value.status) {
    case 'healthy': return 'health-ok'
    case 'unavailable': return 'health-warning'
    default: return 'health-error'
  }
})

const healthIcon = computed(() => {
  if (!healthStatus.value) return 'fas fa-question-circle'
  switch (healthStatus.value.status) {
    case 'healthy': return 'fas fa-check-circle'
    case 'unavailable': return 'fas fa-exclamation-triangle'
    default: return 'fas fa-times-circle'
  }
})

const healthMessage = computed(() => {
  if (!healthStatus.value) return 'Checking service status...'
  switch (healthStatus.value.status) {
    case 'healthy':
      return `Service healthy - ${healthStatus.value.active_operations} active operations`
    case 'unavailable':
      return 'Operations service unavailable'
    default:
      return healthStatus.value.message || 'Service error'
  }
})

// Event handlers
async function handleRefresh() {
  await loadOperations()
  await checkHealth()
}

function handleSelect(operation: Operation) {
  selectOperation(operation)
}

async function handleCancel(operationId: string) {
  await cancelOperation(operationId)
  logger.info('Cancelled operation:', operationId)
}

async function handleResume(operationId: string) {
  await resumeOperation(operationId)
  logger.info('Resumed operation:', operationId)
}

async function handleRefreshOperation(operationId: string) {
  await refreshOperation(operationId)
}

async function handleFilterUpdate(newFilter: OperationsFilter) {
  await setFilter(newFilter)
}

async function handleClearFilter() {
  await clearFilter()
}

function togglePolling() {
  if (autoRefresh.value) {
    startPolling(5000)
  } else {
    stopPolling()
  }
}

// Lifecycle
onMounted(async () => {
  logger.debug('Operations view mounted')
  await loadOperations()
  await checkHealth()
})

onUnmounted(() => {
  stopPolling()
})
</script>

<style scoped>
.operations-view {
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
  padding: 1.5rem;
  max-width: 1600px;
  margin: 0 auto;
}

.view-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 1rem;
}

.header-title {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.header-icon {
  font-size: 1.5rem;
  color: var(--blue-600);
}

.header-title h1 {
  font-size: 1.5rem;
  font-weight: 600;
  color: var(--blue-gray-900);
  margin: 0;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 1rem;
}

.refresh-btn {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem 1rem;
  font-size: 0.875rem;
  font-weight: 500;
  color: var(--blue-gray-700);
  background-color: white;
  border: 1px solid var(--blue-gray-300);
  border-radius: 0.375rem;
  cursor: pointer;
}

.refresh-btn:hover:not(:disabled) {
  background-color: var(--blue-gray-50);
}

.refresh-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.polling-toggle {
  display: flex;
  align-items: center;
}

.toggle-label {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  cursor: pointer;
}

.toggle-text {
  font-size: 0.875rem;
  color: var(--blue-gray-600);
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 1rem;
}

.stat-card {
  display: flex;
  align-items: center;
  gap: 1rem;
  padding: 1rem;
  background-color: white;
  border: 1px solid var(--blue-gray-200);
  border-radius: 0.5rem;
}

.stat-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 48px;
  height: 48px;
  border-radius: 0.5rem;
  font-size: 1.25rem;
}

.stat-icon.active {
  background-color: #dbeafe;
  color: #2563eb;
}

.stat-icon.completed {
  background-color: #dcfce7;
  color: #16a34a;
}

.stat-icon.failed {
  background-color: #fee2e2;
  color: #dc2626;
}

.stat-icon.total {
  background-color: var(--blue-gray-100);
  color: var(--blue-gray-600);
}

.stat-info {
  display: flex;
  flex-direction: column;
}

.stat-value {
  font-size: 1.5rem;
  font-weight: 600;
  color: var(--blue-gray-900);
}

.stat-label {
  font-size: 0.75rem;
  color: var(--blue-gray-500);
}

.health-indicator {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.75rem 1rem;
  border-radius: 0.375rem;
  font-size: 0.875rem;
}

.health-ok {
  background-color: #dcfce7;
  color: #166534;
}

.health-warning {
  background-color: #fef3c7;
  color: #92400e;
}

.health-error {
  background-color: #fee2e2;
  color: #991b1b;
}

.health-unknown {
  background-color: var(--blue-gray-100);
  color: var(--blue-gray-600);
}

.content-area {
  display: grid;
  grid-template-columns: 1fr;
  gap: 1.5rem;
}

.list-panel {
  background-color: white;
  border: 1px solid var(--blue-gray-200);
  border-radius: 0.5rem;
  overflow: hidden;
}

.detail-panel {
  position: fixed;
  top: 0;
  right: 0;
  bottom: 0;
  width: 480px;
  max-width: 100vw;
  background-color: white;
  box-shadow: -4px 0 20px rgba(0, 0, 0, 0.15);
  z-index: 100;
  overflow-y: auto;
}

@media (min-width: 1200px) {
  .content-area {
    grid-template-columns: 1fr 400px;
  }

  .detail-panel {
    position: static;
    width: auto;
    box-shadow: none;
    border: 1px solid var(--blue-gray-200);
    border-radius: 0.5rem;
  }
}

@media (max-width: 640px) {
  .operations-view {
    padding: 1rem;
  }

  .view-header {
    flex-direction: column;
    align-items: flex-start;
  }

  .stats-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}
</style>
