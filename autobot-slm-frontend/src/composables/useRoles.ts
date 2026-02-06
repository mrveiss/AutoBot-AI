// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * Roles Composable (Issue #779)
 *
 * Provides API integration for role management.
 */

import { ref } from 'vue'
import axios from 'axios'
import { getBackendUrl } from '@/config/ssot-config'

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

export function useRoles() {
  const roles = ref<Role[]>([])
  const isLoading = ref(false)
  const error = ref<string | null>(null)

  const API_BASE = getBackendUrl()

  async function fetchRoles(): Promise<void> {
    isLoading.value = true
    error.value = null

    try {
      const response = await axios.get<Role[]>(`${API_BASE}/api/roles`)
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
      const response = await axios.get<NodeRolesInfo>(
        `${API_BASE}/api/nodes/${nodeId}/detected-roles`
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
      const response = await axios.post<NodeRoleItem>(
        `${API_BASE}/api/nodes/${nodeId}/detected-roles`,
        { role_name: roleName, assignment_type: assignmentType }
      )
      return response.data
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } }; message?: string }
      error.value = err.response?.data?.detail || err.message || 'Failed to assign role'
      return null
    }
  }

  async function removeRole(nodeId: string, roleName: string): Promise<boolean> {
    try {
      await axios.delete(`${API_BASE}/api/nodes/${nodeId}/detected-roles/${roleName}`)
      return true
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } }; message?: string }
      error.value = err.response?.data?.detail || err.message || 'Failed to remove role'
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
      const response = await axios.post<SyncResult>(
        `${API_BASE}/api/code-sync/roles/${roleName}/sync`,
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
      const response = await axios.post<{ success: boolean; message: string; commit: string | null }>(
        `${API_BASE}/api/code-sync/pull`
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

  return {
    roles,
    isLoading,
    error,
    fetchRoles,
    getNodeRoles,
    assignRole,
    removeRole,
    syncRole,
    pullFromSource,
  }
}
