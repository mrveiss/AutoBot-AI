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
  isSelfUpdateReconnecting,
  classifyUpdateAllPollError,
  SLM_SELF_UPDATE_STAGE,
  type PendingNode,
  type SyncOptions,
  type UpdateSchedule,
  type ScheduleCreateRequest,
  type FileDriftReport,
  type UpdateAllJob,
  type UpdateAllStage,
  type ComponentSyncJobStatus,
  type FleetSyncJobStatus,
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
// #13851: untracked files (present on the host, absent from this component's
// source) are reported separately from drift and collapsed by default — they
// are informational, and "Resync from source" would DELETE them.
const showUntrackedDetails = ref(false)
const untrackedFiles = computed(() => driftReport.value?.untracked_files ?? [])
const selectedDriftComponent = ref('autobot-slm-backend')

// Async drift/resolve job polling (#11303) — mirrors the update-all pattern so
// the Resync button returns immediately instead of blocking on the rsync +
// post-sync steps (which can take 40-120s and may restart the component itself).
const resolveDriftJob = ref<ComponentSyncJobStatus | null>(null)
const resolveDriftPolling = ref(false)
const resolveDriftTransientErrors = ref(0)
const RESOLVE_DRIFT_MAX_TRANSIENT_ERRORS = 90 // ~3 min at 2s intervals
const RESOLVE_DRIFT_LOST_CONTACT_ERRORS = 30 // ~1 min before "lost contact" banner
const resolveDriftLostContact = ref(false)
// #13851: the resolve refused because it would have deleted deployed paths that
// source does not have. The paths are inside the job message (the job row
// carries no structured field); this flag only decides whether to offer the
// override, so it keys off the backend's own refusal wording.
const RESOLVE_BLOCKED_MARKER = 'would be DELETED'
const resolveDriftBlocked = ref(false)
let resolveDriftPollTimer: ReturnType<typeof setTimeout> | null = null

// Clear stale results when the user switches to a different component (#3433)
watch(selectedDriftComponent, () => {
  driftReport.value = null
  showDriftDetails.value = false
  showUntrackedDetails.value = false
})

// =============================================================================
// Fleet sync job tracking (#13157)
// =============================================================================
// `syncFleet` returns a `job_id` for an asynchronous, per-node rollout, but the
// view used to throw it away: the "queued" toast was the last thing an operator
// ever saw, so a job that failed minutes later reported nothing and the
// backend's `failure_reason` (`autobot-slm-backend/api/code_sync.py:402`) had no
// route to the screen at all. These poll `getJobStatus` for the job just
// started and list the last few jobs via `getRecentJobs`.
const fleetSyncJob = ref<FleetSyncJobStatus | null>(null)
const fleetSyncPolling = ref(false)
const recentFleetJobs = ref<FleetSyncJobStatus[]>([])
const recentFleetJobsLoading = ref(false)
const FLEET_JOB_POLL_INTERVAL_MS = 2000
const RECENT_FLEET_JOBS_LIMIT = 5
let fleetSyncPollTimer: ReturnType<typeof setTimeout> | null = null

// =============================================================================
// One-click update-all state (#9971)
// =============================================================================
const updateAllJob = ref<UpdateAllJob | null>(null)
const updateAllPolling = ref(false)
// F1: track consecutive transient errors to bound backoff
const updateAllTransientErrors = ref(0)
const UPDATE_ALL_MAX_TRANSIENT_ERRORS = 90  // ~3 min at 2s intervals
const UPDATE_ALL_LOST_CONTACT_ERRORS = 30   // ~1 min before "lost contact" banner
const updateAllLostContact = ref(false)
let updateAllPollTimer: ReturnType<typeof setTimeout> | null = null
const showAdvanced = ref(false)
const expandedStageLogs = ref<Set<string>>(new Set())

// Returns the i18n key for a stage name (used in template with $t).
function stageI18nKey(name: string): string {
  const keyMap: Record<string, string> = {
    github_fetch: 'codeSyncView.githubFetchStage',
    code_source_pull: 'codeSyncView.codeSourcePullStage',
    slm_self_update: 'codeSyncView.slmSelfUpdateStage',
    fleet_nodes: 'codeSyncView.fleetNodesStage',
  }
  return keyMap[name] ?? name
}

