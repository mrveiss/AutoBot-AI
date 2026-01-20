<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useSlmApi } from '@/composables/useSlmApi'
import { useSlmWebSocket } from '@/composables/useSlmWebSocket'
import { createLogger } from '@/utils/debugUtils'
import type { Deployment } from '@/types/slm'

const logger = createLogger('DeploymentsView')
const api = useSlmApi()
const ws = useSlmWebSocket()

const deployments = ref<Deployment[]>([])
const isLoading = ref(false)
const showWizard = ref(false)
const isRetrying = ref<string | null>(null)
const isCancelling = ref<string | null>(null)
const isRollingBack = ref<string | null>(null)
const selectedDeployment = ref<Deployment | null>(null)
const showDetailsModal = ref(false)

// Rollback notification
const rollbackNotification = ref<{
  show: boolean
  nodeId: string
  deploymentId: string
  success: boolean
  message: string
}>({
  show: false,
  nodeId: '',
  deploymentId: '',
  success: false,
  message: '',
})

// Summary stats
const stats = computed(() => ({
  total: deployments.value.length,
  completed: deployments.value.filter(d => d.status === 'completed').length,
  inProgress: deployments.value.filter(d => d.status === 'in_progress').length,
  failed: deployments.value.filter(d => d.status === 'failed').length,
  rolledBack: deployments.value.filter(d => d.status === 'rolled_back').length,
}))

onMounted(async () => {
  await fetchDeployments()

  // Connect to WebSocket for real-time updates
  ws.connect()
  ws.subscribeAll()

  // Listen for deployment status updates
  ws.onDeploymentStatus((nodeId, data) => {
    logger.info('Deployment status update:', nodeId, data)
    fetchDeployments()
  })

  // Listen for rollback events
  ws.onRollbackEvent((nodeId, data) => {
    logger.info('Rollback event:', nodeId, data)
    rollbackNotification.value = {
      show: true,
      nodeId,
      deploymentId: data.deployment_id,
      success: data.success ?? false,
      message: data.message ?? 'Rollback completed',
    }

    // Auto-hide after 5 seconds
    setTimeout(() => {
      rollbackNotification.value.show = false
    }, 5000)

    fetchDeployments()
  })
})

onUnmounted(() => {
  ws.disconnect()
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
    alert('Failed to retry deployment')
  } finally {
    isRetrying.value = null
  }
}

async function handleCancel(deploymentId: string): Promise<void> {
  if (!confirm('Are you sure you want to cancel this deployment?')) {
    return
  }

  isCancelling.value = deploymentId
  try {
    await api.cancelDeployment(deploymentId)
    await fetchDeployments()
  } catch (err) {
    logger.error('Failed to cancel deployment:', err)
    alert('Failed to cancel deployment')
  } finally {
    isCancelling.value = null
  }
}

async function handleRollback(deploymentId: string): Promise<void> {
  if (!confirm('Are you sure you want to rollback this deployment? This will revert the node to its previous state.')) {
    return
  }

  isRollingBack.value = deploymentId
  try {
    await api.rollbackDeployment(deploymentId)
    logger.info('Rollback initiated:', deploymentId)
    await fetchDeployments()
  } catch (err) {
    logger.error('Failed to rollback deployment:', err)
    alert('Failed to rollback deployment')
  } finally {
    isRollingBack.value = null
  }
}

function showDetails(deployment: Deployment): void {
  selectedDeployment.value = deployment
  showDetailsModal.value = true
}

function closeDetails(): void {
  showDetailsModal.value = false
  selectedDeployment.value = null
}

function getStatusClass(status: string): string {
  switch (status) {
    case 'completed': return 'bg-green-100 text-green-800'
    case 'in_progress': return 'bg-blue-100 text-blue-800'
    case 'pending': return 'bg-yellow-100 text-yellow-800'
    case 'failed': return 'bg-red-100 text-red-800'
    case 'rolled_back': return 'bg-orange-100 text-orange-800'
    case 'cancelled': return 'bg-gray-100 text-gray-800'
    default: return 'bg-gray-100 text-gray-800'
  }
}

function getStatusIcon(status: string): string {
  switch (status) {
    case 'completed': return 'M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z'
    case 'in_progress': return 'M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z'
    case 'pending': return 'M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z'
    case 'failed': return 'M10 14l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2m7-2a9 9 0 11-18 0 9 9 0 0118 0z'
    case 'rolled_back': return 'M3 10h10a8 8 0 018 8v2M3 10l6 6m-6-6l6-6'
    default: return 'M8.228 9c.549-1.165 2.03-2 3.772-2 2.21 0 4 1.343 4 3 0 1.4-1.278 2.575-3.006 2.907-.542.104-.994.54-.994 1.093m0 3h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z'
  }
}

