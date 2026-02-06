<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * Replication Management View
 *
 * Manages Redis replication between nodes with Ansible orchestration (Issue #726 Phase 4).
 */

import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useSlmApi } from '@/composables/useSlmApi'
import { useSlmWebSocket } from '@/composables/useSlmWebSocket'
import { useFleetStore } from '@/stores/fleet'
import { createLogger } from '@/utils/debugUtils'
import type { Replication, ReplicationRequest } from '@/types/slm'

const logger = createLogger('ReplicationView')
const api = useSlmApi()
const ws = useSlmWebSocket()
const fleetStore = useFleetStore()

// State
const replications = ref<Replication[]>([])
const isLoading = ref(false)
const showCreateDialog = ref(false)
const isCreating = ref(false)
const selectedReplication = ref<Replication | null>(null)
const showDetailsModal = ref(false)
const syncVerifyResult = ref<{
  is_healthy: boolean
  checks: Array<{ name: string; status: string; message: string }>
  details: Record<string, unknown>
} | null>(null)
const isVerifying = ref(false)

// New replication form
const newReplication = ref<ReplicationRequest>({
  source_node_id: '',
  target_node_id: '',
  service_type: 'redis',
})

// Summary stats
const stats = computed(() => ({
  total: replications.value.length,
  active: replications.value.filter(r => r.status === 'active').length,
  syncing: replications.value.filter(r => r.status === 'syncing').length,
  pending: replications.value.filter(r => r.status === 'pending').length,
  failed: replications.value.filter(r => r.status === 'failed').length,
}))

// Filter nodes that have Redis role
const redisNodes = computed(() =>
  fleetStore.nodeList
    .filter(node => node.roles.includes('redis'))
    .map(node => ({
      value: node.node_id,
      label: `${node.hostname} (${node.ip_address})`,
      status: node.status,
    }))
)

// Available target nodes (exclude source)
const availableTargets = computed(() =>
  redisNodes.value.filter(n => n.value !== newReplication.value.source_node_id)
)

onMounted(async () => {
  await Promise.all([
    fetchReplications(),
    fleetStore.fetchNodes(),
  ])

  // Connect to WebSocket for real-time updates
  ws.connect()
  ws.subscribeAll()

  ws.onBackupStatus(() => {
    // Replication status updates come through this channel
    fetchReplications()
  })
})

onUnmounted(() => {
  ws.disconnect()
})

async function fetchReplications(): Promise<void> {
  isLoading.value = true
  try {
    replications.value = await api.getReplications()
  } catch (err) {
    logger.error('Failed to fetch replications:', err)
  } finally {
    isLoading.value = false
  }
}

async function handleCreateReplication(): Promise<void> {
  if (!newReplication.value.source_node_id || !newReplication.value.target_node_id) {
    return
  }

  isCreating.value = true
  try {
    await api.startReplication(newReplication.value)
    showCreateDialog.value = false
    resetForm()
    await fetchReplications()
  } catch (err) {
    logger.error('Failed to start replication:', err)
    alert('Failed to start replication')
  } finally {
    isCreating.value = false
  }
}

async function handlePromote(replicationId: string): Promise<void> {
  if (!confirm('Are you sure you want to promote this replica to primary? This will make the target node a standalone master.')) {
    return
  }

  try {
    await api.promoteReplica(replicationId)
    await fetchReplications()
  } catch (err) {
    logger.error('Failed to promote replica:', err)
    alert('Failed to promote replica')
  }
}

async function handleStop(replicationId: string): Promise<void> {
  if (!confirm('Are you sure you want to stop this replication? The replica will remain connected but replication link will be marked as stopped.')) {
    return
  }

  try {
    await api.stopReplication(replicationId)
    await fetchReplications()
  } catch (err) {
    logger.error('Failed to stop replication:', err)
    alert('Failed to stop replication')
  }
}

async function handleVerifySync(replication: Replication): Promise<void> {
  selectedReplication.value = replication
  showDetailsModal.value = true
  isVerifying.value = true
  syncVerifyResult.value = null

  try {
    syncVerifyResult.value = await api.verifyReplicationSync(replication.replication_id)
  } catch (err) {
    logger.error('Failed to verify sync:', err)
    syncVerifyResult.value = {
      is_healthy: false,
      checks: [{ name: 'verification', status: 'failed', message: String(err) }],
      details: {},
    }
  } finally {
    isVerifying.value = false
  }
}

