<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * Blue-Green Deployments View
 *
 * Manages zero-downtime blue-green deployments with role borrowing (Issue #726 Phase 3).
 */

import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useSlmApi } from '@/composables/useSlmApi'
import { useSlmWebSocket } from '@/composables/useSlmWebSocket'
import { useFleetStore } from '@/stores/fleet'
import { createLogger } from '@/utils/debugUtils'
import type { BlueGreenDeployment, BlueGreenDeploymentCreate, NodeRole } from '@/types/slm'

const logger = createLogger('BlueGreenView')
const api = useSlmApi()
const ws = useSlmWebSocket()
const fleetStore = useFleetStore()

// State
const deployments = ref<BlueGreenDeployment[]>([])
const isLoading = ref(false)
const showCreateDialog = ref(false)
const isCreating = ref(false)
const selectedDeployment = ref<BlueGreenDeployment | null>(null)
const showDetailsModal = ref(false)

// Eligible nodes for role borrowing
const eligibleNodes = ref<Array<{
  node_id: string
  hostname: string
  ip_address: string
  current_roles: string[]
  available_capacity: number
  status: string
}>>([])
const isLoadingEligible = ref(false)

// New deployment form
const newDeployment = ref<BlueGreenDeploymentCreate>({
  blue_node_id: '',
  green_node_id: '',
  roles: [],
  deployment_type: 'upgrade',
  auto_rollback: true,
  purge_on_complete: true,
})

// Available roles
const availableRoles = computed(() => fleetStore.availableRoles.map(r => r.name))

// Summary stats
const stats = computed(() => ({
  total: deployments.value.length,
  active: deployments.value.filter(d => ['borrowing', 'deploying', 'verifying', 'switching', 'active'].includes(d.status)).length,
  completed: deployments.value.filter(d => d.status === 'completed').length,
  failed: deployments.value.filter(d => d.status === 'failed').length,
  rolledBack: deployments.value.filter(d => d.status === 'rolled_back').length,
}))

// Node options for dropdowns
const nodeOptions = computed(() =>
  fleetStore.nodeList.map(node => ({
    value: node.node_id,
    label: `${node.hostname} (${node.ip_address})`,
    roles: node.roles,
  }))
)

onMounted(async () => {
  await Promise.all([
    fetchDeployments(),
    fleetStore.fetchNodes(),
    fleetStore.fetchRoles(),
  ])

  // Connect to WebSocket for real-time updates
  ws.connect()
  ws.subscribeAll()

  ws.onDeploymentStatus(() => {
    fetchDeployments()
  })
})

onUnmounted(() => {
  ws.disconnect()
})

async function fetchDeployments(): Promise<void> {
  isLoading.value = true
  try {
    const response = await api.getBlueGreenDeployments()
    deployments.value = response.deployments
  } catch (err) {
    logger.error('Failed to fetch blue-green deployments:', err)
  } finally {
    isLoading.value = false
  }
}

async function fetchEligibleNodes(roles: string[]): Promise<void> {
  if (roles.length === 0) {
    eligibleNodes.value = []
    return
  }

  isLoadingEligible.value = true
  try {
    const response = await api.getEligibleNodes(roles)
    eligibleNodes.value = response.nodes
  } catch (err) {
    logger.error('Failed to fetch eligible nodes:', err)
    eligibleNodes.value = []
  } finally {
    isLoadingEligible.value = false
  }
}

async function handleCreateDeployment(): Promise<void> {
  if (!newDeployment.value.blue_node_id || !newDeployment.value.green_node_id || newDeployment.value.roles.length === 0) {
    return
  }

  isCreating.value = true
  try {
    await api.createBlueGreenDeployment(newDeployment.value)
    showCreateDialog.value = false
    resetForm()
    await fetchDeployments()
  } catch (err) {
    logger.error('Failed to create blue-green deployment:', err)
    alert('Failed to create deployment')
  } finally {
    isCreating.value = false
  }
}

async function handleSwitch(deploymentId: string): Promise<void> {
  if (!confirm('Are you sure you want to switch traffic to the green node?')) {
    return
  }

  try {
    await api.switchBlueGreenTraffic(deploymentId)
    await fetchDeployments()
  } catch (err) {
    logger.error('Failed to switch traffic:', err)
    alert('Failed to switch traffic')
  }
}

async function handleRollback(deploymentId: string): Promise<void> {
  if (!confirm('Are you sure you want to rollback to the blue node?')) {
    return
  }

  try {
    await api.rollbackBlueGreen(deploymentId)
    await fetchDeployments()
  } catch (err) {
    logger.error('Failed to rollback:', err)
    alert('Failed to rollback')
  }
}

