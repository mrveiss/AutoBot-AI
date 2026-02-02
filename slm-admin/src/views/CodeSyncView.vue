<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * Code Sync View (Issue #741)
 *
 * Dedicated page for managing code version updates across the fleet.
 * Provides status overview, pending updates table, and sync actions.
 */

import { ref, onMounted, computed } from 'vue'
import {
  useCodeSync,
  type PendingNode,
  type SyncOptions,
  type UpdateSchedule,
  type ScheduleCreateRequest,
} from '@/composables/useCodeSync'
import { createLogger } from '@/utils/debugUtils'
import ScheduleModal from '@/components/ScheduleModal.vue'

const logger = createLogger('CodeSyncView')
const codeSync = useCodeSync()

// =============================================================================
// Local State
// =============================================================================

const selectedNodes = ref<Set<string>>(new Set())
const syncStrategy = ref<'immediate' | 'graceful' | 'manual'>('graceful')
const restartAfterSync = ref(true)
const syncingNodeId = ref<string | null>(null)

// Schedule state (Issue #741 - Phase 7)
const showScheduleModal = ref(false)
const editingSchedule = ref<UpdateSchedule | null>(null)
const runningScheduleId = ref<number | null>(null)

// =============================================================================
// Computed Properties
// =============================================================================

const allSelected = computed(() => {
  const pending = codeSync.pendingNodes.value
  return pending.length > 0 && selectedNodes.value.size === pending.length
})

const someSelected = computed(() => {
  return selectedNodes.value.size > 0 && !allSelected.value
})

const selectedCount = computed(() => selectedNodes.value.size)

// =============================================================================
// Methods
// =============================================================================

function toggleSelectAll(): void {
  if (allSelected.value) {
    selectedNodes.value.clear()
  } else {
    const pending = codeSync.pendingNodes.value
    pending.forEach((node) => selectedNodes.value.add(node.node_id))
  }
}

function toggleNode(nodeId: string): void {
  if (selectedNodes.value.has(nodeId)) {
    selectedNodes.value.delete(nodeId)
  } else {
    selectedNodes.value.add(nodeId)
  }
}

function formatVersion(version: string | null): string {
  if (!version) return 'Unknown'
  return version  // Return full version - no truncation
}

function formatDate(dateStr: string | null): string {
  if (!dateStr) return 'Never'
  const date = new Date(dateStr)
  return date.toLocaleString()
}

async function handleRefresh(): Promise<void> {
  logger.info('Refreshing code sync status')
  await codeSync.refreshVersion()
  await codeSync.fetchPendingNodes()
}

async function handleSyncNode(node: PendingNode): Promise<void> {
  logger.info('Syncing node:', node.node_id)
  syncingNodeId.value = node.node_id

  const options: SyncOptions = {
    restart: restartAfterSync.value,
    strategy: syncStrategy.value,
  }

  const result = await codeSync.syncNode(node.node_id, options)

  if (result.success) {
    selectedNodes.value.delete(node.node_id)
    logger.info('Node sync completed:', node.node_id)
  } else {
    logger.error('Node sync failed:', node.node_id, result.message)
  }

  syncingNodeId.value = null
}

async function handleSyncSelected(): Promise<void> {
  const nodeIds = Array.from(selectedNodes.value)
  logger.info('Syncing selected nodes:', nodeIds)

  await codeSync.syncFleet({
    node_ids: nodeIds,
    strategy: syncStrategy.value === 'manual' ? 'manual' : 'rolling',
    restart: restartAfterSync.value,
    batch_size: 1,
  })

  selectedNodes.value.clear()
}

async function handleSyncAll(): Promise<void> {
  logger.info('Syncing all outdated nodes')

  await codeSync.syncFleet({
    strategy: 'rolling',
    restart: restartAfterSync.value,
    batch_size: 1,
  })

  selectedNodes.value.clear()
}

// =============================================================================
// Schedule Methods (Issue #741 - Phase 7)
// =============================================================================

function openCreateScheduleModal(): void {
  editingSchedule.value = null
  showScheduleModal.value = true
}

function openEditScheduleModal(schedule: UpdateSchedule): void {
  editingSchedule.value = schedule
  showScheduleModal.value = true
}

function closeScheduleModal(): void {
  showScheduleModal.value = false
  editingSchedule.value = null
}

async function handleSaveSchedule(scheduleData: ScheduleCreateRequest): Promise<void> {
  if (editingSchedule.value) {
    // Update existing
    await codeSync.updateSchedule(editingSchedule.value.id, scheduleData)
    logger.info('Schedule updated:', editingSchedule.value.id)
  } else {
    // Create new
    await codeSync.createSchedule(scheduleData)
    logger.info('Schedule created:', scheduleData.name)
  }
  closeScheduleModal()
}

async function handleDeleteSchedule(schedule: UpdateSchedule): Promise<void> {
  if (!confirm(`Delete schedule "${schedule.name}"?`)) return

  const success = await codeSync.deleteSchedule(schedule.id)
  if (success) {
    logger.info('Schedule deleted:', schedule.id)
  }
}

async function handleToggleSchedule(schedule: UpdateSchedule): Promise<void> {
  await codeSync.toggleSchedule(schedule.id, !schedule.enabled)
  logger.info('Schedule toggled:', schedule.id, !schedule.enabled)
}

async function handleRunSchedule(schedule: UpdateSchedule): Promise<void> {
  runningScheduleId.value = schedule.id
  const result = await codeSync.runSchedule(schedule.id)
  runningScheduleId.value = null

  if (result?.success) {
    logger.info('Schedule run started:', schedule.id, result.job_id)
  }
}

function formatNextRun(dateStr: string | null): string {
  if (!dateStr) return 'Not scheduled'
  const date = new Date(dateStr)
  return date.toLocaleString()
}

function describeCron(expression: string): string {
  // Common cron patterns
  const patterns: Record<string, string> = {
    '0 * * * *': 'Every hour',
    '0 0 * * *': 'Daily at midnight',
    '0 2 * * *': 'Daily at 2:00 AM',
    '0 0 * * 0': 'Every Sunday',
    '0 2 * * 0': 'Every Sunday at 2 AM',
    '0 0 1 * *': 'First day of month',
    '0 2 1 * *': 'First day at 2 AM',
    '0 */6 * * *': 'Every 6 hours',
  }
  return patterns[expression] || expression
}

// =============================================================================
// Lifecycle
// =============================================================================

onMounted(async () => {
  logger.info('CodeSyncView mounted')
  await codeSync.fetchStatus()
  await codeSync.fetchPendingNodes()
  await codeSync.fetchSchedules()
})
</script>

<template>
  <div class="p-6">
    <!-- Header -->
    <div class="flex items-center justify-between mb-6">
      <div>
        <h1 class="text-2xl font-bold text-gray-900">Code Sync</h1>
        <p class="text-sm text-gray-500 mt-1">
          Manage agent code versions across the fleet
        </p>
      </div>
      <button
        @click="handleRefresh"
        :disabled="codeSync.loading.value"
        class="btn btn-secondary flex items-center gap-2"
      >
        <svg
          :class="['w-4 h-4', codeSync.loading.value ? 'animate-spin' : '']"
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
        {{ codeSync.loading.value ? 'Refreshing...' : 'Refresh' }}
      </button>
    </div>

    <!-- Status Banner -->
    <div class="card p-5 mb-6">
      <div class="grid grid-cols-1 md:grid-cols-4 gap-6">
        <div>
          <span class="text-sm text-gray-500 block mb-1">Latest Version</span>
          <span class="text-lg font-semibold font-mono text-gray-900">
            {{ formatVersion(codeSync.latestVersion.value) }}
          </span>
        </div>
        <div>
          <span class="text-sm text-gray-500 block mb-1">Last Fetch</span>
          <span class="text-lg font-semibold text-gray-900">
            {{ formatDate(codeSync.status.value?.last_fetch ?? null) }}
          </span>
        </div>
        <div>
          <span class="text-sm text-gray-500 block mb-1">Outdated Nodes</span>
          <span
            class="text-lg font-semibold"
            :class="codeSync.hasOutdatedNodes.value ? 'text-yellow-600' : 'text-gray-900'"
          >
            {{ codeSync.outdatedCount.value }} / {{ codeSync.totalNodes.value }}
          </span>
        </div>
        <div class="flex items-end">
          <span
            v-if="codeSync.hasOutdatedNodes.value"
            class="inline-flex items-center px-3 py-1 rounded-full text-sm font-medium bg-yellow-100 text-yellow-800"
          >
            <svg class="w-4 h-4 mr-1.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
            Updates Available
          </span>
          <span
            v-else
            class="inline-flex items-center px-3 py-1 rounded-full text-sm font-medium bg-green-100 text-green-800"
          >
            <svg class="w-4 h-4 mr-1.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" />
            </svg>
            All Up To Date
          </span>
        </div>
      </div>
    </div>

    <!-- Error Display -->
    <div
      v-if="codeSync.error.value"
      class="bg-red-50 border border-red-200 rounded-lg p-4 mb-6 flex items-center justify-between"
    >
      <div class="flex items-center gap-3">
        <svg class="w-5 h-5 text-red-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
        <span class="text-red-700">{{ codeSync.error.value }}</span>
      </div>
      <button
        @click="codeSync.clearError()"
        class="text-red-600 hover:text-red-800 font-medium text-sm"
      >
        Dismiss
      </button>
    </div>

    <!-- Sync Options -->
    <div class="card p-5 mb-6">
      <h2 class="text-lg font-semibold text-gray-800 mb-4">Sync Options</h2>
      <div class="flex flex-wrap items-center gap-6">
        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">Restart Strategy</label>
          <select
            v-model="syncStrategy"
            class="px-3 py-2 border border-gray-300 rounded-md focus:ring-primary-500 focus:border-primary-500"
          >
            <option value="graceful">Graceful (wait for tasks)</option>
            <option value="immediate">Immediate</option>
            <option value="manual">Manual (no restart)</option>
          </select>
        </div>
        <div class="flex items-center">
          <label class="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              v-model="restartAfterSync"
              class="w-4 h-4 text-primary-600 rounded focus:ring-primary-500"
            />
            <span class="text-sm text-gray-700">Restart service after sync</span>
          </label>
        </div>
      </div>
    </div>

    <!-- Pending Updates Section -->
    <div class="card overflow-hidden">
      <!-- Section Header -->
      <div class="px-6 py-4 border-b border-gray-200 flex items-center justify-between">
        <h2 class="text-lg font-semibold text-gray-800">Pending Updates</h2>
        <div v-if="codeSync.pendingNodes.value.length > 0" class="flex items-center gap-3">
          <button
            @click="handleSyncSelected"
            :disabled="selectedCount === 0 || codeSync.loading.value"
            class="btn btn-primary flex items-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
            </svg>
            Sync Selected ({{ selectedCount }})
          </button>
          <button
            @click="handleSyncAll"
            :disabled="codeSync.loading.value"
            class="btn btn-secondary flex items-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            Sync All
          </button>
        </div>
      </div>

      <!-- Empty State -->
      <div
        v-if="codeSync.pendingNodes.value.length === 0 && !codeSync.loading.value"
        class="px-6 py-12 text-center"
      >
        <svg class="w-16 h-16 mx-auto text-gray-400 mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" />
        </svg>
        <h3 class="text-lg font-medium text-gray-900 mb-2">All nodes are up to date</h3>
        <p class="text-gray-500">
          No code updates are pending. Click "Refresh" to check for new versions.
        </p>
      </div>

      <!-- Loading State -->
      <div v-if="codeSync.loading.value && codeSync.pendingNodes.value.length === 0" class="flex items-center justify-center py-12">
        <div class="animate-spin w-8 h-8 border-4 border-primary-600 border-t-transparent rounded-full"></div>
      </div>

      <!-- Pending Updates Table -->
      <table v-if="codeSync.pendingNodes.value.length > 0" class="min-w-full divide-y divide-gray-200">
        <thead class="bg-gray-50">
          <tr>
            <th class="px-6 py-3 text-left w-12">
              <input
                type="checkbox"
                :checked="allSelected"
                :indeterminate="someSelected"
                @change="toggleSelectAll"
                class="w-4 h-4 text-primary-600 rounded focus:ring-primary-500"
              />
            </th>
            <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Hostname</th>
            <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">IP Address</th>
            <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Current Version</th>
            <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Status</th>
            <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Actions</th>
          </tr>
        </thead>
        <tbody class="bg-white divide-y divide-gray-200">
          <tr
            v-for="node in codeSync.pendingNodes.value"
            :key="node.node_id"
            :class="{ 'bg-primary-50': selectedNodes.has(node.node_id) }"
          >
            <td class="px-6 py-4">
              <input
                type="checkbox"
                :checked="selectedNodes.has(node.node_id)"
                @change="toggleNode(node.node_id)"
                class="w-4 h-4 text-primary-600 rounded focus:ring-primary-500"
              />
            </td>
            <td class="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">
              {{ node.hostname }}
            </td>
            <td class="px-6 py-4 whitespace-nowrap text-sm font-mono text-gray-500">
              {{ node.ip_address }}
            </td>
            <td class="px-6 py-4 whitespace-nowrap text-sm font-mono text-gray-500">
              {{ formatVersion(node.current_version) }}
            </td>
            <td class="px-6 py-4 whitespace-nowrap">
              <span class="px-2 py-1 text-xs font-medium rounded-full bg-yellow-100 text-yellow-800">
                Outdated
              </span>
            </td>
            <td class="px-6 py-4 whitespace-nowrap">
              <button
                @click="handleSyncNode(node)"
                :disabled="syncingNodeId === node.node_id"
                class="text-primary-600 hover:text-primary-800 font-medium text-sm disabled:opacity-50"
              >
                {{ syncingNodeId === node.node_id ? 'Syncing...' : 'Sync' }}
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Schedules Section (Issue #741 - Phase 7) -->
    <div class="card overflow-hidden mt-6">
      <!-- Section Header -->
      <div class="px-6 py-4 border-b border-gray-200 flex items-center justify-between">
        <div>
          <h2 class="text-lg font-semibold text-gray-800">Scheduled Updates</h2>
          <p class="text-sm text-gray-500 mt-0.5">Configure automatic code sync schedules</p>
        </div>
        <button
          @click="openCreateScheduleModal"
          class="btn btn-primary flex items-center gap-2"
        >
          <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4" />
          </svg>
          Add Schedule
        </button>
      </div>

      <!-- Empty State -->
      <div
        v-if="codeSync.schedules.value.length === 0"
        class="px-6 py-12 text-center"
      >
        <svg class="w-16 h-16 mx-auto text-gray-400 mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
        <h3 class="text-lg font-medium text-gray-900 mb-2">No schedules configured</h3>
        <p class="text-gray-500 mb-4">
          Create a schedule to automatically sync code at specific times.
        </p>
        <button
          @click="openCreateScheduleModal"
          class="btn btn-primary"
        >
          Create First Schedule
        </button>
      </div>

      <!-- Schedules Table -->
      <table v-if="codeSync.schedules.value.length > 0" class="min-w-full divide-y divide-gray-200">
        <thead class="bg-gray-50">
          <tr>
            <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Name</th>
            <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Schedule</th>
            <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Next Run</th>
            <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Status</th>
            <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Actions</th>
          </tr>
        </thead>
        <tbody class="bg-white divide-y divide-gray-200">
          <tr v-for="schedule in codeSync.schedules.value" :key="schedule.id">
            <td class="px-6 py-4 whitespace-nowrap">
              <div class="text-sm font-medium text-gray-900">{{ schedule.name }}</div>
              <div class="text-xs text-gray-500">
                {{ schedule.target_type === 'all' ? 'All outdated nodes' : `${schedule.target_nodes?.length || 0} specific nodes` }}
              </div>
            </td>
            <td class="px-6 py-4 whitespace-nowrap">
              <div class="text-sm text-gray-900">{{ describeCron(schedule.cron_expression) }}</div>
              <div class="text-xs text-gray-500 font-mono">{{ schedule.cron_expression }}</div>
            </td>
            <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
              {{ formatNextRun(schedule.next_run) }}
            </td>
            <td class="px-6 py-4 whitespace-nowrap">
              <button
                @click="handleToggleSchedule(schedule)"
                :class="[
                  'relative inline-flex h-6 w-11 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none',
                  schedule.enabled ? 'bg-primary-600' : 'bg-gray-200',
                ]"
              >
                <span
                  :class="[
                    'pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out',
                    schedule.enabled ? 'translate-x-5' : 'translate-x-0',
                  ]"
                />
              </button>
            </td>
            <td class="px-6 py-4 whitespace-nowrap text-sm">
              <div class="flex items-center gap-2">
                <button
                  @click="handleRunSchedule(schedule)"
                  :disabled="runningScheduleId === schedule.id"
                  class="text-primary-600 hover:text-primary-800 font-medium disabled:opacity-50"
                  title="Run Now"
                >
                  {{ runningScheduleId === schedule.id ? 'Running...' : 'Run' }}
                </button>
                <span class="text-gray-300">|</span>
                <button
                  @click="openEditScheduleModal(schedule)"
                  class="text-gray-600 hover:text-gray-800 font-medium"
                >
                  Edit
                </button>
                <span class="text-gray-300">|</span>
                <button
                  @click="handleDeleteSchedule(schedule)"
                  class="text-red-600 hover:text-red-800 font-medium"
                >
                  Delete
                </button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Schedule Modal -->
    <ScheduleModal
      :show="showScheduleModal"
      :schedule="editingSchedule"
      :nodes="codeSync.pendingNodes.value"
      @close="closeScheduleModal"
      @save="handleSaveSchedule"
    />
  </div>
</template>