function resetForm(): void {
  newReplication.value = {
    source_node_id: '',
    target_node_id: '',
    service_type: 'redis',
  }
}

function showDetails(replication: Replication): void {
  selectedReplication.value = replication
  syncVerifyResult.value = null
  showDetailsModal.value = true
}

function closeDetails(): void {
  showDetailsModal.value = false
  selectedReplication.value = null
  syncVerifyResult.value = null
}

function getStatusClass(status: string): string {
  switch (status) {
    case 'active': return 'bg-green-100 text-green-800'
    case 'syncing': return 'bg-blue-100 text-blue-800'
    case 'pending': return 'bg-yellow-100 text-yellow-800'
    case 'failed': return 'bg-red-100 text-red-800'
    case 'stopped': return 'bg-gray-100 text-gray-800'
    default: return 'bg-gray-100 text-gray-800'
  }
}

function formatDateTime(isoString: string | null): string {
  if (!isoString) return '-'
  return new Date(isoString).toLocaleString()
}

function formatLag(lagBytes: number): string {
  if (lagBytes === 0) return '0 B (in sync)'
  if (lagBytes < 1024) return `${lagBytes} B`
  if (lagBytes < 1024 * 1024) return `${(lagBytes / 1024).toFixed(1)} KB`
  return `${(lagBytes / (1024 * 1024)).toFixed(2)} MB`
}

function getNodeHostname(nodeId: string): string {
  const node = fleetStore.getNode(nodeId)
  return node?.hostname || nodeId
}
</script>