async function handleCancel(deploymentId: string): Promise<void> {
  if (!confirm('Are you sure you want to cancel this deployment?')) {
    return
  }

  try {
    await api.cancelBlueGreen(deploymentId)
    await fetchDeployments()
  } catch (err) {
    logger.error('Failed to cancel deployment:', err)
    alert('Failed to cancel')
  }
}

function resetForm(): void {
  newDeployment.value = {
    blue_node_id: '',
    green_node_id: '',
    roles: [],
    deployment_type: 'upgrade',
    auto_rollback: true,
    purge_on_complete: true,
  }
  eligibleNodes.value = []
}

function showDetails(deployment: BlueGreenDeployment): void {
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
    case 'active': return 'bg-green-100 text-green-800'
    case 'borrowing':
    case 'deploying':
    case 'verifying':
    case 'switching': return 'bg-blue-100 text-blue-800'
    case 'pending': return 'bg-yellow-100 text-yellow-800'
    case 'failed': return 'bg-red-100 text-red-800'
    case 'rolling_back': return 'bg-orange-100 text-orange-800'
    case 'rolled_back': return 'bg-orange-100 text-orange-800'
    default: return 'bg-gray-100 text-gray-800'
  }
}

function formatDateTime(isoString: string | null): string {
  if (!isoString) return '-'
  return new Date(isoString).toLocaleString()
}

function getNodeHostname(nodeId: string): string {
  const node = fleetStore.getNode(nodeId)
  return node?.hostname || nodeId
}

function toggleRole(role: NodeRole): void {
  const roles = newDeployment.value.roles as string[]
  const index = roles.indexOf(role)
  if (index >= 0) {
    roles.splice(index, 1)
  } else {
    roles.push(role)
  }
  // Fetch eligible nodes when roles change
  fetchEligibleNodes(roles)
}
</script>

