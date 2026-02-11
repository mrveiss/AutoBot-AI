<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * UpdatesView - Fleet update management (Issue #840)
 *
 * Check for updates, track update jobs, cancel running jobs.
 * Wires 3 missing endpoints: /updates/check, /updates/jobs, /updates/jobs/{id}/cancel
 */

import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useSlmApi } from '@/composables/useSlmApi'
import { useFleetStore } from '@/stores/fleet'
import { useAuthStore } from '@/stores/auth'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('UpdatesView')
const api = useSlmApi()
const fleetStore = useFleetStore()
const authStore = useAuthStore()

// Types
interface UpdateInfo {
  package_name: string
  current_version: string
  available_version: string
  severity: string
}

interface UpdateCheckResult {
  updates: UpdateInfo[]
  total: number
}

interface UpdateJob {
  job_id: string
  node_id: string
  status: string
  progress: number
  total_updates: number
  applied_count: number
  failed_count: number
  message: string
  started_at: string | null
  completed_at: string | null
  created_at: string
}

// State
const isChecking = ref(false)
const checkResult = ref<UpdateCheckResult | null>(null)
const jobs = ref<UpdateJob[]>([])
const isLoadingJobs = ref(false)
const cancellingJobId = ref<string | null>(null)
const errorMessage = ref<string | null>(null)
const successMessage = ref<string | null>(null)
let jobPollTimer: ReturnType<typeof setInterval> | null = null

// Computed
const hasRunningJobs = computed(() =>
  jobs.value.some(j => j.status === 'pending' || j.status === 'running')
)

const jobStats = computed(() => ({
  total: jobs.value.length,
  running: jobs.value.filter(j => j.status === 'running').length,
  completed: jobs.value.filter(j => j.status === 'completed').length,
  failed: jobs.value.filter(j => j.status === 'failed').length,
}))

// API helpers
async function apiFetch<T>(path: string, options?: RequestInit): Promise<T | null> {
  try {
    const response = await fetch(`${authStore.getApiUrl()}${path}`, {
      ...options,
      headers: { ...authStore.getAuthHeaders(), ...options?.headers },
    })
    if (!response.ok) throw new Error(`HTTP ${response.status}`)
    return await response.json()
  } catch (err) {
    errorMessage.value = `Request failed: ${err instanceof Error ? err.message : 'Unknown error'}`
    logger.error('API error:', err)
    return null
  }
}

// Actions
async function checkForUpdates(): Promise<void> {
  isChecking.value = true
  errorMessage.value = null
  const result = await apiFetch<UpdateCheckResult>('/api/updates/check')
  if (result) {
    checkResult.value = result
    successMessage.value = `Found ${result.total} available updates`
    setTimeout(() => { successMessage.value = null }, 3000)
  }
  isChecking.value = false
}

async function fetchJobs(): Promise<void> {
  isLoadingJobs.value = true
  const result = await apiFetch<{ jobs: UpdateJob[]; total: number }>('/api/updates/jobs')
  if (result) jobs.value = result.jobs
  isLoadingJobs.value = false
}

async function cancelJob(jobId: string): Promise<void> {
  if (!confirm('Cancel this update job?')) return
  cancellingJobId.value = jobId
  const result = await apiFetch<{ message: string }>(
    `/api/updates/jobs/${jobId}/cancel`,
    { method: 'POST' }
  )
  if (result) {
    successMessage.value = result.message
    await fetchJobs()
    setTimeout(() => { successMessage.value = null }, 3000)
  }
  cancellingJobId.value = null
}

function getStatusBadge(status: string): string {
  const map: Record<string, string> = {
    pending: 'bg-gray-100 text-gray-700',
    running: 'bg-blue-100 text-blue-700',
    completed: 'bg-green-100 text-green-700',
    failed: 'bg-red-100 text-red-700',
    cancelled: 'bg-yellow-100 text-yellow-700',
  }
  return map[status] || 'bg-gray-100 text-gray-700'
}

function formatDate(d: string | null): string {
  if (!d) return '-'
  return new Date(d).toLocaleString()
}

// Lifecycle
onMounted(async () => {
  await Promise.all([fetchJobs(), fleetStore.fetchNodes()])
  // Poll running jobs every 10s
  jobPollTimer = setInterval(() => {
    if (hasRunningJobs.value) fetchJobs()
  }, 10000)
})

onUnmounted(() => {
  if (jobPollTimer) clearInterval(jobPollTimer)
})
</script>

