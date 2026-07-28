// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * System Updates Composable
 *
 * Provides reactive state and methods for system package update
 * discovery and management across the SLM fleet.
 *
 * Migrated onto the canonical `slmApiClient` (#12420 Phase 2). The client
 * resolves the base URL via `getSlmApiBase()`, injects the SLM bearer token,
 * and centrally handles 401 for these non-auth endpoints (clear session +
 * redirect to `/login`) — replacing the previous per-composable axios instance
 * plus request/response interceptors (the response interceptor's #10369
 * `authStore.logout()` on 401 is now the client's centralised concern). Query
 * parameters are serialised onto the endpoint since the canonical client takes
 * a relative path, not an axios `params` object; call sites receive parsed JSON
 * directly (no axios `.data`). The client throws on non-2xx, so each method
 * keeps its try/catch and preserves the graceful `null`/`[]`/`false` returns.
 * The silent poll/badge probes (`fetchSummary`, `pollDiscoverStatus`) request
 * once (`maxRetries: 1`) and suppress the client's failure WARN so they stay
 * quiet, matching the previous single-shot axios behaviour.
 */

import { ref, computed, readonly } from 'vue'
import slmApiClient from '@/utils/ApiClient'

// =============================================================================
// Type Definitions
// =============================================================================

export interface UpdateSummary {
  system_update_count: number
  security_update_count: number
  nodes_with_updates: number
  last_checked: string | null
}

export interface UpdatePackage {
  update_id: string
  node_id: string | null
  package_name: string
  current_version: string | null
  available_version: string
  severity: string
  description: string | null
  is_applied: boolean
  applied_at: string | null
  created_at: string
}

export interface PackagesResponse {
  packages: UpdatePackage[]
  total: number
  by_node: Record<string, number>
}

export interface DiscoverResponse {
  success: boolean
  message: string
  job_id: string
}

export interface DiscoverStatus {
  job_id: string
  status: 'pending' | 'running' | 'completed' | 'failed'
  progress: number
  message: string | null
  nodes_checked: number
  total_nodes: number
  packages_found: number
  started_at: string | null
  completed_at: string | null
}

export interface UpdateJob {
  job_id: string
  node_id: string
  status: string
  progress: number
  current_step: string | null
  total_steps: number
  completed_steps: number
  error: string | null
  output: string | null
  started_at: string | null
  completed_at: string | null
  created_at: string
}

// Minimal shape of the mutating-endpoint envelopes (apply / apply-all / cancel).
interface MutationResult {
  success: boolean
  message?: string
}

// =============================================================================
// Composable
// =============================================================================

export function useSystemUpdates() {
  // ===========================================================================
  // Reactive State
  // ===========================================================================

  const summary = ref<UpdateSummary | null>(null)
  const packages = ref<UpdatePackage[]>([])
  const packagesByNode = ref<Record<string, number>>({})
  const jobs = ref<UpdateJob[]>([])
  const discoverStatus = ref<DiscoverStatus | null>(null)
  const loading = ref(false)
  const discovering = ref(false)
  const error = ref<string | null>(null)

  // ===========================================================================
  // Computed Properties
  // ===========================================================================

  const updateCount = computed(
    () => summary.value?.system_update_count ?? 0,
  )

  const securityCount = computed(
    () => summary.value?.security_update_count ?? 0,
  )

  const nodesWithUpdates = computed(
    () => summary.value?.nodes_with_updates ?? 0,
  )

  const hasUpdates = computed(() => updateCount.value > 0)

  const lastChecked = computed(
    () => summary.value?.last_checked ?? null,
  )

  const isDiscovering = computed(
    () =>
      discovering.value ||
      discoverStatus.value?.status === 'running' ||
      discoverStatus.value?.status === 'pending',
  )

  const hasRunningJobs = computed(() =>
    jobs.value.some(
      (j) => j.status === 'pending' || j.status === 'running',
    ),
  )

  // ===========================================================================
  // API Methods
  // ===========================================================================

  async function fetchSummary(): Promise<UpdateSummary | null> {
    try {
      // Silent fail for badge polling — single-shot, no failure WARN.
      const data = await slmApiClient.get<UpdateSummary>('/updates/summary', {
        maxRetries: 1,
        suppressErrorLog: true,
      })
      summary.value = data
      return data
    } catch {
      // Silent fail for badge polling — don't overwrite error
      return null
    }
  }

  async function fetchPackages(
    nodeId?: string,
    severity?: string,
  ): Promise<UpdatePackage[]> {
    loading.value = true
    error.value = null
    try {
      const query = new URLSearchParams()
      if (nodeId) query.set('node_id', nodeId)
      if (severity) query.set('severity', severity)
      const qs = query.toString()
      const data = await slmApiClient.get<PackagesResponse>(
        `/updates/packages${qs ? `?${qs}` : ''}`,
      )
      packages.value = data.packages
      packagesByNode.value = data.by_node
      return data.packages
    } catch (e) {
      error.value =
        e instanceof Error ? e.message : 'Failed to fetch packages'
      return []
    } finally {
      loading.value = false
    }
  }

  async function discoverUpdates(
    nodeIds?: string[],
    role?: string,
  ): Promise<string | null> {
    discovering.value = true
    error.value = null
    try {
      const data = await slmApiClient.post<DiscoverResponse>(
        '/updates/discover',
        { node_ids: nodeIds || null, role: role || null },
      )
      if (data.success) {
        discoverStatus.value = {
          job_id: data.job_id,
          status: 'pending',
          progress: 0,
          message: 'Starting discovery...',
          nodes_checked: 0,
          total_nodes: 0,
          packages_found: 0,
          started_at: null,
          completed_at: null,
        }
        return data.job_id
      }
      error.value = data.message
      return null
    } catch (e) {
      error.value =
        e instanceof Error ? e.message : 'Failed to start discovery'
      return null
    } finally {
      discovering.value = false
    }
  }

  async function pollDiscoverStatus(
    jobId: string,
  ): Promise<DiscoverStatus | null> {
    try {
      // Single-shot poll — don't retry/backoff or emit a WARN on a miss.
      const data = await slmApiClient.get<DiscoverStatus>(
        `/updates/discover/${jobId}`,
        { maxRetries: 1, suppressErrorLog: true },
      )
      discoverStatus.value = data
      return data
    } catch {
      return null
    }
  }

  async function fetchJobs(limit = 20): Promise<UpdateJob[]> {
    try {
      const query = new URLSearchParams({ limit: String(limit) })
      const data = await slmApiClient.get<{
        jobs: UpdateJob[]
        total: number
      }>(`/updates/jobs?${query.toString()}`)
      jobs.value = data.jobs
      return data.jobs
    } catch (e) {
      error.value =
        e instanceof Error ? e.message : 'Failed to fetch jobs'
      return []
    }
  }

  async function applyUpdates(
    nodeId: string,
    updateIds: string[],
  ): Promise<boolean> {
    loading.value = true
    error.value = null
    try {
      const data = await slmApiClient.post<MutationResult>('/updates/apply', {
        node_id: nodeId,
        update_ids: updateIds,
      })
      if (data.success) {
        await fetchJobs()
        return true
      }
      error.value = data.message ?? null
      return false
    } catch (e) {
      error.value =
        e instanceof Error ? e.message : 'Failed to apply updates'
      return false
    } finally {
      loading.value = false
    }
  }

  async function upgradeAll(nodeId: string): Promise<boolean> {
    loading.value = true
    error.value = null
    try {
      const data = await slmApiClient.post<MutationResult>('/updates/apply-all', {
        node_id: nodeId,
        upgrade_all: true,
      })
      if (data.success) {
        await fetchJobs()
        return true
      }
      error.value = data.message ?? null
      return false
    } catch (e) {
      error.value =
        e instanceof Error ? e.message : 'Failed to upgrade all'
      return false
    } finally {
      loading.value = false
    }
  }

  async function cancelJob(jobId: string): Promise<boolean> {
    try {
      const data = await slmApiClient.post<MutationResult>(
        `/updates/jobs/${jobId}/cancel`,
      )
      if (data.success) {
        await fetchJobs()
        return true
      }
      return false
    } catch (e) {
      error.value =
        e instanceof Error ? e.message : 'Failed to cancel job'
      return false
    }
  }

  function clearError(): void {
    error.value = null
  }

  // ===========================================================================
  // Return Public API
  // ===========================================================================

  return {
    // State (readonly)
    summary: readonly(summary),
    packages: readonly(packages),
    packagesByNode: readonly(packagesByNode),
    jobs: readonly(jobs),
    discoverStatus: readonly(discoverStatus),
    loading: readonly(loading),
    discovering: readonly(discovering),
    error: readonly(error),

    // Computed
    updateCount,
    securityCount,
    nodesWithUpdates,
    hasUpdates,
    lastChecked,
    isDiscovering,
    hasRunningJobs,

    // Methods
    fetchSummary,
    fetchPackages,
    discoverUpdates,
    pollDiscoverStatus,
    fetchJobs,
    applyUpdates,
    upgradeAll,
    cancelJob,
    clearError,
  }
}
