// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * SLM API Composable
 *
 * Provides REST API integration for all SLM endpoints.
 */

import axios, { type AxiosInstance } from 'axios'
import type {
  SLMNode,
  NodeHealth,
  NodeCreate,
  NodeUpdate,
  NodeRole,
  NodeEvent,
  NodeEventFilters,
  CertificateInfo,
  UpdateInfo,
  ConnectionTestRequest,
  ConnectionTestResult,
  Deployment,
  DeploymentRequest,
  Backup,
  BackupRequest,
  Replication,
  ReplicationRequest,
  RoleInfo,
  RoleListResponse,
} from '@/types/slm'

// SLM Admin uses the local SLM backend API
const API_BASE = '/api'

// Backend response types (different from frontend SLMNode)
interface BackendNodeResponse {
  id: number
  node_id: string
  hostname: string
  ip_address: string
  status: string
  roles: string[]
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
}

interface NodesResponse {
  nodes: BackendNodeResponse[]
  total: number
}

/**
 * Maps backend node response to frontend SLMNode type
 * Backend stores metrics directly, frontend expects nested health object
 */
function mapBackendNode(node: BackendNodeResponse): SLMNode {
  return {
    node_id: node.node_id,
    hostname: node.hostname,
    ip_address: node.ip_address,
    status: node.status as SLMNode['status'],
    roles: node.roles as SLMNode['roles'],
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
  }
}

interface DeploymentsResponse {
  deployments: Deployment[]
  total: number
}

interface BackupsResponse {
  backups: Backup[]
  total: number
}

interface ReplicationsResponse {
  replications: Replication[]
  total: number
}

interface ActionResponse {
  action: string
  success: boolean
  message: string
  resource_id?: string
}