<template>
  <div class="p-6 max-w-7xl mx-auto">
    <!-- Header -->
    <div class="flex items-center justify-between mb-6">
      <div>
        <h1 class="text-2xl font-bold text-gray-900">Updates</h1>
        <p class="text-sm text-gray-500 mt-1">Check for updates, track jobs, manage fleet-wide updates</p>
      </div>
      <button
        @click="checkForUpdates"
        :disabled="isChecking"
        class="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
      >
        {{ isChecking ? 'Checking...' : 'Check for Updates' }}
      </button>
    </div>

    <!-- Alerts -->
    <div v-if="errorMessage" class="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm">
      {{ errorMessage }}
      <button @click="errorMessage = null" class="ml-2 underline">Dismiss</button>
    </div>
    <div v-if="successMessage" class="mb-4 p-3 bg-green-50 border border-green-200 rounded-lg text-green-700 text-sm">
      {{ successMessage }}
    </div>

    <!-- Job Stats -->
    <div class="grid grid-cols-4 gap-4 mb-6">
      <div class="bg-white rounded-lg border p-4">
        <p class="text-sm text-gray-500">Total Jobs</p>
        <p class="text-2xl font-bold">{{ jobStats.total }}</p>
      </div>
      <div class="bg-white rounded-lg border p-4">
        <p class="text-sm text-gray-500">Running</p>
        <p class="text-2xl font-bold text-blue-600">{{ jobStats.running }}</p>
      </div>
      <div class="bg-white rounded-lg border p-4">
        <p class="text-sm text-gray-500">Completed</p>
        <p class="text-2xl font-bold text-green-600">{{ jobStats.completed }}</p>
      </div>
      <div class="bg-white rounded-lg border p-4">
        <p class="text-sm text-gray-500">Failed</p>
        <p class="text-2xl font-bold text-red-600">{{ jobStats.failed }}</p>
      </div>
    </div>

    <!-- Check Results -->
    <div v-if="checkResult" class="bg-white rounded-lg border mb-6">
      <div class="px-4 py-3 bg-gray-50 border-b flex items-center justify-between">
        <h2 class="font-medium text-gray-900">Available Updates ({{ checkResult.total }})</h2>
      </div>
      <div v-if="checkResult.updates.length" class="divide-y">
        <div v-for="upd in checkResult.updates" :key="upd.package_name" class="px-4 py-3 flex items-center justify-between">
          <div>
            <p class="font-medium text-gray-900">{{ upd.package_name }}</p>
            <p class="text-xs text-gray-500">{{ upd.current_version }} → {{ upd.available_version }}</p>
          </div>
          <span :class="['px-2 py-1 text-xs rounded-full', upd.severity === 'critical' ? 'bg-red-100 text-red-700' : upd.severity === 'security' ? 'bg-orange-100 text-orange-700' : 'bg-gray-100 text-gray-700']">
            {{ upd.severity }}
          </span>
        </div>
      </div>
      <div v-else class="p-8 text-center text-gray-500">All systems up to date</div>
    </div>

    <!-- Update Jobs -->
    <div class="bg-white rounded-lg border">
      <div class="px-4 py-3 bg-gray-50 border-b flex items-center justify-between">
        <h2 class="font-medium text-gray-900">Update Jobs</h2>
        <button @click="fetchJobs" class="text-sm text-blue-600 hover:underline" :disabled="isLoadingJobs">
          {{ isLoadingJobs ? 'Loading...' : 'Refresh' }}
        </button>
      </div>
      <table class="w-full">
        <thead class="bg-gray-50">
          <tr>
            <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Job ID</th>
            <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Node</th>
            <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Status</th>
            <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Progress</th>
            <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Started</th>
            <th class="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">Actions</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-gray-200">
          <tr v-for="job in jobs" :key="job.job_id" class="hover:bg-gray-50">
            <td class="px-4 py-3 text-sm font-mono text-gray-600">{{ job.job_id.slice(0, 8) }}...</td>
            <td class="px-4 py-3 text-sm text-gray-900">{{ job.node_id }}</td>
            <td class="px-4 py-3">
              <span :class="['px-2 py-1 text-xs font-medium rounded-full', getStatusBadge(job.status)]">
                {{ job.status }}
              </span>
            </td>
            <td class="px-4 py-3">
              <div class="flex items-center gap-2">
                <div class="w-24 h-2 bg-gray-200 rounded-full overflow-hidden">
                  <div
                    class="h-full bg-blue-600 rounded-full transition-all"
                    :style="{ width: `${job.total_updates ? (job.applied_count / job.total_updates) * 100 : 0}%` }"
                  ></div>
                </div>
                <span class="text-xs text-gray-500">{{ job.applied_count }}/{{ job.total_updates }}</span>
              </div>
            </td>
            <td class="px-4 py-3 text-sm text-gray-500">{{ formatDate(job.started_at) }}</td>
            <td class="px-4 py-3 text-right">
              <button
                v-if="job.status === 'running' || job.status === 'pending'"
                @click="cancelJob(job.job_id)"
                :disabled="cancellingJobId === job.job_id"
                class="px-2 py-1 text-xs bg-red-100 text-red-700 rounded hover:bg-red-200 disabled:opacity-50"
              >
                {{ cancellingJobId === job.job_id ? 'Cancelling...' : 'Cancel' }}
              </button>
            </td>
          </tr>
        </tbody>
      </table>
      <div v-if="!jobs.length" class="p-8 text-center text-gray-500">No update jobs found</div>
    </div>
  </div>
</template>
