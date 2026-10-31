// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * `slmApi` node, certificate, update and role calls (#19834): ported from the SLM app's
 * `useSlmApi`, with the response read from the generated contract instead of asserted at the call.
 */
import type { components } from '@autobot/slm-contract/generated'
import type {
  ConnectionTestRequest,
  ConnectionTestResult,
  FleetUpdateSummary,
  NodeCreate,
  NodeEvent,
  NodeEventFilters,
  NodeRole,
  NodeUpdate,
  NodeUpdateCheckResponse,
  RoleInfo,
  SLMNode,
} from '@autobot/slm-contract'
import { slmRequest, slmRequestAs } from './transport'

type Schemas = components['schemas']
type NodeResponse = Schemas['NodeResponse']
type NodeEventResponse = Schemas['NodeEventResponse']

/** The certificate the backend returns for a node (`CertificateResponse`). */
export type NodeCertificate = Schemas['CertificateResponse']

/** The body of an action route whose 200 the contract leaves undeclared (apply updates). */
export interface ApplyUpdatesResult {
  applied_updates: string[]
  failed_updates: string[]
}

/** The backend stores metrics on the node; the UI expects a nested health object. */
function healthStatusOf(status: string): 'healthy' | 'degraded' | 'unhealthy' | 'unknown' {
  if (status === 'online') return 'healthy'
  if (status === 'degraded') return 'degraded'
  if (status === 'error') return 'unhealthy'
  return 'unknown'
}

/** Maps the wire node to the UI `SLMNode` (health nested, optional lists defaulted). */
export function mapNode(node: NodeResponse): SLMNode {
  return {
    node_id: node.node_id,
    hostname: node.hostname,
    ip_address: node.ip_address,
    status: node.status as SLMNode['status'],
    roles: node.roles as SLMNode['roles'],
    detected_roles: node.detected_roles ?? [],
    ssh_user: node.ssh_user ?? undefined,
    ssh_port: node.ssh_port ?? undefined,
    auth_method: (node.auth_method ?? undefined) as SLMNode['auth_method'],
    health: {
      status: healthStatusOf(node.status),
      cpu_percent: node.cpu_percent,
      memory_percent: node.memory_percent,
      disk_percent: node.disk_percent,
      last_heartbeat: node.last_heartbeat ?? null,
      services: [],
    },
    created_at: node.created_at,
    updated_at: node.updated_at,
    code_status: (node.code_status as SLMNode['code_status']) || undefined,
    code_version: node.code_version || undefined,
    // #14794: an older backend that does not send it yields an empty list, which consumers iterate.
    unreachable_roles: (node as { unreachable_roles?: string[] }).unreachable_roles ?? [],
  }
}

function mapEvent(event: NodeEventResponse): NodeEvent {
  return {
    id: event.event_id,
    node_id: event.node_id,
    type: event.event_type as NodeEvent['type'],
    severity: event.severity as NodeEvent['severity'],
    message: event.message,
    timestamp: event.created_at,
    details: event.details ?? {},
  }
}

export async function getNodes(): Promise<SLMNode[]> {
  const body = await slmRequest('get', '/api/nodes')
  return body.nodes.map(mapNode)
}

export async function getNode(nodeId: string): Promise<SLMNode> {
  return mapNode(await slmRequest('get', '/api/nodes/{node_id}', { params: { node_id: nodeId } }))
}

export async function registerNode(data: NodeCreate): Promise<SLMNode> {
  return mapNode(await slmRequest('post', '/api/nodes', { body: data }))
}

export async function updateNode(nodeId: string, data: NodeUpdate): Promise<SLMNode> {
  const node = await slmRequest('patch', '/api/nodes/{node_id}', { params: { node_id: nodeId }, body: data })
  return mapNode(node)
}

export async function deleteNode(nodeId: string): Promise<void> {
  await slmRequest('delete', '/api/nodes/{node_id}', { params: { node_id: nodeId } })
}

export async function updateNodeRoles(nodeId: string, roles: NodeRole[]): Promise<SLMNode> {
  const node = await slmRequest('patch', '/api/nodes/{node_id}/roles', { params: { node_id: nodeId }, body: { roles } })
  return mapNode(node)
}

/** The 200 body is undeclared in the contract; callers read nothing from it. */
export async function enrollNode(nodeId: string, sshPassword?: string): Promise<Record<string, unknown>> {
  const body = sshPassword ? { ssh_password: sshPassword } : {}
  return slmRequestAs<Record<string, unknown>, '/api/nodes/{node_id}/enroll', 'post'>(
    'post',
    '/api/nodes/{node_id}/enroll',
    { params: { node_id: nodeId }, body },
  )
}

export async function testConnection(request: ConnectionTestRequest): Promise<ConnectionTestResult> {
  const body = await slmRequest('post', '/api/nodes/test-connection', { body: request })
  // The contract's nullable fields are absent on the UI type; `os_info` is the field its `os` reads.
  return {
    success: body.success,
    message: body.message,
    error: body.error ?? undefined,
    latency_ms: body.latency_ms ?? undefined,
    os: body.os_info ?? undefined,
  }
}

export async function getNodeEvents(nodeId: string, filters?: NodeEventFilters): Promise<NodeEvent[]> {
  const query = { type: filters?.type, severity: filters?.severity, limit: filters?.limit, offset: filters?.offset }
  const body = await slmRequest('get', '/api/nodes/{node_id}/events', { params: { node_id: nodeId }, query })
  return body.events.map(mapEvent)
}

export async function getCertificateStatus(nodeId: string): Promise<NodeCertificate> {
  return slmRequest('get', '/api/nodes/{node_id}/certificate', { params: { node_id: nodeId } })
}

export async function renewCertificate(nodeId: string): Promise<Schemas['CertificateActionResponse']> {
  return slmRequest('post', '/api/nodes/{node_id}/certificate/renew', { params: { node_id: nodeId } })
}

export async function deployCertificate(nodeId: string): Promise<Schemas['CertificateActionResponse']> {
  return slmRequest('post', '/api/nodes/{node_id}/certificate/deploy', { params: { node_id: nodeId } })
}

export async function getFleetUpdateSummary(): Promise<FleetUpdateSummary> {
  return slmRequest('get', '/api/updates/fleet-summary')
}

/** The 200 body is undeclared in the contract; the shape is `NodeUpdateCheckResponse`. */
export async function checkUpdates(nodeId: string): Promise<NodeUpdateCheckResponse> {
  return slmRequestAs<NodeUpdateCheckResponse, '/api/nodes/{node_id}/updates', 'get'>(
    'get',
    '/api/nodes/{node_id}/updates',
    { params: { node_id: nodeId } },
  )
}

/** The 200 body is undeclared in the contract; the shape is `ApplyUpdatesResult`. */
export async function applyUpdates(nodeId: string, updateIds: string[]): Promise<ApplyUpdatesResult> {
  return slmRequestAs<ApplyUpdatesResult, '/api/nodes/{node_id}/updates/apply', 'post'>(
    'post',
    '/api/nodes/{node_id}/updates/apply',
    { params: { node_id: nodeId }, body: { update_ids: updateIds } },
  )
}

export async function getRoles(): Promise<RoleInfo[]> {
  const body = await slmRequest('get', '/api/deployments/roles')
  return body.roles as RoleInfo[]
}