export function useSlmApi() {
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

  // Nodes
  async function getNodes(): Promise<SLMNode[]> {
    const response = await client.get<NodesResponse>('/nodes')
    return response.data.nodes.map(mapBackendNode)
  }

  async function getNode(nodeId: string): Promise<SLMNode> {
    const response = await client.get<BackendNodeResponse>(`/nodes/${nodeId}`)
    return mapBackendNode(response.data)
  }

  async function getNodeHealth(nodeId: string): Promise<NodeHealth> {
    const response = await client.get<NodeHealth>(`/nodes/${nodeId}/health`)
    return response.data
  }

  async function registerNode(nodeData: NodeCreate): Promise<SLMNode> {
    const response = await client.post<BackendNodeResponse>('/nodes', nodeData)
    return mapBackendNode(response.data)
  }

  async function updateNode(nodeId: string, data: NodeUpdate): Promise<SLMNode> {
    const response = await client.patch<BackendNodeResponse>(`/nodes/${nodeId}`, data)
    return mapBackendNode(response.data)
  }

  async function deleteNode(nodeId: string): Promise<void> {
    await client.delete(`/nodes/${nodeId}`)
  }

  async function replaceNode(nodeId: string, nodeData: NodeCreate): Promise<SLMNode> {
    const response = await client.put<BackendNodeResponse>(`/nodes/${nodeId}/replace`, nodeData)
    return mapBackendNode(response.data)
  }

  async function updateNodeRoles(nodeId: string, roles: NodeRole[]): Promise<SLMNode> {
    const response = await client.patch<BackendNodeResponse>(`/nodes/${nodeId}/roles`, { roles })
    return mapBackendNode(response.data)
  }

  async function enrollNode(nodeId: string, sshPassword?: string): Promise<ActionResponse> {
    const body = sshPassword ? { ssh_password: sshPassword } : {}
    const response = await client.post<ActionResponse>(`/nodes/${nodeId}/enroll`, body)
    return response.data
  }

  async function drainNode(nodeId: string): Promise<SLMNode> {
    const response = await client.post<BackendNodeResponse>(`/nodes/${nodeId}/drain`)
    return mapBackendNode(response.data)
  }

  async function resumeNode(nodeId: string): Promise<SLMNode> {
    const response = await client.post<BackendNodeResponse>(`/nodes/${nodeId}/resume`)
    return mapBackendNode(response.data)
  }

  async function testConnection(request: ConnectionTestRequest): Promise<ConnectionTestResult> {
    const response = await client.post<ConnectionTestResult>('/nodes/test-connection', request)
    return response.data
  }

  // Node Events
  interface BackendNodeEvent {
    event_id: string
    node_id: string
    event_type: string
    severity: string
    message: string
    details: Record<string, unknown>
    created_at: string
  }

  function mapBackendEvent(event: BackendNodeEvent): NodeEvent {
    return {
      id: event.event_id,
      node_id: event.node_id,
      type: event.event_type as NodeEvent['type'],
      severity: event.severity as NodeEvent['severity'],
      message: event.message,
      timestamp: event.created_at,
      details: event.details,
    }
  }

  async function getNodeEvents(nodeId: string, filters?: NodeEventFilters): Promise<NodeEvent[]> {
    const params = new URLSearchParams()
    if (filters?.type) params.append('type', filters.type)
    if (filters?.severity) params.append('severity', filters.severity)
    if (filters?.limit) params.append('limit', filters.limit.toString())
    if (filters?.offset) params.append('offset', filters.offset.toString())

    const response = await client.get<{ events: BackendNodeEvent[], total: number }>(
      `/nodes/${nodeId}/events?${params.toString()}`
    )
    return response.data.events.map(mapBackendEvent)
  }

  // Certificates
  async function getCertificateStatus(nodeId: string): Promise<CertificateInfo> {
    const response = await client.get<CertificateInfo>(`/nodes/${nodeId}/certificate`)
    return response.data
  }

  async function renewCertificate(nodeId: string): Promise<ActionResponse> {
    const response = await client.post<ActionResponse>(`/nodes/${nodeId}/certificate/renew`)
    return response.data
  }

  async function deployCertificate(nodeId: string): Promise<ActionResponse> {
    const response = await client.post<ActionResponse>(`/nodes/${nodeId}/certificate/deploy`)
    return response.data
  }

  // Updates
  async function checkUpdates(nodeId: string): Promise<UpdateInfo[]> {
    const response = await client.get<{ updates: UpdateInfo[] }>(`/nodes/${nodeId}/updates`)
    return response.data.updates
  }

  async function applyUpdates(
    nodeId: string,
    updateIds: string[]
  ): Promise<{ applied_updates: string[]; failed_updates: string[] }> {
    const response = await client.post(`/nodes/${nodeId}/updates/apply`, { update_ids: updateIds })
    return response.data
  }

  // Roles
  async function getRoles(): Promise<RoleInfo[]> {
    const response = await client.get<RoleListResponse>('/deployments/roles')
    return response.data.roles
  }

  // Deployments
  async function getDeployments(): Promise<Deployment[]> {
    const response = await client.get<DeploymentsResponse>('/deployments')
    return response.data.deployments
  }

  async function getDeployment(deploymentId: string): Promise<Deployment> {
    const response = await client.get<Deployment>(`/deployments/${deploymentId}`)
    return response.data
  }

  async function createDeployment(request: DeploymentRequest): Promise<Deployment> {
    const response = await client.post<Deployment>('/deployments', request)
    return response.data
  }

  async function cancelDeployment(deploymentId: string): Promise<ActionResponse> {
    const response = await client.post<ActionResponse>(`/deployments/${deploymentId}/cancel`)
    return response.data
  }

  async function rollbackDeployment(deploymentId: string): Promise<ActionResponse> {
    const response = await client.post<ActionResponse>(`/deployments/${deploymentId}/rollback`)
    return response.data
  }

  async function retryDeployment(deploymentId: string): Promise<Deployment> {
    const response = await client.post<Deployment>(`/deployments/${deploymentId}/retry`)
    return response.data
  }

  // Backups
  async function getBackups(): Promise<Backup[]> {
    const response = await client.get<BackupsResponse>('/stateful/backups')
    return response.data.backups
  }

  async function getBackup(backupId: string): Promise<Backup> {
    const response = await client.get<Backup>(`/stateful/backups/${backupId}`)
    return response.data
  }

  async function createBackup(request: BackupRequest): Promise<Backup> {
    const response = await client.post<Backup>('/stateful/backups', request)
    return response.data
  }

  async function restoreBackup(backupId: string): Promise<ActionResponse> {
    const response = await client.post<ActionResponse>(`/stateful/backups/${backupId}/restore`)
    return response.data
  }

  // Replications
  async function getReplications(): Promise<Replication[]> {
    const response = await client.get<ReplicationsResponse>('/stateful/replications')
    return response.data.replications
  }

  async function getReplication(replicationId: string): Promise<Replication> {
    const response = await client.get<Replication>(`/stateful/replications/${replicationId}`)
    return response.data
  }

  async function startReplication(request: ReplicationRequest): Promise<Replication> {
    const response = await client.post<Replication>('/stateful/replications', request)
    return response.data
  }

  async function promoteReplica(replicationId: string): Promise<ActionResponse> {
    const response = await client.post<ActionResponse>(
      `/stateful/replications/${replicationId}/promote`
    )
    return response.data
  }

  // Data Verification
  async function verifyData(
    nodeId: string,
    serviceType = 'redis'
  ): Promise<{ is_healthy: boolean; details: Record<string, unknown> }> {
    const response = await client.post('/stateful/verify', {
      node_id: nodeId,
      service_type: serviceType,
    })
    return response.data
  }

  return {
    // Nodes
    getNodes,
    getNode,
    getNodeHealth,
    registerNode,
    updateNode,
    deleteNode,
    replaceNode,
    updateNodeRoles,
    enrollNode,
    drainNode,
    resumeNode,
    testConnection,
    // Node Events
    getNodeEvents,
    // Certificates
    getCertificateStatus,
    renewCertificate,
    deployCertificate,
    // Updates
    checkUpdates,
    applyUpdates,
    // Roles
    getRoles,
    // Deployments
    getDeployments,
    getDeployment,
    createDeployment,
    cancelDeployment,
    rollbackDeployment,
    retryDeployment,
    // Backups
    getBackups,
    getBackup,
    createBackup,
    restoreBackup,
    // Replications
    getReplications,
    getReplication,
    startReplication,
    promoteReplica,
    // Verification
    verifyData,
  }
}
