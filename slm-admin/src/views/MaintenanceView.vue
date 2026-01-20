<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

import { ref, computed, onMounted } from 'vue'
import { useFleetStore } from '@/stores/fleet'
import { useSlmApi } from '@/composables/useSlmApi'
import { createLogger } from '@/utils/debugUtils'
import type { MaintenanceWindow, MaintenanceWindowCreate } from '@/types/slm'

const logger = createLogger('MaintenanceView')
const fleetStore = useFleetStore()
const api = useSlmApi()

// State
const windows = ref<MaintenanceWindow[]>([])
const isLoading = ref(false)
const showScheduleDialog = ref(false)
const editingWindow = ref<MaintenanceWindow | null>(null)
const statusFilter = ref<string>('')
const includeCompleted = ref(false)

// Node state
const nodes = computed(() => fleetStore.nodeList)
const maintenanceNodes = computed(() => nodes.value.filter(n => n.status === 'maintenance'))

// Quick actions state
const selectedDrainNode = ref<string | null>(null)
const selectedResumeNode = ref<string | null>(null)
const isDraining = ref(false)
const isResuming = ref(false)

// Form state
const formData = ref<MaintenanceWindowCreate>({
  node_id: undefined,
  start_time: '',
  end_time: '',
  reason: '',
  auto_drain: false,
  suppress_alerts: true,
  suppress_remediation: true,
})
const isSubmitting = ref(false)
const formError = ref<string | null>(null)

// Computed
const activeWindows = computed(() => windows.value.filter(w => w.status === 'active'))
const scheduledWindows = computed(() => windows.value.filter(w => w.status === 'scheduled'))

const filteredWindows = computed(() => {
  let filtered = windows.value
  if (statusFilter.value) {
    filtered = filtered.filter(w => w.status === statusFilter.value)
  }
  return filtered
})

const summaryStats = computed(() => ({
  active: activeWindows.value.length,
  scheduled: scheduledWindows.value.length,
  nodesInMaintenance: maintenanceNodes.value.length,
  totalNodes: nodes.value.length,
}))

// Lifecycle
onMounted(async () => {
  await Promise.all([
    fetchMaintenanceWindows(),
    fleetStore.fetchNodes(),
  ])
})

// Actions
async function fetchMaintenanceWindows(): Promise<void> {
  isLoading.value = true
  try {
    const response = await api.getMaintenanceWindows({
      include_completed: includeCompleted.value,
    })
    windows.value = response.windows
  } catch (err) {
    logger.error('Failed to fetch maintenance windows:', err)
  } finally {
    isLoading.value = false
  }
}

function openScheduleDialog(window?: MaintenanceWindow): void {
  if (window) {
    editingWindow.value = window
    formData.value = {
      node_id: window.node_id || undefined,
      start_time: formatDateTimeLocal(window.start_time),
      end_time: formatDateTimeLocal(window.end_time),
      reason: window.reason || '',
      auto_drain: window.auto_drain,
      suppress_alerts: window.suppress_alerts,
      suppress_remediation: window.suppress_remediation,
    }
  } else {
    editingWindow.value = null
    const now = new Date()
    const oneHourLater = new Date(now.getTime() + 60 * 60 * 1000)
    formData.value = {
      node_id: undefined,
      start_time: formatDateTimeLocal(now.toISOString()),
      end_time: formatDateTimeLocal(oneHourLater.toISOString()),
      reason: '',
      auto_drain: false,
      suppress_alerts: true,
      suppress_remediation: true,
    }
  }
  formError.value = null
  showScheduleDialog.value = true
}

function closeScheduleDialog(): void {
  showScheduleDialog.value = false
  editingWindow.value = null
  formError.value = null
}

async function submitMaintenanceWindow(): Promise<void> {
  formError.value = null

  if (!formData.value.start_time || !formData.value.end_time) {
    formError.value = 'Start and end time are required'
    return
  }

  const startTime = new Date(formData.value.start_time)
  const endTime = new Date(formData.value.end_time)

  if (endTime <= startTime) {
    formError.value = 'End time must be after start time'
    return
  }

  isSubmitting.value = true
  try {
    const payload: MaintenanceWindowCreate = {
      node_id: formData.value.node_id || undefined,
      start_time: startTime.toISOString(),
      end_time: endTime.toISOString(),
      reason: formData.value.reason || undefined,
      auto_drain: formData.value.auto_drain,
      suppress_alerts: formData.value.suppress_alerts,
      suppress_remediation: formData.value.suppress_remediation,
    }

    if (editingWindow.value) {
      await api.updateMaintenanceWindow(editingWindow.value.window_id, payload)
      logger.info('Maintenance window updated:', editingWindow.value.window_id)
    } else {
      await api.createMaintenanceWindow(payload)
      logger.info('Maintenance window created')
    }

    closeScheduleDialog()
    await fetchMaintenanceWindows()
  } catch (err) {
    logger.error('Failed to save maintenance window:', err)
    formError.value = err instanceof Error ? err.message : 'Failed to save maintenance window'
  } finally {
    isSubmitting.value = false
  }
}

