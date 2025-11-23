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

      console.log(`Job ${jobId} retry started as ${data.new_job_id}`)
    } else {
      error.value = new Error(`Failed to retry job: ${data.message || 'Unknown error'}`)
    }
  } catch (err) {
    console.error('Error retrying job:', err)
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
      console.log(`Cleared ${data.deleted_count} failed jobs`)
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
.failed-vectorizations-manager {
  background: white;
  border-radius: 0.5rem;
  padding: 1.5rem;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
}

.manager-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1.5rem;
  padding-bottom: 1rem;
  border-bottom: 2px solid #f3f4f6;
}

.manager-header h3 {
  margin: 0;
  font-size: 1.25rem;
  color: #dc2626;
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.header-actions {
  display: flex;
  gap: 0.75rem;
}

/* Button spacing handled by BaseButton */

.loading-state,
.error-state {
  text-align: center;
  padding: 3rem 1rem;
  color: #6b7280;
}

.loading-state i,
.error-state i {
  font-size: 3rem;
  margin-bottom: 1rem;
  display: block;
}

.error-state {
  color: #dc2626;
}

.failed-jobs-list {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.failed-job-card {
  background: #fef2f2;
  border: 1px solid #fecaca;
  border-radius: 0.5rem;
  padding: 1rem;
  transition: all 0.2s;
}

.failed-job-card:hover {
  box-shadow: 0 4px 6px rgba(220, 38, 38, 0.1);
}

.job-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 0.75rem;
}

.job-id {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-weight: 500;
  color: #374151;
}

.fact-id {
  font-family: monospace;
  font-size: 0.875rem;
  background: white;
  padding: 0.25rem 0.5rem;
  border-radius: 0.25rem;
}

.job-time {
  font-size: 0.75rem;
  color: #6b7280;
}

.job-error {
  display: flex;
  align-items: flex-start;
  gap: 0.5rem;
  padding: 0.75rem;
  background: white;
  border-radius: 0.375rem;
  margin-bottom: 1rem;
  font-size: 0.875rem;
  color: #dc2626;
}

.job-error i {
  flex-shrink: 0;
  margin-top: 0.125rem;
}

.job-actions {
  display: flex;
  gap: 0.5rem;
}

/* Button styling handled by BaseButton component */
</style>
