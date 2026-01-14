<!--
  AutoBot - AI-Powered Automation Platform
  Copyright (c) 2025 mrveiss
  Author: mrveiss

  Batch Job Detail Component - Side panel for job details
  Issue #584 - Batch Processing Manager
-->
<template>
  <div class="batch-job-detail" v-if="job">
    <!-- Header -->
    <div class="detail-header">
      <div class="header-left">
        <i :class="BATCH_TYPE_ICONS[job.job_type]" class="type-icon"></i>
        <div class="header-info">
          <h3 class="job-name">{{ job.name }}</h3>
          <span class="job-type">{{ BATCH_TYPE_LABELS[job.job_type] }}</span>
        </div>
      </div>
      <button class="close-btn" @click="emit('close')" title="Close">
        <i class="fas fa-times"></i>
      </button>
    </div>

    <!-- Status badge -->
    <div class="status-section">
      <span
        class="status-badge"
        :class="[
          BATCH_STATUS_CONFIG[job.status].bgClass,
          BATCH_STATUS_CONFIG[job.status].textClass
        ]"
      >
        <i :class="BATCH_STATUS_CONFIG[job.status].icon"></i>
        {{ BATCH_STATUS_CONFIG[job.status].label }}
      </span>
    </div>

    <!-- Progress -->
    <div class="progress-section">
      <h4 class="section-title">Progress</h4>
      <BatchProgress
        :progress="job.progress"
        :status="job.status"
        size="large"
      />
    </div>

    <!-- Timing info -->
    <div class="timing-section">
      <h4 class="section-title">Timing</h4>
      <div class="timing-grid">
        <div class="timing-item">
          <span class="timing-label">Created</span>
          <span class="timing-value">{{ formatDateTime(job.created_at) }}</span>
        </div>
        <div class="timing-item" v-if="job.started_at">
          <span class="timing-label">Started</span>
          <span class="timing-value">{{ formatDateTime(job.started_at) }}</span>
        </div>
        <div class="timing-item" v-if="job.completed_at">
          <span class="timing-label">Completed</span>
          <span class="timing-value">{{ formatDateTime(job.completed_at) }}</span>
        </div>
        <div class="timing-item">
          <span class="timing-label">Duration</span>
          <span class="timing-value">{{ formatDuration(job.started_at, job.completed_at) }}</span>
        </div>
      </div>
    </div>

    <!-- Error message -->
    <div class="error-section" v-if="job.error_message">
      <h4 class="section-title error-title">
        <i class="fas fa-exclamation-triangle"></i>
        Error
      </h4>
      <div class="error-message">{{ job.error_message }}</div>
    </div>

    <!-- Result (if completed) -->
    <div class="result-section" v-if="job.result && Object.keys(job.result).length > 0">
      <h4 class="section-title">Result</h4>
      <pre class="result-json">{{ JSON.stringify(job.result, null, 2) }}</pre>
    </div>

    <!-- Parameters (collapsible) -->
    <div class="params-section" v-if="hasParameters">
      <button class="params-toggle" @click="showParams = !showParams">
        <i :class="showParams ? 'fas fa-chevron-down' : 'fas fa-chevron-right'"></i>
        <h4 class="section-title">Parameters</h4>
      </button>
      <div class="params-content" v-if="showParams">
        <pre class="params-json">{{ JSON.stringify(job.parameters, null, 2) }}</pre>
      </div>
    </div>

    <!-- Logs section -->
    <div class="logs-section" v-if="logs && logs.logs.length > 0">
      <h4 class="section-title">Logs</h4>
      <div class="logs-container">
        <div
          v-for="(log, index) in logs.logs"
          :key="index"
          class="log-entry"
          :class="`log-${log.level}`"
        >
          <span class="log-time">{{ formatLogTime(log.timestamp) }}</span>
          <span class="log-level">{{ log.level.toUpperCase() }}</span>
          <span class="log-message">{{ log.message }}</span>
        </div>
      </div>
    </div>

    <!-- Actions -->
    <div class="actions-section">
      <button
        class="action-btn cancel-btn"
        v-if="canCancel"
        @click="handleCancel"
        :disabled="actionLoading"
      >
        <i class="fas fa-stop-circle"></i>
        Cancel Job
      </button>
      <button
        class="action-btn delete-btn"
        v-if="canDelete"
        @click="handleDelete"
        :disabled="actionLoading"
      >
        <i class="fas fa-trash"></i>
        Delete Job
      </button>
      <button
        class="action-btn refresh-btn"
        @click="handleRefresh"
        :disabled="actionLoading"
      >
        <i class="fas fa-sync-alt" :class="{ 'fa-spin': actionLoading }"></i>
        Refresh
      </button>
    </div>

    <!-- Job ID footer -->
    <div class="detail-footer">
      <span class="job-id">ID: {{ job.job_id }}</span>
      <button class="copy-id-btn" @click="copyId" :title="copied ? 'Copied!' : 'Copy ID'">
        <i :class="copied ? 'fas fa-check' : 'fas fa-copy'"></i>
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import type { BatchJob, BatchJobLogsResponse } from '@/types/batch-processing'
import {
  BATCH_STATUS_CONFIG,
  BATCH_TYPE_LABELS,
  BATCH_TYPE_ICONS,
  formatDuration,
  formatDateTime,
  canCancelJob,
  isTerminalStatus
} from '@/types/batch-processing'
import { useClipboard } from '@/composables/useClipboard'
import BatchProgress from './BatchProgress.vue'

