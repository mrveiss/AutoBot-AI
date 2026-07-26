// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * Roles Composable (Issue #779)
 *
 * Provides API integration for role management.
 */

import { ref, reactive } from 'vue'
import { slmApiClient } from '@/utils/ApiClient'

export interface Role {
  name: string
  display_name: string | null
  sync_type: string | null
  source_paths: string[]
  target_path: string
  systemd_service: string | null
  auto_restart: boolean
  health_check_port: number | null
  health_check_path: string | null
  pre_sync_cmd: string | null
  post_sync_cmd: string | null
  required: boolean
  degraded_without: string[]
  ansible_playbook: string | null
}

export interface NodeRoleItem {
  role_name: string
  assignment_type: string
  status: string
  current_version: string | null
  last_synced_at: string | null
  last_error: string | null
}

export interface PortInfo {
  port: number
  process: string | null
  pid: number | null
}

export interface NodeRolesInfo {
  node_id: string
  detected_roles: string[]
  role_versions: Record<string, string>
  listening_ports: PortInfo[]
  roles: NodeRoleItem[]
}

export interface SyncResult {
  success: boolean
  message: string
  role_name?: string
  commit?: string
  nodes_synced?: number
  results?: Array<{
    node_id: string
    success: boolean
    message: string
  }>
}

export interface FleetHealth {
  health: 'healthy' | 'degraded' | 'critical'
  required_down: string[]
  optional_down: string[]
  detail: string
}

export interface PlaybookMigrateResult {
  success: boolean
  role: string
  target_node_id: string
  playbook: string
  output: string
  returncode: number
}

// Post-sync action types (Issue #1243)
export interface PostSyncAction {
  role_name: string
  display_name: string
  category: 'build' | 'restart' | 'schema' | 'install'
  label: string
  command: string | null
  systemd_service: string | null
}

export interface NodeActionsResponse {
  node_id: string
  actions: PostSyncAction[]
}

export interface ExecuteActionResult {
  success: boolean
  node_id: string
  role_name: string
  category: string
  output: string
}

// Decommission types (Issue #1369)
export interface DecommissionRoleInfo {
  role_name: string
  display_name: string
  reason: string
}

export interface DecommissionPreflight {
  can_proceed: boolean
  must_migrate: DecommissionRoleInfo[]
  should_migrate: DecommissionRoleInfo[]
  safe_to_remove: DecommissionRoleInfo[]
}

// =============================================================================
// slmApiClient adapter (#12420 Phase 2 batch 7)
//
// useRoles historically owned its own `axios.create()` instance (base URL built
// from getSlmApiBase(), a request interceptor injecting the SLM bearer token, no
// response interceptor). This adapter routes every call through the canonical
// `slmApiClient` — where the auth token, base URL and centralised 401 handling
// now live — while reproducing the axios surface the methods below depend on so
// their bodies, and all consumers, stay unchanged:
//
//   * methods `await client.<verb>(endpoint, body?)` and read `response.data`
//     → the adapter returns `{ data }`.
//   * every catch reads `err.response?.data?.detail || err.message` → the
//     adapter throws an axios-shaped error carrying `response.status` +
//     `response.data` (and a `message` of `HTTP <n>` as the secondary fallback);
//     a network/timeout rejection surfaces the raw Error (no `.response`), so
//     `err.message` remains the fallback exactly as with axios.
//
// It delegates to `slmApiClient.rawRequest` (not the get/post/... helpers) on
// purpose: rawRequest is the single seam that injects the bearer token + base
// URL and runs the 401 handler, WITHOUT the helpers' GET retry/back-off or the
// `HTTP <n>: <msg>` error transform — preserving the original single-shot,
// structured-error behaviour every method relies on.
// =============================================================================

interface AxiosLikeResponse<T> {
  data: T
}

// Serialise an axios-style params object onto the endpoint, matching axios's
// default serialisation: scalars as `key=value`, arrays as repeated `key[]=value`
// (URLSearchParams encodes the brackets to `%5B%5D`, exactly as axios does). Only
// removeRole (scalar) and syncRole (scalar + array) pass a params object.
function withParams(endpoint: string, params?: Record<string, unknown>): string {
  if (!params) return endpoint
  const usp = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null) continue
    if (Array.isArray(value)) {
      for (const item of value) usp.append(`${key}[]`, String(item))
    } else {
      usp.append(key, String(value))
    }
  }
  const qs = usp.toString()
  if (!qs) return endpoint
  return endpoint.includes('?') ? `${endpoint}&${qs}` : `${endpoint}?${qs}`
}

