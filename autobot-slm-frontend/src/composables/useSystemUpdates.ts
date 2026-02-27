// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * System Updates Composable
 *
 * Provides reactive state and methods for system package update
 * discovery and management across the SLM fleet.
 */

import { ref, computed, readonly } from 'vue'
import axios, { type AxiosInstance } from 'axios'

const API_BASE = '/api'

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

// =============================================================================
// Composable
// =============================================================================

export function useSystemUpdates() {
  const client: AxiosInstance = axios.create({
    baseURL: API_BASE,
    headers: { 'Content-Type': 'application/json' },
  })

  client.interceptors.request.use((config) => {
    const token = localStorage.getItem('slm_access_token')
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  })

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
      const response = await client.get<UpdateSummary>(
        '/updates/summary',
      )
      summary.value = response.data
      return response.data
    } catch (e) {
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
      const params: Record<string, string> = {}
      if (nodeId) params.node_id = nodeId
      if (severity) params.severity = severity
      const response = await client.get<PackagesResponse>(
        '/updates/packages',
        { params },
      )
      packages.value = response.data.packages
      packagesByNode.value = response.data.by_node
      return response.data.packages
    } catch (e) {
      error.value =
        e instanceof Error ? e.message : 'Failed to fetch packages'
      if (axios.isAxiosError(e) && e.response?.data?.detail) {
        error.value = e.response.data.detail
      }
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
      const response = await client.post<DiscoverResponse>(
        '/updates/discover',
        { node_ids: nodeIds || null, role: role || null },
      )
      if (response.data.success) {
        discoverStatus.value = {
          job_id: response.data.job_id,
          status: 'pending',
          progress: 0,
          message: 'Starting discovery...',
          nodes_checked: 0,
          total_nodes: 0,
          packages_found: 0,
          started_at: null,
          completed_at: null,
        }
        return response.data.job_id
      }
      error.value = response.data.message
      return null
    } catch (e) {
      error.value =
        e instanceof Error ? e.message : 'Failed to start discovery'
      if (axios.isAxiosError(e) && e.response?.data?.detail) {
        error.value = e.response.data.detail
      }
      return null
    } finally {
      discovering.value = false
    }
  }

  async function pollDiscoverStatus(
    jobId: string,
  ): Promise<DiscoverStatus | null> {
    try {
      const response = await client.get<DiscoverStatus>(
        `/updates/discover/${jobId}`,
      )
      discoverStatus.value = response.data
      return response.data
    } catch (e) {
      return null
    }
  }

  async function fetchJobs(limit = 20): Promise<UpdateJob[]> {
    try {
      const response = await client.get<{
        jobs: UpdateJob[]
        total: number
      }>('/updates/jobs', { params: { limit } })
      jobs.value = response.data.jobs
      return response.data.jobs
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
      const response = await client.post('/updates/apply', {
        node_id: nodeId,
        update_ids: updateIds,
      })
      if (response.data.success) {
        await fetchJobs()
        return true
      }
      error.value = response.data.message
      return false
    } catch (e) {
      error.value =
        e instanceof Error ? e.message : 'Failed to apply updates'
      if (axios.isAxiosError(e) && e.response?.data?.detail) {
        error.value = e.response.data.detail
      }
      return false
    } finally {
      loading.value = false
    }
  }

  async function upgradeAll(nodeId: string): Promise<boolean> {
    loading.value = true
    error.value = null
    try {
      const response = await client.post('/updates/apply-all', {
        node_id: nodeId,
        upgrade_all: true,
      })
      if (response.data.success) {
        await fetchJobs()
        return true
      }
      error.value = response.data.message
      return false
    } catch (e) {
      error.value =
        e instanceof Error ? e.message : 'Failed to upgrade all'
      if (axios.isAxiosError(e) && e.response?.data?.detail) {
        error.value = e.response.data.detail
      }
      return false
    } finally {
      loading.value = false
    }
  }

  async function cancelJob(jobId: string): Promise<boolean> {
    try {
      const response = await client.post(
        `/updates/jobs/${jobId}/cancel`,
      )
      if (response.data.success) {
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
