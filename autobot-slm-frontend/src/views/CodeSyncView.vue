<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * Code Sync View (Issue #741, #779, #9971)
 *
 * Dedicated page for managing code version updates across the fleet.
 * Provides a one-click full-pipeline update CTA (#9971), pipeline progress
 * display, and an Advanced section with existing per-node controls.
 */

import { ref, watch, onMounted, onUnmounted, computed, type DeepReadonly } from 'vue'
import {
  useCodeSync,
  type PendingNode,
  type SyncOptions,
  type UpdateSchedule,
  type ScheduleCreateRequest,
  type FileDriftReport,
  type UpdateAllJob,
  type UpdateAllStage,
} from '@/composables/useCodeSync'
import { createLogger } from '@/utils/debugUtils'
import { formatDateTime } from '@/composables/useTimezone'
import { getCommitHashDisplay, getCommitUrl } from '@/utils/commitHashUtils'
import ScheduleModal from '@/components/ScheduleModal.vue'
import CodeSourceModal from '@/components/CodeSourceModal.vue'
import { useCodeSource } from '@/composables/useCodeSource'

const logger = createLogger('CodeSyncView')
const codeSync = useCodeSync()

// =============================================================================
// Local State
// =============================================================================

const selectedNodes = ref<Set<string>>(new Set())
const syncStrategy = ref<'immediate' | 'graceful' | 'manual'>('graceful')
const restartAfterSync = ref(true)
const syncingNodeId = ref<string | null>(null)

// Progress tracking (Issue #880)
const syncProgress = ref<Map<string, string>>(new Map())
const syncStage = ref<string | null>(null)

// Schedule state (Issue #741 - Phase 7)
const showScheduleModal = ref(false)
const editingSchedule = ref<DeepReadonly<UpdateSchedule> | null>(null)
const runningScheduleId = ref<number | null>(null)

// SLM self-sync restart banner (Issue #1231)
const slmRestartPending = ref(false)
let slmRefreshTimer: ReturnType<typeof setTimeout> | null = null

// Role-based sync state (Issue #779)
const syncingRole = ref<string | null>(null)
const isPulling = ref(false)
const successMessage = ref<string | null>(null)

// Code Source state (Issue #779)
const codeSourceComposable = useCodeSource()
const codeSourceData = codeSourceComposable.codeSource
const showCodeSourceModal = ref(false)

// Drift detection state (Issue #2834)
const driftReport = ref<FileDriftReport | null>(null)
const isDriftLoading = ref(false)
const isResolvingDrift = ref(false) // #7149: separate from drift-check spinner
const showDriftDetails = ref(false)
const selectedDriftComponent = ref('autobot-slm-backend')

// Clear stale results when the user switches to a different component (#3433)
watch(selectedDriftComponent, () => {
  driftReport.value = null
  showDriftDetails.value = false
})

// =============================================================================
// One-click update-all state (#9971)
// =============================================================================
const updateAllJob = ref<UpdateAllJob | null>(null)
const updateAllPolling = ref(false)
let updateAllPollTimer: ReturnType<typeof setTimeout> | null = null
const showAdvanced = ref(false)
const expandedStageLogs = ref<Set<string>>(new Set())

// Stage display metadata
const STAGE_LABELS: Record<string, string> = {
  github_fetch: 'GitHub',
  code_source_pull: 'code_source',
  slm_self_update: 'SLM server',
  fleet_nodes: 'Fleet nodes',
}

function stageLabel(name: string): string {
  return STAGE_LABELS[name] ?? name
}

function stageStatusClass(status: string): string {
  const map: Record<string, string> = {
    pending: 'bg-gray-100 text-gray-500',
    running: 'bg-blue-100 text-blue-700',
    success: 'bg-green-100 text-green-700',
    failed: 'bg-red-100 text-red-700',
    skipped: 'bg-gray-100 text-gray-400',
  }
  return map[status] ?? 'bg-gray-100 text-gray-500'
}

function stageStatusText(stage: UpdateAllStage): string {
  if (stage.status === 'running') {
    if (stage.name === 'fleet_nodes' && updateAllJob.value) {
      const j = updateAllJob.value
      return `${j.completed_fleet_nodes} / ${j.total_fleet_nodes}`
    }
    return 'updating...'
  }
  const labels: Record<string, string> = {
    pending: 'pending',
    success: 'done',
    failed: 'failed',
    skipped: 'skipped',
  }
  return labels[stage.status] ?? stage.status
}

const updateAllButtonLabel = computed(() => {
  const job = updateAllJob.value
  if (!job) {
    // Compute how many stages would actually run
    const outdated = codeSync.outdatedCount.value
    const hasUpdate = codeSync.hasUpdate.value
    if (!hasUpdate && outdated === 0) return null // "already current" label
    return outdated > 0 ? `Update Everything (${outdated} node${outdated !== 1 ? 's' : ''})` : 'Update Everything'
  }
  if (job.status === 'running' || job.status === 'pending') return null // button shows spinner text
  if (job.status === 'completed') return null
  if (job.status === 'already_current') return null
  return 'Update Everything'
})

const updateAllIsRunning = computed(() => {
  const s = updateAllJob.value?.status
  return s === 'pending' || s === 'running'
})

const updateAllIsDone = computed(() => {
  const s = updateAllJob.value?.status
  return s === 'completed' || s === 'already_current' || s === 'failed'
})

function toggleStageLog(name: string): void {
  if (expandedStageLogs.value.has(name)) {
    expandedStageLogs.value.delete(name)
  } else {
    expandedStageLogs.value.add(name)
  }
}

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

// Formatted commit hash with full hash for tooltip (Issue #866)
const codeSourceCommit = computed(() => {
  return getCommitHashDisplay(codeSourceData.value?.last_known_commit)
})

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
  // Use 12-character format for consistency (Issue #866)
  return getCommitHashDisplay(version).display
}

function formatDate(dateStr: string | null): string {
  return formatDateTime(dateStr)
}

async function handleRefresh(): Promise<void> {
  logger.info('Refreshing code sync status')
  await codeSync.refreshVersion()
  await codeSync.fetchPendingNodes()
}

async function handleSyncNode(node: PendingNode): Promise<void> {
  logger.info('Syncing node:', node.node_id)
  syncingNodeId.value = node.node_id
  syncProgress.value.clear()
  syncStage.value = null

  const options: SyncOptions = {
    restart: restartAfterSync.value,
    strategy: syncStrategy.value,
  }

  const result = await codeSync.syncNode(node.node_id, options)

  if (result.success) {
    selectedNodes.value.delete(node.node_id)

    // Issue #1231: SLM self-sync is fire-and-forget — backend returns
    // before the background task completes and restarts the service.
    // Show a banner and auto-refresh after the restart window.
    const isSLMSelfSync = result.message?.includes('update queued')
    if (isSLMSelfSync) {
      slmRestartPending.value = true
      if (slmRefreshTimer) clearTimeout(slmRefreshTimer)
      slmRefreshTimer = setTimeout(async () => {
        slmRestartPending.value = false
        await handleRefresh()
      }, 65000)
    }

    logger.info('Node sync completed:', node.node_id)
  } else {
    logger.error('Node sync failed:', node.node_id, result.message)
  }

  syncingNodeId.value = null
  // Clear progress after a delay to show final message
  setTimeout(() => {
    syncProgress.value.delete(node.node_id)
    syncStage.value = null
  }, 3000)
}

async function handleSyncSelected(): Promise<void> {
  const nodeIds = Array.from(selectedNodes.value)
  logger.info('Syncing selected nodes:', nodeIds)
  codeSync.clearError()
  successMessage.value = null

  const result = await codeSync.syncFleet({
    node_ids: nodeIds,
    strategy: syncStrategy.value === 'manual' ? 'manual' : 'rolling',
    restart: restartAfterSync.value,
    batch_size: 1,
  })

  if (result.success) {
    const count = nodeIds.length
    successMessage.value = `Successfully synced ${count} node${count > 1 ? 's' : ''}`

    // Auto-dismiss after 5 seconds
    setTimeout(() => {
      successMessage.value = null
    }, 5000)

    selectedNodes.value.clear()
    await handleRefresh()
  } else {
    codeSync.setError(result.message || 'Fleet sync failed')
  }
}

async function handleSyncAll(): Promise<void> {
  logger.info('Syncing all outdated nodes')
  codeSync.clearError()
  successMessage.value = null

  const result = await codeSync.syncFleet({
    strategy: 'rolling',
    restart: restartAfterSync.value,
    batch_size: 1,
  })

  if (result.success) {
    const count = result.nodes_queued || codeSync.pendingNodes.value.length
    successMessage.value = `Successfully queued sync for ${count} node${count > 1 ? 's' : ''}`

    // Auto-dismiss after 5 seconds
    setTimeout(() => {
      successMessage.value = null
    }, 5000)

    selectedNodes.value.clear()
    await handleRefresh()
  } else {
    codeSync.setError(result.message || 'Fleet sync failed')
  }
}

// =============================================================================
// SLM Self-Update (#9073)
// =============================================================================

const selfUpdating = ref(false)

async function handleSelfUpdate(): Promise<void> {
  selfUpdating.value = true
  codeSync.clearError()
  successMessage.value = null

  const result = await codeSync.selfUpdate()
  selfUpdating.value = false

  if (result.success) {
    slmRestartPending.value = true
    if (slmRefreshTimer) clearTimeout(slmRefreshTimer)
    slmRefreshTimer = setTimeout(async () => {
      slmRestartPending.value = false
      await handleRefresh()
    }, 65000)
  } else {
    codeSync.setError(result.message || 'Self-update failed')
  }
}

// =============================================================================
// Role-Based Sync Methods (Issue #779)
// =============================================================================

async function handlePullFromSource(): Promise<void> {
  isPulling.value = true
  codeSync.clearError()
  successMessage.value = null

  const result = await codeSync.pullFromSource()
  isPulling.value = false

  if (result.success) {
    logger.info('Pulled from source:', result.commit)
    const shortCommit = result.commit?.substring(0, 12) || 'unknown'
    successMessage.value = `Successfully pulled latest changes (${shortCommit})`

    // Auto-dismiss success message after 5 seconds
    setTimeout(() => {
      successMessage.value = null
    }, 5000)

    // Refresh status to show updated commit
    await handleRefresh()
  } else {
    logger.error('Pull failed:', result.message)
    codeSync.setError(result.message || 'Failed to pull from source')
  }
}

async function handleSyncRole(roleName: string): Promise<void> {
  syncingRole.value = roleName
  const result = await codeSync.syncRole(roleName)
  syncingRole.value = null

  if (result.success) {
    logger.info('Role sync completed:', roleName, result.nodes_synced)
    await handleRefresh()
  } else {
    logger.error('Role sync failed:', result.message)
  }
}

// =============================================================================
// Code Source Methods (Issue #779)
// =============================================================================

async function handleCodeSourceSaved(): Promise<void> {
  await codeSourceComposable.fetchCodeSource()
}

async function handleRemoveCodeSource(): Promise<void> {
  if (!confirm('Remove code source assignment?')) return
  await codeSourceComposable.removeCodeSource()
}

// =============================================================================
// Schedule Methods (Issue #741 - Phase 7)
// =============================================================================

function openCreateScheduleModal(): void {
  editingSchedule.value = null
  showScheduleModal.value = true
}

function openEditScheduleModal(schedule: DeepReadonly<UpdateSchedule>): void {
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

async function handleDeleteSchedule(schedule: DeepReadonly<UpdateSchedule>): Promise<void> {
  if (!confirm(`Delete schedule "${schedule.name}"?`)) return

  const success = await codeSync.deleteSchedule(schedule.id)
  if (success) {
    logger.info('Schedule deleted:', schedule.id)
  }
}

async function handleToggleSchedule(schedule: DeepReadonly<UpdateSchedule>): Promise<void> {
  await codeSync.toggleSchedule(schedule.id, !schedule.enabled)
  logger.info('Schedule toggled:', schedule.id, !schedule.enabled)
}

async function handleRunSchedule(schedule: DeepReadonly<UpdateSchedule>): Promise<void> {
  runningScheduleId.value = schedule.id
  const result = await codeSync.runSchedule(schedule.id)
  runningScheduleId.value = null

  if (result?.success) {
    logger.info('Schedule run started:', schedule.id, result.job_id)
  }
}

function formatNextRun(dateStr: string | null): string {
  if (!dateStr) return 'Not scheduled'
  return formatDateTime(dateStr)
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
// Drift Detection (Issue #2834)
// =============================================================================

async function handleCheckDrift(): Promise<void> {
  isDriftLoading.value = true
  try {
    const result = await codeSync.fetchDrift(selectedDriftComponent.value)
    if (result) {
      driftReport.value = result
      showDriftDetails.value = true
    }
  } finally {
    isDriftLoading.value = false
  }
}

// #7149: Resync the selected component from code_source/, then re-check drift.
async function handleResolveDrift(): Promise<void> {
  if (!driftReport.value?.drift_detected) return
  isResolvingDrift.value = true
  try {
    const result = await codeSync.resolveDrift(selectedDriftComponent.value)
    if (result?.success) {
      successMessage.value = `Resynced ${result.component} from code_source`
      // Re-run drift check to confirm resolution
      await handleCheckDrift()
    }
    // Errors are surfaced via codeSync.error already
  } finally {
    isResolvingDrift.value = false
  }
}

// =============================================================================
// One-click update-all methods (#9971)
// =============================================================================

function _stopUpdateAllPoll(): void {
  if (updateAllPollTimer) {
    clearTimeout(updateAllPollTimer)
    updateAllPollTimer = null
  }
  updateAllPolling.value = false
}

function _scheduleUpdateAllPoll(): void {
  if (updateAllPolling.value) return
  updateAllPolling.value = true
  const poll = async () => {
    const job = await codeSync.getUpdateAllStatus()
    if (job) {
      updateAllJob.value = job
      if (job.status === 'running' || job.status === 'pending') {
        updateAllPollTimer = setTimeout(poll, 2000)
      } else {
        updateAllPolling.value = false
        // Refresh status / pending nodes once pipeline finishes
        await Promise.all([codeSync.fetchStatus(), codeSync.fetchPendingNodes()])
      }
    } else {
      _stopUpdateAllPoll()
    }
  }
  updateAllPollTimer = setTimeout(poll, 1000)
}

async function handleUpdateAll(): Promise<void> {
  codeSync.clearError()
  const job = await codeSync.startUpdateAll()
  if (job) {
    updateAllJob.value = job
    _scheduleUpdateAllPoll()
  }
}

// Resume polling if a job is already running when the view mounts
async function _checkExistingUpdateAllJob(): Promise<void> {
  const job = await codeSync.getUpdateAllStatus()
  if (job && (job.status === 'running' || job.status === 'pending')) {
    updateAllJob.value = job
    _scheduleUpdateAllPoll()
  } else if (job) {
    updateAllJob.value = job
  }
}

// =============================================================================
// Lifecycle
// =============================================================================

onMounted(async () => {
  logger.info('CodeSyncView mounted')
  await Promise.all([
    codeSync.fetchStatus(),
    codeSync.fetchPendingNodes(),
    codeSync.fetchSchedules(),
    codeSync.fetchRoles(),
    codeSourceComposable.fetchCodeSource(),
    _checkExistingUpdateAllJob(),
  ])
})

onUnmounted(() => {
  if (slmRefreshTimer) clearTimeout(slmRefreshTimer)
  _stopUpdateAllPoll()
})
</script>

<template>
  <div>
    <!-- Header -->
    <div class="flex items-center justify-between mb-6">
      <div>
        <h2 class="text-lg font-semibold text-gray-900">{{ $t('codeSyncView.codeSync') }}</h2>
        <p class="text-sm text-gray-500 mt-1">
          {{ $t('codeSyncView.manageAgentCodeVersions') }}
        </p>
      </div>
      <div class="flex items-center gap-2">
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
    </div>

    <!-- PRIMARY CTA: One-click update everything (#9971) -->
    <div class="card p-5 mb-6">
      <div class="flex items-start justify-between gap-4">
        <div class="flex-1">
          <h2 class="text-lg font-semibold text-gray-900 mb-1">{{ $t('codeSyncView.updatePipelineTitle') }}</h2>
          <p class="text-sm text-gray-500">{{ $t('codeSyncView.updatePipelineDesc') }}</p>
        </div>
        <div class="shrink-0">
          <!-- Already current state -->
          <button
            v-if="!codeSync.hasUpdate.value && codeSync.outdatedCount.value === 0 && !updateAllIsRunning"
            disabled
            class="btn btn-primary opacity-50 cursor-not-allowed flex items-center gap-2 min-w-[220px] justify-center"
          >
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" />
            </svg>
            {{ $t('codeSyncView.updateAllAlreadyCurrent') }}
          </button>
          <!-- Running state -->
          <button
            v-else-if="updateAllIsRunning"
            disabled
            class="btn btn-primary opacity-75 cursor-not-allowed flex items-center gap-2 min-w-[220px] justify-center"
          >
            <svg class="w-4 h-4 animate-spin" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
            </svg>
            {{ $t('codeSyncView.updateAllRunning') }}
          </button>
          <!-- Active state -->
          <button
            v-else
            @click="handleUpdateAll"
            class="btn btn-primary flex items-center gap-2 min-w-[220px] justify-center"
          >
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
            </svg>
            {{ updateAllButtonLabel || $t('codeSyncView.updateAll') }}
          </button>
        </div>
      </div>

      <!-- Pipeline progress display (shown when job exists) -->
      <div v-if="updateAllJob" class="mt-5">
        <!-- Stage track -->
        <div class="flex items-start gap-0 overflow-x-auto">
          <template v-for="(stage, idx) in updateAllJob.stages" :key="stage.name">
            <!-- Stage box -->
            <div class="flex flex-col items-center min-w-[120px]">
              <div
                :class="['px-3 py-2 rounded-lg text-xs font-medium w-full text-center', stageStatusClass(stage.status)]"
              >
                <div class="font-semibold mb-0.5">{{ stageLabel(stage.name) }}</div>
                <!-- Running spinner -->
                <div v-if="stage.status === 'running'" class="flex items-center justify-center gap-1">
                  <svg class="w-3 h-3 animate-spin" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                  </svg>
                  <span>{{ stageStatusText(stage) }}</span>
                </div>
                <div v-else class="text-xs">{{ stageStatusText(stage) }}</div>
              </div>
              <!-- SHA badge -->
              <div v-if="stage.sha" class="mt-1 text-xs text-gray-400">
                <a
                  v-if="getCommitUrl(stage.sha)"
                  :href="getCommitUrl(stage.sha)!"
                  target="_blank"
                  rel="noopener noreferrer"
                  class="font-mono text-primary-600 hover:underline"
                  :title="stage.sha"
                >{{ stage.sha }}</a>
                <span v-else class="font-mono">{{ stage.sha }}</span>
              </div>
              <!-- Deps badge -->
              <div v-if="stage.deps_changed" class="mt-1">
                <span class="inline-flex items-center px-1.5 py-0.5 rounded-sm text-xs bg-amber-100 text-amber-700 font-medium">
                  {{ $t('codeSyncView.depsBadge') }}
                </span>
              </div>
              <!-- Log expand toggle -->
              <button
                v-if="stage.log_lines && stage.log_lines.length > 0"
                @click="toggleStageLog(stage.name)"
                class="mt-1 text-xs text-primary-600 hover:text-primary-800"
              >
                {{ expandedStageLogs.has(stage.name) ? $t('codeSyncView.collapseLog') : $t('codeSyncView.expandLog') }}
              </button>
            </div>
            <!-- Connector arrow (not after last) -->
            <div
              v-if="idx < updateAllJob.stages.length - 1"
              class="flex items-center pt-4 px-1 text-gray-300 text-lg select-none"
            >›</div>
          </template>
        </div>

        <!-- Expanded stage logs -->
        <template v-for="stage in updateAllJob.stages" :key="`log-${stage.name}`">
          <div
            v-if="expandedStageLogs.has(stage.name) && stage.log_lines.length > 0"
            class="mt-3 bg-gray-900 rounded-md p-3 font-mono text-xs text-green-300 max-h-40 overflow-y-auto"
          >
            <div v-for="(line, i) in stage.log_lines" :key="i" class="leading-5">{{ line }}</div>
          </div>
        </template>

        <!-- Failure reason -->
        <div
          v-if="updateAllJob.status === 'failed' && updateAllJob.failure_reason"
          class="mt-3 bg-red-50 border border-red-200 rounded-md p-3 text-sm text-red-700"
        >
          {{ updateAllJob.failure_reason }}
        </div>

        <!-- Completed success -->
        <div
          v-if="updateAllJob.status === 'completed' || updateAllJob.status === 'already_current'"
          class="mt-3 flex items-center gap-2 text-sm text-green-700"
        >
          <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" />
          </svg>
          {{ updateAllJob.status === 'already_current' ? $t('codeSyncView.alreadyCurrent') : 'Update complete' }}
        </div>
      </div>
    </div>

    <!-- Status Banner -->
    <div class="card p-5 mb-6">
      <div class="grid grid-cols-1 md:grid-cols-4 gap-6">
        <div>
          <span class="text-sm text-gray-500 block mb-1">{{ $t('codeSyncView.latestVersion') }}</span>
          <a
            v-if="getCommitUrl(codeSync.latestVersion.value)"
            :href="getCommitUrl(codeSync.latestVersion.value)!"
            target="_blank"
            rel="noopener noreferrer"
            class="text-lg font-semibold font-mono text-primary-600 hover:text-primary-800 hover:underline cursor-pointer"
            :title="codeSync.latestVersion.value || 'View commit on GitHub'"
          >
            {{ formatVersion(codeSync.latestVersion.value) }}
          </a>
          <span
            v-else
            class="text-lg font-semibold font-mono text-gray-900"
          >
            {{ formatVersion(codeSync.latestVersion.value) }}
          </span>
        </div>
        <div>
          <span class="text-sm text-gray-500 block mb-1">{{ $t('codeSyncView.lastFetch') }}</span>
          <span class="text-lg font-semibold text-gray-900">
            {{ formatDate(codeSync.status.value?.last_fetch ?? null) }}
          </span>
        </div>
        <div>
          <span class="text-sm text-gray-500 block mb-1">{{ $t('codeSyncView.outdatedNodes') }}</span>
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
            {{ $t('codeSyncView.updatesAvailable') }}
          </span>
          <span
            v-else
            class="inline-flex items-center px-3 py-1 rounded-full text-sm font-medium bg-green-100 text-green-800"
          >
            <svg class="w-4 h-4 mr-1.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" />
            </svg>
            {{ $t('codeSyncView.allUpToDate') }}
          </span>
        </div>
      </div>
    </div>

    <!-- Sync Progress Banner (Issue #880) -->
    <div
      v-if="syncingNodeId && syncProgress.size > 0"
      class="bg-blue-50 border border-blue-200 rounded-lg p-4 mb-6"
    >
      <div class="flex items-center gap-3">
        <svg class="w-5 h-5 text-blue-600 animate-spin" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
        </svg>
        <div class="flex-1">
          <div class="font-medium text-blue-900">{{ $t('codeSyncView.syncInProgress') }}</div>
          <div class="text-sm text-blue-700">
            {{ Array.from(syncProgress.values())[0] }}
          </div>
        </div>
      </div>
    </div>

    <!-- SLM Self-Sync Restart Banner (Issue #1231) -->
    <div
      v-if="slmRestartPending"
      class="bg-amber-50 border border-amber-200 rounded-lg p-4 mb-6"
    >
      <div class="flex items-center gap-3">
        <svg class="w-5 h-5 text-amber-600 animate-spin" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
        </svg>
        <div class="flex-1">
          <div class="font-medium text-amber-900">{{ $t('codeSyncView.sLMManagerRestarting') }}</div>
          <div class="text-sm text-amber-700">
            {{ $t('codeSyncView.codeSyncedSuccessfullyBackend') }}
          </div>
        </div>
      </div>
    </div>

    <!-- Advanced / Diagnostics accordion (#9971 — demoted from primary) -->
    <div class="mb-6">
      <button
        @click="showAdvanced = !showAdvanced"
        class="w-full flex items-center justify-between px-4 py-3 bg-gray-100 hover:bg-gray-200 rounded-lg text-sm font-medium text-gray-700 transition-colors"
        :aria-expanded="showAdvanced"
      >
        <span>{{ $t('codeSyncView.advancedDiagnostics') }}</span>
        <svg
          :class="['w-4 h-4 transition-transform', showAdvanced ? 'rotate-180' : '']"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
        </svg>
      </button>
      <div v-if="showAdvanced" class="mt-1 p-3 bg-amber-50 border border-amber-200 rounded-b-lg text-xs text-amber-700 leading-5">
        {{ $t('codeSyncView.advancedWarning') }}
      </div>
    </div>

    <div v-if="showAdvanced">

    <!-- Advanced: Pull / Self-Update buttons -->
    <div class="flex items-center gap-2 mb-6">
      <button
        @click="handlePullFromSource"
        :disabled="isPulling"
        class="btn btn-secondary flex items-center gap-2"
      >
        <svg
          :class="['w-4 h-4', isPulling ? 'animate-spin' : '']"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            stroke-linecap="round"
            stroke-linejoin="round"
            stroke-width="2"
            d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"
          />
        </svg>
        {{ isPulling ? 'Pulling...' : 'Pull from Source' }}
      </button>
      <button
        @click="handleSelfUpdate"
        :disabled="selfUpdating || slmRestartPending"
        class="btn btn-secondary flex items-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
        title="Sync code from source and restart this SLM server (files only — see Advanced warning)"
      >
        <svg
          :class="['w-4 h-4', selfUpdating ? 'animate-spin' : '']"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            stroke-linecap="round"
            stroke-linejoin="round"
            stroke-width="2"
            d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12"
          />
        </svg>
        {{ selfUpdating ? 'Updating...' : 'Update This Server' }}
      </button>
    </div>

    <!-- Code Source Card (Issue #779) -->
    <div class="card p-5 mb-6">
      <div class="flex items-center justify-between mb-4">
        <h2 class="text-lg font-semibold text-gray-900">{{ $t('codeSyncView.codeSource') }}</h2>
        <button
          @click="showCodeSourceModal = true"
          class="btn btn-primary text-sm"
        >
          {{ codeSourceData ? 'Edit' : 'Configure' }}
        </button>
      </div>

      <div v-if="codeSourceData" class="flex items-center justify-between">
        <div>
          <p class="font-medium text-gray-900">{{ codeSourceData.hostname || codeSourceData.node_id }}</p>
          <p class="text-sm text-gray-500">{{ codeSourceData.repo_path }} ({{ codeSourceData.branch }})</p>
          <p class="text-sm text-gray-500">
            {{ $t('codeSyncView.lastCommit') }}
            <a
              v-if="getCommitUrl(codeSourceCommit.full)"
              :href="getCommitUrl(codeSourceCommit.full)!"
              target="_blank"
              rel="noopener noreferrer"
              class="font-mono text-primary-600 hover:text-primary-800 hover:underline"
              :title="codeSourceCommit.full || 'View commit on GitHub'"
            >
              {{ codeSourceCommit.display }}
            </a>
            <span
              v-else
              class="font-mono cursor-help"
              :title="codeSourceCommit.full || 'Full commit hash unavailable'"
            >
              {{ codeSourceCommit.display }}
            </span>
          </p>
        </div>
        <button @click="handleRemoveCodeSource" class="btn btn-danger text-sm">
          {{ $t('codeSyncView.remove') }}
        </button>
      </div>
      <div v-else class="text-gray-500">
        {{ $t('codeSyncView.noCodeSourceConfigured') }}
      </div>
    </div>

    <!-- Deployed-vs-Source File Drift (Issue #2834) -->
    <div class="card p-5 mb-6">
      <div class="flex items-center justify-between mb-4">
        <div>
          <h2 class="text-lg font-semibold text-gray-900">{{ $t('codeSyncView.fileDriftCheck') }}</h2>
          <p class="text-sm text-gray-500 mt-1">
            {{ $t('codeSyncView.compareChecksumsBetweenCode') }}
          </p>
        </div>
        <div class="flex items-center gap-3">
          <label for="drift-component-select" class="text-sm text-gray-600 font-medium whitespace-nowrap">{{ $t('codeSyncView.component') }}</label>
          <select
            id="drift-component-select"
            v-model="selectedDriftComponent"
            :disabled="isDriftLoading"
            class="form-select text-sm rounded border-gray-300 focus:border-primary-500 focus:ring-primary-500"
          >
            <option value="autobot-slm-backend">autobot-slm-backend</option>
            <option value="autobot-slm-frontend">autobot-slm-frontend</option>
            <option value="autobot-backend">autobot-backend</option>
            <option value="autobot-frontend">autobot-frontend</option>
          </select>
          <button
            @click="handleCheckDrift"
            :disabled="isDriftLoading"
            class="btn btn-secondary flex items-center gap-2 text-sm"
          >
            <svg
              :class="['w-4 h-4', isDriftLoading ? 'animate-spin' : '']"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                stroke-linecap="round"
                stroke-linejoin="round"
                stroke-width="2"
                d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2"
              />
            </svg>
            {{ isDriftLoading ? 'Checking...' : 'Check Drift' }}
          </button>
        </div>
      </div>

      <!-- Drift result summary -->
      <div v-if="driftReport">
        <div class="flex items-center gap-3 mb-3">
          <span
            v-if="driftReport.drift_detected"
            class="inline-flex items-center px-3 py-1 rounded-full text-sm font-medium bg-red-100 text-red-800"
          >
            <svg class="w-4 h-4 mr-1.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
            {{ driftReport.drifted_files.length }} drifted file{{ driftReport.drifted_files.length !== 1 ? 's' : '' }} detected
          </span>
          <span
            v-else
            class="inline-flex items-center px-3 py-1 rounded-full text-sm font-medium bg-green-100 text-green-800"
          >
            <svg class="w-4 h-4 mr-1.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" />
            </svg>
            No drift detected ({{ driftReport.total_compared }} files compared)
          </span>
          <span class="text-sm text-gray-400">
            Checked {{ formatDate(driftReport.checked_at) }}
          </span>
        </div>

        <div class="text-xs text-gray-400 mb-3">
          {{ $t('codeSyncView.source') }} <code class="font-mono">{{ driftReport.source_dir }}</code>
          {{ $t('codeSyncView.nbspRarrNbspDeployed') }} <code class="font-mono">{{ driftReport.deployed_dir }}</code>
        </div>

        <!-- Action row: Resync (#7149) + Toggle details -->
        <div v-if="driftReport.drift_detected" class="flex items-center gap-3 mb-3">
          <button
            @click="handleResolveDrift"
            :disabled="isResolvingDrift || isDriftLoading"
            class="btn btn-primary flex items-center gap-2 text-sm"
            :title="`Run rsync from ${driftReport.source_dir} to ${driftReport.deployed_dir}`"
          >
            <svg
              :class="['w-4 h-4', isResolvingDrift ? 'animate-spin' : '']"
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
            {{ isResolvingDrift ? 'Resyncing...' : 'Resync from Source' }}
          </button>
          <button
            @click="showDriftDetails = !showDriftDetails"
            class="text-sm text-primary-600 hover:text-primary-800 font-medium"
          >
            {{ showDriftDetails ? 'Hide details' : 'Show details' }}
          </button>
        </div>

        <!-- Drifted files table -->
        <div v-if="showDriftDetails && driftReport.drifted_files.length > 0" class="overflow-x-auto">
          <table class="min-w-full text-sm">
            <thead>
              <tr class="text-left text-gray-500 border-b">
                <th class="pb-2 pr-4 font-medium">{{ $t('codeSyncView.status') }}</th>
                <th class="pb-2 pr-4 font-medium">{{ $t('codeSyncView.file') }}</th>
                <th class="pb-2 pr-4 font-medium">{{ $t('codeSyncView.sourceSHA256') }}</th>
                <th class="pb-2 font-medium">{{ $t('codeSyncView.deployedSHA256') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="file in driftReport.drifted_files"
                :key="file.path"
                class="border-b last:border-0"
              >
                <td class="py-2 pr-4">
                  <span
                    :class="{
                      'text-yellow-700 bg-yellow-100 px-2 py-0.5 rounded text-xs': file.status === 'modified',
                      'text-blue-700 bg-blue-100 px-2 py-0.5 rounded text-xs': file.status === 'source_only',
                      'text-orange-700 bg-orange-100 px-2 py-0.5 rounded text-xs': file.status === 'deployed_only',
                    }"
                  >
                    {{ file.status === 'modified' ? 'Modified' : file.status === 'source_only' ? 'Source only' : 'Deployed only' }}
                  </span>
                </td>
                <td class="py-2 pr-4 font-mono text-xs text-gray-700">{{ file.path }}</td>
                <td class="py-2 pr-4 font-mono text-xs text-gray-500">
                  {{ file.source_checksum ? file.source_checksum.substring(0, 16) + '...' : '—' }}
                </td>
                <td class="py-2 font-mono text-xs text-gray-500">
                  {{ file.deployed_checksum ? file.deployed_checksum.substring(0, 16) + '...' : '—' }}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- Placeholder when not yet checked -->
      <div v-else class="text-sm text-gray-400">
        {{ $t('codeSyncView.clickCheckDriftTo') }}
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
        {{ $t('codeSyncView.dismiss') }}
      </button>
    </div>

    <!-- Success Display -->
    <div
      v-if="successMessage"
      class="bg-green-50 border border-green-200 rounded-lg p-4 mb-6 flex items-center justify-between"
    >
      <div class="flex items-center gap-3">
        <svg class="w-5 h-5 text-green-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
        <span class="text-green-700">{{ successMessage }}</span>
      </div>
      <button
        @click="successMessage = null"
        class="text-green-600 hover:text-green-800 font-medium text-sm"
      >
        {{ $t('codeSyncView.dismiss') }}
      </button>
    </div>

    <!-- Sync Options -->
    <div class="card p-5 mb-6">
      <h2 class="text-lg font-semibold text-gray-800 mb-4">{{ $t('codeSyncView.syncOptions') }}</h2>
      <div class="flex flex-wrap items-center gap-6">
        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">{{ $t('codeSyncView.restartStrategy') }}</label>
          <select
            v-model="syncStrategy"
            class="px-3 py-2 border border-gray-300 rounded-md focus:ring-primary-500 focus:border-primary-500"
          >
            <option value="graceful">{{ $t('codeSyncView.gracefulWaitForTasks') }}</option>
            <option value="immediate">{{ $t('codeSyncView.immediate') }}</option>
            <option value="manual">{{ $t('codeSyncView.manualNoRestart') }}</option>
          </select>
        </div>
        <div class="flex items-center">
          <label class="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              v-model="restartAfterSync"
              class="w-4 h-4 text-primary-600 rounded-sm focus:ring-primary-500"
            />
            <span class="text-sm text-gray-700">{{ $t('codeSyncView.restartServiceAfterSync') }}</span>
          </label>
        </div>
      </div>
    </div>

    <!-- Pending Updates Section -->
    <div class="card overflow-hidden">
      <!-- Section Header -->
      <div class="px-6 py-4 border-b border-gray-200 flex items-center justify-between">
        <h2 class="text-lg font-semibold text-gray-800">{{ $t('codeSyncView.pendingUpdates') }}</h2>
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
            {{ $t('codeSyncView.syncAll') }}
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
        <h3 class="text-lg font-medium text-gray-900 mb-2">{{ $t('codeSyncView.allNodesAreUp') }}</h3>
        <p class="text-gray-500">
          {{ $t('codeSyncView.noCodeUpdatesAre') }}
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
                class="w-4 h-4 text-primary-600 rounded-sm focus:ring-primary-500"
              />
            </th>
            <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">{{ $t('codeSyncView.hostname') }}</th>
            <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">{{ $t('codeSyncView.iPAddress') }}</th>
            <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">{{ $t('codeSyncView.currentVersion') }}</th>
            <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">{{ $t('codeSyncView.status') }}</th>
            <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">{{ $t('codeSyncView.actions') }}</th>
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
                class="w-4 h-4 text-primary-600 rounded-sm focus:ring-primary-500"
              />
            </td>
            <td class="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">
              {{ node.hostname }}
            </td>
            <td class="px-6 py-4 whitespace-nowrap text-sm font-mono text-gray-500">
              {{ node.ip_address }}
            </td>
            <td class="px-6 py-4 whitespace-nowrap text-sm font-mono text-gray-500">
              <a
                v-if="getCommitUrl(node.current_version)"
                :href="getCommitUrl(node.current_version)!"
                target="_blank"
                rel="noopener noreferrer"
                class="text-primary-600 hover:text-primary-800 hover:underline"
                :title="node.current_version || 'View commit on GitHub'"
              >
                {{ formatVersion(node.current_version) }}
              </a>
              <span v-else :title="node.current_version || 'Full commit hash unavailable'">
                {{ formatVersion(node.current_version) }}
              </span>
            </td>
            <td class="px-6 py-4 whitespace-nowrap">
              <span class="px-2 py-1 text-xs font-medium rounded-full bg-yellow-100 text-yellow-800">
                {{ $t('codeSyncView.outdated') }}
              </span>
            </td>
            <td class="px-6 py-4">
              <button
                @click="handleSyncNode(node)"
                :disabled="syncingNodeId === node.node_id"
                class="text-primary-600 hover:text-primary-800 font-medium text-sm disabled:opacity-50"
              >
                {{ syncingNodeId === node.node_id ? 'Syncing...' : 'Sync' }}
              </button>
              <!-- Progress indicator (Issue #880) -->
              <div
                v-if="syncingNodeId === node.node_id && syncProgress.has(node.node_id)"
                class="mt-1 text-xs text-gray-600 flex items-center gap-1"
              >
                <svg class="w-3 h-3 animate-spin" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                </svg>
                <span>{{ syncProgress.get(node.node_id) }}</span>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Role-Based Sync Section (Issue #779) -->
    <div class="card p-5 mt-6">
      <div class="flex items-center justify-between mb-4">
        <h2 class="text-lg font-semibold text-gray-900">{{ $t('codeSyncView.roleBasedSync') }}</h2>
        <!-- Pull from Source button moved to page header next to Refresh -->
      </div>

      <div v-if="codeSync.roles.value.length === 0" class="text-gray-500">
        {{ $t('codeSyncView.noRolesConfiguredAdd') }}
      </div>

      <div v-else class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        <div
          v-for="role in codeSync.roles.value"
          :key="role.name"
          class="p-4 bg-gray-50 rounded-lg border border-gray-200"
        >
          <div class="flex items-center justify-between mb-2">
            <span class="font-medium text-gray-900">{{ role.display_name || role.name }}</span>
            <span
              v-if="role.auto_restart"
              class="text-xs px-2 py-1 bg-blue-100 text-blue-700 rounded-sm"
            >
              auto-restart
            </span>
          </div>
          <p class="text-sm text-gray-500 mb-3 truncate" :title="role.target_path">
            {{ role.target_path }}
          </p>
          <button
            @click="handleSyncRole(role.name)"
            :disabled="syncingRole === role.name"
            class="btn btn-primary btn-sm w-full"
          >
            {{ syncingRole === role.name ? 'Syncing...' : 'Sync All Nodes' }}
          </button>
        </div>
      </div>
    </div>

    <!-- Schedules Section (Issue #741 - Phase 7) -->
    <div class="card overflow-hidden mt-6">
      <!-- Section Header -->
      <div class="px-6 py-4 border-b border-gray-200 flex items-center justify-between">
        <div>
          <h2 class="text-lg font-semibold text-gray-800">{{ $t('codeSyncView.scheduledUpdates') }}</h2>
          <p class="text-sm text-gray-500 mt-0.5">{{ $t('codeSyncView.configureAutomaticCodeSync') }}</p>
        </div>
        <button
          @click="openCreateScheduleModal"
          class="btn btn-primary flex items-center gap-2"
        >
          <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4" />
          </svg>
          {{ $t('codeSyncView.addSchedule') }}
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
        <h3 class="text-lg font-medium text-gray-900 mb-2">{{ $t('codeSyncView.noSchedulesConfigured') }}</h3>
        <p class="text-gray-500 mb-4">
          {{ $t('codeSyncView.createAScheduleTo') }}
        </p>
        <button
          @click="openCreateScheduleModal"
          class="btn btn-primary"
        >
          {{ $t('codeSyncView.createFirstSchedule') }}
        </button>
      </div>

      <!-- Schedules Table -->
      <table v-if="codeSync.schedules.value.length > 0" class="min-w-full divide-y divide-gray-200">
        <thead class="bg-gray-50">
          <tr>
            <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">{{ $t('codeSyncView.name') }}</th>
            <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">{{ $t('codeSyncView.schedule') }}</th>
            <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">{{ $t('codeSyncView.nextRun') }}</th>
            <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">{{ $t('codeSyncView.status') }}</th>
            <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">{{ $t('codeSyncView.actions') }}</th>
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
                  'relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-hidden',
                  schedule.enabled ? 'bg-primary-600' : 'bg-gray-200',
                ]"
              >
                <span
                  :class="[
                    'pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow-sm ring-0 transition duration-200 ease-in-out',
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
                  {{ $t('codeSyncView.edit') }}
                </button>
                <span class="text-gray-300">|</span>
                <button
                  @click="handleDeleteSchedule(schedule)"
                  class="text-red-600 hover:text-red-800 font-medium"
                >
                  {{ $t('codeSyncView.delete') }}
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
      :schedule="(editingSchedule as UpdateSchedule | null)"
      :nodes="(codeSync.pendingNodes.value as PendingNode[])"
      @close="closeScheduleModal"
      @save="handleSaveSchedule"
    />

    </div><!-- end v-if="showAdvanced" -->

    <!-- Code Source Modal (Issue #779) — always mounted for advanced section -->
    <CodeSourceModal
      v-if="showCodeSourceModal"
      :current-node-id="codeSourceData?.node_id"
      :current-repo-path="codeSourceData?.repo_path"
      :current-branch="codeSourceData?.branch"
      @close="showCodeSourceModal = false"
      @saved="handleCodeSourceSaved"
    />
  </div>
</template>
