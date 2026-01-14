<!--
  AutoBot - AI-Powered Automation Platform
  Copyright (c) 2025 mrveiss
  Author: mrveiss

  Batch Processing View - Main dashboard for batch job management
  Issue #584 - Batch Processing Manager
-->
<template>
  <div class="batch-processing-view">
    <!-- Header -->
    <div class="view-header">
      <div class="header-title">
        <i class="fas fa-layer-group header-icon"></i>
        <h1>Batch Processing</h1>
      </div>
      <div class="header-actions">
        <button class="create-btn" @click="showCreateForm = true">
          <i class="fas fa-plus"></i>
          New Job
        </button>
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
        <div class="stat-icon pending">
          <i class="fas fa-clock"></i>
        </div>
        <div class="stat-info">
          <span class="stat-value">{{ pendingCount }}</span>
          <span class="stat-label">Pending</span>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-icon running">
          <i class="fas fa-spinner"></i>
        </div>
        <div class="stat-info">
          <span class="stat-value">{{ runningCount }}</span>
          <span class="stat-label">Running</span>
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
    </div>

    <!-- Service health indicator -->
    <div class="health-indicator" :class="healthClass" v-if="healthStatus">
      <i :class="healthIcon"></i>
      <span>{{ healthMessage }}</span>
    </div>

    <!-- Filters -->
    <BatchFilters
      :filter="filter"
      @update:filter="handleFilterUpdate"
      @clear="handleClearFilter"
    />

    <!-- Main content area -->
    <div class="content-area">
      <!-- Jobs list -->
      <div class="list-panel">
        <BatchJobsList
          :jobs="jobs"
          :total-count="totalCount"
          :loading="loading"
          :selected-id="selectedJob?.job_id"
          @select="handleSelect"
          @cancel="handleCancel"
          @delete="handleDelete"
        />
      </div>

      <!-- Detail panel -->
      <div class="detail-panel" v-if="selectedJob">
        <BatchJobDetail
          :job="selectedJob"
          :logs="jobLogs"
          @close="selectedJob = null"
          @cancel="handleCancel"
          @delete="handleDelete"
          @refresh="handleRefreshJob"
        />
      </div>
    </div>

    <!-- Templates and Schedules section -->
    <div class="management-section">
      <BatchTemplates
        :templates="templates"
        :loading="templatesLoading"
        @create="handleCreateTemplate"
        @delete="handleDeleteTemplate"
      />
      <BatchScheduler
        :schedules="schedules"
        :templates="templates"
        :loading="schedulesLoading"
        @create="handleCreateSchedule"
        @toggle="handleToggleSchedule"
        @delete="handleDeleteSchedule"
      />
    </div>

    <!-- Create job form modal -->
    <BatchJobForm
      v-if="showCreateForm"
      :templates="templates"
      @close="showCreateForm = false"
      @submit="handleCreateJob"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useBatchProcessingState } from '@/composables/useBatchProcessing'
import { createLogger } from '@/utils/debugUtils'
import BatchFilters from '@/components/batch/BatchFilters.vue'
import BatchJobsList from '@/components/batch/BatchJobsList.vue'
import BatchJobDetail from '@/components/batch/BatchJobDetail.vue'
import BatchJobForm from '@/components/batch/BatchJobForm.vue'
import BatchTemplates from '@/components/batch/BatchTemplates.vue'
import BatchScheduler from '@/components/batch/BatchScheduler.vue'
import type {
  BatchJob,
  BatchJobsFilter,
  CreateBatchJobRequest,
  CreateBatchTemplateRequest,
  CreateBatchScheduleRequest
} from '@/types/batch-processing'

const logger = createLogger('BatchProcessingView')

const {
  jobs,
  totalCount,
  pendingCount,
  runningCount,
  completedCount,
  failedCount,
  loading,
  selectedJob,
  jobLogs,
  healthStatus,
  filter,
  templates,
  templatesLoading,
  schedules,
  schedulesLoading,
  loadJobs,
  refreshJob,
  createJob,
  cancelJob,
  deleteJob,
  checkHealth,
  setFilter,
  clearFilter,
  selectJob,
  loadTemplates,
  createTemplate,
  deleteTemplate,
  loadSchedules,
  createSchedule,
  toggleSchedule,
  deleteSchedule,
  startPolling,
  stopPolling
} = useBatchProcessingState()

const autoRefresh = ref(false)
const showCreateForm = ref(false)

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
      return `Service healthy - ${healthStatus.value.active_jobs} active jobs`
    case 'unavailable':
      return 'Batch processing service unavailable'
    default:
      return healthStatus.value.message || 'Service error'
  }
})

// Event handlers
async function handleRefresh() {
  await loadJobs()
  await checkHealth()
  await loadTemplates()
  await loadSchedules()
}

function handleSelect(job: BatchJob) {
  selectJob(job)
}

async function handleCancel(jobId: string) {
  await cancelJob(jobId)
  logger.info('Cancelled batch job:', jobId)
}

async function handleDelete(jobId: string) {
  if (confirm('Are you sure you want to delete this job?')) {
    await deleteJob(jobId)
    logger.info('Deleted batch job:', jobId)
  }
}

async function handleRefreshJob(jobId: string) {
  await refreshJob(jobId)
}

async function handleFilterUpdate(newFilter: BatchJobsFilter) {
  await setFilter(newFilter)
}

async function handleClearFilter() {
  await clearFilter()
}

async function handleCreateJob(request: CreateBatchJobRequest) {
  const result = await createJob(request)
  if (result) {
    showCreateForm.value = false
    logger.info('Created batch job:', result.job_id)
  }
}

async function handleCreateTemplate(request: CreateBatchTemplateRequest) {
  await createTemplate(request)
  logger.info('Created batch template:', request.name)
}

async function handleDeleteTemplate(templateId: string) {
  await deleteTemplate(templateId)
  logger.info('Deleted batch template:', templateId)
}

async function handleCreateSchedule(request: CreateBatchScheduleRequest) {
  await createSchedule(request)
  logger.info('Created batch schedule:', request.name)
}

async function handleToggleSchedule(scheduleId: string, enabled: boolean) {
  await toggleSchedule(scheduleId, enabled)
  logger.info('Toggled batch schedule:', scheduleId, enabled)
}

async function handleDeleteSchedule(scheduleId: string) {
  await deleteSchedule(scheduleId)
  logger.info('Deleted batch schedule:', scheduleId)
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
  logger.debug('Batch processing view mounted')
  await loadJobs()
  await checkHealth()
  await loadTemplates()
  await loadSchedules()
})

onUnmounted(() => {
  stopPolling()
})
</script>

<style scoped>
.batch-processing-view {
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

.create-btn {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem 1rem;
  font-size: 0.875rem;
  font-weight: 500;
  color: white;
  background-color: #2563eb;
  border: none;
  border-radius: 0.375rem;
  cursor: pointer;
  transition: background-color 0.15s;
}

.create-btn:hover {
  background-color: #1d4ed8;
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

.stat-icon.pending {
  background-color: #f3f4f6;
  color: #6b7280;
}

.stat-icon.running {
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

.management-section {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(350px, 1fr));
  gap: 1.5rem;
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
  .batch-processing-view {
    padding: 1rem;
  }

  .view-header {
    flex-direction: column;
    align-items: flex-start;
  }

  .header-actions {
    flex-wrap: wrap;
  }

  .stats-grid {
    grid-template-columns: repeat(2, 1fr);
  }

  .management-section {
    grid-template-columns: 1fr;
  }
}
</style>
