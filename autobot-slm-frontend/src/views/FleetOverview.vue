<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * FleetOverview - Main fleet management page.
 *
 * Issue #754: Added ARIA roles for tabs, dialogs, status indicators,
 * aria-labels for icon-only buttons, and role="dialog" for modals.
 */

import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useFleetStore } from '@/stores/fleet'
import { useSlmApi } from '@/composables/useSlmApi'
import { useSlmWebSocket } from '@/composables/useSlmWebSocket'
import { useNodeConnectionTest } from '@/composables/useNodeConnectionTest'

import type { SLMNode, NodeHealth } from '@/types/slm'
import { createLogger } from '@/utils/debugUtils'
import NodeCard from '@/components/fleet/NodeCard.vue'
import FleetSummary from '@/components/fleet/FleetSummary.vue'
import AddNodeModal from '@/components/AddNodeModal.vue'
import NodeLifecyclePanel from '@/components/fleet/NodeLifecyclePanel.vue'
import NodeServicesPanel from '@/components/fleet/NodeServicesPanel.vue'
import NPUWorkersTab from '@/components/fleet/NPUWorkersTab.vue'
import RoleManagementModal from '@/components/RoleManagementModal.vue'
import InfrastructureView from '@/views/InfrastructureView.vue'

const logger = createLogger('FleetOverview')
const fleetStore = useFleetStore()
const slmApi = useSlmApi()
const route = useRoute()
const router = useRouter()

// Connection test composable (Issue #737)
const connectionTest = useNodeConnectionTest()

// WebSocket for real-time updates
const ws = useSlmWebSocket()

// Tab management — route-based
type FleetTab = 'nodes' | 'npu' | 'infrastructure'

function resolveTab(param: unknown): FleetTab {
  const valid: FleetTab[] = ['nodes', 'npu', 'infrastructure']
  return valid.includes(param as FleetTab) ? (param as FleetTab) : 'nodes'
}

const activeTab = computed(() => resolveTab(route.params.tab))

function navigateToTab(tab: FleetTab): void {
  router.push({ name: 'fleet', params: { tab } })
}

watch(() => route.params.tab, (tab) => {
  if (!tab) router.replace({ name: 'fleet', params: { tab: 'nodes' } })
})

// Computed
const nodes = computed(() => fleetStore.nodeList)
const isLoading = computed(() => fleetStore.isLoading)

// Modal states
const showAddNodeModal = ref(false)
const showDeleteConfirm = ref(false)
const showRoleModal = ref(false)
const showLifecyclePanel = ref(false)
const showServicesPanel = ref(false)
const showConnectionTestResult = ref(false)

// Selected node for actions
const selectedNode = ref<SLMNode | null>(null)
const editingNode = ref<SLMNode | null>(null)

// Selected node for role management modal (Issue #779)
const selectedNodeForRoles = ref<{ id: string; hostname: string } | null>(null)

// Action states
const isDeleting = ref(false)
const isEnrolling = ref(false)

// Connection test state from composable (Issue #737)
const connectionTestResult = computed(() => connectionTest.result.value)

// Lifecycle
onMounted(async () => {
  await refreshFleet()
  fleetStore.fetchFleetUpdateSummary()
  ws.connect()

  watch(() => ws.connected.value, (connected) => {
    if (connected) {
      ws.subscribeAll()
      logger.info('WebSocket connected, subscribed to all nodes')
    }
  }, { immediate: true })

  registerWsHandlers()
})

/**
 * Register all WebSocket event handlers.
 *
 * Helper for FleetOverview onMounted (Issue #754 refactor).
 */
