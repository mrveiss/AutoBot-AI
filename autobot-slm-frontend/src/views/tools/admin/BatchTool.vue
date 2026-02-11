// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

<script setup lang="ts">
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('BatchTool')
/**
 * BatchTool - Batch Processing Manager
 *
 * Manage and monitor batch job processing.
 * Migrated from main AutoBot frontend - Issue #729.
 */

import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useAutobotApi } from '@/composables/useAutobotApi'

const api = useAutobotApi()

// State
const loading = ref(false)
const error = ref<string | null>(null)

interface BatchJob {
  id: string
  name: string
  type: string
  status: 'pending' | 'running' | 'completed' | 'failed' | 'cancelled'
  progress: number
  total_items: number
  processed_items: number
  failed_items: number
  created_at: string
  started_at: string | null
  completed_at: string | null
  error: string | null
}

interface BatchStats {
  total_jobs: number
  running_jobs: number
  completed_jobs: number
  failed_jobs: number
}

const jobs = ref<BatchJob[]>([])
const stats = ref<BatchStats>({ total_jobs: 0, running_jobs: 0, completed_jobs: 0, failed_jobs: 0 })
const filterStatus = ref<string>('all')
const selectedJob = ref<BatchJob | null>(null)
const showCreateModal = ref(false)

// New job form
const newJob = ref({
  name: '',
  type: 'file_processing',
  items: [] as string[],
  options: {}
})

let refreshInterval: ReturnType<typeof setInterval> | null = null

// Computed
const filteredJobs = computed(() => {
  if (filterStatus.value === 'all') return jobs.value
  return jobs.value.filter(j => j.status === filterStatus.value)
})

// Methods
function getStatusClass(status: string): string {
  switch (status) {
    case 'pending': return 'bg-yellow-100 text-yellow-800'
    case 'running': return 'bg-blue-100 text-blue-800'
    case 'completed': return 'bg-green-100 text-green-800'
    case 'failed': return 'bg-red-100 text-red-800'
    case 'cancelled': return 'bg-gray-100 text-gray-800'
    default: return 'bg-gray-100 text-gray-800'
  }
}

function getProgressColor(status: string): string {
  switch (status) {
    case 'running': return 'bg-blue-500'
    case 'completed': return 'bg-green-500'
    case 'failed': return 'bg-red-500'
    default: return 'bg-gray-400'
  }
}

function formatDate(dateStr: string | null): string {
  if (!dateStr) return '-'
  return new Date(dateStr).toLocaleString()
}

function formatDuration(start: string | null, end: string | null): string {
  if (!start) return '-'
  const startDate = new Date(start)
  const endDate = end ? new Date(end) : new Date()
  const diff = Math.floor((endDate.getTime() - startDate.getTime()) / 1000)

  if (diff < 60) return `${diff}s`
  if (diff < 3600) return `${Math.floor(diff / 60)}m ${diff % 60}s`
  return `${Math.floor(diff / 3600)}h ${Math.floor((diff % 3600) / 60)}m`
}

async function loadJobs(): Promise<void> {
  loading.value = true
  error.value = null

  try {
    // Issue #835 - use named function from useAutobotApi
    const data = await api.listBatchJobs()
    jobs.value = (data.jobs as BatchJob[]) || []
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Failed to load jobs'
  } finally {
    loading.value = false
  }
}

async function loadStats(): Promise<void> {
  try {
    // Issue #835 - use named function from useAutobotApi
    const data = await api.getBatchJobHealth()
    stats.value = (data as unknown as BatchStats) || { total_jobs: 0, running_jobs: 0, completed_jobs: 0, failed_jobs: 0 }
  } catch (e) {
    logger.error('Failed to load stats:', e)
  }
}

async function refreshData(): Promise<void> {
  await Promise.all([loadJobs(), loadStats()])
}

async function createJob(): Promise<void> {
  if (!newJob.value.name) {
    error.value = 'Please enter a job name'
    return
  }

  loading.value = true
  try {
    // Issue #835 - use named function from useAutobotApi
    await api.createBatchJob(newJob.value)
    showCreateModal.value = false
    newJob.value = { name: '', type: 'file_processing', items: [], options: {} }
    await loadJobs()
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Failed to create job'
  } finally {
    loading.value = false
  }
}

async function cancelJob(jobId: string): Promise<void> {
  try {
    // Issue #835 - use named function from useAutobotApi
    await api.cancelBatchJob(jobId)
    await loadJobs()
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Failed to cancel job'
  }
}

