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

  // =============================================================================
  // Reactive State
  // =============================================================================

  const status = ref<CodeSyncStatus | null>(null)
  const pendingNodes = ref<PendingNode[]>([])
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
    const version = latestVersion.value
    return version ? version.substring(0, 12) : null
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

      // Refresh pending nodes and status after sync
      if (response.data.success) {
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

      // Refresh status after fleet sync is queued
      if (response.data.success) {
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
    loading.value = false
    error.value = null
    lastRefresh.value = null
  }

  // =============================================================================
  // Return Public API
  // =============================================================================

  return {
    // State (readonly to prevent external mutation)
    status: readonly(status),
    pendingNodes: readonly(pendingNodes),
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
    clearError,
    reset,
  }
}