async function activateWindow(windowId: string): Promise<void> {
  try {
    await api.activateMaintenanceWindow(windowId)
    logger.info('Maintenance window activated:', windowId)
    await fetchMaintenanceWindows()
  } catch (err) {
    logger.error('Failed to activate maintenance window:', err)
    alert('Failed to activate maintenance window')
  }
}

async function completeWindow(windowId: string): Promise<void> {
  try {
    await api.completeMaintenanceWindow(windowId)
    logger.info('Maintenance window completed:', windowId)
    await fetchMaintenanceWindows()
  } catch (err) {
    logger.error('Failed to complete maintenance window:', err)
    alert('Failed to complete maintenance window')
  }
}

async function deleteWindow(windowId: string): Promise<void> {
  if (!confirm('Are you sure you want to delete this maintenance window?')) {
    return
  }

  try {
    await api.deleteMaintenanceWindow(windowId)
    logger.info('Maintenance window deleted:', windowId)
    await fetchMaintenanceWindows()
  } catch (err) {
    logger.error('Failed to delete maintenance window:', err)
    alert('Failed to delete maintenance window')
  }
}

async function handleDrainNode(nodeId: string): Promise<void> {
  if (!confirm(`Are you sure you want to drain node ${nodeId}? This will put it in maintenance mode.`)) {
    return
  }

  isDraining.value = true
  try {
    await api.drainNode(nodeId)
    await fleetStore.fetchNodes()
    selectedDrainNode.value = null
    logger.info('Node drained successfully:', nodeId)
  } catch (err) {
    logger.error('Failed to drain node:', err)
    alert('Failed to drain node. Please try again.')
  } finally {
    isDraining.value = false
  }
}

async function handleResumeNode(nodeId: string): Promise<void> {
  isResuming.value = true
  try {
    await api.resumeNode(nodeId)
    await fleetStore.fetchNodes()
    selectedResumeNode.value = null
    logger.info('Node resumed successfully:', nodeId)
  } catch (err) {
    logger.error('Failed to resume node:', err)
    alert('Failed to resume node. Please try again.')
  } finally {
    isResuming.value = false
  }
}

// Helpers
function formatDateTimeLocal(isoString: string): string {
  const date = new Date(isoString)
  const offset = date.getTimezoneOffset()
  const localDate = new Date(date.getTime() - offset * 60 * 1000)
  return localDate.toISOString().slice(0, 16)
}

function formatDateTime(isoString: string): string {
  return new Date(isoString).toLocaleString()
}

function getStatusBadgeClass(status: string): string {
  switch (status) {
    case 'active':
      return 'bg-yellow-100 text-yellow-800'
    case 'scheduled':
      return 'bg-blue-100 text-blue-800'
    case 'completed':
      return 'bg-green-100 text-green-800'
    case 'cancelled':
      return 'bg-gray-100 text-gray-800'
    default:
      return 'bg-gray-100 text-gray-800'
  }
}

function getNodeName(nodeId: string | null): string {
  if (!nodeId) return 'All Nodes'
  const node = nodes.value.find(n => n.node_id === nodeId)
  return node?.hostname || nodeId
}
</script>

