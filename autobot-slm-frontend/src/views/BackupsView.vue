<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * Backups & Replications View
 *
 * Manages backups and replications for stateful services (Phase 4 - Issue #726).
 */

import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useSlmApi } from '@/composables/useSlmApi'
import { useFleetStore } from '@/stores/fleet'
import type { Backup, BackupRequest, Replication, ReplicationRequest } from '@/types/slm'

const api = useSlmApi()
const fleetStore = useFleetStore()
const route = useRoute()
const router = useRouter()

// Active tab — route-based
type Tab = 'backups' | 'replications'
function resolveTab(param: unknown): Tab {
  return param === 'replications' ? 'replications' : 'backups'
}
const activeTab = computed(() => resolveTab(route.params.tab))
function navigateToTab(tab: Tab): void {
  router.push({ name: 'backups', params: { tab } })
}

// Backups state
const backups = ref<Backup[]>([])
const isLoadingBackups = ref(false)
const showCreateBackupDialog = ref(false)
const newBackup = ref<BackupRequest>({
  node_id: '',
  service_type: 'redis',
})
const isCreatingBackup = ref(false)

// Replications state
const replications = ref<Replication[]>([])
const isLoadingReplications = ref(false)
const showCreateReplicationDialog = ref(false)
const newReplication = ref<ReplicationRequest>({
  source_node_id: '',
  target_node_id: '',
  service_type: 'redis',
})
const isCreatingReplication = ref(false)

// Node list for dropdowns
const nodeOptions = computed(() =>
  fleetStore.nodeList.map((node) => ({
    value: node.node_id,
    label: `${node.hostname} (${node.ip_address})`,
  }))
)

// Service types
const serviceTypes = ['redis', 'chromadb', 'sqlite']

onMounted(async () => {
  await Promise.all([fetchBackups(), fetchReplications(), fleetStore.fetchNodes()])
})

// =============================================================================
// Backups
// =============================================================================

async function fetchBackups(): Promise<void> {
  isLoadingBackups.value = true
  try {
    backups.value = await api.getBackups()
  } finally {
    isLoadingBackups.value = false
  }
}

async function handleCreateBackup(): Promise<void> {
  if (!newBackup.value.node_id) return

  isCreatingBackup.value = true
  try {
    await api.createBackup(newBackup.value)
    showCreateBackupDialog.value = false
    newBackup.value = { node_id: '', service_type: 'redis' }
    await fetchBackups()
  } finally {
    isCreatingBackup.value = false
  }
}

async function handleRestore(backupId: string): Promise<void> {
  if (
    !confirm(
      'Are you sure you want to restore this backup? This will overwrite current data.'
    )
  ) {
    return
  }

  try {
    await api.restoreBackup(backupId)
    await fetchBackups()
  } catch (e) {
    alert(`Restore failed: ${e instanceof Error ? e.message : 'Unknown error'}`)
  }
}

// =============================================================================
// Replications
// =============================================================================

async function fetchReplications(): Promise<void> {
  isLoadingReplications.value = true
  try {
    replications.value = await api.getReplications()
  } finally {
    isLoadingReplications.value = false
  }
}

async function handleCreateReplication(): Promise<void> {
  if (!newReplication.value.source_node_id || !newReplication.value.target_node_id) return
  if (newReplication.value.source_node_id === newReplication.value.target_node_id) {
    alert('Source and target nodes must be different')
    return
  }

  isCreatingReplication.value = true
  try {
    await api.startReplication(newReplication.value)
    showCreateReplicationDialog.value = false
    newReplication.value = { source_node_id: '', target_node_id: '', service_type: 'redis' }
    await fetchReplications()
  } finally {
    isCreatingReplication.value = false
  }
}

async function handlePromoteReplica(replicationId: string): Promise<void> {
  if (
    !confirm(
      'Are you sure you want to promote this replica? This will make it the primary.'
    )
  ) {
    return
  }

  try {
    await api.promoteReplica(replicationId)
    await fetchReplications()
  } catch (e) {
    alert(`Promote failed: ${e instanceof Error ? e.message : 'Unknown error'}`)
  }
}

// =============================================================================
// Utilities
// =============================================================================