function stageStatusClass(stageStatus: string): string {
  const map: Record<string, string> = {
    pending: 'bg-gray-100 text-gray-500',
    running: 'bg-blue-100 text-blue-700',
    success: 'bg-green-100 text-green-700',
    failed: 'bg-red-100 text-red-700',
    skipped: 'bg-gray-100 text-gray-400',
    current: 'bg-green-50 text-green-600',
  }
  return map[stageStatus] ?? 'bg-gray-100 text-gray-500'
}

// F2: returns an i18n key for the stage status text
function stageStatusI18nKey(stage: UpdateAllStage): string {
  if (stage.status === 'running') {
    if (stage.name === 'fleet_nodes') {
      return 'codeSyncView.fleetNodesProgress'
    }
    return 'codeSyncView.pipelineStageRunning'
  }
  const keyMap: Record<string, string> = {
    pending: 'codeSyncView.pipelineStagePending',
    success: 'codeSyncView.pipelineStageSuccess',
    failed: 'codeSyncView.pipelineStageFailed',
    skipped: 'codeSyncView.pipelineStageSkipped',
    current: 'codeSyncView.pipelineStageCurrent',
  }
  return keyMap[stage.status] ?? stage.status
}

// Keep stageStatusText for the fleet progress fraction (non-i18n interpolation)
function stageStatusText(stage: UpdateAllStage): string | null {
  if (stage.status === 'running' && stage.name === 'fleet_nodes' && updateAllJob.value) {
    const j = updateAllJob.value
    return `${j.completed_fleet_nodes} / ${j.total_fleet_nodes}`
  }
  return null
}

// #12593: while reconnecting, the stage-3 box shows "reconnecting..." instead
// of the generic "updating..." so the self-restart window doesn't read as dead.
function stageRunningStatusKey(stage: UpdateAllStage): string {
  if (stage.name === SLM_SELF_UPDATE_STAGE && updateAllReconnecting.value) {
    return 'codeSyncView.pipelineStageReconnecting'
  }
  return stageStatusI18nKey(stage)
}

const updateAllButtonLabel = computed(() => {
  const job = updateAllJob.value
  if (!job) {
    // F2: use i18n key via $t in template; return key string for use there
    return 'codeSyncView.updateAll'
  }
  if (job.status === 'running' || job.status === 'pending') return null
  if (job.status === 'completed') return null
  if (job.status === 'already_current') return null
  return 'codeSyncView.updateAll'
})

const updateAllIsRunning = computed(() => {
  const s = updateAllJob.value?.status
  return s === 'pending' || s === 'running'
})

// #12593: reconnecting affordance during the stage-3 (slm_self_update) window,
// when the SLM control plane restarts itself and polling fails transiently.
// Derives from the last-known running stage + transient-error count, so it
// resets to false automatically as soon as a poll succeeds again.
const updateAllReconnecting = computed(() =>
  isSelfUpdateReconnecting(updateAllJob.value, updateAllTransientErrors.value),
)

