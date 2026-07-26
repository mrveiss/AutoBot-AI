// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * Code Source Composable (Issue #779)
 *
 * Manages the code-source node assignment for the AutoBot repository.
 * The code source is the designated node that has git access to pull
 * the latest code changes which can then be synced to other nodes.
 *
 * Migrated onto the canonical `slmApiClient` (#12420 Phase 2). The client
 * resolves the base URL via `getSlmApiBase()`, injects the SLM bearer token
 * (same `slm_access_token` storage the auth store reads), and centrally handles
 * 401 for these non-auth endpoints (clear session + redirect to `/login`) —
 * replacing the previous per-composable axios instance and request interceptor.
 * Call sites pass endpoints relative to the API base and receive parsed JSON
 * directly (no axios `.data`). The client throws on non-2xx, so each method
 * keeps its try/catch and populates `error.value` from the thrown message,
 * preserving the graceful `null`/`false` return semantics.
 */

import { ref } from 'vue'
import slmApiClient from '@/utils/ApiClient'

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

  /**
   * Fetch the current code source configuration.
   */
  async function fetchCodeSource(): Promise<void> {
    isLoading.value = true
    error.value = null

    try {
      codeSource.value = await slmApiClient.get<CodeSource | null>('/code-source')
    } catch (e: unknown) {
      error.value = e instanceof Error ? e.message : 'Failed to fetch code source'
    } finally {
      isLoading.value = false
    }
  }

  /**
   * Assign a node as the code source.
   *
   * @param nodeId - The ID of the node to assign as code source
   * @param repoPath - The repository path on the node (default: /opt/autobot/code_source)
   * @param branch - The git branch to track (default: Dev_new_gui)
   */
  async function assignCodeSource(
    nodeId: string,
    repoPath: string = '/opt/autobot/code_source',
    branch: string = 'Dev_new_gui'
  ): Promise<CodeSource | null> {
    isLoading.value = true
    error.value = null

    try {
      const result = await slmApiClient.post<CodeSource>('/code-source/assign', {
        node_id: nodeId,
        repo_path: repoPath,
        branch,
      })
      codeSource.value = result
      return result
    } catch (e: unknown) {
      error.value = e instanceof Error ? e.message : 'Failed to assign code source'
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
      await slmApiClient.delete('/code-source/assign')
      codeSource.value = null
      return true
    } catch (e: unknown) {
      error.value = e instanceof Error ? e.message : 'Failed to remove code source'
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
