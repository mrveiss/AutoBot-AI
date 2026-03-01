// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * Roles Composable (Issue #779)
 *
 * Provides API integration for role management.
 */

import { ref, reactive } from 'vue'
import axios from 'axios'

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

export function useRoles() {
  const roles = ref<Role[]>([])
  const isLoading = ref(false)
  const error = ref<string | null>(null)
  const fleetHealth = ref<FleetHealth | null>(null)

  // SLM backend endpoints are at /api/* (proxied by nginx)
  // NOT /autobot-api/* which goes to the Main AutoBot backend
  const API_BASE = ''

  // Create axios instance with auth
  const client = axios.create({ baseURL: API_BASE })
  client.interceptors.request.use((config) => {
    const token = localStorage.getItem('slm_access_token')
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  })

  async function fetchRoles(): Promise<void> {
    isLoading.value = true
    error.value = null

    try {
      const response = await client.get<Role[]>('/api/roles')
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
        `/api/nodes/${nodeId}/detected-roles`
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
        `/api/nodes/${nodeId}/detected-roles`,
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
      }>(`/api/nodes/${nodeId}/detected-roles/${roleName}`, {
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
      const response = await client.post<Role>('/api/roles', roleData)
      return response.data
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } }; message?: string }
      error.value = err.response?.data?.detail || err.message || 'Failed to create role'
      return null
    }
  }

  async function updateRole(roleName: string, roleData: Partial<Role>): Promise<Role | null> {
    try {
      const response = await client.put<Role>(`/api/roles/${roleName}`, roleData)
      return response.data
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } }; message?: string }
      error.value = err.response?.data?.detail || err.message || 'Failed to update role'
      return null
    }
  }

  async function deleteRole(roleName: string): Promise<boolean> {
    try {
      await client.delete(`/api/roles/${roleName}`)
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
        `/api/code-sync/roles/${roleName}/sync`,
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
        `/api/code-sync/pull`
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
      const response = await client.get<FleetHealth>('/api/roles/fleet-health')
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
        `/api/roles/${roleName}/migrate`,
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
        `/api/roles/node-actions/${nodeId}`
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
        `/api/roles/node-actions/${nodeId}/execute`,
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
  })
}