async function adapterRequest<T>(
  method: string,
  endpoint: string,
  body?: unknown
): Promise<AxiosLikeResponse<T>> {
  const response = await slmApiClient.rawRequest(endpoint, { method, body })

  if (!response.ok) {
    let data: unknown = null
    try {
      data = await response.json()
    } catch {
      /* non-JSON error body — leave data null, mirroring axios */
    }
    const error = new Error(`HTTP ${response.status}`) as Error & {
      response: { status: number; data: unknown }
    }
    // Reproduce the axios error shape the catch blocks read (err.response.data.detail).
    error.response = { status: response.status, data }
    throw error
  }

  if (response.status === 204) return { data: {} as T }
  const contentType = response.headers.get('content-type')
  if (contentType && contentType.includes('application/json')) {
    return { data: (await response.json()) as T }
  }
  return { data: {} as T }
}

// Axios-compatible facade over slmApiClient consumed by every method below.
const client = {
  get: <T = unknown>(
    endpoint: string,
    config?: { params?: Record<string, unknown> }
  ): Promise<AxiosLikeResponse<T>> =>
    adapterRequest<T>('GET', withParams(endpoint, config?.params)),
  post: <T = unknown>(
    endpoint: string,
    body?: unknown,
    config?: { params?: Record<string, unknown> }
  ): Promise<AxiosLikeResponse<T>> =>
    adapterRequest<T>('POST', withParams(endpoint, config?.params), body ?? undefined),
  put: <T = unknown>(endpoint: string, body?: unknown): Promise<AxiosLikeResponse<T>> =>
    adapterRequest<T>('PUT', endpoint, body),
  delete: <T = unknown>(
    endpoint: string,
    config?: { params?: Record<string, unknown> }
  ): Promise<AxiosLikeResponse<T>> =>
    adapterRequest<T>('DELETE', withParams(endpoint, config?.params)),
}

