<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * Deployments View
 *
 * Unified view for standard and blue-green deployments (Issue #726).
 */

import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useSlmApi } from '@/composables/useSlmApi'
import { useSlmWebSocket } from '@/composables/useSlmWebSocket'
import { useFleetStore } from '@/stores/fleet'
import { createLogger } from '@/utils/debugUtils'
import type { Deployment, BlueGreenDeployment, BlueGreenDeploymentCreate, NodeRole } from '@/types/slm'

const logger = createLogger('DeploymentsView')
const api = useSlmApi()
const ws = useSlmWebSocket()
const fleetStore = useFleetStore()

// Active tab
const activeTab = ref<'standard' | 'blue-green'>('standard')

// ===== STANDARD DEPLOYMENTS STATE =====
const deployments = ref<Deployment[]>([])
const isLoading = ref(false)
const showWizard = ref(false)
const isRetrying = ref<string | null>(null)
const isRetryingBg = ref<string | null>(null)
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

// New standard deployment form
const newDeployment = ref<{
  node_id: string
  roles: string[]
  force: boolean
}>({
  node_id: '',
  roles: [],
  force: false,
})
const isCreatingDeployment = ref(false)

// Standard stats
const standardStats = computed(() => ({
  total: deployments.value.length,
  completed: deployments.value.filter(d => d.status === 'completed').length,
  inProgress: deployments.value.filter(d => d.status === 'in_progress').length,
  failed: deployments.value.filter(d => d.status === 'failed').length,
  rolledBack: deployments.value.filter(d => d.status === 'rolled_back').length,
}))

// ===== BLUE-GREEN DEPLOYMENTS STATE =====
const bgDeployments = ref<BlueGreenDeployment[]>([])
const isLoadingBg = ref(false)
const showBgCreateDialog = ref(false)
const isCreatingBg = ref(false)
const selectedBgDeployment = ref<BlueGreenDeployment | null>(null)
const showBgDetailsModal = ref(false)

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

// New blue-green deployment form
const newBgDeployment = ref<BlueGreenDeploymentCreate>({
  blue_node_id: '',
  green_node_id: '',
  roles: [],
  deployment_type: 'upgrade',
  auto_rollback: true,
  purge_on_complete: true,
})

// Available roles
const availableRoles = computed(() => fleetStore.availableRoles.map(r => r.name))

// Role categories with descriptions and compatibility info
const roleCategories = computed(() => {
  const roles = fleetStore.availableRoles
  const categories: Record<string, {
    label: string
    description: string
    roles: Array<{ name: string; description: string; dependencies: string[] }>
  }> = {
    core: {
      label: 'Core Infrastructure',
      description: 'Required base components for all nodes',
      roles: [],
    },
    data: {
      label: 'Data Layer',
      description: 'Database and caching services',
      roles: [],
    },
    application: {
      label: 'Application Layer',
      description: 'Backend API and frontend web servers',
      roles: [],
    },
    ai: {
      label: 'AI/ML Services',
      description: 'LLM inference and AI processing',
      roles: [],
    },
    automation: {
      label: 'Automation',
      description: 'Browser automation and scripting',
      roles: [],
    },
    observability: {
      label: 'Observability',
      description: 'Monitoring and logging stack',
      roles: [],
    },
    'remote-access': {
      label: 'Remote Access',
      description: 'VNC and remote desktop services',
      roles: [],
    },
  }

  for (const role of roles) {
    const cat = role.category || 'core'
    if (categories[cat]) {
      categories[cat].roles.push({
        name: role.name,
        description: role.description,
        dependencies: role.dependencies || [],
      })
    }
  }

  return categories
})

// Blue-green stats
const bgStats = computed(() => ({
  total: bgDeployments.value.length,
  active: bgDeployments.value.filter(d => ['borrowing', 'deploying', 'verifying', 'switching', 'active'].includes(d.status)).length,
  completed: bgDeployments.value.filter(d => d.status === 'completed').length,
  failed: bgDeployments.value.filter(d => d.status === 'failed').length,
  rolledBack: bgDeployments.value.filter(d => d.status === 'rolled_back').length,
}))