interface Props {
  job: BatchJob
  logs?: BatchJobLogsResponse | null
}

const props = defineProps<Props>()

const emit = defineEmits<{
  close: []
  cancel: [jobId: string]
  delete: [jobId: string]
  refresh: [jobId: string]
}>()

const showParams = ref(false)
const actionLoading = ref(false)
const { copy, copied } = useClipboard({ copiedDuration: 2000 })

const hasParameters = computed(() =>
  props.job.parameters && Object.keys(props.job.parameters).length > 0
)

const canCancel = computed(() => canCancelJob(props.job))
const canDelete = computed(() => isTerminalStatus(props.job.status))

function formatLogTime(timestamp: string): string {
  return new Date(timestamp).toLocaleTimeString()
}

async function handleCancel() {
  actionLoading.value = true
  try {
    emit('cancel', props.job.job_id)
  } finally {
    actionLoading.value = false
  }
}

async function handleDelete() {
  actionLoading.value = true
  try {
    emit('delete', props.job.job_id)
  } finally {
    actionLoading.value = false
  }
}

function handleRefresh() {
  emit('refresh', props.job.job_id)
}

async function copyId() {
  await copy(props.job.job_id)
}
</script>

<style scoped>
.batch-job-detail {
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
  padding: 1.5rem;
  background-color: white;
  border-radius: 0.5rem;
  border: 1px solid var(--blue-gray-200);
  max-height: 80vh;
  overflow-y: auto;
}

.detail-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
}

.header-left {
  display: flex;
  align-items: flex-start;
  gap: 0.75rem;
}

.type-icon {
  font-size: 1.5rem;
  color: #2563eb;
  margin-top: 0.125rem;
}

.header-info {
  display: flex;
  flex-direction: column;
}

.job-name {
  font-size: 1.25rem;
  font-weight: 600;
  color: var(--blue-gray-800);
  margin: 0;
}

.job-type {
  font-size: 0.875rem;
  color: var(--blue-gray-500);
}

.close-btn {
  padding: 0.5rem;
  background: none;
  border: none;
  color: var(--blue-gray-400);
  cursor: pointer;
  border-radius: 0.25rem;
}

.close-btn:hover {
  background-color: var(--blue-gray-100);
  color: var(--blue-gray-600);
}

.status-section {
  display: flex;
  gap: 0.75rem;
  flex-wrap: wrap;
}

.status-badge {
  display: inline-flex;
  align-items: center;
  gap: 0.375rem;
  padding: 0.375rem 0.75rem;
  font-size: 0.875rem;
  font-weight: 500;
  border-radius: 9999px;
}

.section-title {
  font-size: 0.875rem;
  font-weight: 600;
  color: var(--blue-gray-700);
  margin: 0 0 0.5rem 0;
}

.progress-section,
.timing-section,
.result-section,
.logs-section {
  padding-top: 0.75rem;
  border-top: 1px solid var(--blue-gray-100);
}

