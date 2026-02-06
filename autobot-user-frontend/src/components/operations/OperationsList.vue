<!--
  AutoBot - AI-Powered Automation Platform
  Copyright (c) 2025 mrveiss
  Author: mrveiss

  Operations List Component
  Issue #591 - Long-Running Operations Tracker
-->
<template>
  <div class="operations-list">
    <!-- Empty state -->
    <div class="empty-state" v-if="operations.length === 0 && !loading">
      <i class="fas fa-tasks empty-icon"></i>
      <h3 class="empty-title">No Operations</h3>
      <p class="empty-text">{{ emptyMessage }}</p>
    </div>

    <!-- Loading state -->
    <div class="loading-state" v-if="loading">
      <i class="fas fa-spinner fa-spin loading-icon"></i>
      <span>Loading operations...</span>
    </div>

    <!-- Operations table -->
    <div class="table-container" v-if="operations.length > 0 && !loading">
      <table class="operations-table">
        <thead>
          <tr>
            <th class="col-status">Status</th>
            <th class="col-name">Operation</th>
            <th class="col-progress">Progress</th>
            <th class="col-type">Type</th>
            <th class="col-time">Started</th>
            <th class="col-actions">Actions</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="operation in operations"
            :key="operation.operation_id"
            class="operation-row"
            :class="{ 'row-selected': selectedId === operation.operation_id }"
            @click="emit('select', operation)"
          >
            <td class="col-status">
              <span
                class="status-badge"
                :class="[STATUS_CONFIG[operation.status].bgClass, STATUS_CONFIG[operation.status].textClass]"
              >
                <i :class="STATUS_CONFIG[operation.status].icon"></i>
              </span>
            </td>
            <td class="col-name">
              <div class="name-cell">
                <span class="operation-name">{{ operation.name }}</span>
                <span class="operation-step" v-if="operation.current_step && operation.status === 'running'">
                  {{ operation.current_step }}
                </span>
              </div>
            </td>
            <td class="col-progress">
              <div class="progress-cell">
                <OperationProgress
                  :progress="operation.progress"
                  :status="operation.status"
                  :show-info="false"
                  :show-items="false"
                  :show-step="false"
                  size="small"
                />
                <span class="progress-text">{{ operation.progress }}%</span>
              </div>
            </td>
            <td class="col-type">
              <span class="type-badge">
                <i :class="OPERATION_TYPE_ICONS[operation.operation_type]"></i>
                {{ OPERATION_TYPE_LABELS[operation.operation_type] }}
              </span>
            </td>
            <td class="col-time">
              <span class="time-text">{{ formatRelativeTime(operation.started_at || operation.created_at) }}</span>
            </td>
            <td class="col-actions">
              <div class="action-buttons">
                <button
                  class="action-btn cancel-btn"
                  v-if="canCancelOperation(operation)"
                  @click.stop="emit('cancel', operation.operation_id)"
                  title="Cancel"
                >
                  <i class="fas fa-stop"></i>
                </button>
                <button
                  class="action-btn resume-btn"
                  v-if="canResumeOperation(operation)"
                  @click.stop="emit('resume', operation.operation_id)"
                  title="Resume"
                >
                  <i class="fas fa-play"></i>
                </button>
                <button
                  class="action-btn view-btn"
                  @click.stop="emit('select', operation)"
                  title="View Details"
                >
                  <i class="fas fa-eye"></i>
                </button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <div class="list-footer" v-if="operations.length > 0">
      <span class="footer-text">Showing {{ operations.length }} of {{ totalCount }} operations</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { Operation } from '@/types/operations'
import {
  STATUS_CONFIG,
  OPERATION_TYPE_LABELS,
  OPERATION_TYPE_ICONS,
  formatRelativeTime,
  canCancel,
  canResume
} from '@/types/operations'
import OperationProgress from './OperationProgress.vue'

interface Props {
  operations: Operation[]
  totalCount: number
  loading?: boolean
  selectedId?: string | null
  emptyMessage?: string
}

const props = withDefaults(defineProps<Props>(), {
  loading: false,
  selectedId: null,
  emptyMessage: 'No operations found. Operations will appear here when background tasks are running.'
})

const emit = defineEmits<{
  select: [operation: Operation]
  cancel: [operationId: string]
  resume: [operationId: string]
}>()

function canCancelOperation(operation: Operation): boolean {
  return canCancel(operation)
}

function canResumeOperation(operation: Operation): boolean {
  return canResume(operation)
}
</script>

<style scoped>
/* Issue #704: Migrated to CSS design tokens */
.operations-list {
  display: flex;
  flex-direction: column;
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: var(--spacing-12) var(--spacing-4);
  text-align: center;
}

.empty-icon {
  font-size: var(--text-4xl);
  color: var(--text-tertiary);
  margin-bottom: var(--spacing-4);
}

.empty-title {
  font-size: var(--text-xl);
  font-weight: var(--font-semibold);
  color: var(--text-secondary);
  margin: 0 0 var(--spacing-2) 0;
}

.empty-text {
  font-size: var(--text-sm);
  color: var(--text-tertiary);
  margin: 0;
  max-width: 400px;
}

.loading-state {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--spacing-3);
  padding: var(--spacing-8);
  color: var(--text-tertiary);
}

.table-container {
  overflow-x: auto;
}

.operations-table {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--text-sm);
}

.operations-table th {
  text-align: left;
  padding: var(--spacing-3) var(--spacing-4);
  font-weight: var(--font-semibold);
  color: var(--text-secondary);
  background-color: var(--bg-tertiary);
  border-bottom: 1px solid var(--border-default);
}

.operations-table td {
  padding: var(--spacing-3) var(--spacing-4);
  border-bottom: 1px solid var(--border-light);
}

.operation-row {
  cursor: pointer;
  transition: background-color var(--duration-150);
}

.operation-row:hover {
  background-color: var(--bg-tertiary);
}

.row-selected {
  background-color: var(--color-info-bg) !important;
}

.status-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border-radius: 9999px;
}

.name-cell {
  display: flex;
  flex-direction: column;
  gap: 0.125rem;
}

.operation-name {
  font-weight: 500;
  color: var(--blue-gray-800);
}

.operation-step {
  font-size: 0.75rem;
  color: var(--blue-gray-500);
  max-width: 250px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.progress-cell {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  min-width: 120px;
}

.progress-text {
  font-size: 0.75rem;
  font-weight: 500;
  color: var(--blue-gray-600);
}

.type-badge {
  display: inline-flex;
  align-items: center;
  gap: 0.375rem;
  font-size: 0.75rem;
  color: var(--blue-gray-600);
}

.time-text {
  font-size: 0.75rem;
  color: var(--blue-gray-500);
}

.action-buttons {
  display: flex;
  gap: 0.25rem;
}

.action-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border-radius: 0.25rem;
  border: none;
  cursor: pointer;
}

.cancel-btn {
  background-color: #fee2e2;
  color: #dc2626;
}

.resume-btn {
  background-color: #dcfce7;
  color: #16a34a;
}

.view-btn {
  background-color: var(--blue-gray-100);
  color: var(--blue-gray-600);
}

.list-footer {
  padding: 0.75rem 1rem;
  border-top: 1px solid var(--blue-gray-200);
  background-color: var(--blue-gray-50);
}

.footer-text {
  font-size: 0.75rem;
  color: var(--blue-gray-500);
}
</style>
