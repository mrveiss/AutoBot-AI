// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * Code Sync Composable (Issue #741)
 *
 * Provides reactive state and methods for code version tracking
 * and sync operations across the SLM fleet.
 *
 * #12420 Phase 2 (batch 6): migrated off a per-composable axios instance onto
 * the canonical `slmApiClient`. The client injects the SLM bearer token and
 * handles 401 (session clear + redirect to /login), replacing the former
 * request/response interceptors — including #10369's expired-token logout.
 *
 * LOAD-BEARING for #12593: `getUpdateAllStatus()` and `getResolveDriftStatus()`
 * MUST return `undefined` on connection-refused/network/5xx (so the code-sync
 * page keeps polling through the SLM self-restart window) and `null` only on a
 * true 404. `slmApiClient`'s convenience methods THROW on non-2xx, which would
 * collapse that distinction, so those two pollers (and any specific-status
 * handling) use `rawRequest` to inspect `response.status` directly.
 */

import { ref, computed, readonly, toRef } from 'vue'
import { useRoles, type Role, type SyncResult } from './useRoles'
import { formatCommitHash } from '@/utils/commitHashUtils'
import slmApiClient from '@/utils/ApiClient'
import type { components } from '@/types/generated/api'

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

// GET /api/code-sync/pending (autobot-slm-backend/models/schemas.py:1715).
// The wire name is `PendingNodeResponse`; the local `PendingNode` alias is kept
// so existing importers do not churn.
export type PendingNode = components['schemas']['PendingNodeResponse']

// GET /api/code-sync/pending (autobot-slm-backend/models/schemas.py:1725)
export type PendingNodesResponse = components['schemas']['PendingNodesResponse']

export interface SyncResponse {
  success: boolean
  message: string
  node_id?: string
  job_id?: string
}

// POST /api/code-sync/fleet/sync (autobot-slm-backend/models/schemas.py:1766)
export type FleetSyncResponse = components['schemas']['FleetSyncResponse']

// Issue #741 Phase 8: Fleet sync job tracking types.
//
// Both `status` fields are plain `str` in the contract
// (`autobot-slm-backend/models/schemas.py:1780`, `:1790` — the value sets live
// only in a trailing comment), so the generated schema widens them to `string`.
// The narrowings below restate the enumerable assignment sites in
// `autobot-slm-backend/api/code_sync.py`: node states at `:3156`/`:3180`
// (syncing), `:3225`/`:3320` (success), `:3325` (failed) plus the `pending`
// initial value; job states at `:3239` (running), `:3268` (completed/failed),
// `:3272` (failed).
export type FleetSyncNodeState = 'pending' | 'syncing' | 'success' | 'failed'
export type FleetSyncJobState = 'pending' | 'running' | 'completed' | 'failed'

// GET /api/code-sync/fleet/jobs/{job_id} -> nodes[]
// (autobot-slm-backend/models/schemas.py:1775)
export type FleetSyncNodeStatus = components['schemas']['FleetSyncNodeStatus'] & {
  status: FleetSyncNodeState
}

