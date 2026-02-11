// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * Code Source Composable (Issue #779)
 *
 * Manages the code-source node assignment for the AutoBot repository.
 * The code source is the designated node that has git access to pull
 * the latest code changes which can then be synced to other nodes.
 */

import { ref } from 'vue'
import axios from 'axios'
import { useAuthStore } from '@/stores/auth'
import { getBackendUrl } from '@/config/ssot-config'

export interface CodeSource {
  node_id: string
  hostname: string | null
  ip_address: string | null
  repo_path: string
  branch: string
  last_known_commit: string | null
  last_notified_at: string | null
  is_active: boolean
}

export interface CodeSourceAssignRequest {
  node_id: string
  repo_path?: string
  branch?: string
}

export function useCodeSource() {
  const codeSource = ref<CodeSource | null>(null)
  const isLoading = ref(false)
  const error = ref<string | null>(null)

  const API_BASE = getBackendUrl()
  const authStore = useAuthStore()

  const api = axios.create({ baseURL: API_BASE, timeout: 15000 })
  api.interceptors.request.use((config) => {
    const token = authStore.token
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  })

  /**
   * Fetch the current code source configuration.
   */
  async function fetchCodeSource(): Promise<void> {
    isLoading.value = true
    error.value = null

    try {
      const response = await api.get<CodeSource | null>('/api/code-source')
      codeSource.value = response.data
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } }; message?: string }
      error.value = err.response?.data?.detail || err.message || 'Failed to fetch code source'
    } finally {
      isLoading.value = false
    }
  }

  /**
   * Assign a node as the code source.
   *
   * @param nodeId - The ID of the node to assign as code source
   * @param repoPath - The repository path on the node (default: /opt/autobot)
   * @param branch - The git branch to track (default: main)
   */
  async function assignCodeSource(
    nodeId: string,
    repoPath: string = '/opt/autobot',
    branch: string = 'main'
  ): Promise<CodeSource | null> {
    isLoading.value = true
    error.value = null

    try {
      const response = await api.post<CodeSource>('/api/code-source/assign', {
        node_id: nodeId,
        repo_path: repoPath,
        branch,
      })
      codeSource.value = response.data
      return response.data
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } }; message?: string }
      error.value = err.response?.data?.detail || err.message || 'Failed to assign code source'
      return null
    } finally {
      isLoading.value = false
    }
  }

  /**
   * Remove the current code source assignment.
   */
  async function removeCodeSource(): Promise<boolean> {
    isLoading.value = true
    error.value = null

    try {
      await api.delete('/api/code-source/assign')
      codeSource.value = null
      return true
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } }; message?: string }
      error.value = err.response?.data?.detail || err.message || 'Failed to remove code source'
      return false
    } finally {
      isLoading.value = false
    }
  }

  /**
   * Clear the current error state.
   */
  function clearError(): void {
    error.value = null
  }

  return {
    codeSource,
    isLoading,
    error,
    fetchCodeSource,
    assignCodeSource,
    removeCodeSource,
    clearError,
  }
}
