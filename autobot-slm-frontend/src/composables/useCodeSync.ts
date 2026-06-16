// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * Code Sync Composable (Issue #741)
 *
 * Provides reactive state and methods for code version tracking
 * and sync operations across the SLM fleet.
 */

import { ref, computed, readonly, toRef } from 'vue'
import axios, { type AxiosInstance } from 'axios'
import { useRoles, type Role, type SyncResult } from './useRoles'
import { formatCommitHash } from '@/utils/commitHashUtils'
import { getSlmApiBase } from '@/config/ssot-config'

// SLM Admin uses the local SLM backend API
const API_BASE = getSlmApiBase()

// =============================================================================
// Type Definitions
// =============================================================================

// #9956: SLM-component role names — a node carrying any of these IS the SLM
// manager, regardless of its (user-editable) display name. Mirrors the
// backend SLM_ROLES set used for self-identification.
const SLM_ROLE_NAMES = ['slm-backend', 'slm-frontend', 'slm-database', 'slm-monitoring']

export interface CodeSyncStatus {
  latest_version: string | null
  local_version: string | null
  last_fetch: string | null
  has_update: boolean
  outdated_nodes: number
  total_nodes: number
}

export interface PendingNode {
  node_id: string
  hostname: string
  ip_address: string
  current_version: string | null
  code_status: string
}

export interface PendingNodesResponse {
  nodes: PendingNode[]
  total: number
  latest_version: string | null
}

export interface SyncResponse {
  success: boolean
  message: string
  node_id?: string
  job_id?: string
}

export interface FleetSyncResponse {
  success: boolean
  message: string
  job_id: string
  nodes_queued: number
}

// Issue #741 Phase 8: Fleet sync job tracking types
export interface FleetSyncNodeStatus {
  node_id: string
  hostname: string
  status: 'pending' | 'syncing' | 'success' | 'failed'
  message: string | null
  started_at: string | null
  completed_at: string | null
}

export interface FleetSyncJobStatus {
  job_id: string
  status: 'pending' | 'running' | 'completed' | 'failed'
  strategy: string
  total_nodes: number
  completed_nodes: number
  failed_nodes: number
  nodes: FleetSyncNodeStatus[]
  created_at: string
  completed_at: string | null
}

export interface RefreshResponse {
  success: boolean
  latest_version?: string
  message?: string
}

export interface SyncOptions {
  restart?: boolean
  strategy?: 'immediate' | 'graceful' | 'manual'
}

export interface FleetSyncOptions {
  node_ids?: string[]
  strategy?: 'immediate' | 'graceful' | 'manual' | 'rolling'
  batch_size?: number
  restart?: boolean
}

// Issue #741 Phase 7: Schedule types
export interface UpdateSchedule {
  id: number
  name: string
  cron_expression: string
  enabled: boolean
  target_type: 'all' | 'specific' | 'tag' | 'roles'
  target_nodes: string[] | null
  target_roles: string[] | null  // Issue #779: Role-based targeting
  restart_strategy: string
  restart_after_sync: boolean
  last_run: string | null
  next_run: string | null
  last_run_status: string | null
  last_run_message: string | null
  created_at: string
  created_by: string | null
}

export interface ScheduleCreateRequest {
  name: string
  cron_expression: string
  enabled?: boolean
  target_type?: 'all' | 'specific' | 'tag' | 'roles'
  target_nodes?: string[]
  target_roles?: string[]  // Issue #779: Role-based targeting
  restart_strategy?: string
  restart_after_sync?: boolean
}

export interface ScheduleUpdateRequest {
  name?: string
  cron_expression?: string
  enabled?: boolean
  target_type?: 'all' | 'specific' | 'tag' | 'roles'
  target_nodes?: string[]
  target_roles?: string[]  // Issue #779: Role-based targeting
  restart_strategy?: string
  restart_after_sync?: boolean
}

export interface ScheduleRunResponse {
  success: boolean
  message: string
  schedule_id: number
  job_id: string | null
}

// Issue #2834: Drift detection types
export interface DriftedFile {
  path: string
  source_checksum: string | null
  deployed_checksum: string | null
  status: 'modified' | 'source_only' | 'deployed_only'
}

export interface FileDriftReport {
  source_dir: string
  deployed_dir: string
  drifted_files: DriftedFile[]
  total_compared: number
  drift_detected: boolean
  checked_at: string
}