async function retryJob(jobId: string): Promise<void> {
  try {
    // Issue #835 - no retry endpoint in backend, re-create the job
    const job = jobs.value.find(j => j.id === jobId)
    if (job) {
      await api.createBatchJob({ name: job.name, type: job.type })
    }
    await loadJobs()
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Failed to retry job'
  }
}

async function deleteJob(jobId: string): Promise<void> {
  if (!confirm('Are you sure you want to delete this job?')) return

  try {
    // Issue #835 - use cancelBatchJob (DELETE endpoint)
    await api.cancelBatchJob(jobId)
    if (selectedJob.value?.id === jobId) {
      selectedJob.value = null
    }
    await loadJobs()
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Failed to delete job'
  }
}

onMounted(() => {
  refreshData()
  refreshInterval = setInterval(() => refreshData(), 10000)
})

onUnmounted(() => {
  if (refreshInterval) {
    clearInterval(refreshInterval)
  }
})
</script>

<template>
  <div class="p-6">
    <!-- Stats Cards -->
    <div class="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
      <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
        <div class="flex items-center justify-between">
          <div>
            <p class="text-sm text-gray-500">Total Jobs</p>
            <p class="text-2xl font-bold text-gray-900">{{ stats.total_jobs }}</p>
          </div>
          <div class="p-3 bg-gray-100 rounded-lg">
            <svg class="w-6 h-6 text-gray-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
            </svg>
          </div>
        </div>
      </div>

      <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
        <div class="flex items-center justify-between">
          <div>
            <p class="text-sm text-gray-500">Running</p>
            <p class="text-2xl font-bold text-blue-600">{{ stats.running_jobs }}</p>
          </div>
          <div class="p-3 bg-blue-100 rounded-lg">
            <svg class="w-6 h-6 text-blue-600 animate-spin" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
            </svg>
          </div>
        </div>
      </div>

      <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
        <div class="flex items-center justify-between">
          <div>
            <p class="text-sm text-gray-500">Completed</p>
            <p class="text-2xl font-bold text-green-600">{{ stats.completed_jobs }}</p>
          </div>
          <div class="p-3 bg-green-100 rounded-lg">
            <svg class="w-6 h-6 text-green-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          </div>
        </div>
      </div>

      <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
        <div class="flex items-center justify-between">
          <div>
            <p class="text-sm text-gray-500">Failed</p>
            <p class="text-2xl font-bold text-red-600">{{ stats.failed_jobs }}</p>
          </div>
          <div class="p-3 bg-red-100 rounded-lg">
            <svg class="w-6 h-6 text-red-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          </div>
        </div>
      </div>
    </div>

    <!-- Toolbar -->
    <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-4 mb-6">
      <div class="flex items-center justify-between">
        <div class="flex items-center gap-4">
          <select
            v-model="filterStatus"
            class="px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500"
          >
            <option value="all">All Status</option>
            <option value="pending">Pending</option>
            <option value="running">Running</option>
            <option value="completed">Completed</option>
            <option value="failed">Failed</option>
            <option value="cancelled">Cancelled</option>
          </select>

          <button
            @click="refreshData"
            :disabled="loading"
            class="px-4 py-2 text-gray-600 hover:text-gray-800 hover:bg-gray-100 rounded-lg transition-colors flex items-center gap-2"
          >
            <svg class="w-4 h-4" :class="{ 'animate-spin': loading }" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
            </svg>
            Refresh
          </button>
        </div>

        <button
          @click="showCreateModal = true"
          class="px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition-colors flex items-center gap-2"
        >
          <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4" />
          </svg>
          Create Job
        </button>
      </div>
    </div>

    <!-- Error Message -->
    <div v-if="error" class="mb-6 p-4 bg-red-50 border border-red-200 rounded-lg text-red-700">
      {{ error }}
    </div>

    <!-- Jobs List -->
    <div v-if="loading && !jobs.length" class="text-center py-12">
      <svg class="animate-spin w-8 h-8 mx-auto text-primary-500" fill="none" viewBox="0 0 24 24">
        <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
        <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
      </svg>
      <p class="mt-4 text-gray-600">Loading jobs...</p>
    </div>

    <div v-else-if="filteredJobs.length === 0" class="text-center py-12 bg-white rounded-lg shadow-sm border border-gray-200">
      <svg class="w-12 h-12 mx-auto text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
      </svg>
      <p class="mt-4 text-gray-600">No batch jobs found</p>
    </div>

    <div v-else class="space-y-4">
      <div
        v-for="job in filteredJobs"
        :key="job.id"
        class="bg-white rounded-lg shadow-sm border border-gray-200 p-6"
      >
        <!-- Job Header -->
        <div class="flex items-start justify-between mb-4">
          <div>
            <div class="flex items-center gap-3">
              <h3 class="text-lg font-semibold text-gray-900">{{ job.name }}</h3>
              <span :class="['px-2 py-1 text-xs font-medium rounded-full', getStatusClass(job.status)]">
                {{ job.status }}
              </span>
            </div>
            <p class="text-sm text-gray-500 mt-1">{{ job.type }} - ID: {{ job.id.slice(0, 8) }}</p>
          </div>
          <div class="flex items-center gap-2">
            <button
              v-if="job.status === 'running'"
              @click="cancelJob(job.id)"
              class="px-3 py-1.5 text-xs bg-red-100 text-red-700 rounded-lg hover:bg-red-200"
            >
              Cancel
            </button>
            <button
              v-if="job.status === 'failed'"
              @click="retryJob(job.id)"
              class="px-3 py-1.5 text-xs bg-amber-100 text-amber-700 rounded-lg hover:bg-amber-200"
            >
              Retry
            </button>
            <button
              v-if="job.status !== 'running'"
              @click="deleteJob(job.id)"
              class="px-3 py-1.5 text-xs text-gray-600 hover:text-red-600 hover:bg-red-50 rounded-lg"
            >
              Delete
            </button>
          </div>
        </div>

        <!-- Progress Bar -->
        <div class="mb-4">
          <div class="flex items-center justify-between text-sm text-gray-600 mb-1">
            <span>Progress</span>
            <span>{{ job.processed_items }} / {{ job.total_items }} items ({{ job.progress.toFixed(0) }}%)</span>
          </div>
          <div class="w-full bg-gray-200 rounded-full h-2">
            <div
              :class="['h-2 rounded-full transition-all', getProgressColor(job.status)]"
              :style="{ width: `${job.progress}%` }"
            ></div>
          </div>
        </div>

        <!-- Job Details -->
        <div class="grid grid-cols-4 gap-4 text-sm">
          <div>
            <p class="text-gray-500">Created</p>
            <p class="text-gray-900">{{ formatDate(job.created_at) }}</p>
          </div>
          <div>
            <p class="text-gray-500">Started</p>
            <p class="text-gray-900">{{ formatDate(job.started_at) }}</p>
          </div>
          <div>
            <p class="text-gray-500">Duration</p>
            <p class="text-gray-900">{{ formatDuration(job.started_at, job.completed_at) }}</p>
          </div>
          <div>
            <p class="text-gray-500">Failed Items</p>
            <p :class="job.failed_items > 0 ? 'text-red-600' : 'text-gray-900'">{{ job.failed_items }}</p>
          </div>
        </div>

        <!-- Error Message -->
        <div v-if="job.error" class="mt-4 p-3 bg-red-50 border border-red-200 rounded-lg">
          <p class="text-sm text-red-700">{{ job.error }}</p>
        </div>
      </div>
    </div>

    <!-- Create Job Modal -->
    <div v-if="showCreateModal" class="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div class="bg-white rounded-lg shadow-xl max-w-lg w-full mx-4 p-6">
        <div class="flex items-center justify-between mb-6">
          <h3 class="text-lg font-semibold text-gray-900">Create Batch Job</h3>
          <button @click="showCreateModal = false" class="text-gray-400 hover:text-gray-600">
            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div class="space-y-4">
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">Job Name</label>
            <input
              v-model="newJob.name"
              type="text"
              class="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
              placeholder="Enter job name"
            />
          </div>

          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">Job Type</label>
            <select
              v-model="newJob.type"
              class="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500"
            >
              <option value="file_processing">File Processing</option>
              <option value="data_export">Data Export</option>
              <option value="report_generation">Report Generation</option>
              <option value="cleanup">Cleanup</option>
            </select>
          </div>
        </div>

        <div class="flex justify-end gap-3 mt-6">
          <button
            @click="showCreateModal = false"
            class="px-4 py-2 text-gray-700 hover:text-gray-900"
          >
            Cancel
          </button>
          <button
            @click="createJob"
            :disabled="loading || !newJob.name"
            class="px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition-colors disabled:opacity-50"
          >
            {{ loading ? 'Creating...' : 'Create Job' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