function registerWsHandlers(): void {
  ws.onHealthUpdate((nodeId: string, health: NodeHealth) => {
    logger.debug('WebSocket health update:', nodeId, health)
    fleetStore.updateNodeHealth(nodeId, health)
  })

  ws.onNodeStatus((nodeId: string, status: string) => {
    logger.debug('WebSocket node status:', nodeId, status)
    fleetStore.updateNodeStatus(nodeId, status)
  })

  ws.onRemediationEvent((nodeId: string, event) => {
    logger.info('Remediation event:', nodeId, event)
    if (event.event_type === 'completed') {
      fleetStore.refreshNode(nodeId).catch(err => {
        logger.error('Failed to refresh node after remediation:', err)
      })
    }
  })

  ws.onServiceStatus((nodeId: string, data) => {
    logger.debug('Service status update:', nodeId, data)
  })

  ws.onBackupStatus((nodeId: string, backup) => {
    logger.info('Backup status update:', nodeId, backup)
    if (backup.status === 'completed') {
      logger.info(`Backup completed for node ${nodeId}`)
    } else if (backup.status === 'failed') {
      logger.error(`Backup failed for node ${nodeId}:`, backup.error)
    }
  })

  ws.onDeploymentStatus((nodeId: string, deployment) => {
    logger.info('Deployment status update:', nodeId, deployment)
    if (deployment.status === 'completed' || deployment.status === 'failed') {
      fleetStore.refreshNode(nodeId).catch(err => {
        logger.error('Failed to refresh node after deployment:', err)
      })
    }
  })

  ws.onRollbackEvent((nodeId: string, data) => {
    logger.info('Rollback event:', nodeId, data)
    if (data.event_type === 'completed') {
      fleetStore.refreshNode(nodeId).catch(err => {
        logger.error('Failed to refresh node after rollback:', err)
      })
    }
  })
}

onUnmounted(() => {
  ws.disconnect()
})

// Actions
async function refreshFleet(): Promise<void> {
  try {
    await fleetStore.fetchNodes()
  } catch (err) {
    logger.error('Failed to refresh fleet:', err)
  }
}

function handleNodeAction(action: string, nodeId: string): void {
  const node = fleetStore.getNode(nodeId)
  if (!node) return

  selectedNode.value = node

  switch (action) {
    case 'edit':
      openEditModal(node)
      break
    case 'delete':
      openDeleteConfirm()
      break
    case 'enroll':
      handleEnroll(nodeId)
      break
    case 'test':
      handleTestConnection(nodeId)
      break
    case 'roles':
      openRoleModal(node)
      break
    case 'events':
    case 'view':
    case 'certificate':
    case 'updates':
      openLifecyclePanel(node)
      break
    case 'services':
      openServicesPanel(node)
      break
    case 'restart':
      handleRestart(nodeId)
      break
    default:
      logger.warn('Unknown action:', action)
  }
}

function openAddNodeModal(): void {
  editingNode.value = null
  showAddNodeModal.value = true
}

function openEditModal(node: SLMNode): void {
  editingNode.value = node
  showAddNodeModal.value = true
}

function closeAddNodeModal(): void {
  showAddNodeModal.value = false
  editingNode.value = null
}

async function handleNodeSaved(): Promise<void> {
  closeAddNodeModal()
  await refreshFleet()
}

function openDeleteConfirm(): void {
  showDeleteConfirm.value = true
}

function closeDeleteConfirm(): void {
  showDeleteConfirm.value = false
  selectedNode.value = null
}

async function confirmDelete(): Promise<void> {
  if (!selectedNode.value) return

  isDeleting.value = true
  try {
    await fleetStore.deleteNode(selectedNode.value.node_id)
    closeDeleteConfirm()
  } catch (err) {
    logger.error('Failed to delete node:', err)
  } finally {
    isDeleting.value = false
  }
}

async function handleEnroll(nodeId: string): Promise<void> {
  isEnrolling.value = true
  try {
    await fleetStore.enrollNode(nodeId)
  } catch (err) {
    logger.error('Failed to enroll node:', err)
  } finally {
    isEnrolling.value = false
  }
}

async function handleTestConnection(nodeId: string): Promise<void> {
  connectionTest.reset()
  await connectionTest.testByNodeId(nodeId)
  showConnectionTestResult.value = true
}

function closeConnectionTestResult(): void {
  showConnectionTestResult.value = false
  connectionTest.reset()
}

function openRoleModal(node: SLMNode): void {
  selectedNodeForRoles.value = { id: node.node_id, hostname: node.hostname }
  showRoleModal.value = true
}

function closeRoleModal(): void {
  showRoleModal.value = false
  selectedNodeForRoles.value = null
}