// GET /api/code-sync/fleet/jobs/{job_id}
// (autobot-slm-backend/models/schemas.py:1786). Derived: the hand-written copy
// omitted `failure_reason`, which the backend populates on every job failure
// (`autobot-slm-backend/api/code_sync.py:386,401-402`).
export type FleetSyncJobStatus = components['schemas']['FleetSyncJobStatus'] & {
  status: FleetSyncJobState
  nodes: FleetSyncNodeStatus[]
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

// POST /api/code-sync/schedules/{id}/run
// (autobot-slm-backend/models/schemas.py:1880)
export type ScheduleRunResponse = components['schemas']['ScheduleRunResponse']

// Issue #2834: Drift detection types.
// GET /api/code-sync/drift (autobot-slm-backend/models/schemas.py:1655, :1664).
// `status` is a real `Literal` server-side, so the contract already carries the
// union and no narrowing is needed.
export type DriftedFile = components['schemas']['DriftedFile']
export type FileDriftReport = components['schemas']['FileDriftReport']

// Issue #7149: Drift resolution types.
// POST /api/code-sync/drift/resolve (autobot-slm-backend/models/schemas.py:1681).
// Derived: the hand-written copy omitted `deps_changed` and `post_steps`
// (`schemas.py:1689-1690`), so the caller could not tell whether the resync
// changed dependencies or what post-steps ran.
export type DriftResolveResponse = components['schemas']['DriftResolveResponse']

// Issue #11303: Async per-component drift/resolve job types.
// POST /api/code-sync/drift/resolve-async
// (autobot-slm-backend/models/schemas.py:1693)
export type DriftResolveJobResponse = components['schemas']['DriftResolveJobResponse']

/**
 * The four states a component-resolve job row can hold.
 *
 * `ComponentSyncJobStatus.status` is `str` in the contract
 * (`autobot-slm-backend/models/schemas.py:1706`); the assignment sites are
 * enumerable — `code_sync.py:945` (running), `:191` (queued, the #11437
 * requeue path), `:298` (completed/failed) and `:182`/`:230`/`:265`/`:280`
 * (failed). `CodeSyncView.vue:566,605` branches on these literals.
 */
export type ComponentSyncJobState = 'queued' | 'running' | 'completed' | 'failed'

// GET /api/code-sync/drift/resolve/status/{job_id}
// (autobot-slm-backend/models/schemas.py:1701)
export type ComponentSyncJobStatus = components['schemas']['ComponentSyncJobStatus'] & {
  status: ComponentSyncJobState
}

// Re-export role types for consumers (Issue #779)
export type { Role, SyncResult }

// Issue #9971: One-click update-all types.

/**
 * Pipeline stage status — mirrors `_StageStatus`
 * (`autobot-slm-backend/api/code_sync.py:4239-4245`).
 *
 * `'current'` ("already at target commit", C4) was missing from the previous
 * hand-written union even though `CodeSyncView.vue:127` and `:145` already map
 * it, so the type contradicted the view's own rendering.
 */
export type StageStatus =
  | 'pending'
  | 'running'
  | 'success'
  | 'failed'
  | 'skipped'
  | 'current'

/**
 * Update-all job status — mirrors every `job.status = …` site in
 * `autobot-slm-backend/api/code_sync.py`: `:5053` (running), `:5033`
 * (already_current), `:5036`/`:5176` (completed), `:4940`
 * (partial | completed), `:5144`/`:5184`/`:5294` (failed), plus the `pending`
 * default at `:4266`.
 *
 * `'partial'` was missing from the previous hand-written union. The backend has
 * emitted it since #11511, whenever a non-operational fleet node is skipped.
 */
export type UpdateAllJobStatus =
  | 'pending'
  | 'running'
  | 'completed'
  | 'partial'
  | 'failed'
  | 'already_current'

// GET /api/code-sync/update-all/status -> stages[]
// (autobot-slm-backend/api/code_sync.py:4248)
export type UpdateAllStage = components['schemas']['UpdateAllStage'] & {
  status: StageStatus
}

// POST /api/code-sync/update-all, GET /api/code-sync/update-all/status
// (autobot-slm-backend/api/code_sync.py:4261). Derived: the hand-written copy
// omitted `skipped_fleet_nodes` (`code_sync.py:4270`), the #11511 counter for
// nodes skipped as non-operational.
export type UpdateAllJob = components['schemas']['UpdateAllJob'] & {
  status: UpdateAllJobStatus
  stages: UpdateAllStage[]
}

// =============================================================================
// Update-All poll helpers (#9971 F1, #12593) — pure functions, unit-tested.
// =============================================================================

// Pipeline stage (index 3) that restarts the SLM control plane the code-sync
// page itself polls; ~1min of transient poll failures follow (issue #12593).
export const SLM_SELF_UPDATE_STAGE = 'slm_self_update'

/**
 * True when the pipeline is mid stage-3 self-restart AND at least one poll has
 * failed transiently — i.e. the control plane is bouncing, so the UI should
 * show a "reconnecting" affordance immediately (#12593) instead of a bare
 * "updating..." spinner. `transientErrors` resets to 0 on the next successful
 * poll, so this flips back to false automatically once contact is restored.
 */
export function isSelfUpdateReconnecting(
  job: UpdateAllJob | null,
  transientErrors: number,
): boolean {
  if (!job || transientErrors < 1) return false
  const running = job.stages.find((s) => s.status === 'running')
  return running?.name === SLM_SELF_UPDATE_STAGE
}

export type UpdateAllPollDecision = 'continue' | 'lost-contact' | 'giveup'

/**
 * Classify a run of consecutive transient poll errors (#9971 F1). Show the
 * "lost contact" banner at `lostContactThreshold`; hard give-up (stop polling)
 * at `maxThreshold`. Thresholds are unchanged by #12593.
 */
export function classifyUpdateAllPollError(
  transientErrors: number,
  lostContactThreshold: number,
  maxThreshold: number,
): UpdateAllPollDecision {
  if (transientErrors >= maxThreshold) return 'giveup'
  if (transientErrors >= lostContactThreshold) return 'lost-contact'
  return 'continue'
}

// =============================================================================
// Internal helpers
// =============================================================================

/**
 * Best-effort read of a FastAPI `{ detail }` error body from a raw Response.
 * Returns null when the body is absent/non-JSON so callers can fall back to a
 * generic message. Used by the `rawRequest`-based methods that must preserve
 * the exact detail-derived error strings the axios implementation produced.
 */
async function readDetail(response: Response): Promise<string | null> {
  try {
    const body = (await response.json()) as { detail?: unknown } | null
    const detail = body?.detail
    return typeof detail === 'string' ? detail : null
  } catch {
    return null
  }
}

// =============================================================================
// Composable
// =============================================================================

export function useCodeSync() {
  // #10369 / auth: token injection and 401 handling (session clear + redirect
  // to /login) are now performed by `slmApiClient`, replacing the former axios
  // request/response interceptors — no per-composable client needed.

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
      const data = await slmApiClient.get<CodeSyncStatus>('/code-sync/status')
      status.value = data
      lastRefresh.value = new Date()
      return data
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Failed to fetch code sync status'
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
      const data = await slmApiClient.post<RefreshResponse>('/code-sync/refresh')

      if (data.success) {
        // Refresh status after manual refresh to get updated data
        await fetchStatus()
      }

      return data.success
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Failed to refresh version'
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
      const data = await slmApiClient.get<PendingNodesResponse>('/code-sync/pending')
      pendingNodes.value = data.nodes
      return data.nodes
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Failed to fetch pending nodes'
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
      // rawRequest (single-shot, raw status): the SLM Manager self-restart path
      // returns a 502 that must be interpreted as success, not surfaced as an
      // error — the convenience `post` would throw and lose the status code.
      const response = await slmApiClient.rawRequest(
        `/code-sync/nodes/${nodeId}/sync`,
        { method: 'POST', body: payload }
      )

      // Special handling for SLM Manager self-restart (502 errors expected)
      if (response.status === 502) {
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

      if (!response.ok) {
        const detail = await readDetail(response)
        error.value = detail || 'Sync failed'
        return { success: false, message: error.value, node_id: nodeId }
      }

      const data = (await response.json()) as SyncResponse

      // Set error if sync failed
      if (!data.success) {
        error.value = data.message
      } else {
        // Issue #1231: SLM self-sync is fire-and-forget — the backend
        // returns immediately before the background task completes.
        // Refreshing now would return stale data (node still outdated).
        // Skip refresh and let the caller handle the delayed update.
        const isSLMSelfSync = data.message?.includes('SLM update queued')
        if (!isSLMSelfSync) {
          await fetchPendingNodes()
          await fetchStatus()
        }
      }

      return data
    } catch (e) {
      const message = e instanceof Error ? e.message : 'Sync failed'
      error.value = message
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
      const data = await slmApiClient.post<FleetSyncResponse>(
        '/code-sync/fleet/sync',
        payload
      )

      // Set error if fleet sync failed
      if (!data.success) {
        error.value = data.message
      } else {
        // Refresh status after fleet sync is queued
        await fetchStatus()
      }

      return data
    } catch (e) {
      const message = e instanceof Error ? e.message : 'Fleet sync failed'
      error.value = message
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
      // Single-shot poll — no retry/backoff (matches the former axios call).
      return await slmApiClient.get<FleetSyncJobStatus>(
        `/code-sync/fleet/jobs/${jobId}`,
        { maxRetries: 1 }
      )
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Failed to fetch job status'
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
      // Single-shot poll — no retry/backoff (matches the former axios call).
      return await slmApiClient.get<FleetSyncJobStatus[]>(
        `/code-sync/fleet/jobs?limit=${limit}`,
        { maxRetries: 1 }
      )
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Failed to fetch recent jobs'
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
      const data = await slmApiClient.get<UpdateSchedule[]>('/code-sync/schedules')
      schedules.value = data
      return data
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Failed to fetch schedules'
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
      const data = await slmApiClient.post<UpdateSchedule>(
        '/code-sync/schedules',
        schedule
      )
      await fetchSchedules()
      return data
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Failed to create schedule'
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
      const data = await slmApiClient.put<UpdateSchedule>(
        `/code-sync/schedules/${id}`,
        update
      )
      await fetchSchedules()
      return data
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Failed to update schedule'
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
      await slmApiClient.delete(`/code-sync/schedules/${id}`)
      await fetchSchedules()
      return true
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Failed to delete schedule'
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
      const data = await slmApiClient.post<ScheduleRunResponse>(
        `/code-sync/schedules/${id}/run`
      )
      await fetchSchedules()
      return data
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Failed to run schedule'
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
      const data = await slmApiClient.get<FileDriftReport>(
        `/code-sync/drift?component=${encodeURIComponent(component)}`
      )
      driftReport.value = data
      return data
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Failed to fetch drift report'
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
      const data = await slmApiClient.post<DriftResolveResponse>('/code-sync/drift/resolve', {
        component,
      })
      if (!data.success) {
        error.value = data.message
      }
      return data
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Failed to resolve drift'
      return null
    } finally {
      loading.value = false
    }
  }

  /**
   * Start an async per-component drift/resolve job (#11303).
   *
   * Returns immediately with a job_id instead of awaiting the full rsync +
   * post-sync steps inline, so the GUI never blocks on a slow resync or the
   * component's own service restart. Poll getResolveDriftStatus() for progress.
   *
   * Uses rawRequest so the 409 (restart in flight) detail is surfaced verbatim
   * in `error.value` (the convenience `post` would prefix "HTTP 409: ").
   *
   * #13851: `force` overrides the deletion guard. A resolve is a delete-style
   * rsync, so the backend refuses when it would remove deployed paths that
   * source does not have and names them in the job message. Without this
   * parameter the GUI would have no way past a refusal — and updates must go
   * through this builtin updater.
   */
  async function startResolveDriftAsync(
    component: string,
    force = false
  ): Promise<DriftResolveJobResponse | null> {
    error.value = null
    try {
      const response = await slmApiClient.rawRequest('/code-sync/drift/resolve-async', {
        method: 'POST',
        body: { component, force },
      })
      if (!response.ok) {
        const detail = await readDetail(response)
        error.value = detail || 'Failed to start drift resolve job'
        return null
      }
      return (await response.json()) as DriftResolveJobResponse
    } catch {
      error.value = 'Failed to start drift resolve job'
      return null
    }
  }

  /**
   * Poll the status of an async drift/resolve job (#11303).
   *
   * Returns null ONLY on a true 404 (unknown job_id) so the caller stops
   * polling. Returns undefined on transient errors (network refused / 5xx
   * during the component's own restart) so the caller keeps polling instead
   * of treating a self-restart as job failure. rawRequest gives the raw status
   * needed to keep this 404-vs-transient distinction intact.
   */
  async function getResolveDriftStatus(jobId: string): Promise<ComponentSyncJobStatus | null | undefined> {
    try {
      const response = await slmApiClient.rawRequest(
        `/code-sync/drift/resolve/status/${jobId}`,
        { method: 'GET' }
      )
      if (response.status === 404) {
        return null
      }
      if (!response.ok) {
        return undefined
      }
      return (await response.json()) as ComponentSyncJobStatus
    } catch {
      return undefined
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

    // Drift detection (Issue #2834) + resolution (#7149) + async job (#11303)
    fetchDrift,
    resolveDrift,
    startResolveDriftAsync,
    getResolveDriftStatus,

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
   *
   * rawRequest preserves the exact 409-vs-other detail-derived error strings
   * the axios implementation surfaced in `error.value`.
   */
  async function startUpdateAll(): Promise<UpdateAllJob | null> {
    try {
      const response = await slmApiClient.rawRequest('/code-sync/update-all', {
        method: 'POST',
      })
      if (!response.ok) {
        const detail = await readDetail(response)
        if (response.status === 409) {
          error.value = detail || 'Update already running'
        } else {
          error.value = detail || 'Failed to start update'
        }
        return null
      }
      return (await response.json()) as UpdateAllJob
    } catch {
      error.value = 'Failed to start update'
      return null
    }
  }

  /**
   * Poll the status of the current update-all job.
   *
   * F1 / #12593: Returns null ONLY on a true 404 (no job ever started) so the
   * caller stops polling. Returns undefined on transient errors (connection
   * refused / network / 5xx during the SLM self-restart window) so the caller
   * keeps polling instead of treating the control-plane bounce as a hard stop.
   *
   * MUST use rawRequest: `slmApiClient.get` throws a generic `Error('HTTP <n>:
   * …')` on non-2xx and retries transient failures, which would erase the
   * 404-vs-transient distinction this #12593 contract depends on.
   */
  async function getUpdateAllStatus(): Promise<UpdateAllJob | null | undefined> {
    try {
      const response = await slmApiClient.rawRequest('/code-sync/update-all/status', {
        method: 'GET',
      })
      // True 404 = no job started yet → stop polling
      if (response.status === 404) {
        return null
      }
      // 5xx (or any other non-2xx) during SLM restart → transient, keep polling
      if (!response.ok) {
        return undefined
      }
      return (await response.json()) as UpdateAllJob
    } catch {
      // Network error / connection refused / timeout → transient, keep polling
      return undefined
    }
  }

  async function selfUpdate(): Promise<{ success: boolean; message: string }> {
    try {
      const response = await slmApiClient.rawRequest('/code-sync/self-update', {
        method: 'POST',
      })
      if (!response.ok) {
        const detail = await readDetail(response)
        return { success: false, message: detail || 'Self-update request failed' }
      }
      const data = (await response.json()) as {
        success: boolean
        message: string
        node_id?: string
      }
      return { success: data.success, message: data.message }
    } catch {
      return { success: false, message: 'Self-update request failed' }
    }
  }
}