<template>
  <div class="p-6">
    <!-- Header -->
    <div class="flex items-center justify-between mb-6">
      <div>
        <h1 class="text-2xl font-bold text-gray-900">Redis Replication</h1>
        <p class="text-sm text-gray-500 mt-1">
          Manage Redis master-replica replication with Ansible orchestration
        </p>
      </div>
      <div class="flex items-center gap-3">
        <button
          @click="fetchReplications"
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
          :disabled="redisNodes.length < 2"
          class="btn btn-primary flex items-center gap-2"
        >
          <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4" />
          </svg>
          New Replication
        </button>
      </div>
    </div>

    <!-- Warning if less than 2 Redis nodes -->
    <div v-if="redisNodes.length < 2" class="mb-6 p-4 bg-yellow-50 border border-yellow-200 rounded-lg">
      <div class="flex items-center gap-3">
        <svg class="w-5 h-5 text-yellow-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
        </svg>
        <p class="text-sm text-yellow-700">
          At least 2 nodes with the Redis role are required to set up replication.
          Currently {{ redisNodes.length }} Redis node(s) available.
        </p>
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
            <p class="text-2xl font-bold text-green-600">{{ stats.active }}</p>
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
            <p class="text-sm text-gray-500">Syncing</p>
            <p class="text-2xl font-bold text-blue-600">{{ stats.syncing }}</p>
          </div>
          <div class="w-10 h-10 rounded-full bg-blue-100 flex items-center justify-center">
            <svg class="w-5 h-5 text-blue-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
            </svg>
          </div>
        </div>
      </div>

      <div class="card p-4">
        <div class="flex items-center justify-between">
          <div>
            <p class="text-sm text-gray-500">Pending</p>
            <p class="text-2xl font-bold text-yellow-600">{{ stats.pending }}</p>
          </div>
          <div class="w-10 h-10 rounded-full bg-yellow-100 flex items-center justify-center">
            <svg class="w-5 h-5 text-yellow-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
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
    </div>

    <!-- Replications Table -->
    <div class="card overflow-hidden">
      <div class="px-6 py-4 border-b border-gray-200">
        <h2 class="text-lg font-semibold">Replication Links</h2>
      </div>
      <div class="overflow-x-auto">
        <table class="min-w-full divide-y divide-gray-200">
          <thead class="bg-gray-50">
            <tr>
              <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Status</th>
              <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Source (Primary)</th>
              <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Target (Replica)</th>
              <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Service</th>
              <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Lag</th>
              <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Started</th>
              <th class="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase">Actions</th>
            </tr>
          </thead>
          <tbody class="bg-white divide-y divide-gray-200">
            <tr v-for="replication in replications" :key="replication.replication_id" class="hover:bg-gray-50">
              <td class="px-6 py-4 whitespace-nowrap">
                <span :class="['px-2 py-1 text-xs font-medium rounded-full', getStatusClass(replication.status)]">
                  {{ replication.status }}
                </span>
              </td>
              <td class="px-6 py-4 whitespace-nowrap">
                <div class="flex items-center gap-2">
                  <div class="w-3 h-3 rounded-full bg-purple-500" title="Primary"></div>
                  <span class="text-sm font-medium text-gray-900">{{ getNodeHostname(replication.source_node_id) }}</span>
                </div>
              </td>
              <td class="px-6 py-4 whitespace-nowrap">
                <div class="flex items-center gap-2">
                  <div class="w-3 h-3 rounded-full bg-cyan-500" title="Replica"></div>
                  <span class="text-sm font-medium text-gray-900">{{ getNodeHostname(replication.target_node_id) }}</span>
                </div>
              </td>
              <td class="px-6 py-4 whitespace-nowrap">
                <span class="px-2 py-0.5 text-xs font-medium bg-red-100 text-red-700 rounded">
                  {{ replication.service_type }}
                </span>
              </td>
              <td class="px-6 py-4 whitespace-nowrap">
                <span :class="[
                  'text-sm',
                  replication.lag_bytes === 0 ? 'text-green-600' :
                  replication.lag_bytes < 1024 * 1024 ? 'text-yellow-600' : 'text-red-600'
                ]">
                  {{ formatLag(replication.lag_bytes) }}
                </span>
              </td>
              <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                {{ formatDateTime(replication.started_at) }}
              </td>
              <td class="px-6 py-4 whitespace-nowrap text-right">
                <div class="flex items-center justify-end gap-2">
                  <!-- Verify Sync -->
                  <button
                    @click="handleVerifySync(replication)"
                    class="text-blue-600 hover:text-blue-800"
                    title="Verify sync status"
                  >
                    <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                    </svg>
                  </button>

                  <!-- View Details -->
                  <button
                    @click="showDetails(replication)"
                    class="text-gray-600 hover:text-gray-800"
                    title="View details"
                  >
                    <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
                    </svg>
                  </button>

                  <!-- Promote Replica (when active) -->
                  <button
                    v-if="replication.status === 'active'"
                    @click="handlePromote(replication.replication_id)"
                    class="text-green-600 hover:text-green-800"
                    title="Promote to primary"
                  >
                    <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 10l7-7m0 0l7 7m-7-7v18" />
                    </svg>
                  </button>

                  <!-- Stop Replication (when active/syncing) -->
                  <button
                    v-if="['active', 'syncing'].includes(replication.status)"
                    @click="handleStop(replication.replication_id)"
                    class="text-red-600 hover:text-red-800"
                    title="Stop replication"
                  >
                    <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 10a1 1 0 011-1h4a1 1 0 011 1v4a1 1 0 01-1 1h-4a1 1 0 01-1-1v-4z" />
                    </svg>
                  </button>
                </div>
              </td>
            </tr>
            <tr v-if="replications.length === 0 && !isLoading">
              <td colspan="7" class="px-6 py-12 text-center text-gray-500">
                <svg class="w-12 h-12 mx-auto text-gray-400 mb-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 7h12m0 0l-4-4m4 4l-4 4m0 6H4m0 0l4 4m-4-4l4-4" />
                </svg>
                <p>No replications configured yet. Click "New Replication" to set up master-replica replication.</p>
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
      <div class="bg-white rounded-lg shadow-xl max-w-lg w-full mx-4">
        <div class="px-6 py-4 border-b border-gray-200">
          <h3 class="text-lg font-semibold text-gray-900">New Replication</h3>
          <p class="text-sm text-gray-500 mt-1">
            Set up Redis master-replica replication using Ansible
          </p>
        </div>
        <div class="px-6 py-4 space-y-4">
          <!-- Source Node Selection -->
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">
              <span class="flex items-center gap-2">
                <div class="w-3 h-3 rounded-full bg-purple-500"></div>
                Source Node (Primary/Master)
              </span>
            </label>
            <select
              v-model="newReplication.source_node_id"
              class="w-full px-3 py-2 border border-gray-300 rounded-md focus:ring-primary-500 focus:border-primary-500"
            >
              <option value="">Select primary node...</option>
              <option v-for="opt in redisNodes" :key="opt.value" :value="opt.value">
                {{ opt.label }} - {{ opt.status }}
              </option>
            </select>
          </div>

          <!-- Target Node Selection -->
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">
              <span class="flex items-center gap-2">
                <div class="w-3 h-3 rounded-full bg-cyan-500"></div>
                Target Node (Replica)
              </span>
            </label>
            <select
              v-model="newReplication.target_node_id"
              :disabled="!newReplication.source_node_id"
              class="w-full px-3 py-2 border border-gray-300 rounded-md focus:ring-primary-500 focus:border-primary-500 disabled:bg-gray-100"
            >
              <option value="">Select replica node...</option>
              <option v-for="opt in availableTargets" :key="opt.value" :value="opt.value">
                {{ opt.label }} - {{ opt.status }}
              </option>
            </select>
          </div>

          <!-- Service Type -->
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">Service Type</label>
            <select
              v-model="newReplication.service_type"
              class="w-full px-3 py-2 border border-gray-300 rounded-md focus:ring-primary-500 focus:border-primary-500"
            >
              <option value="redis">Redis</option>
            </select>
            <p class="text-xs text-gray-500 mt-1">Currently only Redis replication is supported</p>
          </div>

          <!-- Info Box -->
          <div class="bg-blue-50 border border-blue-200 rounded-md p-3">
            <p class="text-sm text-blue-700">
              This will configure the target node as a replica of the source using the
              <code class="bg-blue-100 px-1 rounded">REPLICAOF</code> command via Ansible.
              The replica will sync all data from the primary and stay in read-only mode.
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
            @click="handleCreateReplication"
            :disabled="!newReplication.source_node_id || !newReplication.target_node_id || isCreating"
            class="px-4 py-2 text-sm font-medium text-white bg-primary-600 rounded-md hover:bg-primary-700 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
          >
            <div v-if="isCreating" class="animate-spin w-4 h-4 border-2 border-white border-t-transparent rounded-full"></div>
            Start Replication
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
          v-if="showDetailsModal && selectedReplication"
          class="fixed inset-0 z-50 flex items-center justify-center p-4"
        >
          <div class="fixed inset-0 bg-gray-500 bg-opacity-75" @click="closeDetails"></div>
          <div class="relative bg-white rounded-lg shadow-xl max-w-2xl w-full max-h-[80vh] overflow-hidden">
            <div class="flex items-center justify-between px-6 py-4 border-b border-gray-200">
              <div class="flex items-center gap-3">
                <h3 class="text-lg font-semibold text-gray-900">Replication Details</h3>
                <span :class="['px-2 py-1 text-xs font-medium rounded-full', getStatusClass(selectedReplication.status)]">
                  {{ selectedReplication.status }}
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
                <div class="p-4 bg-purple-50 rounded-lg">
                  <p class="text-sm font-medium text-purple-800 mb-1">Source (Primary)</p>
                  <p class="text-lg font-semibold text-purple-900">{{ getNodeHostname(selectedReplication.source_node_id) }}</p>
                  <p class="text-xs text-purple-600 mt-1">{{ selectedReplication.source_node_id }}</p>
                </div>
                <div class="p-4 bg-cyan-50 rounded-lg">
                  <p class="text-sm font-medium text-cyan-800 mb-1">Target (Replica)</p>
                  <p class="text-lg font-semibold text-cyan-900">{{ getNodeHostname(selectedReplication.target_node_id) }}</p>
                  <p class="text-xs text-cyan-600 mt-1">{{ selectedReplication.target_node_id }}</p>
                </div>
              </div>

              <!-- Lag & Sync Info -->
              <div class="mb-6 p-4 border border-gray-200 rounded-lg">
                <div class="flex items-center justify-between mb-2">
                  <p class="text-sm font-medium text-gray-700">Replication Lag</p>
                  <span :class="[
                    'text-lg font-bold',
                    selectedReplication.lag_bytes === 0 ? 'text-green-600' :
                    selectedReplication.lag_bytes < 1024 * 1024 ? 'text-yellow-600' : 'text-red-600'
                  ]">
                    {{ formatLag(selectedReplication.lag_bytes) }}
                  </span>
                </div>
                <div v-if="selectedReplication.sync_position" class="text-xs text-gray-500">
                  Sync position: {{ selectedReplication.sync_position }}
                </div>
              </div>

              <!-- Sync Verification Results -->
              <div v-if="isVerifying" class="mb-6 flex items-center justify-center py-8">
                <div class="animate-spin w-8 h-8 border-4 border-primary-600 border-t-transparent rounded-full"></div>
                <span class="ml-3 text-gray-600">Verifying sync status...</span>
              </div>

              <div v-else-if="syncVerifyResult" class="mb-6">
                <div class="flex items-center gap-2 mb-3">
                  <svg
                    :class="['w-5 h-5', syncVerifyResult.is_healthy ? 'text-green-600' : 'text-red-600']"
                    fill="none" stroke="currentColor" viewBox="0 0 24 24"
                  >
                    <path
                      v-if="syncVerifyResult.is_healthy"
                      stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                      d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"
                    />
                    <path
                      v-else
                      stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                      d="M10 14l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2m7-2a9 9 0 11-18 0 9 9 0 0118 0z"
                    />
                  </svg>
                  <p :class="['font-medium', syncVerifyResult.is_healthy ? 'text-green-700' : 'text-red-700']">
                    {{ syncVerifyResult.is_healthy ? 'Replication is healthy and in sync' : 'Replication issues detected' }}
                  </p>
                </div>

                <!-- Checks -->
                <div class="space-y-2">
                  <div
                    v-for="check in syncVerifyResult.checks"
                    :key="check.name"
                    class="flex items-center gap-2 p-2 rounded-md"
                    :class="check.status === 'passed' ? 'bg-green-50' : check.status === 'failed' ? 'bg-red-50' : 'bg-gray-50'"
                  >
                    <svg
                      :class="[
                        'w-4 h-4',
                        check.status === 'passed' ? 'text-green-500' :
                        check.status === 'failed' ? 'text-red-500' : 'text-gray-400'
                      ]"
                      fill="none" stroke="currentColor" viewBox="0 0 24 24"
                    >
                      <path
                        v-if="check.status === 'passed'"
                        stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"
                      />
                      <path
                        v-else-if="check.status === 'failed'"
                        stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"
                      />
                      <path
                        v-else
                        stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4m0 4h.01"
                      />
                    </svg>
                    <span class="text-sm font-medium">{{ check.name }}:</span>
                    <span class="text-sm text-gray-600">{{ check.message }}</span>
                  </div>
                </div>
              </div>

              <!-- Timestamps -->
              <div class="grid grid-cols-2 gap-4 mb-6">
                <div>
                  <p class="text-sm text-gray-500">Created</p>
                  <p class="text-sm font-medium">{{ formatDateTime(selectedReplication.created_at) }}</p>
                </div>
                <div>
                  <p class="text-sm text-gray-500">Started</p>
                  <p class="text-sm font-medium">{{ formatDateTime(selectedReplication.started_at) }}</p>
                </div>
                <div v-if="selectedReplication.completed_at">
                  <p class="text-sm text-gray-500">Completed</p>
                  <p class="text-sm font-medium">{{ formatDateTime(selectedReplication.completed_at) }}</p>
                </div>
              </div>

              <!-- Error -->
              <div v-if="selectedReplication.error" class="mb-6">
                <p class="text-sm text-gray-500 mb-2">Error</p>
                <div class="p-4 bg-red-50 border border-red-200 rounded-lg">
                  <p class="text-sm text-red-800 font-mono whitespace-pre-wrap">{{ selectedReplication.error }}</p>
                </div>
              </div>
            </div>

            <div class="flex justify-end gap-3 px-6 py-4 border-t border-gray-200">
              <button
                @click="handleVerifySync(selectedReplication)"
                :disabled="isVerifying"
                class="btn btn-secondary flex items-center gap-2"
              >
                <div v-if="isVerifying" class="animate-spin w-4 h-4 border-2 border-gray-500 border-t-transparent rounded-full"></div>
                Verify Sync
              </button>
              <button
                v-if="selectedReplication.status === 'active'"
                @click="handlePromote(selectedReplication.replication_id); closeDetails()"
                class="btn bg-green-600 text-white hover:bg-green-700"
              >
                Promote to Primary
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
