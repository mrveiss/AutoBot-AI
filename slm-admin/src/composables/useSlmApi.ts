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
  Deployment,
  DeploymentRequest,
  Backup,
  BackupRequest,
  Replication,
  ReplicationRequest,
} from '@/types/slm'

const API_BASE = '/v1/slm'

interface NodesResponse {
  nodes: SLMNode[]
  total: number
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

  // Nodes
  async function getNodes(): Promise<SLMNode[]> {
    const response = await client.get<NodesResponse>('/nodes')
    return response.data.nodes
  }

  async function getNode(nodeId: string): Promise<SLMNode> {
    const response = await client.get<SLMNode>(`/nodes/${nodeId}`)
    return response.data
  }

  async function getNodeHealth(nodeId: string): Promise<NodeHealth> {
    const response = await client.get<NodeHealth>(`/nodes/${nodeId}/health`)
    return response.data
  }

  async function registerNode(nodeData: Partial<SLMNode>): Promise<SLMNode> {
    const response = await client.post<SLMNode>('/nodes', nodeData)
    return response.data
  }

  async function updateNodeRoles(nodeId: string, roles: string[]): Promise<SLMNode> {
    const response = await client.patch<SLMNode>(`/nodes/${nodeId}/roles`, { roles })
    return response.data
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
    updateNodeRoles,
    // Deployments
    getDeployments,
    getDeployment,
    createDeployment,
    cancelDeployment,
    rollbackDeployment,
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
