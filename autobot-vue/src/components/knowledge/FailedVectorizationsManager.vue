<template>
  <div class="failed-vectorizations-manager">
    <div class="manager-header">
      <h3>
        <i class="fas fa-exclamation-triangle"></i>
        Failed Vectorizations
      </h3>
      <div class="header-actions">
        <BaseButton
          variant="primary"
          size="sm"
          @click="refreshFailedJobs"
          :disabled="loading"
          :loading="loading"
          class="btn-refresh"
        >
          <i v-if="!loading" class="fas fa-sync-alt"></i>
          Refresh
        </BaseButton>
        <BaseButton
          v-if="failedJobs.length > 0"
          variant="danger"
          size="sm"
          @click="clearAllFailed"
          :disabled="loading"
          class="btn-clear-all"
        >
          <i class="fas fa-trash-alt"></i>
          Clear All
        </BaseButton>
      </div>
    </div>

    <!-- Loading State -->
    <div v-if="loading && failedJobs.length === 0" class="loading-state">
      <i class="fas fa-spinner fa-spin"></i>
      Loading failed jobs...
    </div>

    <!-- Error State -->
    <div v-else-if="error" class="error-state">
      <i class="fas fa-exclamation-circle"></i>
      {{ error }}
    </div>

    <!-- Empty State -->
    <EmptyState
      v-else-if="failedJobs.length === 0"
      icon="fas fa-check-circle"
      message="No failed vectorizations!"
      variant="success"
    />

    <!-- Failed Jobs List -->
    <div v-else class="failed-jobs-list">
      <div v-for="job in failedJobs" :key="job.job_id" class="failed-job-card">
        <div class="job-header">
          <div class="job-id">
            <i class="fas fa-file-alt"></i>
            <span class="fact-id">{{ job.fact_id.substring(0, 8) }}...</span>
          </div>
          <div class="job-time">
            {{ formatTime(job.started_at) }}
          </div>
        </div>

        <div class="job-error">
          <i class="fas fa-times-circle"></i>
          {{ job.error || 'Unknown error' }}
        </div>

        <div class="job-actions">
          <BaseButton
            variant="success"
            size="sm"
            @click="retryJob(job.job_id)"
            :disabled="loading || retryingJobs.has(job.job_id)"
            :loading="retryingJobs.has(job.job_id)"
            class="btn-retry"
          >
            <i v-if="!retryingJobs.has(job.job_id)" class="fas fa-redo"></i>
            {{ retryingJobs.has(job.job_id) ? 'Retrying...' : 'Retry' }}
          </BaseButton>
          <BaseButton
            variant="secondary"
            size="sm"
            @click="deleteJob(job.job_id)"
            :disabled="loading"
            class="btn-delete"
          >
            <i class="fas fa-trash"></i>
            Delete
          </BaseButton>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import apiClient from '@/utils/ApiClient'
import { parseApiResponse } from '@/utils/apiResponseHelpers'
import { formatDateTime } from '@/utils/formatHelpers'
import { useAsyncOperation } from '@/composables/useAsyncOperation'
import EmptyState from '@/components/ui/EmptyState.vue'
import BaseButton from '@/components/base/BaseButton.vue'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('FailedVectorizationsManager')

interface FailedJob {
  job_id: string
  fact_id: string
  status: string
  started_at: string
  completed_at: string | null
  error: string | null
}

// State
const failedJobs = ref<FailedJob[]>([])
const retryingJobs = ref<Set<string>>(new Set())

// Use composable for async operations
const { execute: fetchFailedJobs, loading, error } = useAsyncOperation()

// Fetch failed jobs
const fetchFailedJobsFn = async () => {
  const response = await apiClient.get('/api/knowledge_base/vectorize_jobs/failed')
  const data = await parseApiResponse(response)

  if (data.status === 'success') {
    failedJobs.value = data.failed_jobs
  } else {
    throw new Error('Failed to load failed jobs')
  }
}

// Refresh failed jobs
const refreshFailedJobs = async () => {
  await fetchFailedJobs(fetchFailedJobsFn)
}