function openLifecyclePanel(node: SLMNode): void {
  selectedNode.value = node
  showLifecyclePanel.value = true
}

function closeLifecyclePanel(): void {
  showLifecyclePanel.value = false
}

function openServicesPanel(node: SLMNode): void {
  selectedNode.value = node
  showServicesPanel.value = true
}

function closeServicesPanel(): void {
  showServicesPanel.value = false
}

const isRestarting = ref(false)

async function handleRestart(nodeId: string): Promise<void> {
  const node = fleetStore.getNode(nodeId)
  const hostname = node?.hostname || nodeId
  if (!confirm(`Reboot node "${hostname}"? The node will go offline temporarily.`)) {
    return
  }

  isRestarting.value = true
  try {
    const result = await slmApi.rebootNode(nodeId)
    logger.info('Reboot initiated:', result.message)
    fleetStore.updateNodeStatus(nodeId, 'rebooting')
  } catch (err) {
    logger.error('Failed to reboot node:', err)
    alert(`Failed to reboot node: ${err instanceof Error ? err.message : 'Unknown error'}`)
  } finally {
    isRestarting.value = false
  }
}
</script>

<template>
  <div class="p-6">
    <!-- Header -->
    <div class="flex items-center justify-between mb-6">
      <div>
        <h1 class="text-2xl font-bold text-gray-900">Fleet Overview</h1>
        <p class="text-sm text-gray-500 mt-1 flex items-center gap-2">
          Real-time health status of all managed nodes
          <!-- WebSocket Connection Indicator (Issue #754: aria) -->
          <span
            role="status"
            :aria-label="`WebSocket: ${ws.connected.value ? 'Connected' : ws.reconnecting.value ? 'Reconnecting' : 'Disconnected'}`"
            class="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs font-medium"
            :class="ws.connected.value
              ? 'bg-green-100 text-green-800'
              : ws.reconnecting.value
                ? 'bg-yellow-100 text-yellow-800'
                : 'bg-red-100 text-red-800'"
          >
            <span
              class="w-1.5 h-1.5 rounded-full"
              aria-hidden="true"
              :class="ws.connected.value
                ? 'bg-green-500'
                : ws.reconnecting.value
                  ? 'bg-yellow-500 animate-pulse'
                  : 'bg-red-500'"
            ></span>
            {{ ws.connected.value ? 'Live' : ws.reconnecting.value ? 'Reconnecting' : 'Disconnected' }}
          </span>
        </p>
      </div>
      <div class="flex items-center gap-3">
        <button
          @click="refreshFleet"
          :disabled="isLoading"
          aria-label="Refresh fleet data"
          class="btn btn-secondary flex items-center gap-2"
        >
          <svg :class="['w-4 h-4', isLoading ? 'animate-spin' : '']" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
          </svg>
          Refresh
        </button>
        <button
          v-if="activeTab === 'nodes'"
          @click="openAddNodeModal"
          aria-label="Add new node to fleet"
          class="btn btn-primary flex items-center gap-2"
        >
          <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4" />
          </svg>
          Add Node
        </button>
      </div>
    </div>

    <!-- Tabs (Issue #754: ARIA tablist) -->
    <div class="border-b border-gray-200 mb-6">
      <nav class="-mb-px flex space-x-8" role="tablist" aria-label="Fleet view tabs">
        <button
          @click="navigateToTab('nodes')"
          role="tab"
          :aria-selected="activeTab === 'nodes'"
          aria-controls="tabpanel-nodes"
          :class="[
            'whitespace-nowrap pb-4 px-1 border-b-2 font-medium text-sm transition-colors',
            activeTab === 'nodes'
              ? 'border-primary-500 text-primary-600'
              : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
          ]"
        >
          <div class="flex items-center gap-2">
            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 12h14M5 12a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v4a2 2 0 01-2 2M5 12a2 2 0 00-2 2v4a2 2 0 002 2h14a2 2 0 002-2v-4a2 2 0 00-2-2" />
            </svg>
            Nodes
          </div>
        </button>
        <button
          @click="navigateToTab('npu')"
          role="tab"
          :aria-selected="activeTab === 'npu'"
          aria-controls="tabpanel-npu"
          :class="[
            'whitespace-nowrap pb-4 px-1 border-b-2 font-medium text-sm transition-colors',
            activeTab === 'npu'
              ? 'border-primary-500 text-primary-600'
              : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
          ]"
        >
          <div class="flex items-center gap-2">
            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 3v2m6-2v2M9 19v2m6-2v2M5 9H3m2 6H3m18-6h-2m2 6h-2M7 19h10a2 2 0 002-2V7a2 2 0 00-2-2H7a2 2 0 00-2 2v10a2 2 0 002 2zM9 9h6v6H9V9z" />
            </svg>
            NPU Workers
          </div>
        </button>
        <button
          @click="navigateToTab('infrastructure')"
          role="tab"
          :aria-selected="activeTab === 'infrastructure'"
          aria-controls="tabpanel-infrastructure"
          :class="[
            'whitespace-nowrap pb-4 px-1 border-b-2 font-medium text-sm transition-colors',
            activeTab === 'infrastructure'
              ? 'border-primary-500 text-primary-600'
              : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
          ]"
        >
          <div class="flex items-center gap-2">
            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19.428 15.428a2 2 0 00-1.022-.547l-2.387-.477a6 6 0 00-3.86.517l-.318.158a6 6 0 01-3.86.517L6.05 15.21a2 2 0 00-1.806.547M8 4h8l-1 1v5.172a2 2 0 00.586 1.414l5 5c1.26 1.26.367 3.414-1.415 3.414H4.828c-1.782 0-2.674-2.154-1.414-3.414l5-5A2 2 0 009 10.172V5L8 4z" />
            </svg>
            Infrastructure
          </div>
        </button>
      </nav>
    </div>

    <!-- Nodes Tab Content -->
    <div v-show="activeTab === 'nodes'" id="tabpanel-nodes" role="tabpanel" aria-label="Nodes overview">
      <FleetSummary class="mb-6" />

      <!-- Node Grid -->
      <div v-if="nodes.length > 0" class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4" role="list" aria-label="Fleet nodes">
        <NodeCard
          v-for="node in nodes"
          :key="node.node_id"
          :node="node"
          @action="handleNodeAction"
        />
      </div>

      <!-- Empty State -->
      <div v-else-if="!isLoading" class="card p-12 text-center">
        <svg class="w-16 h-16 mx-auto text-gray-400 mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 12h14M5 12a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v4a2 2 0 01-2 2M5 12a2 2 0 00-2 2v4a2 2 0 002 2h14a2 2 0 002-2v-4a2 2 0 00-2-2m-2-4h.01M17 16h.01" />
        </svg>
        <h3 class="text-lg font-medium text-gray-900 mb-2">No nodes registered</h3>
        <p class="text-gray-500 mb-4">Add a node to start managing your infrastructure.</p>
        <button @click="openAddNodeModal" class="btn btn-primary">Add First Node</button>
      </div>

      <!-- Loading State -->
      <div v-if="isLoading && nodes.length === 0" class="flex items-center justify-center py-12" role="status" aria-label="Loading fleet data">
        <div class="animate-spin w-8 h-8 border-4 border-primary-600 border-t-transparent rounded-full"></div>
        <span class="sr-only">Loading fleet data...</span>
      </div>
    </div>

    <!-- NPU Workers Tab Content -->
    <div v-show="activeTab === 'npu'" id="tabpanel-npu" role="tabpanel" aria-label="NPU workers">
      <NPUWorkersTab />
    </div>

    <!-- Infrastructure Tab Content -->
    <div v-show="activeTab === 'infrastructure'" id="tabpanel-infrastructure" role="tabpanel" aria-label="Infrastructure setup">
      <InfrastructureView />
    </div>

    <!-- Add/Edit Node Modal -->
    <AddNodeModal
      :visible="showAddNodeModal"
      :mode="editingNode ? 'edit' : 'add'"
      :existing-node="(editingNode as any)"
      @close="closeAddNodeModal"
      @added="handleNodeSaved"
      @updated="handleNodeSaved"
    />

    <!-- Delete Confirmation Modal (Issue #754: role=dialog) -->
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
          v-if="showDeleteConfirm"
          class="fixed inset-0 z-50 flex items-center justify-center p-4"
          role="dialog"
          aria-modal="true"
          aria-labelledby="delete-dialog-title"
          @keydown.escape="closeDeleteConfirm"
        >
          <div class="fixed inset-0 bg-gray-500 bg-opacity-75" @click="closeDeleteConfirm"></div>
          <div class="relative bg-white rounded-lg shadow-xl max-w-md w-full p-6">
            <div class="flex items-center gap-4 mb-4">
              <div class="flex-shrink-0 w-12 h-12 rounded-full bg-red-100 flex items-center justify-center" aria-hidden="true">
                <svg class="w-6 h-6 text-red-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                </svg>
              </div>
              <div>
                <h3 id="delete-dialog-title" class="text-lg font-semibold text-gray-900">Delete Node</h3>
                <p class="text-sm text-gray-500">This action cannot be undone.</p>
              </div>
            </div>
            <p class="text-gray-700 mb-6">
              Are you sure you want to delete
              <span class="font-medium">{{ selectedNode?.hostname }}</span>?
              All associated data will be permanently removed.
            </p>
            <div class="flex justify-end gap-3">
              <button @click="closeDeleteConfirm" :disabled="isDeleting" class="btn btn-secondary">Cancel</button>
              <button @click="confirmDelete" :disabled="isDeleting" class="btn bg-red-600 text-white hover:bg-red-700 disabled:opacity-50">
                {{ isDeleting ? 'Deleting...' : 'Delete Node' }}
              </button>
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>

    <!-- Role Management Modal (Issue #779) -->
    <RoleManagementModal
      v-if="showRoleModal && selectedNodeForRoles"
      :node-id="selectedNodeForRoles.id"
      :hostname="selectedNodeForRoles.hostname"
      @close="closeRoleModal"
      @saved="refreshFleet"
    />

    <!-- Connection Test Result Modal (Issue #754: role=dialog) -->
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
          v-if="showConnectionTestResult"
          class="fixed inset-0 z-50 flex items-center justify-center p-4"
          role="dialog"
          aria-modal="true"
          aria-label="Connection test result"
          @keydown.escape="closeConnectionTestResult"
        >
          <div class="fixed inset-0 bg-gray-500 bg-opacity-75" @click="closeConnectionTestResult"></div>
          <div class="relative bg-white rounded-lg shadow-xl max-w-md w-full p-6">
            <div class="flex items-center gap-4 mb-4">
              <div
                class="flex-shrink-0 w-12 h-12 rounded-full flex items-center justify-center"
                :class="connectionTestResult?.success ? 'bg-green-100' : 'bg-red-100'"
                aria-hidden="true"
              >
                <svg v-if="connectionTestResult?.success" class="w-6 h-6 text-green-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" />
                </svg>
                <svg v-else class="w-6 h-6 text-red-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </div>
              <div>
                <h3 class="text-lg font-semibold text-gray-900">
                  {{ connectionTestResult?.success ? 'Connection Successful' : 'Connection Failed' }}
                </h3>
                <p class="text-sm text-gray-500">{{ selectedNode?.hostname }}</p>
              </div>
            </div>
            <div v-if="connectionTestResult?.success" class="space-y-2 mb-6">
              <div v-if="connectionTestResult.latency_ms" class="flex justify-between text-sm">
                <span class="text-gray-500">Latency:</span>
                <span class="font-medium">{{ connectionTestResult.latency_ms }}ms</span>
              </div>
              <div v-if="connectionTestResult.message" class="text-sm text-gray-700">
                {{ connectionTestResult.message }}
              </div>
            </div>
            <div v-else class="mb-6">
              <p class="text-sm text-red-600" role="alert">
                {{ connectionTestResult?.error || 'Failed to connect to node' }}
              </p>
            </div>
            <div class="flex justify-end">
              <button @click="closeConnectionTestResult" class="btn btn-primary">Close</button>
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>

    <!-- Lifecycle Panel Slide-over (Issue #754: role=dialog) -->
    <Teleport to="body">
      <Transition
        enter-active-class="transition duration-300 ease-out"
        enter-from-class="opacity-0"
        enter-to-class="opacity-100"
        leave-active-class="transition duration-200 ease-in"
        leave-from-class="opacity-100"
        leave-to-class="opacity-0"
      >
        <div
          v-if="showLifecyclePanel"
          class="fixed inset-0 z-50 overflow-hidden"
          role="dialog"
          aria-modal="true"
          aria-label="Node details panel"
          @keydown.escape="closeLifecyclePanel"
        >
          <div class="fixed inset-0 bg-gray-500 bg-opacity-75" @click="closeLifecyclePanel"></div>
          <div class="fixed inset-y-0 right-0 flex max-w-full pl-10">
            <Transition
              enter-active-class="transform transition duration-300 ease-out"
              enter-from-class="translate-x-full"
              enter-to-class="translate-x-0"
              leave-active-class="transform transition duration-200 ease-in"
              leave-from-class="translate-x-0"
              leave-to-class="translate-x-full"
            >
              <div v-if="showLifecyclePanel" class="w-screen max-w-2xl">
                <div class="h-full flex flex-col bg-white shadow-xl">
                  <div class="flex items-center justify-between px-6 py-4 border-b border-gray-200">
                    <div>
                      <h2 class="text-lg font-semibold text-gray-900">Node Details</h2>
                      <p class="text-sm text-gray-500">{{ selectedNode?.hostname }}</p>
                    </div>
                    <button @click="closeLifecyclePanel" aria-label="Close node details panel" class="rounded-md text-gray-400 hover:text-gray-600">
                      <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
                      </svg>
                    </button>
                  </div>
                  <div class="flex-1 overflow-y-auto">
                    <NodeLifecyclePanel v-if="selectedNode" :node-id="selectedNode.node_id" @close="closeLifecyclePanel" />
                  </div>
                </div>
              </div>
            </Transition>
          </div>
        </div>
      </Transition>
    </Teleport>

    <!-- Services Panel Slide-over (Issue #754: role=dialog) -->
    <Teleport to="body">
      <Transition
        enter-active-class="transition duration-300 ease-out"
        enter-from-class="opacity-0"
        enter-to-class="opacity-100"
        leave-active-class="transition duration-200 ease-in"
        leave-from-class="opacity-100"
        leave-to-class="opacity-0"
      >
        <div
          v-if="showServicesPanel"
          class="fixed inset-0 z-50 overflow-hidden"
          role="dialog"
          aria-modal="true"
          aria-label="Node services panel"
          @keydown.escape="closeServicesPanel"
        >
          <div class="fixed inset-0 bg-gray-500 bg-opacity-75" @click="closeServicesPanel"></div>
          <div class="fixed inset-y-0 right-0 flex max-w-full pl-10">
            <Transition
              enter-active-class="transform transition duration-300 ease-out"
              enter-from-class="translate-x-full"
              enter-to-class="translate-x-0"
              leave-active-class="transform transition duration-200 ease-in"
              leave-from-class="translate-x-0"
              leave-to-class="translate-x-full"
            >
              <div v-if="showServicesPanel" class="w-screen max-w-3xl">
                <div class="h-full flex flex-col bg-white shadow-xl">
                  <div class="flex items-center justify-between px-6 py-4 border-b border-gray-200">
                    <div>
                      <h2 class="text-lg font-semibold text-gray-900">Services</h2>
                      <p class="text-sm text-gray-500">{{ selectedNode?.hostname }}</p>
                    </div>
                    <button @click="closeServicesPanel" aria-label="Close services panel" class="rounded-md text-gray-400 hover:text-gray-600">
                      <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
                      </svg>
                    </button>
                  </div>
                  <div class="flex-1 overflow-y-auto">
                    <NodeServicesPanel v-if="selectedNode" :node-id="selectedNode.node_id" :node-name="selectedNode.hostname" @close="closeServicesPanel" />
                  </div>
                </div>
              </div>
            </Transition>
          </div>
        </div>
      </Transition>
    </Teleport>
  </div>
</template>