export function useRoles() {
  const roles = ref<Role[]>([])
  const isLoading = ref(false)
  const error = ref<string | null>(null)
  const fleetHealth = ref<FleetHealth | null>(null)

  async function fetchRoles(): Promise<void> {
    isLoading.value = true
    error.value = null

    try {
      const response = await client.get<Role[]>('/roles')
      roles.value = response.data
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } }; message?: string }
      error.value = err.response?.data?.detail || err.message || 'Failed to fetch roles'
    } finally {
      isLoading.value = false
    }
  }

  async function getNodeRoles(nodeId: string): Promise<NodeRolesInfo | null> {
    try {
      const response = await client.get<NodeRolesInfo>(
        `/nodes/${nodeId}/detected-roles`
      )
      return response.data
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } }; message?: string }
      error.value = err.response?.data?.detail || err.message || 'Failed to fetch node roles'
      return null
    }
  }

  async function assignRole(
    nodeId: string,
    roleName: string,
    assignmentType: string = 'manual'
  ): Promise<NodeRoleItem | null> {
    try {
      const response = await client.post<NodeRoleItem>(
        `/nodes/${nodeId}/detected-roles`,
        { role_name: roleName, assignment_type: assignmentType }
      )
      return response.data
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } }; message?: string }
      error.value = err.response?.data?.detail || err.message || 'Failed to assign role'
      return null
    }
  }

  async function removeRole(
    nodeId: string,
    roleName: string,
    backup = false,
  ): Promise<{ success: boolean; message?: string; backup_path?: string }> {
    try {
      const response = await client.delete<{
        success: boolean
        message: string
        backup_path?: string
      }>(`/nodes/${nodeId}/detected-roles/${roleName}`, {
        params: { backup },
      })
      return response.data
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } }; message?: string }
      const msg = err.response?.data?.detail || err.message || 'Failed to remove role'
      error.value = msg
      return { success: false, message: msg }
    }
  }

  async function createRole(roleData: Partial<Role>): Promise<Role | null> {
    try {
      const response = await client.post<Role>('/roles', roleData)
      return response.data
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } }; message?: string }
      error.value = err.response?.data?.detail || err.message || 'Failed to create role'
      return null
    }
  }

  async function updateRole(roleName: string, roleData: Partial<Role>): Promise<Role | null> {
    try {
      const response = await client.put<Role>(`/roles/${roleName}`, roleData)
      return response.data
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } }; message?: string }
      error.value = err.response?.data?.detail || err.message || 'Failed to update role'
      return null
    }
  }

  async function deleteRole(roleName: string): Promise<boolean> {
    try {
      await client.delete(`/roles/${roleName}`)
      return true
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } }; message?: string }
      error.value = err.response?.data?.detail || err.message || 'Failed to delete role'
      return false
    }
  }

  async function syncRole(
    roleName: string,
    nodeIds?: string[],
    restart: boolean = true
  ): Promise<SyncResult> {
    try {
      const params: Record<string, unknown> = { restart }
      if (nodeIds && nodeIds.length > 0) {
        params.node_ids = nodeIds
      }
      const response = await client.post<SyncResult>(
        `/code-sync/roles/${roleName}/sync`,
        null,
        { params }
      )
      return response.data
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } }; message?: string }
      return {
        success: false,
        message: err.response?.data?.detail || err.message || 'Sync failed',
        nodes_synced: 0,
      }
    }
  }

  async function pullFromSource(): Promise<{ success: boolean; message: string; commit: string | null }> {
    try {
      const response = await client.post<{ success: boolean; message: string; commit: string | null }>(
        '/code-sync/pull'
      )
      return response.data
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } }; message?: string }
      return {
        success: false,
        message: err.response?.data?.detail || err.message || 'Pull failed',
        commit: null,
      }
    }
  }

  async function fetchFleetHealth(): Promise<void> {
    try {
      const response = await client.get<FleetHealth>('/roles/fleet-health')
      fleetHealth.value = response.data
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } }; message?: string }
      error.value = err.response?.data?.detail || err.message || 'Failed to fetch fleet health'
    }
  }

  async function migrateRole(
    roleName: string,
    targetNodeId: string
  ): Promise<PlaybookMigrateResult | null> {
    try {
      const response = await client.post<PlaybookMigrateResult>(
        `/roles/${roleName}/migrate`,
        { target_node_id: targetNodeId }
      )
      return response.data
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } }; message?: string }
      error.value = err.response?.data?.detail || err.message || 'Migration failed'
      return null
    }
  }

  // Post-sync actions (Issue #1243)
  async function fetchNodeActions(
    nodeId: string
  ): Promise<NodeActionsResponse | null> {
    try {
      const resp = await client.get<NodeActionsResponse>(
        `/roles/node-actions/${nodeId}`
      )
      return resp.data
    } catch (e: unknown) {
      const err = e as {
        response?: { data?: { detail?: string } }
        message?: string
      }
      error.value =
        err.response?.data?.detail ||
        err.message ||
        'Failed to fetch node actions'
      return null
    }
  }

  async function executeNodeAction(
    nodeId: string,
    roleName: string,
    category: string
  ): Promise<ExecuteActionResult | null> {
    try {
      const resp = await client.post<ExecuteActionResult>(
        `/roles/node-actions/${nodeId}/execute`,
        { role_name: roleName, category }
      )
      return resp.data
    } catch (e: unknown) {
      const err = e as {
        response?: { data?: { detail?: string } }
        message?: string
      }
      error.value =
        err.response?.data?.detail ||
        err.message ||
        'Failed to execute action'
      return null
    }
  }

  // Decommission API (Issue #1369)
  async function decommissionPreflight(
    nodeId: string
  ): Promise<DecommissionPreflight | null> {
    try {
      const resp = await client.get<DecommissionPreflight>(
        `/nodes/${nodeId}/decommission/preflight`
      )
      return resp.data
    } catch (e: unknown) {
      const err = e as {
        response?: { data?: { detail?: string } }
        message?: string
      }
      error.value =
        err.response?.data?.detail ||
        err.message ||
        'Failed to fetch decommission preflight'
      return null
    }
  }

  async function decommissionNode(
    nodeId: string,
    backup: boolean,
    confirmNodeId: string
  ): Promise<{ success: boolean; message?: string; deployment_id?: string; output?: string }> {
    try {
      const resp = await client.post<{
        success: boolean
        message: string
        deployment_id: string
        output: string
      }>(`/nodes/${nodeId}/decommission`, {
        backup,
        confirm_node_id: confirmNodeId,
      })
      return resp.data
    } catch (e: unknown) {
      const err = e as {
        response?: { data?: { detail?: string } }
        message?: string
      }
      const msg =
        err.response?.data?.detail ||
        err.message ||
        'Decommission failed'
      error.value = msg
      return { success: false, message: msg }
    }
  }

  async function reenrollNode(
    nodeId: string
  ): Promise<{ success: boolean; message?: string }> {
    try {
      const resp = await client.post<{
        success: boolean
        message: string
      }>(`/nodes/${nodeId}/reenroll`)
      return resp.data
    } catch (e: unknown) {
      const err = e as {
        response?: { data?: { detail?: string } }
        message?: string
      }
      const msg =
        err.response?.data?.detail ||
        err.message ||
        'Re-enrollment failed'
      error.value = msg
      return { success: false, message: msg }
    }
  }

  return reactive({
    roles,
    isLoading,
    error,
    fleetHealth,
    fetchRoles,
    getNodeRoles,
    assignRole,
    removeRole,
    createRole,
    updateRole,
    deleteRole,
    syncRole,
    pullFromSource,
    fetchFleetHealth,
    migrateRole,
    fetchNodeActions,
    executeNodeAction,
    decommissionPreflight,
    decommissionNode,
    reenrollNode,
  })
}
