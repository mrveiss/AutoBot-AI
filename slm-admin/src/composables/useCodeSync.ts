// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * Code Sync Composable (Issue #741)
 *
 * Provides reactive state and methods for code version tracking
 * and sync operations across the SLM fleet.
 */

import { ref, computed, readonly } from 'vue'
import axios, { type AxiosInstance } from 'axios'
import { useRoles, type Role, type SyncResult } from './useRoles'

// SLM Admin uses the local SLM backend API
const API_BASE = '/api'

// =============================================================================
// Type Definitions
// =============================================================================

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

// Re-export role types for consumers (Issue #779)
export type { Role, SyncResult }

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
    const token = localStorage.getItem('slm_access_token')
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
    // Return full version - no truncation per user request
    return latestVersion.value
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
        // Refresh pending nodes and status after successful sync
        await fetchPendingNodes()
        await fetchStatus()
      }

      return response.data
    } catch (e) {
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
    reset,

    // Schedule methods (Issue #741 - Phase 7)
    fetchSchedules,
    createSchedule,
    updateSchedule,
    deleteSchedule,
    toggleSchedule,
    runSchedule,

    // Role-based sync methods (Issue #779)
    roles: rolesComposable.roles,
    fetchRoles: rolesComposable.fetchRoles,
    syncRole: rolesComposable.syncRole,
    pullFromSource: rolesComposable.pullFromSource,
  }
}
