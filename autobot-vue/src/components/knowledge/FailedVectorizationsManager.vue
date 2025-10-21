<template>
  <div class="failed-vectorizations-manager">
    <div class="manager-header">
      <h3>
        <i class="fas fa-exclamation-triangle"></i>
        Failed Vectorizations
      </h3>
      <div class="header-actions">
        <button class="btn-refresh" @click="refreshFailedJobs" :disabled="loading">
          <i class="fas fa-sync-alt" :class="{ 'fa-spin': loading }"></i>
          Refresh
        </button>
        <button
          v-if="failedJobs.length > 0"
          class="btn-clear-all"
          @click="clearAllFailed"
          :disabled="loading"
        >
          <i class="fas fa-trash-alt"></i>
          Clear All
        </button>
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
    <div v-else-if="failedJobs.length === 0" class="empty-state">
      <i class="fas fa-check-circle"></i>
      <p>No failed vectorizations!</p>
    </div>

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
          <button
            class="btn-retry"
            @click="retryJob(job.job_id)"
            :disabled="loading || retryingJobs.has(job.job_id)"
          >
            <i
              class="fas"
              :class="retryingJobs.has(job.job_id) ? 'fa-spinner fa-spin' : 'fa-redo'"
            ></i>
            {{ retryingJobs.has(job.job_id) ? 'Retrying...' : 'Retry' }}
          </button>
          <button
            class="btn-delete"
            @click="deleteJob(job.job_id)"
            :disabled="loading"
          >
            <i class="fas fa-trash"></i>
            Delete
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import apiClient from '@/utils/ApiClient'

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
const loading = ref(false)
const error = ref<string | null>(null)
const retryingJobs = ref<Set<string>>(new Set())

// Fetch failed jobs
const fetchFailedJobs = async () => {
  loading.value = true
  error.value = null

  try {
    const response = await apiClient.get('/api/knowledge_base/vectorize_jobs/failed')
    const data = await response.json()

    if (data.status === 'success') {
      failedJobs.value = data.failed_jobs
    } else {
      error.value = 'Failed to load failed jobs'
    }
  } catch (err) {
    console.error('Error fetching failed jobs:', err)
    error.value = `Error loading failed jobs: ${err}`
  } finally {
    loading.value = false
  }
}

// Refresh failed jobs
const refreshFailedJobs = async () => {
  await fetchFailedJobs()
}

// Retry a single job
const retryJob = async (jobId: string) => {
  retryingJobs.value.add(jobId)

  try {
    const response = await apiClient.post(`/api/knowledge_base/vectorize_jobs/${jobId}/retry`)
    const data = await response.json()

    if (data.status === 'success') {
      // Remove from failed list
      failedJobs.value = failedJobs.value.filter(job => job.job_id !== jobId)

      console.log(`Job ${jobId} retry started as ${data.new_job_id}`)
    } else {
      error.value = `Failed to retry job: ${data.message || 'Unknown error'}`
    }
  } catch (err) {
    console.error('Error retrying job:', err)
    error.value = `Error retrying job: ${err}`
  } finally {
    retryingJobs.value.delete(jobId)
  }
}

// Delete a single job
const deleteJob = async (jobId: string) => {
  if (!confirm('Are you sure you want to delete this failed job record?')) {
    return
  }

  loading.value = true

  try {
    const response = await apiClient.delete(`/api/knowledge_base/vectorize_jobs/${jobId}`)
    const data = await response.json()

    if (data.status === 'success') {
      // Remove from list
      failedJobs.value = failedJobs.value.filter(job => job.job_id !== jobId)
    } else {
      error.value = `Failed to delete job: ${data.message || 'Unknown error'}`
    }
  } catch (err) {
    console.error('Error deleting job:', err)
    error.value = `Error deleting job: ${err}`
  } finally {
    loading.value = false
  }
}

// Clear all failed jobs
const clearAllFailed = async () => {
  if (!confirm(`Are you sure you want to clear all ${failedJobs.value.length} failed jobs?`)) {
    return
  }

  loading.value = true

  try {
    const response = await apiClient.delete('/api/knowledge_base/vectorize_jobs/failed/clear')
    const data = await response.json()

    if (data.status === 'success') {
      failedJobs.value = []
      console.log(`Cleared ${data.deleted_count} failed jobs`)
    } else {
      error.value = `Failed to clear jobs: ${data.message || 'Unknown error'}`
    }
  } catch (err) {
    console.error('Error clearing failed jobs:', err)
    error.value = `Error clearing failed jobs: ${err}`
  } finally {
    loading.value = false
  }
}

// Format timestamp
const formatTime = (isoString: string): string => {
  try {
    const date = new Date(isoString)
    return date.toLocaleString()
  } catch {
    return isoString
  }
}

// Load on mount
onMounted(() => {
  fetchFailedJobs()
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

.btn-refresh,
.btn-clear-all,
.btn-retry,
.btn-delete {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem 1rem;
  border: none;
  border-radius: 0.375rem;
  font-size: 0.875rem;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
}

.btn-refresh {
  background: #3b82f6;
  color: white;
}

.btn-refresh:hover:not(:disabled) {
  background: #2563eb;
}

.btn-clear-all {
  background: #dc2626;
  color: white;
}

.btn-clear-all:hover:not(:disabled) {
  background: #b91c1c;
}

.btn-refresh:disabled,
.btn-clear-all:disabled,
.btn-retry:disabled,
.btn-delete:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.loading-state,
.error-state,
.empty-state {
  text-align: center;
  padding: 3rem 1rem;
  color: #6b7280;
}

.loading-state i,
.error-state i,
.empty-state i {
  font-size: 3rem;
  margin-bottom: 1rem;
  display: block;
}

.error-state {
  color: #dc2626;
}

.empty-state {
  color: #10b981;
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

.btn-retry {
  flex: 1;
  background: #10b981;
  color: white;
}

.btn-retry:hover:not(:disabled) {
  background: #059669;
}

.btn-delete {
  background: #6b7280;
  color: white;
}

.btn-delete:hover:not(:disabled) {
  background: #4b5563;
}
</style>