<template>
  <div class="p-6">
    <!-- Header -->
    <div class="flex items-center justify-between mb-6">
      <div>
        <h1 class="text-2xl font-bold text-gray-900">Maintenance</h1>
        <p class="text-sm text-gray-500 mt-1">
          Schedule maintenance windows and manage node availability
        </p>
      </div>
      <div class="flex items-center gap-3">
        <button
          @click="fetchMaintenanceWindows"
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
          @click="openScheduleDialog()"
          class="btn btn-primary flex items-center gap-2"
        >
          <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
          </svg>
          Schedule Maintenance
        </button>
      </div>
    </div>

    <!-- Summary Cards -->
    <div class="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
      <div class="card p-4">
        <div class="flex items-center justify-between">
          <div>
            <p class="text-sm text-gray-500">Active Windows</p>
            <p class="text-2xl font-bold text-yellow-600">{{ summaryStats.active }}</p>
          </div>
          <div class="w-10 h-10 rounded-full bg-yellow-100 flex items-center justify-center">
            <svg class="w-5 h-5 text-yellow-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
          </div>
        </div>
      </div>

      <div class="card p-4">
        <div class="flex items-center justify-between">
          <div>
            <p class="text-sm text-gray-500">Scheduled</p>
            <p class="text-2xl font-bold text-blue-600">{{ summaryStats.scheduled }}</p>
          </div>
          <div class="w-10 h-10 rounded-full bg-blue-100 flex items-center justify-center">
            <svg class="w-5 h-5 text-blue-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
            </svg>
          </div>
        </div>
      </div>

      <div class="card p-4">
        <div class="flex items-center justify-between">
          <div>
            <p class="text-sm text-gray-500">Nodes in Maintenance</p>
            <p class="text-2xl font-bold text-orange-600">{{ summaryStats.nodesInMaintenance }}</p>
          </div>
          <div class="w-10 h-10 rounded-full bg-orange-100 flex items-center justify-center">
            <svg class="w-5 h-5 text-orange-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
            </svg>
          </div>
        </div>
      </div>

      <div class="card p-4">
        <div class="flex items-center justify-between">
          <div>
            <p class="text-sm text-gray-500">Total Nodes</p>
            <p class="text-2xl font-bold text-gray-900">{{ summaryStats.totalNodes }}</p>
          </div>
          <div class="w-10 h-10 rounded-full bg-gray-100 flex items-center justify-center">
            <svg class="w-5 h-5 text-gray-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 12h14M5 12a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v4a2 2 0 01-2 2M5 12a2 2 0 00-2 2v4a2 2 0 002 2h14a2 2 0 002-2v-4a2 2 0 00-2-2m-2-4h.01M17 16h.01" />
            </svg>
          </div>
        </div>
      </div>
    </div>

    <!-- Quick Actions -->
    <div class="card p-6 mb-6">
      <h2 class="text-lg font-semibold mb-4">Quick Actions</h2>
      <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div class="border border-gray-200 rounded-lg p-4">
          <h3 class="font-medium text-gray-900 mb-2">Drain Node</h3>
          <p class="text-sm text-gray-500 mb-3">
            Put a node into maintenance mode, making it unavailable for new workloads.
          </p>
          <select
            v-model="selectedDrainNode"
            class="input mb-2"
            :disabled="isDraining"
          >
            <option value="">Select a node...</option>
            <option
              v-for="node in nodes.filter(n => n.status !== 'maintenance')"
              :key="node.node_id"
              :value="node.node_id"
            >
              {{ node.hostname }} ({{ node.ip_address }})
            </option>
          </select>
          <button
            @click="selectedDrainNode && handleDrainNode(selectedDrainNode)"
            :disabled="!selectedDrainNode || isDraining"
            class="btn btn-secondary w-full"
          >
            {{ isDraining ? 'Draining...' : 'Drain Node' }}
          </button>
        </div>

        <div class="border border-gray-200 rounded-lg p-4">
          <h3 class="font-medium text-gray-900 mb-2">Resume Node</h3>
          <p class="text-sm text-gray-500 mb-3">
            Return a maintenance node to active service.
          </p>
          <select
            v-model="selectedResumeNode"
            class="input mb-2"
            :disabled="isResuming"
          >
            <option value="">Select a node...</option>
            <option
              v-for="node in maintenanceNodes"
              :key="node.node_id"
              :value="node.node_id"
            >
              {{ node.hostname }} ({{ node.ip_address }})
            </option>
          </select>
          <button
            @click="selectedResumeNode && handleResumeNode(selectedResumeNode)"
            :disabled="!selectedResumeNode || isResuming"
            class="btn btn-success w-full"
          >
            {{ isResuming ? 'Resuming...' : 'Resume Node' }}
          </button>
        </div>

        <div class="border border-gray-200 rounded-lg p-4">
          <h3 class="font-medium text-gray-900 mb-2">Fleet-Wide Maintenance</h3>
          <p class="text-sm text-gray-500 mb-3">
            Schedule maintenance across all nodes with rolling updates.
          </p>
          <button
            @click="openScheduleDialog()"
            class="btn btn-primary w-full"
          >
            Schedule Window
          </button>
        </div>
      </div>
    </div>

    <!-- Maintenance Windows Table -->
    <div class="card overflow-hidden">
      <div class="px-6 py-4 border-b border-gray-200 flex items-center justify-between">
        <h2 class="text-lg font-semibold">Maintenance Windows</h2>
        <div class="flex items-center gap-4">
          <label class="flex items-center gap-2 text-sm text-gray-600">
            <input
              type="checkbox"
              v-model="includeCompleted"
              @change="fetchMaintenanceWindows"
              class="rounded text-primary-600 focus:ring-primary-500"
            />
            Show completed
          </label>
          <select
            v-model="statusFilter"
            class="input py-1.5 text-sm"
          >
            <option value="">All statuses</option>
            <option value="scheduled">Scheduled</option>
            <option value="active">Active</option>
            <option value="completed">Completed</option>
            <option value="cancelled">Cancelled</option>
          </select>
        </div>
      </div>

      <!-- Loading State -->
      <div v-if="isLoading" class="p-6 text-center">
        <div class="animate-spin w-8 h-8 border-4 border-primary-600 border-t-transparent rounded-full mx-auto"></div>
        <p class="text-gray-500 mt-2">Loading maintenance windows...</p>
      </div>

      <!-- Empty State -->
      <div v-else-if="filteredWindows.length === 0" class="p-6 text-center text-gray-500">
        <svg class="w-12 h-12 mx-auto text-gray-400 mb-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
        </svg>
        <p>No maintenance windows {{ statusFilter ? `with status "${statusFilter}"` : 'scheduled' }}.</p>
        <button
          @click="openScheduleDialog()"
          class="btn btn-primary mt-4"
        >
          Schedule First Window
        </button>
      </div>

      <!-- Windows Table -->
      <div v-else class="overflow-x-auto">
        <table class="w-full">
          <thead class="bg-gray-50">
            <tr>
              <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Status</th>
              <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Node</th>
              <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Start Time</th>
              <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">End Time</th>
              <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Reason</th>
              <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Options</th>
              <th class="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">Actions</th>
            </tr>
          </thead>
          <tbody class="bg-white divide-y divide-gray-200">
            <tr v-for="window in filteredWindows" :key="window.window_id" class="hover:bg-gray-50">
              <td class="px-6 py-4 whitespace-nowrap">
                <span
                  class="px-2 py-1 text-xs font-medium rounded-full capitalize"
                  :class="getStatusBadgeClass(window.status)"
                >
                  {{ window.status }}
                </span>
              </td>
              <td class="px-6 py-4 whitespace-nowrap">
                <span class="text-sm text-gray-900">{{ getNodeName(window.node_id) }}</span>
              </td>
              <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                {{ formatDateTime(window.start_time) }}
              </td>
              <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                {{ formatDateTime(window.end_time) }}
              </td>
              <td class="px-6 py-4 text-sm text-gray-500 max-w-xs truncate">
                {{ window.reason || '-' }}
              </td>
              <td class="px-6 py-4 whitespace-nowrap">
                <div class="flex items-center gap-2 text-xs">
                  <span
                    v-if="window.suppress_alerts"
                    class="px-1.5 py-0.5 bg-purple-100 text-purple-700 rounded"
                    title="Alerts suppressed"
                  >
                    Alerts
                  </span>
                  <span
                    v-if="window.suppress_remediation"
                    class="px-1.5 py-0.5 bg-indigo-100 text-indigo-700 rounded"
                    title="Auto-remediation suppressed"
                  >
                    Remediation
                  </span>
                  <span
                    v-if="window.auto_drain"
                    class="px-1.5 py-0.5 bg-orange-100 text-orange-700 rounded"
                    title="Auto-drain enabled"
                  >
                    Drain
                  </span>
                </div>
              </td>
              <td class="px-6 py-4 whitespace-nowrap text-right text-sm">
                <div class="flex items-center justify-end gap-2">
                  <!-- Activate Button (for scheduled) -->
                  <button
                    v-if="window.status === 'scheduled'"
                    @click="activateWindow(window.window_id)"
                    class="text-yellow-600 hover:text-yellow-800"
                    title="Activate now"
                  >
                    <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" />
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                    </svg>
                  </button>

                  <!-- Complete Button (for active) -->
                  <button
                    v-if="window.status === 'active'"
                    @click="completeWindow(window.window_id)"
                    class="text-green-600 hover:text-green-800"
                    title="Complete maintenance"
                  >
                    <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                    </svg>
                  </button>

                  <!-- Edit Button (for scheduled) -->
                  <button
                    v-if="window.status === 'scheduled'"
                    @click="openScheduleDialog(window)"
                    class="text-gray-600 hover:text-gray-800"
                    title="Edit window"
                  >
                    <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                    </svg>
                  </button>

                  <!-- Delete Button -->
                  <button
                    v-if="window.status !== 'active'"
                    @click="deleteWindow(window.window_id)"
                    class="text-red-600 hover:text-red-800"
                    title="Delete window"
                  >
                    <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                    </svg>
                  </button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Schedule/Edit Modal -->
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
          v-if="showScheduleDialog"
          class="fixed inset-0 z-50 flex items-center justify-center p-4"
        >
          <div class="fixed inset-0 bg-gray-500 bg-opacity-75" @click="closeScheduleDialog"></div>
          <div class="relative bg-white rounded-lg shadow-xl max-w-lg w-full p-6">
            <div class="flex items-center justify-between mb-4">
              <h3 class="text-lg font-semibold text-gray-900">
                {{ editingWindow ? 'Edit Maintenance Window' : 'Schedule Maintenance Window' }}
              </h3>
              <button
                @click="closeScheduleDialog"
                class="text-gray-400 hover:text-gray-600"
              >
                <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            <!-- Error Alert -->
            <div v-if="formError" class="mb-4 p-3 bg-red-50 border border-red-200 rounded-md">
              <p class="text-sm text-red-600">{{ formError }}</p>
            </div>

            <form @submit.prevent="submitMaintenanceWindow" class="space-y-4">
              <!-- Node Selection -->
              <div>
                <label class="block text-sm font-medium text-gray-700 mb-1">
                  Target Node
                </label>
                <select v-model="formData.node_id" class="input">
                  <option :value="undefined">All Nodes (Fleet-Wide)</option>
                  <option
                    v-for="node in nodes"
                    :key="node.node_id"
                    :value="node.node_id"
                  >
                    {{ node.hostname }} ({{ node.ip_address }})
                  </option>
                </select>
                <p class="text-xs text-gray-500 mt-1">
                  Leave empty for fleet-wide maintenance
                </p>
              </div>

              <!-- Time Range -->
              <div class="grid grid-cols-2 gap-4">
                <div>
                  <label class="block text-sm font-medium text-gray-700 mb-1">
                    Start Time <span class="text-red-500">*</span>
                  </label>
                  <input
                    type="datetime-local"
                    v-model="formData.start_time"
                    required
                    class="input"
                  />
                </div>
                <div>
                  <label class="block text-sm font-medium text-gray-700 mb-1">
                    End Time <span class="text-red-500">*</span>
                  </label>
                  <input
                    type="datetime-local"
                    v-model="formData.end_time"
                    required
                    class="input"
                  />
                </div>
              </div>

              <!-- Reason -->
              <div>
                <label class="block text-sm font-medium text-gray-700 mb-1">
                  Reason
                </label>
                <textarea
                  v-model="formData.reason"
                  rows="2"
                  class="input"
                  placeholder="Optional: Describe the maintenance activity..."
                ></textarea>
              </div>

              <!-- Options -->
              <div class="space-y-3">
                <label class="flex items-center gap-3">
                  <input
                    type="checkbox"
                    v-model="formData.suppress_alerts"
                    class="rounded text-primary-600 focus:ring-primary-500"
                  />
                  <div>
                    <span class="text-sm font-medium text-gray-900">Suppress Alerts</span>
                    <p class="text-xs text-gray-500">Don't send alerts during this window</p>
                  </div>
                </label>

                <label class="flex items-center gap-3">
                  <input
                    type="checkbox"
                    v-model="formData.suppress_remediation"
                    class="rounded text-primary-600 focus:ring-primary-500"
                  />
                  <div>
                    <span class="text-sm font-medium text-gray-900">Suppress Auto-Remediation</span>
                    <p class="text-xs text-gray-500">Disable automatic remediation actions</p>
                  </div>
                </label>

                <label class="flex items-center gap-3">
                  <input
                    type="checkbox"
                    v-model="formData.auto_drain"
                    class="rounded text-primary-600 focus:ring-primary-500"
                  />
                  <div>
                    <span class="text-sm font-medium text-gray-900">Auto-Drain</span>
                    <p class="text-xs text-gray-500">Automatically drain services before maintenance starts</p>
                  </div>
                </label>
              </div>

              <!-- Actions -->
              <div class="flex justify-end gap-3 pt-4 border-t border-gray-200">
                <button
                  type="button"
                  @click="closeScheduleDialog"
                  :disabled="isSubmitting"
                  class="btn btn-secondary"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  :disabled="isSubmitting"
                  class="btn btn-primary"
                >
                  {{ isSubmitting ? 'Saving...' : (editingWindow ? 'Update Window' : 'Schedule Window') }}
                </button>
              </div>
            </form>
          </div>
        </div>
      </Transition>
    </Teleport>
  </div>
</template>