// Retry a single job
const retryJob = async (jobId: string) => {
  retryingJobs.value.add(jobId)

  try {
    const response = await apiClient.post(`/api/knowledge_base/vectorize_jobs/${jobId}/retry`)
    const data = await parseApiResponse(response)

    if (data.status === 'success') {
      // Remove from failed list
      failedJobs.value = failedJobs.value.filter(job => job.job_id !== jobId)

      logger.debug(`Job ${jobId} retry started as ${data.new_job_id}`)
    } else {
      error.value = new Error(`Failed to retry job: ${data.message || 'Unknown error'}`)
    }
  } catch (err) {
    logger.error('Error retrying job:', err)
    error.value = new Error(`Error retrying job: ${err}`)
  } finally {
    retryingJobs.value.delete(jobId)
  }
}

// Delete a single job
const deleteJob = async (jobId: string) => {
  if (!confirm('Are you sure you want to delete this failed job record?')) {
    return
  }

  await fetchFailedJobs(async () => {
    const response = await apiClient.delete(`/api/knowledge_base/vectorize_jobs/${jobId}`)
    const data = await parseApiResponse(response)

    if (data.status === 'success') {
      // Remove from list
      failedJobs.value = failedJobs.value.filter(job => job.job_id !== jobId)
    } else {
      throw new Error(data.message || 'Failed to delete job')
    }
  })
}

// Clear all failed jobs
const clearAllFailed = async () => {
  if (!confirm(`Are you sure you want to clear all ${failedJobs.value.length} failed jobs?`)) {
    return
  }

  await fetchFailedJobs(async () => {
    const response = await apiClient.delete('/api/knowledge_base/vectorize_jobs/failed/clear')
    const data = await parseApiResponse(response)

    if (data.status === 'success') {
      failedJobs.value = []
      logger.debug(`Cleared ${data.deleted_count} failed jobs`)
    } else {
      throw new Error(data.message || 'Failed to clear jobs')
    }
  })
}

// Use shared datetime formatting utility
const formatTime = formatDateTime

// Load on mount
onMounted(() => {
  fetchFailedJobs(fetchFailedJobsFn)
})
</script>

<style scoped>
/* Issue #704: Migrated to CSS design tokens */
.failed-vectorizations-manager {
  background: var(--bg-primary);
  border-radius: var(--radius-lg);
  padding: var(--spacing-6);
  box-shadow: var(--shadow-sm);
}

.manager-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--spacing-6);
  padding-bottom: var(--spacing-4);
  border-bottom: 2px solid var(--border-default);
}

.manager-header h3 {
  margin: 0;
  font-size: var(--text-xl);
  color: var(--color-error);
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
}

.header-actions {
  display: flex;
  gap: var(--spacing-3);
}

/* Button spacing handled by BaseButton */

.loading-state,
.error-state {
  text-align: center;
  padding: var(--spacing-8) var(--spacing-4);
  color: var(--text-secondary);
}

.loading-state i,
.error-state i {
  font-size: var(--text-4xl);
  margin-bottom: var(--spacing-4);
  display: block;
}

.error-state {
  color: var(--color-error);
}

.failed-jobs-list {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-4);
}

.failed-job-card {
  background: var(--color-error-bg);
  border: 1px solid var(--color-error-border);
  border-radius: var(--radius-lg);
  padding: var(--spacing-4);
  transition: all var(--duration-200);
}

.failed-job-card:hover {
  box-shadow: var(--shadow-md);
}

.job-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--spacing-3);
}

.job-id {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  font-weight: var(--font-medium);
  color: var(--text-primary);
}

.fact-id {
  font-family: var(--font-mono);
  font-size: var(--text-sm);
  background: var(--bg-primary);
  padding: var(--spacing-1) var(--spacing-2);
  border-radius: var(--radius-sm);
}

.job-time {
  font-size: var(--text-xs);
  color: var(--text-secondary);
}

.job-error {
  display: flex;
  align-items: flex-start;
  gap: var(--spacing-2);
  padding: var(--spacing-3);
  background: var(--bg-primary);
  border-radius: var(--radius-md);
  margin-bottom: var(--spacing-4);
  font-size: var(--text-sm);
  color: var(--color-error);
}

.job-error i {
  flex-shrink: 0;
  margin-top: var(--spacing-px);
}

.job-actions {
  display: flex;
  gap: var(--spacing-2);
}

/* Button styling handled by BaseButton component */
</style>