// Issue #7149: Drift resolution types
export interface DriftResolveResponse {
  success: boolean
  component: string
  message: string
  source_dir: string
  deployed_dir: string
}

// Re-export role types for consumers (Issue #779)
export type { Role, SyncResult }

// Issue #9971: One-click update-all types
export type StageStatus = 'pending' | 'running' | 'success' | 'failed' | 'skipped'

export interface UpdateAllStage {
  name: string
  status: StageStatus
  message: string | null
  sha: string | null
  deps_changed: boolean
  log_lines: string[]
  started_at: string | null
  completed_at: string | null
}

export interface UpdateAllJob {
  job_id: string
  status: 'pending' | 'running' | 'completed' | 'failed' | 'already_current'
  stages: UpdateAllStage[]
  total_fleet_nodes: number
  completed_fleet_nodes: number
  failed_fleet_nodes: number
  created_at: string
  completed_at: string | null
  failure_reason: string | null
}

// =============================================================================
// Composable
// =============================================================================

export function useCodeSync() {
  // Create axios client
  const client: AxiosInstance = axios.create({
    baseURL: API_BASE,
    headers: {
      'Content-Type': 'application/json',
    },
  })

  // Add auth token to all requests
  client.interceptors.request.use((config) => {
    const token = sessionStorage.getItem('slm_access_token')
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  })

  // Initialize roles composable (Issue #779)
  const rolesComposable = useRoles()

  // =============================================================================
  // Reactive State
  // =============================================================================

  const status = ref<CodeSyncStatus | null>(null)
  const pendingNodes = ref<PendingNode[]>([])
  const schedules = ref<UpdateSchedule[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)
  const lastRefresh = ref<Date | null>(null)
  const driftReport = ref<FileDriftReport | null>(null) // Issue #2834

  // =============================================================================
  // Computed Properties
  // =============================================================================

  const hasOutdatedNodes = computed(() => {
    return status.value ? status.value.outdated_nodes > 0 : false
  })

  const outdatedCount = computed(() => {
    return status.value?.outdated_nodes ?? 0
  })

  const latestVersion = computed(() => {
    return status.value?.latest_version ?? null
  })

  const latestVersionShort = computed(() => {
    // Return 12-character format for consistency (Issue #866)
    return formatCommitHash(latestVersion.value)
  })

  const totalNodes = computed(() => {
    return status.value?.total_nodes ?? 0
  })

  const hasUpdate = computed(() => {
    return status.value?.has_update ?? false
  })

  // =============================================================================
  // API Methods
  // =============================================================================

  /**
   * Fetch current code sync status from the backend.
   * Updates the reactive status state.
   */
  async function fetchStatus(): Promise<CodeSyncStatus | null> {
    loading.value = true
    error.value = null

    try {
      const response = await client.get<CodeSyncStatus>('/code-sync/status')
      status.value = response.data
      lastRefresh.value = new Date()
      return response.data
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Failed to fetch code sync status'
      if (axios.isAxiosError(e) && e.response?.data?.detail) {
        error.value = e.response.data.detail
      }
      return null
    } finally {
      loading.value = false
    }
  }

  /**
   * Trigger a manual refresh of the latest version from git.
   * This fetches the latest commit hash from the repository.
   */
  async function refreshVersion(): Promise<boolean> {
    loading.value = true
    error.value = null

    try {
      const response = await client.post<RefreshResponse>('/code-sync/refresh')

      if (response.data.success) {
        // Refresh status after manual refresh to get updated data
        await fetchStatus()
      }

      return response.data.success
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Failed to refresh version'
      if (axios.isAxiosError(e) && e.response?.data?.detail) {
        error.value = e.response.data.detail
      }
      return false
    } finally {
      loading.value = false
    }
  }

  /**
   * Fetch list of nodes that need code updates.
   * Updates the reactive pendingNodes state.
   */
  async function fetchPendingNodes(): Promise<PendingNode[]> {
    loading.value = true
    error.value = null

    try {
      const response = await client.get<PendingNodesResponse>('/code-sync/pending')
      pendingNodes.value = response.data.nodes
      return response.data.nodes
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Failed to fetch pending nodes'
      if (axios.isAxiosError(e) && e.response?.data?.detail) {
        error.value = e.response.data.detail
      }
      return []
    } finally {
      loading.value = false
    }
  }

  /**
   * Trigger code sync for a specific node.
   *
   * @param nodeId - The ID of the node to sync
   * @param options - Sync options (restart, strategy)
   */
  async function syncNode(
    nodeId: string,
    options: SyncOptions = {}
  ): Promise<SyncResponse> {
    loading.value = true
    error.value = null

    const payload = {
      restart: options.restart ?? true,
      strategy: options.strategy ?? 'graceful',
    }

    try {
      const response = await client.post<SyncResponse>(
        `/code-sync/nodes/${nodeId}/sync`,
        payload
      )

      // Set error if sync failed
      if (!response.data.success) {
        error.value = response.data.message
      } else {
        // Issue #1231: SLM self-sync is fire-and-forget — the backend
        // returns immediately before the background task completes.
        // Refreshing now would return stale data (node still outdated).
        // Skip refresh and let the caller handle the delayed update.
        const isSLMSelfSync = response.data.message?.includes(
          'SLM update queued'
        )
        if (!isSLMSelfSync) {
          await fetchPendingNodes()
          await fetchStatus()
        }
      }

      return response.data
    } catch (e) {
      // Special handling for SLM Manager self-restart (502 errors expected)
      if (axios.isAxiosError(e) && e.response?.status === 502) {
        // #9956: Identify the SLM server by its detected SLM roles, not by a
        // hardcoded/substring node name — operators may rename the node.
        const nodeRoles = await rolesComposable
          .getNodeRoles(nodeId)
          .catch(() => null)
        const isSLMServer = (nodeRoles?.detected_roles ?? []).some((r) =>
          SLM_ROLE_NAMES.includes(r)
        )

        if (isSLMServer && (options.restart ?? true)) {
          // 502 is expected when SLM restarts itself - treat as success
          return {
            success: true,
            message: 'SLM Manager restart in progress. Backend will be available in ~30 seconds. Refresh the page after waiting.',
            node_id: nodeId
          }
        }
      }

      const message = e instanceof Error ? e.message : 'Sync failed'
      error.value = message
      if (axios.isAxiosError(e) && e.response?.data?.detail) {
        error.value = e.response.data.detail
      }
      return { success: false, message: error.value || message, node_id: nodeId }
    } finally {
      loading.value = false
    }
  }

  /**
   * Trigger code sync for multiple nodes or the entire fleet.
   *
   * @param options - Fleet sync options (node_ids, strategy, batch_size, restart)
   */
  async function syncFleet(options: FleetSyncOptions = {}): Promise<FleetSyncResponse> {
    loading.value = true
    error.value = null

    const payload = {
      node_ids: options.node_ids,
      strategy: options.strategy ?? 'rolling',
      batch_size: options.batch_size ?? 1,
      restart: options.restart ?? true,
    }

    try {
      const response = await client.post<FleetSyncResponse>(
        '/code-sync/fleet/sync',
        payload
      )

      // Set error if fleet sync failed
      if (!response.data.success) {
        error.value = response.data.message
      } else {
        // Refresh status after fleet sync is queued
        await fetchStatus()
      }

      return response.data
    } catch (e) {
      const message = e instanceof Error ? e.message : 'Fleet sync failed'
      error.value = message
      if (axios.isAxiosError(e) && e.response?.data?.detail) {
        error.value = e.response.data.detail
      }
      return { success: false, message: error.value || message, job_id: '', nodes_queued: 0 }
    } finally {
      loading.value = false
    }
  }

  /**
   * Get status of a fleet sync job.
   *
   * @param jobId - The job ID returned from syncFleet
   */
  async function getJobStatus(jobId: string): Promise<FleetSyncJobStatus | null> {
    try {
      const response = await client.get<FleetSyncJobStatus>(
        `/code-sync/fleet/jobs/${jobId}`
      )
      return response.data
    } catch (e) {
      if (axios.isAxiosError(e) && e.response?.data?.detail) {
        error.value = e.response.data.detail
      }
      return null
    }
  }

  /**
   * List recent fleet sync jobs.
   *
   * @param limit - Maximum number of jobs to return (default: 10)
   */
  async function getRecentJobs(limit = 10): Promise<FleetSyncJobStatus[]> {
    try {
      const response = await client.get<FleetSyncJobStatus[]>(
        '/code-sync/fleet/jobs',
        { params: { limit } }
      )
      return response.data
    } catch (e) {
      if (axios.isAxiosError(e) && e.response?.data?.detail) {
        error.value = e.response.data.detail
      }
      return []
    }
  }

  /**
   * Clear the current error state.
   */
  function clearError(): void {
    error.value = null
  }

  /**
   * Set the error message.
   */
  function setError(message: string): void {
    error.value = message
  }

  /**
   * Reset all state to initial values.
   */
  function reset(): void {
    status.value = null
    pendingNodes.value = []
    schedules.value = []
    loading.value = false
    error.value = null
    lastRefresh.value = null
  }

  // ===========================================================================
  // Schedule Methods (Issue #741 - Phase 7)
  // ===========================================================================

  /**
   * Fetch all update schedules.
   */
  async function fetchSchedules(): Promise<UpdateSchedule[]> {
    try {
      const response = await client.get<UpdateSchedule[]>('/code-sync/schedules')
      schedules.value = response.data
      return response.data
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Failed to fetch schedules'
      if (axios.isAxiosError(e) && e.response?.data?.detail) {
        error.value = e.response.data.detail
      }
      return []
    }
  }

  /**
   * Create a new update schedule.
   */
  async function createSchedule(
    schedule: ScheduleCreateRequest
  ): Promise<UpdateSchedule | null> {
    loading.value = true
    error.value = null

    try {
      const response = await client.post<UpdateSchedule>(
        '/code-sync/schedules',
        schedule
      )
      await fetchSchedules()
      return response.data
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Failed to create schedule'
      if (axios.isAxiosError(e) && e.response?.data?.detail) {
        error.value = e.response.data.detail
      }
      return null
    } finally {
      loading.value = false
    }
  }

  /**
   * Update an existing schedule.
   */
  async function updateSchedule(
    id: number,
    update: ScheduleUpdateRequest
  ): Promise<UpdateSchedule | null> {
    loading.value = true
    error.value = null

    try {
      const response = await client.put<UpdateSchedule>(
        `/code-sync/schedules/${id}`,
        update
      )
      await fetchSchedules()
      return response.data
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Failed to update schedule'
      if (axios.isAxiosError(e) && e.response?.data?.detail) {
        error.value = e.response.data.detail
      }
      return null
    } finally {
      loading.value = false
    }
  }

  /**
   * Delete a schedule.
   */
  async function deleteSchedule(id: number): Promise<boolean> {
    loading.value = true
    error.value = null

    try {
      await client.delete(`/code-sync/schedules/${id}`)
      await fetchSchedules()
      return true
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Failed to delete schedule'
      if (axios.isAxiosError(e) && e.response?.data?.detail) {
        error.value = e.response.data.detail
      }
      return false
    } finally {
      loading.value = false
    }
  }

  /**
   * Toggle a schedule's enabled state.
   */
  async function toggleSchedule(id: number, enabled: boolean): Promise<boolean> {
    const result = await updateSchedule(id, { enabled })
    return result !== null
  }

  /**
   * Manually trigger a schedule to run now.
   */
  async function runSchedule(id: number): Promise<ScheduleRunResponse | null> {
    loading.value = true
    error.value = null

    try {
      const response = await client.post<ScheduleRunResponse>(
        `/code-sync/schedules/${id}/run`
      )
      await fetchSchedules()
      return response.data
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Failed to run schedule'
      if (axios.isAxiosError(e) && e.response?.data?.detail) {
        error.value = e.response.data.detail
      }
      return null
    } finally {
      loading.value = false
    }
  }

  // =============================================================================
  // Drift Detection (Issue #2834)
  // =============================================================================

  /**
   * Fetch a file-level drift report comparing code_source vs deployed files.
   *
   * @param component - Sub-directory to compare (default: autobot-slm-backend).
   */
  async function fetchDrift(component = 'autobot-slm-backend'): Promise<FileDriftReport | null> {
    loading.value = true
    error.value = null

    try {
      const response = await client.get<FileDriftReport>('/code-sync/drift', {
        params: { component },
      })
      driftReport.value = response.data
      return response.data
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Failed to fetch drift report'
      if (axios.isAxiosError(e) && e.response?.data?.detail) {
        error.value = e.response.data.detail
      }
      return null
    } finally {
      loading.value = false
    }
  }

  /**
   * Resync a component from code_source/ to /opt/autobot/<component>/ (#7149).
   *
   * Drives the same local rsync used by SLM self-sync. Used by CodeSyncView's
   * "Resync from Source" button on the drift card so users can clear drift in
   * one click instead of finding the SLM self-node and triggering a full sync.
   *
   * @param component - Sub-directory under /opt/autobot/. Must be in ALLOWED_COMPONENTS.
   */
  async function resolveDrift(component: string): Promise<DriftResolveResponse | null> {
    loading.value = true
    error.value = null

    try {
      const response = await client.post<DriftResolveResponse>('/code-sync/drift/resolve', {
        component,
      })
      if (!response.data.success) {
        error.value = response.data.message
      }
      return response.data
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Failed to resolve drift'
      if (axios.isAxiosError(e) && e.response?.data?.detail) {
        error.value = e.response.data.detail
      }
      return null
    } finally {
      loading.value = false
    }
  }

  // =============================================================================
  // Return Public API
  // =============================================================================

  return {
    // State (readonly to prevent external mutation)
    status: readonly(status),
    pendingNodes: readonly(pendingNodes),
    schedules: readonly(schedules),
    loading: readonly(loading),
    error: readonly(error),
    lastRefresh: readonly(lastRefresh),
    driftReport: readonly(driftReport), // Issue #2834

    // Computed
    hasOutdatedNodes,
    outdatedCount,
    latestVersion,
    latestVersionShort,
    totalNodes,
    hasUpdate,

    // Methods
    fetchStatus,
    refreshVersion,
    fetchPendingNodes,
    syncNode,
    syncFleet,
    getJobStatus,
    getRecentJobs,
    clearError,
    setError,
    reset,

    // Schedule methods (Issue #741 - Phase 7)
    fetchSchedules,
    createSchedule,
    updateSchedule,
    deleteSchedule,
    toggleSchedule,
    runSchedule,

    // Role-based sync methods (Issue #779)
    // useRoles() returns reactive() which auto-unwraps the inner roles ref, so
    // rolesComposable.roles is a plain array. toRef() restores the ref shape so
    // callers can use .value as expected in templates.
    roles: toRef(rolesComposable, 'roles'),
    fetchRoles: rolesComposable.fetchRoles,
    syncRole: rolesComposable.syncRole,
    pullFromSource: rolesComposable.pullFromSource,

    // Drift detection (Issue #2834) + resolution (#7149)
    fetchDrift,
    resolveDrift,

    // SLM self-update (#9073)
    selfUpdate,

    // One-click full-pipeline update (#9971)
    startUpdateAll,
    getUpdateAllStatus,
  }

  // ---------------------------------------------------------------------------
  // One-click full-pipeline update (#9971)
  // ---------------------------------------------------------------------------

  /**
   * Start the one-click update-all orchestration pipeline.
   * Returns the initial UpdateAllJob or null on 409 (already running).
   * F1: distinguishes 404 (no job) from transient errors (network/5xx).
   */
  async function startUpdateAll(): Promise<UpdateAllJob | null> {
    try {
      const response = await client.post<UpdateAllJob>('/code-sync/update-all')
      return response.data
    } catch (e: unknown) {
      const axiosErr = e as { response?: { status?: number; data?: { detail?: string } } }
      if (axiosErr?.response?.status === 409) {
        error.value = axiosErr.response?.data?.detail || 'Update already running'
      } else {
        error.value = axiosErr?.response?.data?.detail || 'Failed to start update'
      }
      return null
    }
  }

  /**
   * Poll the status of the current update-all job.
   *
   * F1: Returns null ONLY on true 404 (no job ever started).
   *     Returns undefined on transient errors (network refused / 5xx during
   *     SLM restart) so the caller can distinguish "stop polling" from "keep polling".
   */
  async function getUpdateAllStatus(): Promise<UpdateAllJob | null | undefined> {
    try {
      const response = await client.get<UpdateAllJob>('/code-sync/update-all/status')
      return response.data
    } catch (e: unknown) {
      const axiosErr = e as { response?: { status?: number }; code?: string; message?: string }
      // True 404 = no job started yet → stop polling
      if (axiosErr?.response?.status === 404) {
        return null
      }
      // Network error or 5xx during SLM restart → transient, keep polling
      return undefined
    }
  }

  async function selfUpdate(): Promise<{ success: boolean; message: string }> {
    try {
      const response = await client.post<{ success: boolean; message: string; node_id?: string }>(
        '/code-sync/self-update'
      )
      return { success: response.data.success, message: response.data.message }
    } catch (e: unknown) {
      const msg =
        (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        'Self-update request failed'
      return { success: false, message: msg }
    }
  }
}