// #12593: auto-expand stage-3 logs while reconnecting so the backend
// "service will restart" message is visible during the restart window.
watch(updateAllReconnecting, (reconnecting) => {
  if (reconnecting) expandedStageLogs.value.add(SLM_SELF_UPDATE_STAGE)
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

// `current_version` / `stage.sha` are optional *and* nullable in the contract
// (`autobot-slm-backend/models/schemas.py:1721`), so `undefined` is reachable.
// `getCommitHashDisplay` already accepts it; only this wrapper narrowed it out.
function formatVersion(version: string | null | undefined): string {
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
    // #13157: the rollout is asynchronous — follow the returned job so a later
    // per-node failure and its `failure_reason` still reach the operator.
    trackFleetSyncJob(result.job_id)
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
    // #13157: same asynchronous rollout as handleSyncSelected.
    trackFleetSyncJob(result.job_id)
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

function _stopResolveDriftPoll(): void {
  if (resolveDriftPollTimer) {
    clearTimeout(resolveDriftPollTimer)
    resolveDriftPollTimer = null
  }
  resolveDriftPolling.value = false
}

/**
 * A transient error means the request never reached the poller (e.g. the
 * component restarting itself). Returns true if polling should continue.
 */
function _handleResolveDriftTransientError(): boolean {
  resolveDriftTransientErrors.value += 1
  if (resolveDriftTransientErrors.value >= RESOLVE_DRIFT_MAX_TRANSIENT_ERRORS) {
    resolveDriftLostContact.value = true
    _stopResolveDriftPoll()
    isResolvingDrift.value = false
    return false
  }
  if (resolveDriftTransientErrors.value >= RESOLVE_DRIFT_LOST_CONTACT_ERRORS) {
    resolveDriftLostContact.value = true
  }
  return true
}

/** Job reached a terminal status ('completed'/'failed') — stop polling and report. */
async function _handleResolveDriftTerminal(result: ComponentSyncJobStatus): Promise<void> {
  _stopResolveDriftPoll()
  isResolvingDrift.value = false
  if (result.status === 'completed' && result.success) {
    successMessage.value = result.message || `Resynced ${result.component} from code_source`
    await handleCheckDrift()
    return
  }
  // #13851: a refusal is not a failure — the resolve would have DELETED
  // deployed paths that source does not have, and it named them in the
  // message. Surfacing it as a plain error would leave the operator with no
  // way forward inside the GUI, which is the only sanctioned updater.
  resolveDriftBlocked.value = (result.message || '').includes(RESOLVE_BLOCKED_MARKER)
  codeSync.setError(result.message || 'Drift resolve job failed')
}

/**
 * Resilient polling loop for the async drift/resolve job (#11303). Mirrors
 * _scheduleUpdateAllPoll: undefined = transient error (component's own
 * restart) → keep polling; null = unknown job_id → stop; otherwise update the
 * job state and keep polling until a terminal status.
 */
function _scheduleResolveDriftPoll(jobId: string): void {
  if (resolveDriftPolling.value) return
  resolveDriftPolling.value = true
  resolveDriftTransientErrors.value = 0

  const poll = async () => {
    const result = await codeSync.getResolveDriftStatus(jobId)

    if (result === undefined) {
      if (_handleResolveDriftTransientError()) {
        resolveDriftPollTimer = setTimeout(poll, 2000)
      }
      return
    }

    resolveDriftLostContact.value = false
    resolveDriftTransientErrors.value = 0

    if (result === null) {
      _stopResolveDriftPoll()
      isResolvingDrift.value = false
      return
    }

    resolveDriftJob.value = result
    if (result.status === 'running' || result.status === 'queued') {
      resolveDriftPollTimer = setTimeout(poll, 2000)
      return
    }

    await _handleResolveDriftTerminal(result)
  }

  resolveDriftPollTimer = setTimeout(poll, 1000)
}

// #7149/#11303: Resync the selected component from code_source/ as an async
// job so the button returns immediately instead of blocking on the rsync +
// post-sync steps (which can take 40-120s and may restart the component).
async function handleResolveDrift(force = false): Promise<void> {
  if (!driftReport.value?.drift_detected) return
  codeSync.clearError()
  resolveDriftLostContact.value = false
  resolveDriftJob.value = null
  // #13851: a previous refusal is answered by this attempt — clear it so a
  // stale "would delete N paths" banner cannot outlive the run it described.
  resolveDriftBlocked.value = false
  isResolvingDrift.value = true
  const job = await codeSync.startResolveDriftAsync(selectedDriftComponent.value, force)
  if (!job) {
    isResolvingDrift.value = false
    return
  }
  _scheduleResolveDriftPoll(job.job_id)
}

// =============================================================================
// Fleet sync job methods (#13157)
// =============================================================================

function _stopFleetJobPoll(): void {
  if (fleetSyncPollTimer) {
    clearTimeout(fleetSyncPollTimer)
    fleetSyncPollTimer = null
  }
  fleetSyncPolling.value = false
}

/** Load the last few fleet sync jobs so past failures stay inspectable. */
async function loadRecentFleetJobs(): Promise<void> {
  recentFleetJobsLoading.value = true
  try {
    recentFleetJobs.value = await codeSync.getRecentJobs(RECENT_FLEET_JOBS_LIMIT)
  } finally {
    recentFleetJobsLoading.value = false
  }
}

/**
 * Poll one fleet sync job to completion.
 *
 * `getJobStatus` is a single-shot call that already reports its own failures
 * through `codeSync.error` and returns `null`, so `null` ends the loop rather
 * than being retried here.
 */
function _scheduleFleetJobPoll(jobId: string): void {
  if (fleetSyncPolling.value) return
  fleetSyncPolling.value = true

  const poll = async () => {
    const result = await codeSync.getJobStatus(jobId)
    if (result === null) {
      _stopFleetJobPoll()
      return
    }
    fleetSyncJob.value = result
    if (result.status === 'pending' || result.status === 'running') {
      fleetSyncPollTimer = setTimeout(poll, FLEET_JOB_POLL_INTERVAL_MS)
      return
    }
    _stopFleetJobPoll()
    await loadRecentFleetJobs()
  }

  fleetSyncPollTimer = setTimeout(poll, FLEET_JOB_POLL_INTERVAL_MS)
}

/** Begin tracking the job a just-queued fleet sync returned (#13157). */
function trackFleetSyncJob(jobId: string | undefined): void {
  if (!jobId) return
  _stopFleetJobPoll()
  fleetSyncJob.value = null
  _scheduleFleetJobPoll(jobId)
}

function fleetJobStatusClass(jobStatus: string): string {
  const map: Record<string, string> = {
    pending: 'bg-gray-100 text-gray-500',
    running: 'bg-blue-100 text-blue-700',
    completed: 'bg-green-100 text-green-700',
    failed: 'bg-red-100 text-red-700',
  }
  return map[jobStatus] ?? 'bg-gray-100 text-gray-500'
}

function fleetJobStatusI18nKey(jobStatus: string): string {
  const map: Record<string, string> = {
    pending: 'codeSyncView.pipelineStagePending',
    running: 'codeSyncView.pipelineStageRunning',
    completed: 'codeSyncView.pipelineStageSuccess',
    failed: 'codeSyncView.pipelineStageFailed',
  }
  return map[jobStatus] ?? jobStatus
}

// Refresh the recent-jobs list whenever the Advanced section is opened, so the
// list an operator reads is never a stale snapshot from an earlier visit.
watch(showAdvanced, (open) => {
  if (open) void loadRecentFleetJobs()
})

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

/**
 * F1: Resilient polling loop.
 *   - null   = 404, no job → stop
 *   - undefined = transient error (network/5xx) → keep polling with bounded backoff
 *   - UpdateAllJob = update UI, decide whether to continue
 */
function _scheduleUpdateAllPoll(): void {
  if (updateAllPolling.value) return
  updateAllPolling.value = true
  updateAllTransientErrors.value = 0

  const poll = async () => {
    const result = await codeSync.getUpdateAllStatus()

    if (result === undefined) {
      // Transient error (SLM restart in progress)
      updateAllTransientErrors.value += 1
      const decision = classifyUpdateAllPollError(
        updateAllTransientErrors.value,
        UPDATE_ALL_LOST_CONTACT_ERRORS,
        UPDATE_ALL_MAX_TRANSIENT_ERRORS,
      )
      if (decision === 'giveup') {
        // Gave up — show "lost contact" banner, re-enable CTA
        updateAllLostContact.value = true
        updateAllPolling.value = false
        updateAllPollTimer = null
        return
      }
      if (decision === 'lost-contact') {
        updateAllLostContact.value = true
      }
      // Keep polling (backoff: 2s). During stage-3, updateAllReconnecting is
      // already true (transient errors >= 1) so the reconnecting affordance
      // shows immediately without waiting for the lost-contact threshold.
      updateAllPollTimer = setTimeout(poll, 2000)
      return
    }

    // Successful contact — clear lost-contact banner if it was showing
    updateAllLostContact.value = false
    updateAllTransientErrors.value = 0

    if (result === null) {
      // True 404: no job ever started → stop polling
      _stopUpdateAllPoll()
      return
    }

    updateAllJob.value = result
    if (result.status === 'running' || result.status === 'pending') {
      updateAllPollTimer = setTimeout(poll, 2000)
    } else {
      updateAllPolling.value = false
      updateAllPollTimer = null
      // Refresh status / pending nodes once pipeline finishes
      await Promise.all([codeSync.fetchStatus(), codeSync.fetchPendingNodes()])
    }
  }

  updateAllPollTimer = setTimeout(poll, 1000)
}

async function handleUpdateAll(): Promise<void> {
  codeSync.clearError()
  updateAllLostContact.value = false
  const job = await codeSync.startUpdateAll()
  if (job) {
    updateAllJob.value = job
    _scheduleUpdateAllPoll()
  }
}

// Resume polling if a job is already running when the view mounts
async function _checkExistingUpdateAllJob(): Promise<void> {
  const result = await codeSync.getUpdateAllStatus()
  if (result === undefined || result === null) {
    return
  }
  updateAllJob.value = result
  if (result.status === 'running' || result.status === 'pending') {
    _scheduleUpdateAllPoll()
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
  _stopResolveDriftPoll()
  _stopFleetJobPoll()
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
          {{ codeSync.loading.value ? $t('codeSyncView.refreshing') : $t('codeSyncView.refresh') }}
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
            {{ $t(updateAllButtonLabel ?? 'codeSyncView.updateAll') }}
          </button>
        </div>
      </div>

      <!-- Pipeline progress display (shown when job exists) -->
      <div v-if="updateAllJob" class="mt-5">
        <!-- #12593: inline reconnecting notice during the stage-3 self-restart window -->
        <div
          v-if="updateAllReconnecting"
          class="mb-3 flex items-center gap-2 text-sm text-amber-700"
        >
          <svg class="w-4 h-4 animate-spin shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
          </svg>
          {{ $t('codeSyncView.pipelineReconnectingAttempt', { attempt: updateAllTransientErrors }) }}
        </div>
        <!-- Stage track -->
        <div class="flex items-start gap-0 overflow-x-auto">
          <template v-for="(stage, idx) in updateAllJob.stages" :key="stage.name">
            <!-- Stage box -->
            <div class="flex flex-col items-center min-w-[120px]">
              <div
                :class="['px-3 py-2 rounded-lg text-xs font-medium w-full text-center', stageStatusClass(stage.status)]"
              >
                <!-- F2: stage name via i18n -->
                <div class="font-semibold mb-0.5">{{ $t(stageI18nKey(stage.name)) }}</div>
                <!-- Running spinner -->
                <div v-if="stage.status === 'running'" class="flex items-center justify-center gap-1">
                  <svg class="w-3 h-3 animate-spin" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                  </svg>
                  <!-- Fleet progress shows numeric fraction; others use i18n status key
                       (stage-3 shows "reconnecting..." while the control plane restarts, #12593) -->
                  <span v-if="stageStatusText(stage) !== null">{{ stageStatusText(stage) }}</span>
                  <span v-else>{{ $t(stageRunningStatusKey(stage)) }}</span>
                </div>
                <!-- F2: terminal/pending status via i18n -->
                <div v-else class="text-xs">{{ $t(stageStatusI18nKey(stage)) }}</div>
              </div>
              <!-- #13156: the backend's own per-stage explanation. Rendered for
                   EVERY stage that carries one, not just failed/skipped ones:
                   the fleet stage of a `partial` run ends `success` with
                   `message = "Updated N/M nodes (K skipped - not operational)"`
                   (code_sync.py:4937-4941), so a non-terminal-only filter would
                   hide exactly the reason #13156 was filed about. -->
              <div
                v-if="stage.message"
                class="mt-1 text-xs text-gray-600 text-center leading-4 break-words w-full"
                :title="stage.message"
                data-testid="stage-message"
              >{{ stage.message }}</div>
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

        <!-- Partial: fleet stage skipped one or more non-operational nodes
             (#11511). The backend reports this as its own terminal status, so
             without this branch the run ended with no outcome at all — neither
             the failure banner above nor the success banner below matched. -->
        <div
          v-if="updateAllJob.status === 'partial'"
          class="mt-3 flex items-center gap-2 text-sm text-amber-700"
        >
          <svg class="w-4 h-4 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01M5 19h14a2 2 0 001.84-2.75L13.74 4a2 2 0 00-3.48 0L3.16 16.25A2 2 0 005 19z" />
          </svg>
          {{ $t('codeSyncView.pipelinePartial', { count: updateAllJob.skipped_fleet_nodes }) }}
        </div>

        <!-- Completed success: F2 use i18n for both terminal labels -->
        <div
          v-if="updateAllJob.status === 'completed' || updateAllJob.status === 'already_current'"
          class="mt-3 flex items-center gap-2 text-sm text-green-700"
        >
          <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" />
          </svg>
          {{ updateAllJob.status === 'already_current' ? $t('codeSyncView.alreadyCurrent') : $t('codeSyncView.pipelineStageSuccess') }}
        </div>
      </div>
    </div>

    <!-- #12593: reconnecting / lost-contact banner. Shows IMMEDIATELY (spinner)
         during the stage-3 self-restart window; escalates to a static warning
         with a retry CTA only once polling has lost contact / given up. -->
    <div
      v-if="updateAllLostContact || updateAllReconnecting"
      class="bg-amber-50 border border-amber-200 rounded-lg p-4 mb-6 flex items-center justify-between"
    >
      <div class="flex items-center gap-3">
        <svg
          v-if="updateAllReconnecting && !updateAllLostContact"
          class="w-5 h-5 text-amber-600 animate-spin"
          fill="none" stroke="currentColor" viewBox="0 0 24 24"
        >
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
        </svg>
        <svg v-else class="w-5 h-5 text-amber-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
        <div class="flex-1">
          <div class="font-medium text-amber-900">{{ $t('codeSyncView.sLMManagerRestarting') }}</div>
          <div class="text-sm text-amber-700">
            <span v-if="updateAllReconnecting && !updateAllLostContact">
              {{ $t('codeSyncView.pipelineReconnectingAttempt', { attempt: updateAllTransientErrors }) }}
            </span>
            <span v-else>{{ $t('codeSyncView.codeSyncedSuccessfullyBackend') }}</span>
          </div>
        </div>
      </div>
      <button
        v-if="updateAllLostContact"
        @click="updateAllLostContact = false; handleUpdateAll()"
        class="btn btn-secondary text-sm shrink-0 ml-4"
      >
        {{ $t('codeSyncView.updateAll') }}
      </button>
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
        {{ isPulling ? $t('codeSyncView.pulling') : $t('codeSyncView.pullFromSource') }}
      </button>
      <button
        @click="handleSelfUpdate"
        :disabled="selfUpdating || slmRestartPending"
        class="btn btn-secondary flex items-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
        :title="$t('codeSyncView.syncCodeFromSourceAndRestart')"
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
        {{ selfUpdating ? $t('codeSyncView.updateAllRunning') : $t('codeSyncView.updateThisServer') }}
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
          {{ codeSourceData ? $t('codeSyncView.edit') : $t('codeSyncView.configure') }}
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
            :disabled="isDriftLoading || isResolvingDrift"
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
            {{ isDriftLoading ? $t('codeSyncView.checking') : $t('codeSyncView.checkDrift') }}
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
            </svg>{{ $t('codeSyncView.countDriftedFilePluralDetected', { count: driftReport.drifted_files.length, plural: driftReport.drifted_files.length !== 1 ? 's' : '' }) }}</span>
          <span
            v-else
            class="inline-flex items-center px-3 py-1 rounded-full text-sm font-medium bg-green-100 text-green-800"
          >
            <svg class="w-4 h-4 mr-1.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" />
            </svg>{{ $t('codeSyncView.noDriftDetectedValue0FilesCompared', { value0: driftReport.total_compared }) }}</span>
          <span class="text-sm text-gray-400">{{ $t('codeSyncView.checkedValue0', { value0: formatDate(driftReport.checked_at) }) }}</span>
        </div>

        <div class="text-xs text-gray-400 mb-3">
          {{ $t('codeSyncView.source') }} <code class="font-mono">{{ driftReport.source_dir }}</code>
          {{ $t('codeSyncView.nbspRarrNbspDeployed') }} <code class="font-mono">{{ driftReport.deployed_dir }}</code>
        </div>

        <!-- Action row: Resync (#7149) + Toggle details -->
        <div v-if="driftReport.drift_detected" class="flex items-center gap-3 mb-3">
          <button
            @click="handleResolveDrift()"
            :disabled="isResolvingDrift || isDriftLoading"
            class="btn btn-primary flex items-center gap-2 text-sm"
            :title="$t('codeSyncView.runRsyncFromTo', { source: driftReport.source_dir, dest: driftReport.deployed_dir })"
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
            {{ isResolvingDrift ? $t('codeSyncView.resyncing') : $t('codeSyncView.resyncFromSource') }}
          </button>
          <button
            @click="showDriftDetails = !showDriftDetails"
            class="text-sm text-primary-600 hover:text-primary-800 font-medium"
          >
            {{ showDriftDetails ? $t('codeSyncView.hideDetails') : $t('codeSyncView.showDetails') }}
          </button>
        </div>

        <!-- #11303: Async resolve job progress (rsync/pip/build/restart may take 40-120s) -->
        <div
          v-if="isResolvingDrift && resolveDriftJob && !resolveDriftLostContact"
          class="text-sm text-gray-600 mb-3 flex items-center gap-2"
        >
          <svg class="w-4 h-4 animate-spin" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
          </svg>
          {{ resolveDriftJob.post_steps[resolveDriftJob.post_steps.length - 1] || $t('codeSyncView.resyncing') }}
        </div>

        <!--
          #13851: the resolve refused rather than deleting. The message names
          the paths; this offers the documented override so the operator is not
          stuck — the builtin updater is the only sanctioned path.
        -->
        <div
          v-if="resolveDriftBlocked"
          class="bg-red-50 border border-red-200 rounded-lg p-3 mb-3"
        >
          <div class="flex items-start gap-3">
            <svg class="w-5 h-5 text-red-600 shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
            <div>
              <div class="font-medium text-red-900 text-sm">{{ $t('codeSyncView.resolveWouldDelete') }}</div>
              <div class="text-sm text-red-700">{{ $t('codeSyncView.resolveWouldDeleteExplainer') }}</div>
              <button
                @click="handleResolveDrift(true)"
                :disabled="isResolvingDrift"
                class="mt-2 text-sm font-medium text-red-800 underline hover:text-red-900"
              >
                {{ $t('codeSyncView.resyncAndDeleteAnyway') }}
              </button>
            </div>
          </div>
        </div>

        <!-- #11303: Lost contact banner — component's own service restart drops the connection -->
        <div
          v-if="resolveDriftLostContact"
          class="bg-amber-50 border border-amber-200 rounded-lg p-3 mb-3 flex items-center gap-3"
        >
          <svg class="w-5 h-5 text-amber-600 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          <div>
            <div class="font-medium text-amber-900 text-sm">{{ $t('codeSyncView.sLMManagerRestarting') }}</div>
            <div class="text-sm text-amber-700">{{ $t('codeSyncView.codeSyncedSuccessfullyBackend') }}</div>
          </div>
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
                      'text-orange-700 bg-orange-100 px-2 py-0.5 rounded text-xs': file.status === 'untracked',
                    }"
                  >
                    {{ file.status === 'modified' ? $t('codeSyncView.modified') : file.status === 'source_only' ? $t('codeSyncView.sourceOnly') : $t('codeSyncView.untracked') }}
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

        <!--
          #13851: files present on the host with no counterpart in this
          component's source. Reported separately because they are NOT drift —
          folding them in made every healthy host look stale, and "Resync from
          source" is a delete-style rsync, so acting on them removes them.
        -->
        <div v-if="untrackedFiles.length > 0" class="mt-4">
          <button
            @click="showUntrackedDetails = !showUntrackedDetails"
            class="text-sm text-gray-600 hover:text-gray-800 font-medium flex items-center gap-1.5"
          >
            <svg class="w-4 h-4 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            {{ $t('codeSyncView.countUntrackedFilePlural', { count: untrackedFiles.length, plural: untrackedFiles.length !== 1 ? 's' : '' }) }}
          </button>
          <div v-if="showUntrackedDetails" class="mt-2">
            <p class="text-xs text-gray-500 mb-2">{{ $t('codeSyncView.untrackedExplainer') }}</p>
            <ul class="text-xs font-mono text-gray-700 space-y-1">
              <li v-for="file in untrackedFiles" :key="file.path">{{ file.path }}</li>
            </ul>
          </div>
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

    <!-- Fleet sync jobs (#13157) — the asynchronous per-node rollout that
         "Sync Selected" / "Sync All" queue. Without this panel the job_id
         returned by syncFleet was discarded, so `failure_reason` and the
         per-node ansible error never reached the operator. -->
    <div class="card p-5 mb-6">
      <div class="flex items-center justify-between mb-4">
        <div>
          <h2 class="text-lg font-semibold text-gray-900">{{ $t('codeSyncView.fleetSyncJobs') }}</h2>
          <p class="text-sm text-gray-500">{{ $t('codeSyncView.fleetSyncJobsDesc') }}</p>
        </div>
        <button
          @click="loadRecentFleetJobs"
          :disabled="recentFleetJobsLoading"
          class="btn btn-secondary text-sm disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {{ recentFleetJobsLoading ? $t('codeSyncView.refreshing') : $t('codeSyncView.refresh') }}
        </button>
      </div>

      <!-- The job started from this page, polled to completion -->
      <div
        v-if="fleetSyncJob"
        data-testid="fleet-sync-job"
        class="border border-gray-200 rounded-md p-3 mb-4"
      >
        <div class="flex items-center gap-2 flex-wrap">
          <span
            :class="['px-2 py-0.5 rounded-sm text-xs font-medium', fleetJobStatusClass(fleetSyncJob.status)]"
          >{{ $t(fleetJobStatusI18nKey(fleetSyncJob.status)) }}</span>
          <span class="font-mono text-xs text-gray-500">{{ fleetSyncJob.job_id }}</span>
          <span class="text-sm text-gray-700">{{
            $t('codeSyncView.fleetJobProgress', {
              completed: fleetSyncJob.completed_nodes,
              total: fleetSyncJob.total_nodes,
            })
          }}</span>
          <span v-if="fleetSyncJob.failed_nodes > 0" class="text-sm text-red-700">{{
            $t('codeSyncView.fleetJobFailedNodes', { count: fleetSyncJob.failed_nodes })
          }}</span>
        </div>
        <!-- #13157: the reason the backend recorded (code_sync.py:402) -->
        <div
          v-if="fleetSyncJob.failure_reason"
          data-testid="fleet-job-failure-reason"
          class="mt-2 bg-red-50 border border-red-200 rounded-md p-2 text-sm text-red-700"
        >
          <span class="font-medium">{{ $t('codeSyncView.fleetJobFailureReason') }}</span>
          {{ fleetSyncJob.failure_reason }}
        </div>
        <!-- Per-node outcome; `message` carries the ansible fatal on failure -->
        <ul v-if="fleetSyncJob.nodes.length > 0" class="mt-2 space-y-1">
          <li
            v-for="node in fleetSyncJob.nodes"
            :key="node.node_id"
            class="text-xs text-gray-600 flex gap-2"
          >
            <span class="font-medium shrink-0">{{ node.hostname || node.node_id }}</span>
            <span class="shrink-0">{{ node.status }}</span>
            <span v-if="node.message" class="text-gray-500 break-words">{{ node.message }}</span>
          </li>
        </ul>
      </div>

      <!-- Recent jobs, so a rollout that failed while the page was closed is
           still inspectable -->
      <h3 class="text-sm font-medium text-gray-700 mb-2">{{ $t('codeSyncView.recentFleetJobs') }}</h3>
      <div v-if="recentFleetJobs.length > 0" class="space-y-2">
        <div
          v-for="job in recentFleetJobs"
          :key="job.job_id"
          data-testid="recent-fleet-job"
          class="border border-gray-200 rounded-md p-2"
        >
          <div class="flex items-center gap-2 flex-wrap">
            <span
              :class="['px-2 py-0.5 rounded-sm text-xs font-medium', fleetJobStatusClass(job.status)]"
            >{{ $t(fleetJobStatusI18nKey(job.status)) }}</span>
            <span class="font-mono text-xs text-gray-500">{{ job.job_id }}</span>
            <span class="text-xs text-gray-500">{{ formatDateTime(job.created_at) }}</span>
            <span class="text-xs text-gray-700">{{
              $t('codeSyncView.fleetJobProgress', {
                completed: job.completed_nodes,
                total: job.total_nodes,
              })
            }}</span>
          </div>
          <div v-if="job.failure_reason" class="mt-1 text-xs text-red-700 break-words">
            {{ job.failure_reason }}
          </div>
        </div>
      </div>
      <div v-else-if="!recentFleetJobsLoading" class="text-sm text-gray-500">
        {{ $t('codeSyncView.noRecentFleetJobs') }}
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
            </svg>{{ $t('codeSyncView.syncSelectedValue0', { value0: selectedCount }) }}</button>
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
                {{ syncingNodeId === node.node_id ? $t('codeSyncView.syncing') : $t('codeSyncView.sync') }}
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
            >{{ $t('codeSyncView.autoRestart') }}</span>
          </div>
          <p class="text-sm text-gray-500 mb-3 truncate" :title="role.target_path">
            {{ role.target_path }}
          </p>
          <button
            @click="handleSyncRole(role.name)"
            :disabled="syncingRole === role.name"
            class="btn btn-primary btn-sm w-full"
          >
            {{ syncingRole === role.name ? $t('codeSyncView.syncing') : $t('codeSyncView.syncAllNodes') }}
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
                {{ schedule.target_type === 'all' ? $t('codeSyncView.allOutdatedNodes') : `${schedule.target_nodes?.length || 0} specific nodes` }}
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
                  :title="$t('codeSyncView.runNow')"
                >
                  {{ runningScheduleId === schedule.id ? $t('codeSyncView.running') : $t('codeSyncView.run') }}
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