<template>
  <div class="p-6">
    <!-- Header -->
    <div class="flex items-center justify-between mb-6">
      <div>
        <h1 class="text-2xl font-bold text-gray-900">Blue-Green Deployments</h1>
        <p class="text-sm text-gray-500 mt-1">
          Zero-downtime deployments with role borrowing and automatic rollback
        </p>
      </div>
      <div class="flex items-center gap-3">
        <button
          @click="fetchDeployments"
          :disabled="isLoading"
          class="btn btn-secondary flex items-center gap-2"
        >
          <svg :class="['w-4 h-4', isLoading ? 'animate-spin' : '']" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
          </svg>
          Refresh
        </button>
        <button
          @click="showCreateDialog = true"
          class="btn btn-primary flex items-center gap-2"
        >
          <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4" />
          </svg>
          New Blue-Green
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
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 7h12m0 0l-4-4m4 4l-4 4m0 6H4m0 0l4 4m-4-4l4-4" />
            </svg>
          </div>
        </div>
      </div>

      <div class="card p-4">
        <div class="flex items-center justify-between">
          <div>
            <p class="text-sm text-gray-500">Active</p>
            <p class="text-2xl font-bold text-blue-600">{{ stats.active }}</p>
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
        <h2 class="text-lg font-semibold">Blue-Green Deployments</h2>
      </div>
      <div class="overflow-x-auto">
        <table class="min-w-full divide-y divide-gray-200">
          <thead class="bg-gray-50">
            <tr>
              <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Status</th>
              <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Blue Node</th>
              <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Green Node</th>
              <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Roles</th>
              <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Progress</th>
              <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Started</th>
              <th class="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase">Actions</th>
            </tr>
          </thead>
          <tbody class="bg-white divide-y divide-gray-200">
            <tr v-for="deployment in deployments" :key="deployment.bg_deployment_id" class="hover:bg-gray-50">
              <td class="px-6 py-4 whitespace-nowrap">
                <span :class="['px-2 py-1 text-xs font-medium rounded-full', getStatusClass(deployment.status)]">
                  {{ deployment.status.replace('_', ' ') }}
                </span>
              </td>
              <td class="px-6 py-4 whitespace-nowrap">
                <div class="flex items-center gap-2">
                  <div class="w-3 h-3 rounded-full bg-blue-500"></div>
                  <span class="text-sm font-medium text-gray-900">{{ getNodeHostname(deployment.blue_node_id) }}</span>
                </div>
              </td>
              <td class="px-6 py-4 whitespace-nowrap">
                <div class="flex items-center gap-2">
                  <div class="w-3 h-3 rounded-full bg-green-500"></div>
                  <span class="text-sm font-medium text-gray-900">{{ getNodeHostname(deployment.green_node_id) }}</span>
                </div>
              </td>
              <td class="px-6 py-4">
                <div class="flex flex-wrap gap-1">
                  <span
                    v-for="role in deployment.blue_roles"
                    :key="role"
                    class="px-2 py-0.5 text-xs font-medium bg-primary-100 text-primary-700 rounded"
                  >
                    {{ role }}
                  </span>
                </div>
              </td>
              <td class="px-6 py-4 whitespace-nowrap">
                <div class="flex items-center gap-2">
                  <div class="w-24 bg-gray-200 rounded-full h-2">
                    <div
                      class="bg-primary-600 h-2 rounded-full transition-all"
                      :style="{ width: `${deployment.progress_percent}%` }"
                    ></div>
                  </div>
                  <span class="text-xs text-gray-500">{{ deployment.progress_percent }}%</span>
                </div>
              </td>
              <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                {{ formatDateTime(deployment.started_at) }}
              </td>
              <td class="px-6 py-4 whitespace-nowrap text-right">
                <div class="flex items-center justify-end gap-2">
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

                  <!-- Switch traffic (when verifying) -->
                  <button
                    v-if="deployment.status === 'verifying'"
                    @click="handleSwitch(deployment.bg_deployment_id)"
                    class="text-green-600 hover:text-green-800"
                    title="Switch to green"
                  >
                    <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M14 5l7 7m0 0l-7 7m7-7H3" />
                    </svg>
                  </button>

                  <!-- Rollback (when active) -->
                  <button
                    v-if="deployment.status === 'active'"
                    @click="handleRollback(deployment.bg_deployment_id)"
                    class="text-orange-600 hover:text-orange-800"
                    title="Rollback to blue"
                  >
                    <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 10h10a8 8 0 018 8v2M3 10l6 6m-6-6l6-6" />
                    </svg>
                  </button>

                  <!-- Cancel (when in progress) -->
                  <button
                    v-if="['pending', 'borrowing', 'deploying'].includes(deployment.status)"
                    @click="handleCancel(deployment.bg_deployment_id)"
                    class="text-red-600 hover:text-red-800"
                    title="Cancel"
                  >
                    <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
                    </svg>
                  </button>
                </div>
              </td>
            </tr>
            <tr v-if="deployments.length === 0 && !isLoading">
              <td colspan="7" class="px-6 py-12 text-center text-gray-500">
                <svg class="w-12 h-12 mx-auto text-gray-400 mb-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 7h12m0 0l-4-4m4 4l-4 4m0 6H4m0 0l4 4m-4-4l4-4" />
                </svg>
                <p>No blue-green deployments yet. Click "New Blue-Green" to start.</p>
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

    <!-- Create Dialog -->
    <div
      v-if="showCreateDialog"
      class="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50"
      @click.self="showCreateDialog = false"
    >
      <div class="bg-white rounded-lg shadow-xl max-w-lg w-full mx-4 max-h-[90vh] overflow-y-auto">
        <div class="px-6 py-4 border-b border-gray-200">
          <h3 class="text-lg font-semibold text-gray-900">New Blue-Green Deployment</h3>
          <p class="text-sm text-gray-500 mt-1">
            Deploy roles from blue (source) to green (target) with zero downtime
          </p>
        </div>
        <div class="px-6 py-4 space-y-4">
          <!-- Blue Node Selection -->
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">
              <span class="flex items-center gap-2">
                <div class="w-3 h-3 rounded-full bg-blue-500"></div>
                Blue Node (Source)
              </span>
            </label>
            <select
              v-model="newDeployment.blue_node_id"
              class="w-full px-3 py-2 border border-gray-300 rounded-md focus:ring-primary-500 focus:border-primary-500"
            >
              <option value="">Select source node...</option>
              <option v-for="opt in nodeOptions" :key="opt.value" :value="opt.value">
                {{ opt.label }}
              </option>
            </select>
          </div>

          <!-- Roles Selection -->
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-2">Roles to Migrate</label>
            <div class="flex flex-wrap gap-2">
              <button
                v-for="role in availableRoles"
                :key="role"
                @click="toggleRole(role)"
                :class="[
                  'px-3 py-1 text-sm font-medium rounded-full border transition-colors',
                  (newDeployment.roles as string[]).includes(role)
                    ? 'bg-primary-100 text-primary-700 border-primary-300'
                    : 'bg-gray-50 text-gray-600 border-gray-200 hover:bg-gray-100'
                ]"
              >
                {{ role }}
              </button>
            </div>
          </div>

          <!-- Green Node Selection -->
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">
              <span class="flex items-center gap-2">
                <div class="w-3 h-3 rounded-full bg-green-500"></div>
                Green Node (Target)
              </span>
            </label>
            <div v-if="isLoadingEligible" class="text-sm text-gray-500 py-2">
              Finding eligible nodes...
            </div>
            <div v-else-if="eligibleNodes.length > 0">
              <select
                v-model="newDeployment.green_node_id"
                class="w-full px-3 py-2 border border-gray-300 rounded-md focus:ring-primary-500 focus:border-primary-500"
              >
                <option value="">Select target node...</option>
                <option
                  v-for="node in eligibleNodes"
                  :key="node.node_id"
                  :value="node.node_id"
                  :disabled="node.node_id === newDeployment.blue_node_id"
                >
                  {{ node.hostname }} ({{ node.available_capacity.toFixed(0) }}% capacity)
                </option>
              </select>
            </div>
            <div v-else-if="newDeployment.roles.length > 0" class="text-sm text-yellow-600 py-2">
              No eligible nodes found for these roles
            </div>
            <div v-else>
              <select
                v-model="newDeployment.green_node_id"
                class="w-full px-3 py-2 border border-gray-300 rounded-md focus:ring-primary-500 focus:border-primary-500"
              >
                <option value="">Select target node...</option>
                <option
                  v-for="opt in nodeOptions"
                  :key="opt.value"
                  :value="opt.value"
                  :disabled="opt.value === newDeployment.blue_node_id"
                >
                  {{ opt.label }}
                </option>
              </select>
            </div>
          </div>

          <!-- Deployment Type -->
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">Deployment Type</label>
            <select
              v-model="newDeployment.deployment_type"
              class="w-full px-3 py-2 border border-gray-300 rounded-md focus:ring-primary-500 focus:border-primary-500"
            >
              <option value="upgrade">Upgrade</option>
              <option value="migration">Migration</option>
              <option value="failover">Failover</option>
            </select>
          </div>

          <!-- Options -->
          <div class="flex items-center gap-6">
            <label class="flex items-center gap-2">
              <input
                type="checkbox"
                v-model="newDeployment.auto_rollback"
                class="w-4 h-4 text-primary-600 border-gray-300 rounded focus:ring-primary-500"
              />
              <span class="text-sm text-gray-700">Auto-rollback on failure</span>
            </label>
            <label class="flex items-center gap-2">
              <input
                type="checkbox"
                v-model="newDeployment.purge_on_complete"
                class="w-4 h-4 text-primary-600 border-gray-300 rounded focus:ring-primary-500"
              />
              <span class="text-sm text-gray-700">Purge blue roles after completion</span>
            </label>
          </div>

          <!-- Info Box -->
          <div class="bg-blue-50 border border-blue-200 rounded-md p-3">
            <p class="text-sm text-blue-700">
              The green node will temporarily borrow the selected roles from the blue node.
              After verification, traffic switches to green. If purge is enabled, blue's roles
              are cleaned up after completion.
            </p>
          </div>
        </div>
        <div class="px-6 py-4 border-t border-gray-200 flex justify-end gap-3">
          <button
            @click="showCreateDialog = false; resetForm()"
            class="px-4 py-2 text-sm font-medium text-gray-700 bg-gray-100 rounded-md hover:bg-gray-200"
          >
            Cancel
          </button>
          <button
            @click="handleCreateDeployment"
            :disabled="!newDeployment.blue_node_id || !newDeployment.green_node_id || newDeployment.roles.length === 0 || isCreating"
            class="px-4 py-2 text-sm font-medium text-white bg-primary-600 rounded-md hover:bg-primary-700 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
          >
            <div v-if="isCreating" class="animate-spin w-4 h-4 border-2 border-white border-t-transparent rounded-full"></div>
            Start Deployment
          </button>
        </div>
      </div>
    </div>

    <!-- Details Modal -->
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
                <h3 class="text-lg font-semibold text-gray-900">Blue-Green Deployment Details</h3>
                <span :class="['px-2 py-1 text-xs font-medium rounded-full', getStatusClass(selectedDeployment.status)]">
                  {{ selectedDeployment.status.replace('_', ' ') }}
                </span>
              </div>
              <button @click="closeDetails" class="text-gray-400 hover:text-gray-600">
                <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            <div class="p-6 overflow-y-auto max-h-[calc(80vh-8rem)]">
              <!-- Node Info -->
              <div class="grid grid-cols-2 gap-4 mb-6">
                <div class="p-4 bg-blue-50 rounded-lg">
                  <p class="text-sm font-medium text-blue-800 mb-1">Blue Node (Source)</p>
                  <p class="text-lg font-semibold text-blue-900">{{ getNodeHostname(selectedDeployment.blue_node_id) }}</p>
                  <p class="text-xs text-blue-600 mt-1">Roles: {{ selectedDeployment.blue_roles.join(', ') }}</p>
                </div>
                <div class="p-4 bg-green-50 rounded-lg">
                  <p class="text-sm font-medium text-green-800 mb-1">Green Node (Target)</p>
                  <p class="text-lg font-semibold text-green-900">{{ getNodeHostname(selectedDeployment.green_node_id) }}</p>
                  <p class="text-xs text-green-600 mt-1">Borrowed: {{ selectedDeployment.borrowed_roles.join(', ') || 'None yet' }}</p>
                </div>
              </div>

              <!-- Progress -->
              <div class="mb-6">
                <div class="flex items-center justify-between mb-2">
                  <p class="text-sm font-medium text-gray-700">Progress</p>
                  <p class="text-sm text-gray-500">{{ selectedDeployment.progress_percent }}%</p>
                </div>
                <div class="w-full bg-gray-200 rounded-full h-3">
                  <div
                    class="bg-primary-600 h-3 rounded-full transition-all"
                    :style="{ width: `${selectedDeployment.progress_percent}%` }"
                  ></div>
                </div>
                <p v-if="selectedDeployment.current_step" class="text-sm text-gray-500 mt-2">
                  {{ selectedDeployment.current_step }}
                </p>
              </div>

              <!-- Timestamps -->
              <div class="grid grid-cols-2 gap-4 mb-6">
                <div>
                  <p class="text-sm text-gray-500">Started</p>
                  <p class="text-sm font-medium">{{ formatDateTime(selectedDeployment.started_at) }}</p>
                </div>
                <div>
                  <p class="text-sm text-gray-500">Switched</p>
                  <p class="text-sm font-medium">{{ formatDateTime(selectedDeployment.switched_at) }}</p>
                </div>
                <div>
                  <p class="text-sm text-gray-500">Completed</p>
                  <p class="text-sm font-medium">{{ formatDateTime(selectedDeployment.completed_at) }}</p>
                </div>
                <div v-if="selectedDeployment.rollback_at">
                  <p class="text-sm text-gray-500">Rolled Back</p>
                  <p class="text-sm font-medium text-orange-600">{{ formatDateTime(selectedDeployment.rollback_at) }}</p>
                </div>
              </div>

              <!-- Error -->
              <div v-if="selectedDeployment.error" class="mb-6">
                <p class="text-sm text-gray-500 mb-2">Error</p>
                <div class="p-4 bg-red-50 border border-red-200 rounded-lg">
                  <p class="text-sm text-red-800 font-mono whitespace-pre-wrap">{{ selectedDeployment.error }}</p>
                </div>
              </div>

              <!-- Configuration -->
              <div class="grid grid-cols-2 gap-4">
                <div>
                  <p class="text-sm text-gray-500">Deployment Type</p>
                  <p class="text-sm font-medium capitalize">{{ selectedDeployment.deployment_type }}</p>
                </div>
                <div>
                  <p class="text-sm text-gray-500">Auto Rollback</p>
                  <p class="text-sm font-medium">{{ selectedDeployment.auto_rollback ? 'Yes' : 'No' }}</p>
                </div>
                <div>
                  <p class="text-sm text-gray-500">Purge on Complete</p>
                  <p class="text-sm font-medium">{{ selectedDeployment.purge_on_complete ? 'Yes' : 'No' }}</p>
                </div>
                <div>
                  <p class="text-sm text-gray-500">Health Check Timeout</p>
                  <p class="text-sm font-medium">{{ selectedDeployment.health_check_timeout }}s</p>
                </div>
              </div>
            </div>

            <div class="flex justify-end gap-3 px-6 py-4 border-t border-gray-200">
              <button
                v-if="selectedDeployment.status === 'verifying'"
                @click="handleSwitch(selectedDeployment.bg_deployment_id); closeDetails()"
                class="btn bg-green-600 text-white hover:bg-green-700"
              >
                Switch to Green
              </button>
              <button
                v-if="selectedDeployment.status === 'active'"
                @click="handleRollback(selectedDeployment.bg_deployment_id); closeDetails()"
                class="btn bg-orange-600 text-white hover:bg-orange-700"
              >
                Rollback
              </button>
              <button @click="closeDetails" class="btn btn-secondary">
                Close
              </button>
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>
  </div>
</template>
