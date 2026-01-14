<!--
  AutoBot - AI-Powered Automation Platform
  Copyright (c) 2025 mrveiss
  Author: mrveiss

  Batch Jobs List Component - Table/list of batch jobs
  Issue #584 - Batch Processing Manager
-->
<template>
  <div class="batch-jobs-list">
    <!-- Empty state -->
    <div class="empty-state" v-if="jobs.length === 0 && !loading">
      <i class="fas fa-layer-group empty-icon"></i>
      <h3 class="empty-title">No Batch Jobs</h3>
      <p class="empty-text">{{ emptyMessage }}</p>
    </div>

    <!-- Loading state -->
    <div class="loading-state" v-if="loading">
      <i class="fas fa-spinner fa-spin loading-icon"></i>
      <span>Loading batch jobs...</span>
    </div>

    <!-- Jobs table -->
    <div class="table-container" v-if="jobs.length > 0 && !loading">
      <table class="jobs-table">
        <thead>
          <tr>
            <th class="col-status">Status</th>
            <th class="col-name">Job Name</th>
            <th class="col-progress">Progress</th>
            <th class="col-type">Type</th>
            <th class="col-time">Created</th>
            <th class="col-actions">Actions</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="job in jobs"
            :key="job.job_id"
            class="job-row"
            :class="{ 'row-selected': selectedId === job.job_id }"
            @click="emit('select', job)"
          >
            <td class="col-status">
              <span
                class="status-badge"
                :class="[
                  BATCH_STATUS_CONFIG[job.status].bgClass,
                  BATCH_STATUS_CONFIG[job.status].textClass
                ]"
              >
                <i :class="BATCH_STATUS_CONFIG[job.status].icon"></i>
              </span>
            </td>
            <td class="col-name">
              <div class="name-cell">
                <span class="job-name">{{ job.name }}</span>
              </div>
            </td>
            <td class="col-progress">
              <div class="progress-cell">
                <BatchProgress
                  :progress="job.progress"
                  :status="job.status"
                  :show-info="false"
                  size="small"
                />
                <span class="progress-text">{{ job.progress }}%</span>
              </div>
            </td>
            <td class="col-type">
              <span class="type-badge">
                <i :class="BATCH_TYPE_ICONS[job.job_type]"></i>
                {{ BATCH_TYPE_LABELS[job.job_type] }}
              </span>
            </td>
            <td class="col-time">
              <span class="time-text">{{ formatRelativeTime(job.created_at) }}</span>
            </td>
            <td class="col-actions">
              <div class="action-buttons">
                <button
                  class="action-btn cancel-btn"
                  v-if="canCancelJob(job)"
                  @click.stop="emit('cancel', job.job_id)"
                  title="Cancel"
                >
                  <i class="fas fa-stop"></i>
                </button>
                <button
                  class="action-btn delete-btn"
                  v-if="canDeleteJob(job)"
                  @click.stop="emit('delete', job.job_id)"
                  title="Delete"
                >
                  <i class="fas fa-trash"></i>
                </button>
                <button
                  class="action-btn view-btn"
                  @click.stop="emit('select', job)"
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

    <div class="list-footer" v-if="jobs.length > 0">
      <span class="footer-text">Showing {{ jobs.length }} of {{ totalCount }} jobs</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { BatchJob } from '@/types/batch-processing'
import {
  BATCH_STATUS_CONFIG,
  BATCH_TYPE_LABELS,
  BATCH_TYPE_ICONS,
  formatRelativeTime,
  canCancelJob as canCancel,
  isTerminalStatus
} from '@/types/batch-processing'
import BatchProgress from './BatchProgress.vue'

interface Props {
  jobs: BatchJob[]
  totalCount: number
  loading?: boolean
  selectedId?: string | null
  emptyMessage?: string
}

const props = withDefaults(defineProps<Props>(), {
  loading: false,
  selectedId: null,
  emptyMessage: 'No batch jobs found. Create a new job to get started.'
})

const emit = defineEmits<{
  select: [job: BatchJob]
  cancel: [jobId: string]
  delete: [jobId: string]
}>()

function canCancelJob(job: BatchJob): boolean {
  return canCancel(job)
}

function canDeleteJob(job: BatchJob): boolean {
  return isTerminalStatus(job.status)
}
</script>

<style scoped>
.batch-jobs-list {
  display: flex;
  flex-direction: column;
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 3rem 1rem;
  text-align: center;
}

.empty-icon {
  font-size: 3rem;
  color: var(--blue-gray-300);
  margin-bottom: 1rem;
}

.empty-title {
  font-size: 1.25rem;
  font-weight: 600;
  color: var(--blue-gray-600);
  margin: 0 0 0.5rem 0;
}

.empty-text {
  font-size: 0.875rem;
  color: var(--blue-gray-500);
  margin: 0;
  max-width: 400px;
}

.loading-state {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.75rem;
  padding: 2rem;
  color: var(--blue-gray-500);
}

.table-container {
  overflow-x: auto;
}

.jobs-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.875rem;
}

.jobs-table th {
  text-align: left;
  padding: 0.75rem 1rem;
  font-weight: 600;
  color: var(--blue-gray-600);
  background-color: var(--blue-gray-50);
  border-bottom: 1px solid var(--blue-gray-200);
}

.jobs-table td {
  padding: 0.75rem 1rem;
  border-bottom: 1px solid var(--blue-gray-100);
}

.job-row {
  cursor: pointer;
  transition: background-color 0.15s;
}

.job-row:hover {
  background-color: var(--blue-gray-50);
}

.row-selected {
  background-color: #dbeafe !important;
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

.job-name {
  font-weight: 500;
  color: var(--blue-gray-800);
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
  transition: opacity 0.15s;
}

.action-btn:hover {
  opacity: 0.8;
}

.cancel-btn {
  background-color: #fee2e2;
  color: #dc2626;
}

.delete-btn {
  background-color: #fef3c7;
  color: #d97706;
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

/* Status badge colors */
.bg-gray-100 {
  background-color: #f3f4f6;
}

.text-gray-700 {
  color: #374151;
}

.bg-blue-100 {
  background-color: #dbeafe;
}

.text-blue-700 {
  color: #1d4ed8;
}

.bg-green-100 {
  background-color: #dcfce7;
}

.text-green-700 {
  color: #15803d;
}

.bg-red-100 {
  background-color: #fee2e2;
}

.text-red-700 {
  color: #b91c1c;
}

.bg-yellow-100 {
  background-color: #fef3c7;
}

.text-yellow-700 {
  color: #a16207;
}
</style>