function formatDateTime(isoString: string | null): string {
  if (!isoString) return '-'
  return new Date(isoString).toLocaleString()
}
</script>

<template>
  <div class="p-6">
    <!-- Rollback Notification Toast -->
    <Transition
      enter-active-class="transition duration-300 ease-out"
      enter-from-class="opacity-0 translate-y-2"
      enter-to-class="opacity-100 translate-y-0"
      leave-active-class="transition duration-200 ease-in"
      leave-from-class="opacity-100 translate-y-0"
      leave-to-class="opacity-0 translate-y-2"
    >
      <div
        v-if="rollbackNotification.show"
        class="fixed top-4 right-4 z-50 max-w-md"
      >
        <div
          :class="[
            'rounded-lg shadow-lg p-4 flex items-start gap-3',
            rollbackNotification.success ? 'bg-green-50 border border-green-200' : 'bg-red-50 border border-red-200'
          ]"
        >
          <div :class="['flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center',
            rollbackNotification.success ? 'bg-green-100' : 'bg-red-100'
          ]">
            <svg
              class="w-5 h-5"
              :class="rollbackNotification.success ? 'text-green-600' : 'text-red-600'"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                stroke-linecap="round"
                stroke-linejoin="round"
                stroke-width="2"
                d="M3 10h10a8 8 0 018 8v2M3 10l6 6m-6-6l6-6"
              />
            </svg>
          </div>
          <div class="flex-1">
            <h4 :class="['font-medium', rollbackNotification.success ? 'text-green-800' : 'text-red-800']">
              {{ rollbackNotification.success ? 'Rollback Completed' : 'Rollback Failed' }}
            </h4>
            <p :class="['text-sm', rollbackNotification.success ? 'text-green-600' : 'text-red-600']">
              {{ rollbackNotification.message }}
            </p>
          </div>
          <button
            @click="rollbackNotification.show = false"
            class="text-gray-400 hover:text-gray-600"
          >
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
      </div>
    </Transition>

    <!-- Header -->
    <div class="flex items-center justify-between mb-6">
      <div>
        <h1 class="text-2xl font-bold text-gray-900">Deployments</h1>
        <p class="text-sm text-gray-500 mt-1">
          Deploy and manage roles across your fleet
        </p>
      </div>
      <div class="flex items-center gap-3">
        <button
          @click="fetchDeployments"
          :disabled="isLoading"
          class="btn btn-secondary flex items-center gap-2"
        >
          <svg
            :class="['w-4 h-4', isLoading ? 'animate-spin' : '']"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              stroke-linecap="round"
              stroke-linejoin="round"
              stroke-width="2"
              d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
            />
          </svg>
          Refresh
        </button>
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
    </div>

    <!-- Summary Stats -->
    <div class="grid grid-cols-2 md:grid-cols-5 gap-4 mb-6">
      <div class="card p-4">
        <div class="flex items-center justify-between">
          <div>
            <p class="text-sm text-gray-500">Total</p>
            <p class="text-2xl font-bold text-gray-900">{{ stats.total }}</p>
          </div>
          <div class="w-10 h-10 rounded-full bg-gray-100 flex items-center justify-center">
            <svg class="w-5 h-5 text-gray-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
            </svg>
          </div>
        </div>
      </div>

      <div class="card p-4">
        <div class="flex items-center justify-between">
          <div>
            <p class="text-sm text-gray-500">Completed</p>
            <p class="text-2xl font-bold text-green-600">{{ stats.completed }}</p>
          </div>
          <div class="w-10 h-10 rounded-full bg-green-100 flex items-center justify-center">
            <svg class="w-5 h-5 text-green-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          </div>
        </div>
      </div>

      <div class="card p-4">
        <div class="flex items-center justify-between">
          <div>
            <p class="text-sm text-gray-500">In Progress</p>
            <p class="text-2xl font-bold text-blue-600">{{ stats.inProgress }}</p>
          </div>
          <div class="w-10 h-10 rounded-full bg-blue-100 flex items-center justify-center">
            <svg class="w-5 h-5 text-blue-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          </div>
        </div>
      </div>

      <div class="card p-4">
        <div class="flex items-center justify-between">
          <div>
            <p class="text-sm text-gray-500">Failed</p>
            <p class="text-2xl font-bold text-red-600">{{ stats.failed }}</p>
          </div>
          <div class="w-10 h-10 rounded-full bg-red-100 flex items-center justify-center">
            <svg class="w-5 h-5 text-red-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 14l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2m7-2a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          </div>
        </div>
      </div>

      <div class="card p-4">
        <div class="flex items-center justify-between">
          <div>
            <p class="text-sm text-gray-500">Rolled Back</p>
            <p class="text-2xl font-bold text-orange-600">{{ stats.rolledBack }}</p>
          </div>
          <div class="w-10 h-10 rounded-full bg-orange-100 flex items-center justify-center">
            <svg class="w-5 h-5 text-orange-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 10h10a8 8 0 018 8v2M3 10l6 6m-6-6l6-6" />
            </svg>
          </div>
        </div>
      </div>
    </div>

    <!-- Deployments Table -->
    <div class="card overflow-hidden">
      <div class="px-6 py-4 border-b border-gray-200">
        <h2 class="text-lg font-semibold">Recent Deployments</h2>
      </div>
      <div class="overflow-x-auto">
        <table class="min-w-full divide-y divide-gray-200">
          <thead class="bg-gray-50">
            <tr>
              <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Status</th>
              <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Node</th>
              <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Roles</th>
              <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Started</th>
              <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Completed</th>
              <th class="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase">Actions</th>
            </tr>
          </thead>
          <tbody class="bg-white divide-y divide-gray-200">
            <tr v-for="deployment in deployments" :key="deployment.deployment_id" class="hover:bg-gray-50">
              <td class="px-6 py-4 whitespace-nowrap">
                <div class="flex items-center gap-2">
                  <svg
                    class="w-5 h-5"
                    :class="{
                      'text-green-600': deployment.status === 'completed',
                      'text-blue-600': deployment.status === 'in_progress',
                      'text-yellow-600': deployment.status === 'pending',
                      'text-red-600': deployment.status === 'failed',
                      'text-orange-600': deployment.status === 'rolled_back',
                      'text-gray-600': deployment.status === 'cancelled',
                    }"
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" :d="getStatusIcon(deployment.status)" />
                  </svg>
                  <span :class="['px-2 py-1 text-xs font-medium rounded-full', getStatusClass(deployment.status)]">
                    {{ deployment.status.replace('_', ' ') }}
                  </span>
                </div>
              </td>
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
              <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                {{ formatDateTime(deployment.started_at) }}
              </td>
              <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                {{ formatDateTime(deployment.completed_at) }}
              </td>
              <td class="px-6 py-4 whitespace-nowrap text-right text-sm">
                <div class="flex items-center justify-end gap-2">
                  <!-- View Details -->
                  <button
                    @click="showDetails(deployment)"
                    class="text-gray-600 hover:text-gray-800"
                    title="View details"
                  >
                    <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
                    </svg>
                  </button>

                  <!-- Cancel (for in_progress) -->
                  <button
                    v-if="deployment.status === 'in_progress'"
                    @click="handleCancel(deployment.deployment_id)"
                    :disabled="isCancelling === deployment.deployment_id"
                    class="text-red-600 hover:text-red-800 disabled:opacity-50"
                    title="Cancel deployment"
                  >
                    <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
                    </svg>
                  </button>

                  <!-- Retry (for failed) -->
                  <button
                    v-if="deployment.status === 'failed'"
                    @click="handleRetry(deployment.deployment_id)"
                    :disabled="isRetrying === deployment.deployment_id"
                    class="text-blue-600 hover:text-blue-800 disabled:opacity-50"
                    title="Retry deployment"
                  >
                    <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                    </svg>
                  </button>

                  <!-- Rollback (for completed) -->
                  <button
                    v-if="deployment.status === 'completed'"
                    @click="handleRollback(deployment.deployment_id)"
                    :disabled="isRollingBack === deployment.deployment_id"
                    class="text-orange-600 hover:text-orange-800 disabled:opacity-50"
                    title="Rollback deployment"
                  >
                    <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 10h10a8 8 0 018 8v2M3 10l6 6m-6-6l6-6" />
                    </svg>
                  </button>
                </div>
              </td>
            </tr>
            <tr v-if="deployments.length === 0 && !isLoading">
              <td colspan="6" class="px-6 py-12 text-center text-gray-500">
                <svg class="w-12 h-12 mx-auto text-gray-400 mb-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
                </svg>
                <p>No deployments yet. Click "New Deployment" to get started.</p>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Loading -->
    <div v-if="isLoading" class="flex items-center justify-center py-12">
      <div class="animate-spin w-8 h-8 border-4 border-primary-600 border-t-transparent rounded-full"></div>
    </div>

    <!-- Deployment Details Modal -->
    <Teleport to="body">
      <Transition
        enter-active-class="transition duration-200 ease-out"
        enter-from-class="opacity-0"
        enter-to-class="opacity-100"
        leave-active-class="transition duration-150 ease-in"
        leave-from-class="opacity-100"
        leave-to-class="opacity-0"
      >
        <div
          v-if="showDetailsModal && selectedDeployment"
          class="fixed inset-0 z-50 flex items-center justify-center p-4"
        >
          <div class="fixed inset-0 bg-gray-500 bg-opacity-75" @click="closeDetails"></div>
          <div class="relative bg-white rounded-lg shadow-xl max-w-2xl w-full max-h-[80vh] overflow-hidden">
            <div class="flex items-center justify-between px-6 py-4 border-b border-gray-200">
              <div class="flex items-center gap-3">
                <h3 class="text-lg font-semibold text-gray-900">Deployment Details</h3>
                <span :class="['px-2 py-1 text-xs font-medium rounded-full', getStatusClass(selectedDeployment.status)]">
                  {{ selectedDeployment.status.replace('_', ' ') }}
                </span>
              </div>
              <button
                @click="closeDetails"
                class="text-gray-400 hover:text-gray-600"
              >
                <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            <div class="p-6 overflow-y-auto max-h-[calc(80vh-8rem)]">
              <!-- Basic Info -->
              <div class="grid grid-cols-2 gap-4 mb-6">
                <div>
                  <p class="text-sm text-gray-500">Deployment ID</p>
                  <p class="font-mono text-sm">{{ selectedDeployment.deployment_id }}</p>
                </div>
                <div>
                  <p class="text-sm text-gray-500">Node ID</p>
                  <p class="font-mono text-sm">{{ selectedDeployment.node_id }}</p>
                </div>
                <div>
                  <p class="text-sm text-gray-500">Started At</p>
                  <p class="text-sm">{{ formatDateTime(selectedDeployment.started_at) }}</p>
                </div>
                <div>
                  <p class="text-sm text-gray-500">Completed At</p>
                  <p class="text-sm">{{ formatDateTime(selectedDeployment.completed_at) }}</p>
                </div>
              </div>

              <!-- Roles -->
              <div class="mb-6">
                <p class="text-sm text-gray-500 mb-2">Roles</p>
                <div class="flex flex-wrap gap-2">
                  <span
                    v-for="role in selectedDeployment.roles"
                    :key="role"
                    class="px-3 py-1 text-sm font-medium bg-primary-100 text-primary-700 rounded-full"
                  >
                    {{ role }}
                  </span>
                </div>
              </div>

              <!-- Rollback indicator -->
              <div v-if="selectedDeployment.status === 'rolled_back'" class="mb-6 p-4 bg-orange-50 border border-orange-200 rounded-lg">
                <div class="flex items-center gap-2">
                  <svg class="w-5 h-5 text-orange-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 10h10a8 8 0 018 8v2M3 10l6 6m-6-6l6-6" />
                  </svg>
                  <span class="font-medium text-orange-800">This deployment was rolled back</span>
                </div>
                <p class="text-sm text-orange-600 mt-1">
                  The deployment was reverted to the previous state due to health failures or manual action.
                </p>
              </div>

              <!-- Error Message -->
              <div v-if="selectedDeployment.error" class="mb-6">
                <p class="text-sm text-gray-500 mb-2">Error</p>
                <div class="p-4 bg-red-50 border border-red-200 rounded-lg">
                  <p class="text-sm text-red-800 font-mono whitespace-pre-wrap">{{ selectedDeployment.error }}</p>
                </div>
              </div>

              <!-- Playbook Output -->
              <div v-if="selectedDeployment.playbook_output">
                <p class="text-sm text-gray-500 mb-2">Playbook Output</p>
                <div class="bg-gray-900 rounded-lg p-4 overflow-x-auto">
                  <pre class="text-sm text-gray-100 font-mono whitespace-pre-wrap">{{ selectedDeployment.playbook_output }}</pre>
                </div>
              </div>
            </div>

            <div class="flex justify-end gap-3 px-6 py-4 border-t border-gray-200">
              <!-- Rollback button in modal -->
              <button
                v-if="selectedDeployment.status === 'completed'"
                @click="handleRollback(selectedDeployment.deployment_id); closeDetails()"
                :disabled="isRollingBack === selectedDeployment.deployment_id"
                class="btn bg-orange-600 text-white hover:bg-orange-700 disabled:opacity-50"
              >
                {{ isRollingBack === selectedDeployment.deployment_id ? 'Rolling Back...' : 'Rollback' }}
              </button>
              <button
                v-if="selectedDeployment.status === 'failed'"
                @click="handleRetry(selectedDeployment.deployment_id); closeDetails()"
                :disabled="isRetrying === selectedDeployment.deployment_id"
                class="btn btn-primary disabled:opacity-50"
              >
                {{ isRetrying === selectedDeployment.deployment_id ? 'Retrying...' : 'Retry Deployment' }}
              </button>
              <button
                @click="closeDetails"
                class="btn btn-secondary"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>
  </div>
</template>
