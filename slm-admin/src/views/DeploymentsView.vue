<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

import { ref, onMounted } from 'vue'
import { useSlmApi } from '@/composables/useSlmApi'
import { createLogger } from '@/utils/debugUtils'
import type { Deployment } from '@/types/slm'

const logger = createLogger('DeploymentsView')
const api = useSlmApi()

const deployments = ref<Deployment[]>([])
const isLoading = ref(false)
const showWizard = ref(false)
const isRetrying = ref<string | null>(null)
const isCancelling = ref<string | null>(null)

onMounted(async () => {
  await fetchDeployments()
})

async function fetchDeployments(): Promise<void> {
  isLoading.value = true
  try {
    deployments.value = await api.getDeployments()
  } finally {
    isLoading.value = false
  }
}

async function handleRetry(deploymentId: string): Promise<void> {
  isRetrying.value = deploymentId
  try {
    await api.retryDeployment(deploymentId)
    await fetchDeployments()
  } catch (err) {
    logger.error('Failed to retry deployment:', err)
  } finally {
    isRetrying.value = null
  }
}

async function handleCancel(deploymentId: string): Promise<void> {
  isCancelling.value = deploymentId
  try {
    await api.cancelDeployment(deploymentId)
    await fetchDeployments()
  } catch (err) {
    logger.error('Failed to cancel deployment:', err)
  } finally {
    isCancelling.value = null
  }
}

function getStatusClass(status: string): string {
  switch (status) {
    case 'completed': return 'bg-green-100 text-green-800'
    case 'in_progress': return 'bg-blue-100 text-blue-800'
    case 'pending': return 'bg-yellow-100 text-yellow-800'
    case 'failed': return 'bg-red-100 text-red-800'
    case 'rolled_back': return 'bg-orange-100 text-orange-800'
    default: return 'bg-gray-100 text-gray-800'
  }
}
</script>

<template>
  <div class="p-6">
    <!-- Header -->
    <div class="flex items-center justify-between mb-6">
      <div>
        <h1 class="text-2xl font-bold text-gray-900">Deployments</h1>
        <p class="text-sm text-gray-500 mt-1">
          Deploy and manage roles across your fleet
        </p>
      </div>
      <button
        @click="showWizard = true"
        class="btn btn-primary flex items-center gap-2"
      >
        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4" />
        </svg>
        New Deployment
      </button>
    </div>

    <!-- Deployments Table -->
    <div class="card overflow-hidden">
      <table class="min-w-full divide-y divide-gray-200">
        <thead class="bg-gray-50">
          <tr>
            <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Node</th>
            <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Roles</th>
            <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Status</th>
            <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Started</th>
            <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Actions</th>
          </tr>
        </thead>
        <tbody class="bg-white divide-y divide-gray-200">
          <tr v-for="deployment in deployments" :key="deployment.deployment_id">
            <td class="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">
              {{ deployment.node_id }}
            </td>
            <td class="px-6 py-4 whitespace-nowrap">
              <div class="flex flex-wrap gap-1">
                <span
                  v-for="role in deployment.roles"
                  :key="role"
                  class="px-2 py-0.5 text-xs font-medium bg-primary-100 text-primary-700 rounded"
                >
                  {{ role }}
                </span>
              </div>
            </td>
            <td class="px-6 py-4 whitespace-nowrap">
              <span :class="['px-2 py-1 text-xs font-medium rounded-full', getStatusClass(deployment.status)]">
                {{ deployment.status }}
              </span>
            </td>
            <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
              {{ new Date(deployment.started_at).toLocaleString() }}
            </td>
            <td class="px-6 py-4 whitespace-nowrap text-sm">
              <button
                v-if="deployment.status === 'in_progress'"
                @click="handleCancel(deployment.deployment_id)"
                :disabled="isCancelling === deployment.deployment_id"
                class="text-red-600 hover:text-red-800 disabled:opacity-50"
              >
                {{ isCancelling === deployment.deployment_id ? 'Cancelling...' : 'Cancel' }}
              </button>
              <button
                v-else-if="deployment.status === 'failed'"
                @click="handleRetry(deployment.deployment_id)"
                :disabled="isRetrying === deployment.deployment_id"
                class="text-blue-600 hover:text-blue-800 disabled:opacity-50"
              >
                {{ isRetrying === deployment.deployment_id ? 'Retrying...' : 'Retry' }}
              </button>
            </td>
          </tr>
          <tr v-if="deployments.length === 0 && !isLoading">
            <td colspan="5" class="px-6 py-12 text-center text-gray-500">
              No deployments yet. Click "New Deployment" to get started.
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Loading -->
    <div v-if="isLoading" class="flex items-center justify-center py-12">
      <div class="animate-spin w-8 h-8 border-4 border-primary-600 border-t-transparent rounded-full"></div>
    </div>
  </div>
</template>
