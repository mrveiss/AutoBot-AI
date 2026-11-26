// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * The node list's backend shape and its mapping to the frontend `SLMNode`, split out of useSlmApi.ts
 * (#21584) so that file does not grow past its size ceiling.
 */

import type { SLMNode } from '@/types/slm'

// Backend response types (different from frontend SLMNode)
export interface BackendNodeResponse {
  id: number
  node_id: string
  hostname: string
  ip_address: string
  status: string
  roles: string[]
  detected_roles?: string[]
  cpu_percent: number
  memory_percent: number
  disk_percent: number
  last_heartbeat: string | null
  agent_version: string | null
  os_info: string | null
  created_at: string
  updated_at: string
  ssh_user?: string
  ssh_port?: number
  auth_method?: string
  code_status?: string
  code_version?: string
  // #14794: the backend reports roles that reach no deploy path. It was absent
  // here, so the mapper below silently dropped it and the setup wizard's toast
  // could never fire — producer and consumer both built, the hop missing.
  unreachable_roles?: string[]
}

export interface NodesResponse {
  nodes: BackendNodeResponse[]
  total: number
}

/**
 * Maps backend node response to frontend SLMNode type
 * Backend stores metrics directly, frontend expects nested health object
 */
export function mapBackendNode(node: BackendNodeResponse): SLMNode {
  return {
    node_id: node.node_id,
    hostname: node.hostname,
    ip_address: node.ip_address,
    status: node.status as SLMNode['status'],
    roles: node.roles as SLMNode['roles'],
    detected_roles: node.detected_roles ?? [],
    ssh_user: node.ssh_user,
    ssh_port: node.ssh_port,
    auth_method: node.auth_method as SLMNode['auth_method'],
    health: {
      status: node.status === 'online' ? 'healthy' :
              node.status === 'degraded' ? 'degraded' :
              node.status === 'error' ? 'unhealthy' : 'unknown',
      cpu_percent: node.cpu_percent,
      memory_percent: node.memory_percent,
      disk_percent: node.disk_percent,
      last_heartbeat: node.last_heartbeat,
      services: [],
    },
    created_at: node.created_at,
    updated_at: node.updated_at,
    code_status: (node.code_status as SLMNode['code_status']) || undefined,
    code_version: node.code_version || undefined,
    // #14794: carry it through. Defaulted so an older backend that does not
    // send the field yields an empty list rather than undefined, which is what
    // the consumers iterate.
    unreachable_roles: node.unreachable_roles ?? [],
  }
}