.timing-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 0.75rem;
}

.timing-item {
  display: flex;
  flex-direction: column;
  gap: 0.125rem;
}

.timing-label {
  font-size: 0.75rem;
  color: var(--blue-gray-500);
}

.timing-value {
  font-size: 0.875rem;
  color: var(--blue-gray-700);
}

.error-section {
  padding: 1rem;
  background-color: #fef2f2;
  border: 1px solid #fecaca;
  border-radius: 0.375rem;
}

.error-title {
  display: flex;
  align-items: center;
  gap: 0.375rem;
  color: #991b1b;
}

.error-message {
  font-size: 0.875rem;
  color: #7f1d1d;
  font-family: monospace;
  white-space: pre-wrap;
  word-break: break-word;
}

.result-json,
.params-json {
  font-size: 0.75rem;
  background-color: var(--blue-gray-50);
  padding: 1rem;
  border-radius: 0.375rem;
  overflow-x: auto;
  margin: 0;
}

.params-section {
  border-top: 1px solid var(--blue-gray-100);
  padding-top: 0.75rem;
}

.params-toggle {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  background: none;
  border: none;
  padding: 0;
  cursor: pointer;
  color: var(--blue-gray-600);
}

.params-toggle:hover {
  color: var(--blue-gray-800);
}

.params-toggle .section-title {
  margin: 0;
}

.params-content {
  margin-top: 0.75rem;
}

.logs-container {
  max-height: 200px;
  overflow-y: auto;
  background-color: var(--blue-gray-50);
  border-radius: 0.375rem;
  padding: 0.5rem;
}

.log-entry {
  display: flex;
  gap: 0.5rem;
  font-size: 0.75rem;
  font-family: monospace;
  padding: 0.25rem 0;
}

.log-time {
  color: var(--blue-gray-400);
}

.log-level {
  font-weight: 600;
  min-width: 50px;
}

.log-debug .log-level {
  color: var(--blue-gray-500);
}

.log-info .log-level {
  color: #2563eb;
}

.log-warning .log-level {
  color: #d97706;
}

.log-error .log-level {
  color: #dc2626;
}

.log-message {
  color: var(--blue-gray-700);
  word-break: break-word;
}

.actions-section {
  display: flex;
  gap: 0.75rem;
  padding-top: 1rem;
  border-top: 1px solid var(--blue-gray-200);
}

.action-btn {
  display: flex;
  align-items: center;
  gap: 0.375rem;
  padding: 0.5rem 1rem;
  font-size: 0.875rem;
  font-weight: 500;
  border-radius: 0.375rem;
  cursor: pointer;
  transition: all 0.2s;
}

.action-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.cancel-btn {
  background-color: #fee2e2;
  color: #991b1b;
  border: 1px solid #fecaca;
}

.cancel-btn:hover:not(:disabled) {
  background-color: #fecaca;
}

.delete-btn {
  background-color: #fef3c7;
  color: #92400e;
  border: 1px solid #fde68a;
}

.delete-btn:hover:not(:disabled) {
  background-color: #fde68a;
}

.refresh-btn {
  background-color: white;
  color: var(--blue-gray-700);
  border: 1px solid var(--blue-gray-300);
}

.refresh-btn:hover:not(:disabled) {
  background-color: var(--blue-gray-50);
}

.detail-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-top: 0.75rem;
  border-top: 1px solid var(--blue-gray-100);
}

.job-id {
  font-size: 0.75rem;
  font-family: monospace;
  color: var(--blue-gray-400);
}

.copy-id-btn {
  padding: 0.25rem 0.5rem;
  font-size: 0.75rem;
  background: none;
  border: 1px solid var(--blue-gray-200);
  color: var(--blue-gray-500);
  border-radius: 0.25rem;
  cursor: pointer;
}

.copy-id-btn:hover {
  background-color: var(--blue-gray-50);
  color: var(--blue-gray-700);
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

/* Responsive */
@media (max-width: 640px) {
  .timing-grid {
    grid-template-columns: 1fr;
  }

  .actions-section {
    flex-direction: column;
  }

  .action-btn {
    width: 100%;
    justify-content: center;
  }
}
</style>