// Node options for dropdowns
const nodeOptions = computed(() =>
  fleetStore.nodeList.map(node => ({
    value: node.node_id,
    label: `${node.hostname} (${node.ip_address})`,
    roles: node.roles,
  }))
)

// ===== LIFECYCLE =====
onMounted(async () => {
  await Promise.all([
    fetchDeployments(),
    fetchBgDeployments(),
    fleetStore.fetchNodes(),
    fleetStore.fetchRoles(),
  ])

  // Connect to WebSocket for real-time updates
  ws.connect()
  ws.subscribeAll()

  // Listen for deployment status updates
  ws.onDeploymentStatus((nodeId, data) => {
    logger.info('Deployment status update:', nodeId, data)
    fetchDeployments()
    fetchBgDeployments()
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

    setTimeout(() => {
      rollbackNotification.value.show = false
    }, 5000)

    fetchDeployments()
    fetchBgDeployments()
  })
})

onUnmounted(() => {
  ws.disconnect()
})

// ===== STANDARD DEPLOYMENT METHODS =====
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

// ===== BLUE-GREEN DEPLOYMENT METHODS =====
async function fetchBgDeployments(): Promise<void> {
  isLoadingBg.value = true
  try {
    const response = await api.getBlueGreenDeployments()
    bgDeployments.value = response.deployments as BlueGreenDeployment[]
  } catch (err) {
    logger.error('Failed to fetch blue-green deployments:', err)
  } finally {
    isLoadingBg.value = false
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

async function handleCreateBgDeployment(): Promise<void> {
  if (!newBgDeployment.value.blue_node_id) {
    alert('Please select a blue (source) node')
    return
  }
  if (!newBgDeployment.value.green_node_id) {
    alert('Please select a green (target) node')
    return
  }
  if (newBgDeployment.value.roles.length === 0) {
    alert('Please select at least one role to migrate')
    return
  }

  isCreatingBg.value = true
  try {
    logger.info('Creating blue-green deployment:', newBgDeployment.value)
    await api.createBlueGreenDeployment(newBgDeployment.value)
    showBgCreateDialog.value = false
    resetBgForm()
    await fetchBgDeployments()
  } catch (err: unknown) {
    logger.error('Failed to create blue-green deployment:', err)
    const errorMessage = err instanceof Error ? err.message : String(err)
    const axiosError = err as { response?: { data?: { detail?: string }; status?: number } }
    const detail = axiosError?.response?.data?.detail || errorMessage
    const status = axiosError?.response?.status
    if (status === 403) {
      alert('Access denied: Blue-green deployments require admin privileges')
    } else {
      alert(`Failed to create blue-green deployment: ${detail}`)
    }
  } finally {
    isCreatingBg.value = false
  }
}

async function handleBgSwitch(deploymentId: string): Promise<void> {
  if (!confirm('Are you sure you want to switch traffic to the green node?')) {
    return
  }

  try {
    await api.switchBlueGreenTraffic(deploymentId)
    await fetchBgDeployments()
  } catch (err) {
    logger.error('Failed to switch traffic:', err)
    alert('Failed to switch traffic')
  }
}

async function handleBgRollback(deploymentId: string): Promise<void> {
  if (!confirm('Are you sure you want to rollback to the blue node?')) {
    return
  }

  try {
    await api.rollbackBlueGreen(deploymentId)
    await fetchBgDeployments()
  } catch (err) {
    logger.error('Failed to rollback:', err)
    alert('Failed to rollback')
  }
}

async function handleBgCancel(deploymentId: string): Promise<void> {
  if (!confirm('Are you sure you want to cancel this deployment?')) {
    return
  }

  try {
    await api.cancelBlueGreen(deploymentId)
    await fetchBgDeployments()
  } catch (err) {
    logger.error('Failed to cancel deployment:', err)
    alert('Failed to cancel')
  }
}

async function handleBgRetry(deploymentId: string): Promise<void> {
  if (!confirm('Are you sure you want to retry this deployment?')) {
    return
  }

  isRetryingBg.value = deploymentId
  try {
    await api.retryBlueGreen(deploymentId)
    await fetchBgDeployments()
  } catch (err) {
    logger.error('Failed to retry deployment:', err)
    alert('Failed to retry deployment')
  } finally {
    isRetryingBg.value = null
  }
}

function resetBgForm(): void {
  newBgDeployment.value = {
    blue_node_id: '',
    green_node_id: '',
    roles: [],
    deployment_type: 'upgrade',
    auto_rollback: true,
    purge_on_complete: true,
  }
  eligibleNodes.value = []
}

function showBgDetails(deployment: BlueGreenDeployment): void {
  selectedBgDeployment.value = deployment
  showBgDetailsModal.value = true
}

function closeBgDetails(): void {
  showBgDetailsModal.value = false
  selectedBgDeployment.value = null
}

function toggleRole(role: NodeRole): void {
  const roles = newBgDeployment.value.roles as string[]
  const index = roles.indexOf(role)
  if (index >= 0) {
    roles.splice(index, 1)
  } else {
    roles.push(role)
  }
  fetchEligibleNodes(roles)
}

// ===== STANDARD DEPLOYMENT CREATE METHODS =====
async function handleCreateDeployment(): Promise<void> {
  if (!newDeployment.value.node_id) {
    alert('Please select a target node')
    return
  }
  if (newDeployment.value.roles.length === 0) {
    alert('Please select at least one role to deploy')
    return
  }

  isCreatingDeployment.value = true
  try {
    logger.info('Creating deployment:', {
      node_id: newDeployment.value.node_id,
      roles: newDeployment.value.roles,
      force: newDeployment.value.force,
    })
    await api.createDeployment({
      node_id: newDeployment.value.node_id,
      roles: newDeployment.value.roles as NodeRole[],
      force: newDeployment.value.force,
    })
    showWizard.value = false
    resetDeploymentForm()
    await fetchDeployments()
  } catch (err: unknown) {
    logger.error('Failed to create deployment:', err)
    const errorMessage = err instanceof Error ? err.message : String(err)
    const axiosError = err as { response?: { data?: { detail?: string } } }
    const detail = axiosError?.response?.data?.detail || errorMessage
    alert(`Failed to create deployment: ${detail}`)
  } finally {
    isCreatingDeployment.value = false
  }
}

function resetDeploymentForm(): void {
  newDeployment.value = {
    node_id: '',
    roles: [],
    force: false,
  }
}

function toggleDeploymentRole(role: string): void {
  const index = newDeployment.value.roles.indexOf(role)
  if (index >= 0) {
    newDeployment.value.roles.splice(index, 1)
  } else {
    newDeployment.value.roles.push(role)
  }
}

// ===== SHARED HELPERS =====
function getStatusClass(status: string): string {
  switch (status) {
    case 'completed': return 'bg-green-100 text-green-800'
    case 'active': return 'bg-green-100 text-green-800'
    case 'in_progress':
    case 'borrowing':
    case 'deploying':
    case 'verifying':
    case 'switching': return 'bg-blue-100 text-blue-800'
    case 'pending': return 'bg-yellow-100 text-yellow-800'
    case 'failed': return 'bg-red-100 text-red-800'
    case 'rolling_back':
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

function getNodeHostname(nodeId: string): string {
  const node = fleetStore.getNode(nodeId)
  return node?.hostname || nodeId
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
          @click="activeTab === 'standard' ? fetchDeployments() : fetchBgDeployments()"
          :disabled="isLoading || isLoadingBg"
          class="btn btn-secondary flex items-center gap-2"
        >
          <svg
            :class="['w-4 h-4', (isLoading || isLoadingBg) ? 'animate-spin' : '']"
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
          v-if="activeTab === 'standard'"
          @click="showWizard = true"
          class="btn btn-primary flex items-center gap-2"
        >
          <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4" />
          </svg>
          New Deployment
        </button>
        <button
          v-else
          @click="showBgCreateDialog = true"
          class="btn btn-primary flex items-center gap-2"
        >
          <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4" />
          </svg>
          New Blue-Green
        </button>
      </div>
    </div>

    <!-- Tabs -->
    <div class="border-b border-gray-200 mb-6">
      <nav class="flex gap-8">
        <button
          @click="activeTab = 'standard'"
          :class="[
            'py-4 px-1 text-sm font-medium border-b-2 transition-colors',
            activeTab === 'standard'
              ? 'border-primary-500 text-primary-600'
              : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
          ]"
        >
          Standard Deployments
          <span class="ml-2 px-2 py-0.5 text-xs font-medium rounded-full bg-gray-100 text-gray-600">
            {{ standardStats.total }}
          </span>
        </button>
        <button
          @click="activeTab = 'blue-green'"
          :class="[
            'py-4 px-1 text-sm font-medium border-b-2 transition-colors',
            activeTab === 'blue-green'
              ? 'border-primary-500 text-primary-600'
              : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
          ]"
        >
          Blue-Green Deployments
          <span class="ml-2 px-2 py-0.5 text-xs font-medium rounded-full bg-gray-100 text-gray-600">
            {{ bgStats.total }}
          </span>
        </button>
      </nav>
    </div>

    <!-- ===== STANDARD TAB ===== -->
    <div v-show="activeTab === 'standard'">
      <!-- Summary Stats -->
      <div class="grid grid-cols-2 md:grid-cols-5 gap-4 mb-6">
        <div class="card p-4">
          <div class="flex items-center justify-between">
            <div>
              <p class="text-sm text-gray-500">Total</p>
              <p class="text-2xl font-bold text-gray-900">{{ standardStats.total }}</p>
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
              <p class="text-2xl font-bold text-green-600">{{ standardStats.completed }}</p>
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
              <p class="text-2xl font-bold text-blue-600">{{ standardStats.inProgress }}</p>
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
              <p class="text-2xl font-bold text-red-600">{{ standardStats.failed }}</p>
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
              <p class="text-2xl font-bold text-orange-600">{{ standardStats.rolledBack }}</p>
            </div>
            <div class="w-10 h-10 rounded-full bg-orange-100 flex items-center justify-center">
              <svg class="w-5 h-5 text-orange-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 10h10a8 8 0 018 8v2M3 10l6 6m-6-6l6-6" />
              </svg>
            </div>
          </div>
        </div>
      </div>

      <!-- Standard Deployments Table -->
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

      <div v-if="isLoading" class="flex items-center justify-center py-12">
        <div class="animate-spin w-8 h-8 border-4 border-primary-600 border-t-transparent rounded-full"></div>
      </div>
    </div>

    <!-- ===== BLUE-GREEN TAB ===== -->
    <div v-show="activeTab === 'blue-green'">
      <!-- Blue-Green Stats -->
      <div class="grid grid-cols-2 md:grid-cols-5 gap-4 mb-6">
        <div class="card p-4">
          <div class="flex items-center justify-between">
            <div>
              <p class="text-sm text-gray-500">Total</p>
              <p class="text-2xl font-bold text-gray-900">{{ bgStats.total }}</p>
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
              <p class="text-2xl font-bold text-blue-600">{{ bgStats.active }}</p>
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
              <p class="text-2xl font-bold text-green-600">{{ bgStats.completed }}</p>
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
              <p class="text-2xl font-bold text-red-600">{{ bgStats.failed }}</p>
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
              <p class="text-2xl font-bold text-orange-600">{{ bgStats.rolledBack }}</p>
            </div>
            <div class="w-10 h-10 rounded-full bg-orange-100 flex items-center justify-center">
              <svg class="w-5 h-5 text-orange-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 10h10a8 8 0 018 8v2M3 10l6 6m-6-6l6-6" />
              </svg>
            </div>
          </div>
        </div>
      </div>

      <!-- Blue-Green Deployments Table -->
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
              <tr v-for="deployment in bgDeployments" :key="deployment.bg_deployment_id" class="hover:bg-gray-50">
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
                      @click="showBgDetails(deployment)"
                      class="text-gray-600 hover:text-gray-800"
                      title="View details"
                    >
                      <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
                      </svg>
                    </button>

                    <button
                      v-if="deployment.status === 'verifying'"
                      @click="handleBgSwitch(deployment.bg_deployment_id)"
                      class="text-green-600 hover:text-green-800"
                      title="Switch to green"
                    >
                      <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M14 5l7 7m0 0l-7 7m7-7H3" />
                      </svg>
                    </button>

                    <button
                      v-if="deployment.status === 'active'"
                      @click="handleBgRollback(deployment.bg_deployment_id)"
                      class="text-orange-600 hover:text-orange-800"
                      title="Rollback to blue"
                    >
                      <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 10h10a8 8 0 018 8v2M3 10l6 6m-6-6l6-6" />
                      </svg>
                    </button>

                    <button
                      v-if="['pending', 'borrowing', 'deploying'].includes(deployment.status)"
                      @click="handleBgCancel(deployment.bg_deployment_id)"
                      class="text-red-600 hover:text-red-800"
                      title="Cancel"
                    >
                      <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
                      </svg>
                    </button>

                    <button
                      v-if="deployment.status === 'failed'"
                      @click="handleBgRetry(deployment.bg_deployment_id)"
                      :disabled="isRetryingBg === deployment.bg_deployment_id"
                      class="text-blue-600 hover:text-blue-800 disabled:opacity-50"
                      title="Retry deployment"
                    >
                      <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                      </svg>
                    </button>
                  </div>
                </td>
              </tr>
              <tr v-if="bgDeployments.length === 0 && !isLoadingBg">
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

      <div v-if="isLoadingBg" class="flex items-center justify-center py-12">
        <div class="animate-spin w-8 h-8 border-4 border-primary-600 border-t-transparent rounded-full"></div>
      </div>
    </div>

    <!-- Standard Deployment Wizard Dialog -->
    <div
      v-if="showWizard"
      class="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50"
      @click.self="showWizard = false"
    >
      <div class="bg-white rounded-lg shadow-xl max-w-lg w-full mx-4 max-h-[90vh] overflow-y-auto">
        <div class="px-6 py-4 border-b border-gray-200">
          <h3 class="text-lg font-semibold text-gray-900">New Deployment</h3>
          <p class="text-sm text-gray-500 mt-1">
            Deploy roles to a node in your fleet
          </p>
        </div>
        <div class="px-6 py-4 space-y-4">
          <!-- Node Selection -->
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">Target Node</label>
            <select
              v-model="newDeployment.node_id"
              class="w-full px-3 py-2 border border-gray-300 rounded-md focus:ring-primary-500 focus:border-primary-500"
            >
              <option value="">Select a node...</option>
              <option v-for="opt in nodeOptions" :key="opt.value" :value="opt.value">
                {{ opt.label }}
              </option>
            </select>
          </div>

          <!-- Node Info (if selected) -->
          <div v-if="newDeployment.node_id" class="bg-gray-50 rounded-lg p-3">
            <p class="text-sm font-medium text-gray-700 mb-1">Current Roles</p>
            <div class="flex flex-wrap gap-1">
              <span
                v-for="role in (nodeOptions.find(n => n.value === newDeployment.node_id)?.roles || [])"
                :key="role"
                class="px-2 py-0.5 text-xs font-medium bg-gray-200 text-gray-700 rounded"
              >
                {{ role }}
              </span>
              <span v-if="(nodeOptions.find(n => n.value === newDeployment.node_id)?.roles || []).length === 0" class="text-xs text-gray-500">
                No roles assigned
              </span>
            </div>
          </div>

          <!-- Roles Selection by Category -->
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-2">Roles to Deploy</label>
            <p v-if="availableRoles.length === 0" class="text-sm text-gray-500">
              Loading available roles...
            </p>
            <div v-else class="space-y-3">
              <template v-for="(category, _catKey) in roleCategories" :key="_catKey">
                <div v-if="category.roles.length > 0" class="border border-gray-200 rounded-lg overflow-hidden">
                  <!-- Category Header -->
                  <div class="bg-gray-50 px-3 py-2 border-b border-gray-200">
                    <div class="flex items-center justify-between">
                      <span class="text-sm font-medium text-gray-800">{{ category.label }}</span>
                      <span class="text-xs text-gray-500">{{ category.description }}</span>
                    </div>
                  </div>
                  <!-- Category Roles -->
                  <div class="p-3 space-y-2">
                    <div
                      v-for="role in category.roles"
                      :key="role.name"
                      @click="toggleDeploymentRole(role.name)"
                      :class="[
                        'flex items-start gap-3 p-2 rounded-md cursor-pointer transition-colors',
                        newDeployment.roles.includes(role.name)
                          ? 'bg-primary-50 border border-primary-200'
                          : 'hover:bg-gray-50 border border-transparent'
                      ]"
                    >
                      <!-- Checkbox -->
                      <div :class="[
                        'w-5 h-5 rounded flex-shrink-0 flex items-center justify-center mt-0.5',
                        newDeployment.roles.includes(role.name)
                          ? 'bg-primary-600'
                          : 'border-2 border-gray-300'
                      ]">
                        <svg
                          v-if="newDeployment.roles.includes(role.name)"
                          class="w-3 h-3 text-white"
                          fill="none"
                          stroke="currentColor"
                          viewBox="0 0 24 24"
                        >
                          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="3" d="M5 13l4 4L19 7" />
                        </svg>
                      </div>
                      <!-- Role Info -->
                      <div class="flex-1 min-w-0">
                        <div class="flex items-center gap-2">
                          <span :class="[
                            'text-sm font-medium',
                            newDeployment.roles.includes(role.name) ? 'text-primary-700' : 'text-gray-900'
                          ]">
                            {{ role.name }}
                          </span>
                          <!-- Dependencies Badge -->
                          <span
                            v-if="role.dependencies.length > 0"
                            class="px-1.5 py-0.5 text-xs bg-amber-100 text-amber-700 rounded"
                            :title="'Requires: ' + role.dependencies.join(', ')"
                          >
                            needs: {{ role.dependencies.join(', ') }}
                          </span>
                        </div>
                        <p class="text-xs text-gray-500 mt-0.5">{{ role.description }}</p>
                      </div>
                    </div>
                  </div>
                </div>
              </template>
            </div>
          </div>

          <!-- Selected Roles Summary -->
          <div v-if="newDeployment.roles.length > 0" class="bg-green-50 border border-green-200 rounded-md p-3">
            <p class="text-sm font-medium text-green-800 mb-1">Selected Roles ({{ newDeployment.roles.length }})</p>
            <div class="flex flex-wrap gap-1">
              <span
                v-for="role in newDeployment.roles"
                :key="role"
                class="px-2 py-0.5 text-xs font-medium bg-green-100 text-green-700 rounded"
              >
                {{ role }}
              </span>
            </div>
          </div>

          <!-- Force Option -->
          <div class="flex items-center gap-2">
            <input
              type="checkbox"
              id="force-deploy"
              v-model="newDeployment.force"
              class="w-4 h-4 text-primary-600 border-gray-300 rounded focus:ring-primary-500"
            />
            <label for="force-deploy" class="text-sm text-gray-700">
              Force deployment (skip checks and redeploy even if roles already exist)
            </label>
          </div>

          <!-- Info Box -->
          <div class="bg-blue-50 border border-blue-200 rounded-md p-3">
            <p class="text-sm text-blue-700">
              This will deploy the selected roles to the target node using Ansible.
              The deployment progress can be tracked in real-time.
            </p>
          </div>
        </div>
        <div class="px-6 py-4 border-t border-gray-200 flex justify-end gap-3">
          <button
            @click="showWizard = false; resetDeploymentForm()"
            class="px-4 py-2 text-sm font-medium text-gray-700 bg-gray-100 rounded-md hover:bg-gray-200"
          >
            Cancel
          </button>
          <button
            @click="handleCreateDeployment"
            :disabled="!newDeployment.node_id || newDeployment.roles.length === 0 || isCreatingDeployment"
            class="px-4 py-2 text-sm font-medium text-white bg-primary-600 rounded-md hover:bg-primary-700 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
          >
            <div v-if="isCreatingDeployment" class="animate-spin w-4 h-4 border-2 border-white border-t-transparent rounded-full"></div>
            Start Deployment
          </button>
        </div>
      </div>
    </div>

    <!-- Blue-Green Create Dialog -->
    <div
      v-if="showBgCreateDialog"
      class="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50"
      @click.self="showBgCreateDialog = false"
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
              v-model="newBgDeployment.blue_node_id"
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
                  (newBgDeployment.roles as string[]).includes(role)
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
                v-model="newBgDeployment.green_node_id"
                class="w-full px-3 py-2 border border-gray-300 rounded-md focus:ring-primary-500 focus:border-primary-500"
              >
                <option value="">Select target node...</option>
                <option
                  v-for="node in eligibleNodes"
                  :key="node.node_id"
                  :value="node.node_id"
                  :disabled="node.node_id === newBgDeployment.blue_node_id"
                >
                  {{ node.hostname }} ({{ node.available_capacity.toFixed(0) }}% capacity)
                </option>
              </select>
            </div>
            <div v-else-if="newBgDeployment.roles.length > 0" class="text-sm text-yellow-600 py-2">
              No eligible nodes found for these roles
            </div>
            <div v-else>
              <select
                v-model="newBgDeployment.green_node_id"
                class="w-full px-3 py-2 border border-gray-300 rounded-md focus:ring-primary-500 focus:border-primary-500"
              >
                <option value="">Select target node...</option>
                <option
                  v-for="opt in nodeOptions"
                  :key="opt.value"
                  :value="opt.value"
                  :disabled="opt.value === newBgDeployment.blue_node_id"
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
              v-model="newBgDeployment.deployment_type"
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
                v-model="newBgDeployment.auto_rollback"
                class="w-4 h-4 text-primary-600 border-gray-300 rounded focus:ring-primary-500"
              />
              <span class="text-sm text-gray-700">Auto-rollback on failure</span>
            </label>
            <label class="flex items-center gap-2">
              <input
                type="checkbox"
                v-model="newBgDeployment.purge_on_complete"
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
            @click="showBgCreateDialog = false; resetBgForm()"
            class="px-4 py-2 text-sm font-medium text-gray-700 bg-gray-100 rounded-md hover:bg-gray-200"
          >
            Cancel
          </button>
          <button
            @click="handleCreateBgDeployment"
            :disabled="!newBgDeployment.blue_node_id || !newBgDeployment.green_node_id || newBgDeployment.roles.length === 0 || isCreatingBg"
            class="px-4 py-2 text-sm font-medium text-white bg-primary-600 rounded-md hover:bg-primary-700 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
          >
            <div v-if="isCreatingBg" class="animate-spin w-4 h-4 border-2 border-white border-t-transparent rounded-full"></div>
            Start Deployment
          </button>
        </div>
      </div>
    </div>

    <!-- Standard Deployment Details Modal -->
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
              <button @click="closeDetails" class="text-gray-400 hover:text-gray-600">
                <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            <div class="p-6 overflow-y-auto max-h-[calc(80vh-8rem)]">
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

              <div v-if="selectedDeployment.error" class="mb-6">
                <p class="text-sm text-gray-500 mb-2">Error</p>
                <div class="p-4 bg-red-50 border border-red-200 rounded-lg">
                  <p class="text-sm text-red-800 font-mono whitespace-pre-wrap">{{ selectedDeployment.error }}</p>
                </div>
              </div>

              <div v-if="selectedDeployment.playbook_output">
                <p class="text-sm text-gray-500 mb-2">Playbook Output</p>
                <div class="bg-gray-900 rounded-lg p-4 overflow-x-auto">
                  <pre class="text-sm text-gray-100 font-mono whitespace-pre-wrap">{{ selectedDeployment.playbook_output }}</pre>
                </div>
              </div>
            </div>

            <div class="flex justify-end gap-3 px-6 py-4 border-t border-gray-200">
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
              <button @click="closeDetails" class="btn btn-secondary">
                Close
              </button>
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>

    <!-- Blue-Green Details Modal -->
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
          v-if="showBgDetailsModal && selectedBgDeployment"
          class="fixed inset-0 z-50 flex items-center justify-center p-4"
        >
          <div class="fixed inset-0 bg-gray-500 bg-opacity-75" @click="closeBgDetails"></div>
          <div class="relative bg-white rounded-lg shadow-xl max-w-2xl w-full max-h-[80vh] overflow-hidden">
            <div class="flex items-center justify-between px-6 py-4 border-b border-gray-200">
              <div class="flex items-center gap-3">
                <h3 class="text-lg font-semibold text-gray-900">Blue-Green Deployment Details</h3>
                <span :class="['px-2 py-1 text-xs font-medium rounded-full', getStatusClass(selectedBgDeployment.status)]">
                  {{ selectedBgDeployment.status.replace('_', ' ') }}
                </span>
              </div>
              <button @click="closeBgDetails" class="text-gray-400 hover:text-gray-600">
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
                  <p class="text-lg font-semibold text-blue-900">{{ getNodeHostname(selectedBgDeployment.blue_node_id) }}</p>
                  <p class="text-xs text-blue-600 mt-1">Roles: {{ selectedBgDeployment.blue_roles.join(', ') }}</p>
                </div>
                <div class="p-4 bg-green-50 rounded-lg">
                  <p class="text-sm font-medium text-green-800 mb-1">Green Node (Target)</p>
                  <p class="text-lg font-semibold text-green-900">{{ getNodeHostname(selectedBgDeployment.green_node_id) }}</p>
                  <p class="text-xs text-green-600 mt-1">Borrowed: {{ selectedBgDeployment.borrowed_roles.join(', ') || 'None yet' }}</p>
                </div>
              </div>

              <!-- Progress -->
              <div class="mb-6">
                <div class="flex items-center justify-between mb-2">
                  <p class="text-sm font-medium text-gray-700">Progress</p>
                  <p class="text-sm text-gray-500">{{ selectedBgDeployment.progress_percent }}%</p>
                </div>
                <div class="w-full bg-gray-200 rounded-full h-3">
                  <div
                    class="bg-primary-600 h-3 rounded-full transition-all"
                    :style="{ width: `${selectedBgDeployment.progress_percent}%` }"
                  ></div>
                </div>
                <p v-if="selectedBgDeployment.current_step" class="text-sm text-gray-500 mt-2">
                  {{ selectedBgDeployment.current_step }}
                </p>
              </div>

              <!-- Error -->
              <div v-if="selectedBgDeployment.error" class="mb-6">
                <p class="text-sm text-gray-500 mb-2">Error</p>
                <div class="p-4 bg-red-50 border border-red-200 rounded-lg">
                  <p class="text-sm text-red-800 font-mono whitespace-pre-wrap">{{ selectedBgDeployment.error }}</p>
                </div>
              </div>

              <!-- Configuration -->
              <div class="grid grid-cols-2 gap-4">
                <div>
                  <p class="text-sm text-gray-500">Deployment Type</p>
                  <p class="text-sm font-medium capitalize">{{ selectedBgDeployment.deployment_type }}</p>
                </div>
                <div>
                  <p class="text-sm text-gray-500">Auto Rollback</p>
                  <p class="text-sm font-medium">{{ selectedBgDeployment.auto_rollback ? 'Yes' : 'No' }}</p>
                </div>
                <div>
                  <p class="text-sm text-gray-500">Purge on Complete</p>
                  <p class="text-sm font-medium">{{ selectedBgDeployment.purge_on_complete ? 'Yes' : 'No' }}</p>
                </div>
                <div>
                  <p class="text-sm text-gray-500">Started</p>
                  <p class="text-sm font-medium">{{ formatDateTime(selectedBgDeployment.started_at) }}</p>
                </div>
              </div>
            </div>

            <div class="flex justify-end gap-3 px-6 py-4 border-t border-gray-200">
              <button
                v-if="selectedBgDeployment.status === 'verifying'"
                @click="handleBgSwitch(selectedBgDeployment.bg_deployment_id); closeBgDetails()"
                class="btn bg-green-600 text-white hover:bg-green-700"
              >
                Switch to Green
              </button>
              <button
                v-if="selectedBgDeployment.status === 'active'"
                @click="handleBgRollback(selectedBgDeployment.bg_deployment_id); closeBgDetails()"
                class="btn bg-orange-600 text-white hover:bg-orange-700"
              >
                Rollback
              </button>
              <button
                v-if="selectedBgDeployment.status === 'failed'"
                @click="handleBgRetry(selectedBgDeployment.bg_deployment_id); closeBgDetails()"
                :disabled="isRetryingBg === selectedBgDeployment.bg_deployment_id"
                class="btn bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50"
              >
                {{ isRetryingBg === selectedBgDeployment.bg_deployment_id ? 'Retrying...' : 'Retry Deployment' }}
              </button>
              <button @click="closeBgDetails" class="btn btn-secondary">
                Close
              </button>
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>
  </div>
</template>