function getBackupStatusClass(state: string): string {
  switch (state) {
    case 'completed':
      return 'bg-green-100 text-green-800'
    case 'in_progress':
      return 'bg-blue-100 text-blue-800'
    case 'pending':
      return 'bg-yellow-100 text-yellow-800'
    case 'failed':
      return 'bg-red-100 text-red-800'
    default:
      return 'bg-gray-100 text-gray-800'
  }
}

function getReplicationStatusClass(state: string): string {
  switch (state) {
    case 'synced':
    case 'active':
      return 'bg-green-100 text-green-800'
    case 'syncing':
      return 'bg-blue-100 text-blue-800'
    case 'pending':
      return 'bg-yellow-100 text-yellow-800'
    case 'failed':
      return 'bg-red-100 text-red-800'
    case 'stopped':
      return 'bg-gray-100 text-gray-800'
    default:
      return 'bg-gray-100 text-gray-800'
  }
}

function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i]
}

function formatDate(dateStr: string | null): string {
  if (!dateStr) return '-'
  return new Date(dateStr).toLocaleString()
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
        <h1 class="text-2xl font-bold text-gray-900">Stateful Services</h1>
        <p class="text-sm text-gray-500 mt-1">
          Manage backups and replications for Redis and other stateful services
        </p>
      </div>
    </div>

    <!-- Tabs -->
    <div class="border-b border-gray-200 mb-6">
      <nav class="-mb-px flex space-x-8">
        <button
          @click="navigateToTab('backups')"
          :class="[
            'py-4 px-1 border-b-2 font-medium text-sm',
            activeTab === 'backups'
              ? 'border-primary-500 text-primary-600'
              : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300',
          ]"
        >
          Backups
          <span class="ml-2 py-0.5 px-2 rounded-full text-xs bg-gray-100 text-gray-600">
            {{ backups.length }}
          </span>
        </button>
        <button
          @click="activeTab = 'replications'"
          :class="[
            'py-4 px-1 border-b-2 font-medium text-sm',
            activeTab === 'replications'
              ? 'border-primary-500 text-primary-600'
              : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300',
          ]"
        >
          Replications
          <span class="ml-2 py-0.5 px-2 rounded-full text-xs bg-gray-100 text-gray-600">
            {{ replications.length }}
          </span>
        </button>
      </nav>
    </div>

    <!-- Backups Tab -->
    <div v-if="activeTab === 'backups'">
      <!-- Backups Header -->
      <div class="flex items-center justify-between mb-4">
        <h2 class="text-lg font-semibold text-gray-800">Backup History</h2>
        <button
          @click="showCreateBackupDialog = true"
          class="btn btn-primary flex items-center gap-2"
        >
          <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4" />
          </svg>
          Create Backup
        </button>
      </div>

      <!-- Backups Table -->
      <div class="card overflow-hidden">
        <table class="min-w-full divide-y divide-gray-200">
          <thead class="bg-gray-50">
            <tr>
              <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Backup ID</th>
              <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Node</th>
              <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Service</th>
              <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Size</th>
              <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Status</th>
              <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Created</th>
              <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Actions</th>
            </tr>
          </thead>
          <tbody class="bg-white divide-y divide-gray-200">
            <tr v-for="backup in backups" :key="backup.backup_id">
              <td class="px-6 py-4 whitespace-nowrap text-sm font-mono text-gray-900">
                {{ backup.backup_id.slice(0, 8) }}...
              </td>
              <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                {{ getNodeHostname(backup.node_id) }}
              </td>
              <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                {{ backup.service_type }}
              </td>
              <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                {{ formatBytes(backup.size_bytes) }}
              </td>
              <td class="px-6 py-4 whitespace-nowrap">
                <span :class="['px-2 py-1 text-xs font-medium rounded-full', getBackupStatusClass(backup.state)]">
                  {{ backup.state }}
                </span>
              </td>
              <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                {{ formatDate(backup.started_at) }}
              </td>
              <td class="px-6 py-4 whitespace-nowrap text-sm">
                <button
                  v-if="backup.state === 'completed'"
                  @click="handleRestore(backup.backup_id)"
                  class="text-blue-600 hover:text-blue-800 font-medium"
                >
                  Restore
                </button>
                <span v-else class="text-gray-400">-</span>
              </td>
            </tr>
            <tr v-if="backups.length === 0 && !isLoadingBackups">
              <td colspan="7" class="px-6 py-12 text-center text-gray-500">
                No backups yet. Click "Create Backup" to get started.
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- Backups Loading -->
      <div v-if="isLoadingBackups" class="flex items-center justify-center py-12">
        <div class="animate-spin w-8 h-8 border-4 border-primary-600 border-t-transparent rounded-full"></div>
      </div>
    </div>

    <!-- Replications Tab -->
    <div v-if="activeTab === 'replications'">
      <!-- Replications Header -->
      <div class="flex items-center justify-between mb-4">
        <h2 class="text-lg font-semibold text-gray-800">Active Replications</h2>
        <button
          @click="showCreateReplicationDialog = true"
          class="btn btn-primary flex items-center gap-2"
        >
          <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4" />
          </svg>
          Start Replication
        </button>
      </div>

      <!-- Replications Table -->
      <div class="card overflow-hidden">
        <table class="min-w-full divide-y divide-gray-200">
          <thead class="bg-gray-50">
            <tr>
              <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">ID</th>
              <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Source</th>
              <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Target</th>
              <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Service</th>
              <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Status</th>
              <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Lag</th>
              <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Started</th>
              <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Actions</th>
            </tr>
          </thead>
          <tbody class="bg-white divide-y divide-gray-200">
            <tr v-for="repl in replications" :key="repl.replication_id">
              <td class="px-6 py-4 whitespace-nowrap text-sm font-mono text-gray-900">
                {{ repl.replication_id.slice(0, 8) }}...
              </td>
              <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                {{ getNodeHostname(repl.source_node_id) }}
              </td>
              <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                {{ getNodeHostname(repl.target_node_id) }}
              </td>
              <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                {{ repl.service_type }}
              </td>
              <td class="px-6 py-4 whitespace-nowrap">
                <span :class="['px-2 py-1 text-xs font-medium rounded-full', getReplicationStatusClass(repl.status)]">
                  {{ repl.status }}
                </span>
              </td>
              <td class="px-6 py-4 whitespace-nowrap">
                <div class="flex items-center gap-2">
                  <span class="text-xs text-gray-500">
                    {{ repl.lag_bytes > 0 ? formatBytes(repl.lag_bytes) + ' lag' : 'In sync' }}
                  </span>
                </div>
              </td>
              <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                {{ formatDate(repl.started_at) }}
              </td>
              <td class="px-6 py-4 whitespace-nowrap text-sm">
                <button
                  v-if="repl.status === 'syncing' || repl.status === 'active'"
                  @click="handlePromoteReplica(repl.replication_id)"
                  class="text-blue-600 hover:text-blue-800 font-medium"
                >
                  Promote
                </button>
                <span v-else class="text-gray-400">-</span>
              </td>
            </tr>
            <tr v-if="replications.length === 0 && !isLoadingReplications">
              <td colspan="8" class="px-6 py-12 text-center text-gray-500">
                No active replications. Click "Start Replication" to set up data replication.
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- Replications Loading -->
      <div v-if="isLoadingReplications" class="flex items-center justify-center py-12">
        <div class="animate-spin w-8 h-8 border-4 border-primary-600 border-t-transparent rounded-full"></div>
      </div>
    </div>

    <!-- Create Backup Dialog -->
    <div
      v-if="showCreateBackupDialog"
      class="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50"
      @click.self="showCreateBackupDialog = false"
    >
      <div class="bg-white rounded-lg shadow-xl max-w-md w-full mx-4">
        <div class="px-6 py-4 border-b border-gray-200">
          <h3 class="text-lg font-semibold text-gray-900">Create Backup</h3>
        </div>
        <div class="px-6 py-4 space-y-4">
          <!-- Node Selection -->
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">Node</label>
            <select
              v-model="newBackup.node_id"
              class="w-full px-3 py-2 border border-gray-300 rounded-md focus:ring-primary-500 focus:border-primary-500"
            >
              <option value="">Select a node...</option>
              <option v-for="opt in nodeOptions" :key="opt.value" :value="opt.value">
                {{ opt.label }}
              </option>
            </select>
          </div>

          <!-- Service Type Selection -->
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">Service Type</label>
            <select
              v-model="newBackup.service_type"
              class="w-full px-3 py-2 border border-gray-300 rounded-md focus:ring-primary-500 focus:border-primary-500"
            >
              <option v-for="svc in serviceTypes" :key="svc" :value="svc">
                {{ svc }}
              </option>
            </select>
          </div>
        </div>
        <div class="px-6 py-4 border-t border-gray-200 flex justify-end gap-3">
          <button
            @click="showCreateBackupDialog = false"
            class="px-4 py-2 text-sm font-medium text-gray-700 bg-gray-100 rounded-md hover:bg-gray-200"
          >
            Cancel
          </button>
          <button
            @click="handleCreateBackup"
            :disabled="!newBackup.node_id || isCreatingBackup"
            class="px-4 py-2 text-sm font-medium text-white bg-primary-600 rounded-md hover:bg-primary-700 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
          >
            <div v-if="isCreatingBackup" class="animate-spin w-4 h-4 border-2 border-white border-t-transparent rounded-full"></div>
            Create Backup
          </button>
        </div>
      </div>
    </div>

    <!-- Create Replication Dialog -->
    <div
      v-if="showCreateReplicationDialog"
      class="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50"
      @click.self="showCreateReplicationDialog = false"
    >
      <div class="bg-white rounded-lg shadow-xl max-w-md w-full mx-4">
        <div class="px-6 py-4 border-b border-gray-200">
          <h3 class="text-lg font-semibold text-gray-900">Start Replication</h3>
        </div>
        <div class="px-6 py-4 space-y-4">
          <!-- Source Node Selection -->
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">Source Node (Primary)</label>
            <select
              v-model="newReplication.source_node_id"
              class="w-full px-3 py-2 border border-gray-300 rounded-md focus:ring-primary-500 focus:border-primary-500"
            >
              <option value="">Select source node...</option>
              <option v-for="opt in nodeOptions" :key="opt.value" :value="opt.value">
                {{ opt.label }}
              </option>
            </select>
          </div>

          <!-- Target Node Selection -->
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">Target Node (Replica)</label>
            <select
              v-model="newReplication.target_node_id"
              class="w-full px-3 py-2 border border-gray-300 rounded-md focus:ring-primary-500 focus:border-primary-500"
            >
              <option value="">Select target node...</option>
              <option
                v-for="opt in nodeOptions"
                :key="opt.value"
                :value="opt.value"
                :disabled="opt.value === newReplication.source_node_id"
              >
                {{ opt.label }}
              </option>
            </select>
          </div>

          <!-- Service Type Selection -->
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">Service Type</label>
            <select
              v-model="newReplication.service_type"
              class="w-full px-3 py-2 border border-gray-300 rounded-md focus:ring-primary-500 focus:border-primary-500"
            >
              <option v-for="svc in serviceTypes" :key="svc" :value="svc">
                {{ svc }}
              </option>
            </select>
          </div>

          <!-- Info Box -->
          <div class="bg-blue-50 border border-blue-200 rounded-md p-3">
            <p class="text-sm text-blue-700">
              Replication will configure the replica to continuously sync data from the primary node.
            </p>
          </div>
        </div>
        <div class="px-6 py-4 border-t border-gray-200 flex justify-end gap-3">
          <button
            @click="showCreateReplicationDialog = false"
            class="px-4 py-2 text-sm font-medium text-gray-700 bg-gray-100 rounded-md hover:bg-gray-200"
          >
            Cancel
          </button>
          <button
            @click="handleCreateReplication"
            :disabled="!newReplication.source_node_id || !newReplication.target_node_id || isCreatingReplication"
            class="px-4 py-2 text-sm font-medium text-white bg-primary-600 rounded-md hover:bg-primary-700 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
          >
            <div v-if="isCreatingReplication" class="animate-spin w-4 h-4 border-2 border-white border-t-transparent rounded-full"></div>
            Start Replication
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
