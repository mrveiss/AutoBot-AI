// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
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
  ServiceListResponse,
  ServiceActionResponse,
  ServiceLogsResponse,
  FleetServicesResponse,
  MaintenanceWindow,
  MaintenanceWindowCreate,
  MaintenanceWindowListResponse,
  NPUNodeStatus,
  NPULoadBalancingConfig,
  NPUFleetMetrics,
  NPUWorkerMetrics,
  NPUWorkerConfig,
  FleetUpdateSummary,
  EligibleNode,
} from '@/types/slm'
import { getSlmApiBase } from '@/config/ssot-config'
import type {
  ActionResponse,
  SyncVerifyResponse,
  RestartAllServicesRequest,
  RestartAllServicesResponse,
  VNCCredentialCreate,
  VNCCredentialResponse,
  VNCEndpointsResponse,
  VNCConnectionInfo,
  TLSCredentialCreate,
  TLSCredentialResponse,
  TLSEndpointsResponse,
  TLSRenewResponse,
  TLSRotateResponse,
  TLSBulkRenewResponse,
  TLSEnableResponse,
  FleetMetrics,
  AlertsResponse,
  MonitoringSystemHealth,
  DashboardOverview,
  LogsResponse,
  BlueGreenDeploymentApi,
  BlueGreenCreate,
  BlueGreenListResponse,
  NPUNodesResponse,
  NPURoleResponse,
  NPUDetectionResponse,
  ErrorStatistics,
  RecentErrorsResponse,
  CategoriesResponse,
  ComponentsResponse,
  ErrorHealthResponse,
  MetricsSummary,
  TimelineResponse,
  TopErrorsResponse,
  AlertThresholdConfig,
  AlertThresholdResponse,
  CleanupResponse,
  ClearResponse,
  ResolveResponse,
  SecurityEventResponse,
  SecurityOverviewResponse,
  AuditLogListResponse,
  SecurityEventListResponse,
  ThreatSummary,
  SecurityPolicyResponse,
  SecurityPolicyListResponse,
  FleetCert,
  WizardStatusResponse,
} from '@/types/api-responses'

// SLM Admin uses the local SLM backend API
const API_BASE = getSlmApiBase()

// Backend response types (different from frontend SLMNode)
interface BackendNodeResponse {
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

export function useSlmApi() {
  const client: AxiosInstance = axios.create({
    baseURL: API_BASE,
    headers: {
      'Content-Type': 'application/json',
    },
  })

  // Add auth token to all requests
  client.interceptors.request.use((config) => {
    const token = sessionStorage.getItem('slm_access_token')
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

  // Fleet Update Summary (#682)
  async function getFleetUpdateSummary(): Promise<FleetUpdateSummary> {
    const response = await client.get<FleetUpdateSummary>('/updates/fleet-summary')
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

  async function getRoleOwners(): Promise<Record<string, string>> {
    const response = await client.get<{ owners: Record<string, string> }>('/roles/owners')
    return response.data.owners
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

  async function stopReplication(replicationId: string): Promise<ActionResponse> {
    const response = await client.post<ActionResponse>(
      `/stateful/replications/${replicationId}/stop`
    )
    return response.data
  }

  async function verifyReplicationSync(replicationId: string): Promise<SyncVerifyResponse> {
    const response = await client.post<SyncVerifyResponse>(
      `/stateful/replications/${replicationId}/verify-sync`
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

  // Services (Issue #728)
  async function getNodeServices(
    nodeId: string,
    options?: { status?: string; search?: string; page?: number; per_page?: number }
  ): Promise<ServiceListResponse> {
    const params = new URLSearchParams()
    if (options?.status) params.append('status', options.status)
    if (options?.search) params.append('search', options.search)
    if (options?.page) params.append('page', options.page.toString())
    if (options?.per_page) params.append('per_page', options.per_page.toString())

    const response = await client.get<ServiceListResponse>(
      `/nodes/${nodeId}/services?${params.toString()}`
    )
    return response.data
  }

  async function startService(nodeId: string, serviceName: string): Promise<ServiceActionResponse> {
    const response = await client.post<ServiceActionResponse>(
      `/nodes/${nodeId}/services/${serviceName}/start`
    )
    return response.data
  }

  async function stopService(nodeId: string, serviceName: string): Promise<ServiceActionResponse> {
    const response = await client.post<ServiceActionResponse>(
      `/nodes/${nodeId}/services/${serviceName}/stop`
    )
    return response.data
  }

  async function restartService(nodeId: string, serviceName: string): Promise<ServiceActionResponse> {
    const response = await client.post<ServiceActionResponse>(
      `/nodes/${nodeId}/services/${serviceName}/restart`
    )
    return response.data
  }

  async function getServiceLogs(
    nodeId: string,
    serviceName: string,
    options?: { lines?: number; since?: string }
  ): Promise<ServiceLogsResponse> {
    const params = new URLSearchParams()
    if (options?.lines) params.append('lines', options.lines.toString())
    if (options?.since) params.append('since', options.since)

    const response = await client.get<ServiceLogsResponse>(
      `/nodes/${nodeId}/services/${serviceName}/logs?${params.toString()}`
    )
    return response.data
  }

  async function getFleetServices(): Promise<FleetServicesResponse> {
    const response = await client.get<FleetServicesResponse>('/fleet/services')
    return response.data
  }

  async function startFleetService(serviceName: string): Promise<ServiceActionResponse> {
    const response = await client.post<ServiceActionResponse>(
      `/fleet/services/${serviceName}/start`
    )
    return response.data
  }

  async function stopFleetService(serviceName: string): Promise<ServiceActionResponse> {
    const response = await client.post<ServiceActionResponse>(
      `/fleet/services/${serviceName}/stop`
    )
    return response.data
  }

  async function restartFleetService(serviceName: string): Promise<ServiceActionResponse> {
    const response = await client.post<ServiceActionResponse>(
      `/fleet/services/${serviceName}/restart`
    )
    return response.data
  }

  async function updateServiceCategory(
    serviceName: string,
    category: 'autobot' | 'system'
  ): Promise<{ service_name: string; category: string; nodes_updated: number }> {
    const response = await client.patch<{
      service_name: string
      category: string
      nodes_updated: number
    }>(`/fleet/services/${serviceName}/category`, { category })
    return response.data
  }

  // Restart All Services on a Node (Issue #725)
  async function restartAllNodeServices(
    nodeId: string,
    options?: RestartAllServicesRequest
  ): Promise<RestartAllServicesResponse> {
    const response = await client.post<RestartAllServicesResponse>(
      `/nodes/${nodeId}/services/restart-all`,
      options || {}
    )
    return response.data
  }

  // VNC Credentials (Issue #725)
  async function getVncEndpoints(includeInactive = false): Promise<VNCEndpointsResponse> {
    const params = includeInactive ? '?include_inactive=true' : ''
    const response = await client.get<VNCEndpointsResponse>(`/vnc/endpoints${params}`)
    return response.data
  }

  async function getNodeVncCredentials(nodeId: string): Promise<{ credentials: VNCCredentialResponse[]; total: number }> {
    const response = await client.get<{ credentials: VNCCredentialResponse[]; total: number }>(
      `/nodes/${nodeId}/vnc-credentials`
    )
    return response.data
  }

  async function createVncCredential(nodeId: string, data: VNCCredentialCreate): Promise<VNCCredentialResponse> {
    const response = await client.post<VNCCredentialResponse>(
      `/nodes/${nodeId}/vnc-credentials`,
      data
    )
    return response.data
  }

  async function updateVncCredential(
    credentialId: string,
    data: Partial<VNCCredentialCreate> & { is_active?: boolean }
  ): Promise<VNCCredentialResponse> {
    const response = await client.patch<VNCCredentialResponse>(
      `/vnc/credentials/${credentialId}`,
      data
    )
    return response.data
  }

  async function deleteVncCredential(credentialId: string): Promise<void> {
    await client.delete(`/vnc/credentials/${credentialId}`)
  }

  async function getVncConnectionInfo(credentialId: string): Promise<VNCConnectionInfo> {
    const response = await client.post<VNCConnectionInfo>(
      `/vnc/credentials/${credentialId}/connect`
    )
    return response.data
  }

  // TLS Credentials (Issue #725: mTLS support)
  async function getTlsEndpoints(includeInactive = false): Promise<TLSEndpointsResponse> {
    const params = includeInactive ? '?include_inactive=true' : ''
    const response = await client.get<TLSEndpointsResponse>(`/tls/endpoints${params}`)
    return response.data
  }

  async function getTlsExpiringCertificates(days = 30): Promise<TLSEndpointsResponse> {
    const response = await client.get<TLSEndpointsResponse>(`/tls/expiring?days=${days}`)
    return response.data
  }

  async function getNodeTlsCredentials(nodeId: string, includeInactive = false): Promise<{ credentials: TLSCredentialResponse[]; total: number }> {
    const params = includeInactive ? '?include_inactive=true' : ''
    const response = await client.get<{ credentials: TLSCredentialResponse[]; total: number }>(
      `/nodes/${nodeId}/tls-credentials${params}`
    )
    return response.data
  }

  async function getTlsCredential(credentialId: string): Promise<TLSCredentialResponse> {
    const response = await client.get<TLSCredentialResponse>(`/tls/credentials/${credentialId}`)
    return response.data
  }

  async function createTlsCredential(nodeId: string, data: TLSCredentialCreate): Promise<TLSCredentialResponse> {
    const response = await client.post<TLSCredentialResponse>(
      `/nodes/${nodeId}/tls-credentials`,
      data
    )
    return response.data
  }

  async function updateTlsCredential(
    credentialId: string,
    data: Partial<TLSCredentialCreate> & { is_active?: boolean }
  ): Promise<TLSCredentialResponse> {
    const response = await client.patch<TLSCredentialResponse>(
      `/tls/credentials/${credentialId}`,
      data
    )
    return response.data
  }

  async function deleteTlsCredential(credentialId: string): Promise<void> {
    await client.delete(`/tls/credentials/${credentialId}`)
  }

  async function downloadTlsCaCert(credentialId: string): Promise<string> {
    const response = await client.get<string>(`/tls/credentials/${credentialId}/ca-cert`)
    return response.data
  }

  async function downloadTlsServerCert(credentialId: string): Promise<string> {
    const response = await client.get<string>(`/tls/credentials/${credentialId}/server-cert`)
    return response.data
  }

  // TLS Certificate Lifecycle (Issue #725: renew/rotate workflows)
  async function renewTlsCertificate(
    credentialId: string,
    deploy = false
  ): Promise<TLSRenewResponse> {
    const response = await client.post<TLSRenewResponse>(
      `/tls/credentials/${credentialId}/renew?deploy=${deploy}`
    )
    return response.data
  }

  async function rotateTlsCertificate(
    credentialId: string,
    deploy = true,
    deactivateOld = true
  ): Promise<TLSRotateResponse> {
    const response = await client.post<TLSRotateResponse>(
      `/tls/credentials/${credentialId}/rotate?deploy=${deploy}&deactivate_old=${deactivateOld}`
    )
    return response.data
  }

  async function bulkRenewExpiringCertificates(
    days = 30,
    deploy = false
  ): Promise<TLSBulkRenewResponse> {
    const response = await client.post<TLSBulkRenewResponse>(
      `/tls/bulk-renew?days=${days}&deploy=${deploy}`
    )
    return response.data
  }

  // TLS Service Enablement (Issue #164)
  async function enableTlsOnServices(
    services: string[] = ['frontend', 'backend', 'redis'],
    deployCertsFirst = true
  ): Promise<TLSEnableResponse> {
    const params = new URLSearchParams()
    services.forEach(s => params.append('services', s))
    params.append('deploy_certs_first', deployCertsFirst.toString())
    const response = await client.post<TLSEnableResponse>(
      `/tls/enable?${params.toString()}`
    )
    return response.data
  }

  // Maintenance Windows
  async function getMaintenanceWindows(options?: {
    node_id?: string
    status?: string
    include_completed?: boolean
    page?: number
    per_page?: number
  }): Promise<MaintenanceWindowListResponse> {
    const params = new URLSearchParams()
    if (options?.node_id) params.append('node_id', options.node_id)
    if (options?.status) params.append('status', options.status)
    if (options?.include_completed) params.append('include_completed', 'true')
    if (options?.page) params.append('page', options.page.toString())
    if (options?.per_page) params.append('per_page', options.per_page.toString())

    const response = await client.get<MaintenanceWindowListResponse>(
      `/maintenance?${params.toString()}`
    )
    return response.data
  }

  async function getActiveMaintenanceWindows(nodeId?: string): Promise<MaintenanceWindowListResponse> {
    const params = nodeId ? `?node_id=${nodeId}` : ''
    const response = await client.get<MaintenanceWindowListResponse>(
      `/maintenance/active${params}`
    )
    return response.data
  }

  async function getMaintenanceWindow(windowId: string): Promise<MaintenanceWindow> {
    const response = await client.get<MaintenanceWindow>(`/maintenance/${windowId}`)
    return response.data
  }

  async function createMaintenanceWindow(data: MaintenanceWindowCreate): Promise<MaintenanceWindow> {
    const response = await client.post<MaintenanceWindow>('/maintenance', data)
    return response.data
  }

  async function updateMaintenanceWindow(
    windowId: string,
    data: Partial<MaintenanceWindowCreate> & { status?: string }
  ): Promise<MaintenanceWindow> {
    const response = await client.put<MaintenanceWindow>(`/maintenance/${windowId}`, data)
    return response.data
  }

  async function deleteMaintenanceWindow(windowId: string): Promise<void> {
    await client.delete(`/maintenance/${windowId}`)
  }

  async function activateMaintenanceWindow(windowId: string): Promise<MaintenanceWindow> {
    const response = await client.post<MaintenanceWindow>(`/maintenance/${windowId}/activate`)
    return response.data
  }

  async function completeMaintenanceWindow(windowId: string): Promise<MaintenanceWindow> {
    const response = await client.post<MaintenanceWindow>(`/maintenance/${windowId}/complete`)
    return response.data
  }

  // =============================================================================
  // Monitoring API (Issue #729)
  // =============================================================================

  async function getFleetMetrics(): Promise<FleetMetrics> {
    const response = await client.get<FleetMetrics>('/monitoring/metrics/fleet')
    return response.data
  }

  async function getNodeMetrics(nodeId: string): Promise<FleetMetrics['nodes'][0]> {
    const response = await client.get(`/monitoring/metrics/node/${nodeId}`)
    return response.data
  }

  async function getAlerts(options?: {
    severity?: string
    hours?: number
  }): Promise<AlertsResponse> {
    const params = new URLSearchParams()
    if (options?.severity) params.append('severity', options.severity)
    if (options?.hours) params.append('hours', options.hours.toString())
    const response = await client.get<AlertsResponse>(
      `/monitoring/alerts?${params.toString()}`
    )
    return response.data
  }

  async function getSystemHealth(): Promise<MonitoringSystemHealth> {
    const response = await client.get<MonitoringSystemHealth>('/monitoring/health')
    return response.data
  }

  async function getMonitoringDashboard(): Promise<DashboardOverview> {
    const response = await client.get<DashboardOverview>('/monitoring/dashboard')
    return response.data
  }

  async function getMonitoringLogs(options?: {
    node_id?: string
    event_type?: string
    severity?: string
    hours?: number
    page?: number
    per_page?: number
  }): Promise<LogsResponse> {
    const params = new URLSearchParams()
    if (options?.node_id) params.append('node_id', options.node_id)
    if (options?.event_type) params.append('event_type', options.event_type)
    if (options?.severity) params.append('severity', options.severity)
    if (options?.hours) params.append('hours', options.hours.toString())
    if (options?.page) params.append('page', options.page.toString())
    if (options?.per_page) params.append('per_page', options.per_page.toString())
    const response = await client.get<LogsResponse>(
      `/monitoring/logs?${params.toString()}`
    )
    return response.data
  }

  async function getErrorSummary(hours?: number): Promise<{
    total_errors: number
    by_type: Record<string, number>
    by_node: Record<string, number>
    recent_errors: Array<{
      event_id: string
      node_id: string
      hostname: string
      event_type: string
      message: string
      timestamp: string
    }>
    time_window_hours: number
  }> {
    const params = hours ? `?hours=${hours}` : ''
    const response = await client.get(`/monitoring/errors${params}`)
    return response.data
  }

  // =============================================================================
  // Blue-Green Deployments API (Issue #726 Phase 3)
  // =============================================================================

  async function getBlueGreenDeployments(options?: {
    status?: string
    page?: number
    per_page?: number
  }): Promise<BlueGreenListResponse> {
    const params = new URLSearchParams()
    if (options?.status) params.append('status', options.status)
    if (options?.page) params.append('page', options.page.toString())
    if (options?.per_page) params.append('per_page', options.per_page.toString())
    const response = await client.get<BlueGreenListResponse>(
      `/blue-green?${params.toString()}`
    )
    return response.data
  }

  async function getBlueGreenDeployment(deploymentId: string): Promise<BlueGreenDeploymentApi> {
    const response = await client.get<BlueGreenDeploymentApi>(`/blue-green/${deploymentId}`)
    return response.data
  }

  async function createBlueGreenDeployment(data: BlueGreenCreate): Promise<BlueGreenDeploymentApi> {
    const response = await client.post<BlueGreenDeploymentApi>('/blue-green', data)
    return response.data
  }

  async function switchBlueGreenTraffic(deploymentId: string): Promise<ActionResponse> {
    const response = await client.post<ActionResponse>(`/blue-green/${deploymentId}/switch`)
    return response.data
  }

  async function rollbackBlueGreen(deploymentId: string): Promise<ActionResponse> {
    const response = await client.post<ActionResponse>(`/blue-green/${deploymentId}/rollback`)
    return response.data
  }

  async function cancelBlueGreen(deploymentId: string): Promise<ActionResponse> {
    const response = await client.post<ActionResponse>(`/blue-green/${deploymentId}/cancel`)
    return response.data
  }

  async function retryBlueGreen(deploymentId: string): Promise<ActionResponse> {
    const response = await client.post<ActionResponse>(`/blue-green/${deploymentId}/retry`)
    return response.data
  }

  async function getEligibleNodes(roles: string[]): Promise<{ nodes: EligibleNode[]; total: number }> {
    const params = new URLSearchParams()
    params.append('roles', roles.join(','))
    const response = await client.get<{ nodes: EligibleNode[]; total: number }>(
      `/blue-green/eligible-nodes?${params.toString()}`
    )
    return response.data
  }

  async function purgeRoles(
    nodeId: string,
    roles: string[],
    force = false
  ): Promise<ActionResponse> {
    const response = await client.post<ActionResponse>('/blue-green/purge', {
      node_id: nodeId,
      roles,
      force,
    })
    return response.data
  }

  // =============================================================================
  // NPU Management API (Issue #255 - NPU Fleet Integration)
  // =============================================================================

  async function getNpuNodes(): Promise<NPUNodeStatus[]> {
    const response = await client.get<NPUNodesResponse>('/npu/nodes')
    return response.data.nodes
  }

  async function getNpuStatus(nodeId: string): Promise<NPUNodeStatus> {
    const response = await client.get<NPUNodeStatus>(`/npu/nodes/${nodeId}/status`)
    return response.data
  }

  async function triggerNpuDetection(nodeId: string, force: boolean = false): Promise<NPUDetectionResponse> {
    const response = await client.post<NPUDetectionResponse>(`/npu/nodes/${nodeId}/detect`, { force })
    return response.data
  }

  async function assignNpuRole(nodeId: string): Promise<NPURoleResponse> {
    const response = await client.post<NPURoleResponse>(`/npu/nodes/${nodeId}/assign-role`)
    return response.data
  }

  async function removeNpuRole(nodeId: string): Promise<{ success: boolean; message: string }> {
    const response = await client.delete<{ success: boolean; message: string }>(`/npu/nodes/${nodeId}/role`)
    return response.data
  }

  async function getNpuLoadBalancing(): Promise<NPULoadBalancingConfig> {
    const response = await client.get<NPULoadBalancingConfig>('/npu/load-balancing')
    return response.data
  }

  async function updateNpuLoadBalancing(config: NPULoadBalancingConfig): Promise<void> {
    await client.post('/npu/load-balancing', config)
  }

  // NPU Metrics & Config (Issue #590 - NPU Dashboard Improvements)

  async function getNpuFleetMetrics(): Promise<NPUFleetMetrics> {
    const response = await client.get<NPUFleetMetrics>('/npu/metrics')
    return response.data
  }

  async function getNpuNodeMetrics(nodeId: string): Promise<NPUWorkerMetrics> {
    const response = await client.get<NPUWorkerMetrics>(`/npu/nodes/${nodeId}/metrics`)
    return response.data
  }

  async function getNpuWorkerConfig(nodeId: string): Promise<NPUWorkerConfig> {
    const response = await client.get<NPUWorkerConfig>(`/npu/nodes/${nodeId}/config`)
    return response.data
  }

  async function updateNpuWorkerConfig(
    nodeId: string,
    config: NPUWorkerConfig
  ): Promise<{ success: boolean; message: string; config: NPUWorkerConfig }> {
    const response = await client.put<{
      success: boolean
      message: string
      node_id: string
      config: NPUWorkerConfig
    }>(`/npu/nodes/${nodeId}/config`, config)
    return response.data
  }

  // =============================================================================
  // Error Monitoring API (Issue #563)
  // =============================================================================

  async function getErrorStatistics(): Promise<ErrorStatistics> {
    const response = await client.get<ErrorStatistics>('/errors/statistics')
    return response.data
  }

  async function getRecentErrors(options?: {
    page?: number
    per_page?: number
    severity?: string
    resolved?: boolean
  }): Promise<RecentErrorsResponse> {
    const params = new URLSearchParams()
    if (options?.page) params.append('page', options.page.toString())
    if (options?.per_page) params.append('per_page', options.per_page.toString())
    if (options?.severity) params.append('severity', options.severity)
    if (options?.resolved !== undefined) params.append('resolved', options.resolved.toString())
    const response = await client.get<RecentErrorsResponse>(`/errors/recent?${params}`)
    return response.data
  }

  async function getErrorCategories(hours: number = 24): Promise<CategoriesResponse> {
    const response = await client.get<CategoriesResponse>(`/errors/categories?hours=${hours}`)
    return response.data
  }

  async function getErrorComponents(hours: number = 24): Promise<ComponentsResponse> {
    const response = await client.get<ComponentsResponse>(`/errors/components?hours=${hours}`)
    return response.data
  }

  async function getErrorHealth(): Promise<ErrorHealthResponse> {
    const response = await client.get<ErrorHealthResponse>('/errors/health')
    return response.data
  }

  async function clearErrors(options?: {
    severity?: string
    older_than_hours?: number
  }): Promise<ClearResponse> {
    const params = new URLSearchParams()
    if (options?.severity) params.append('severity', options.severity)
    if (options?.older_than_hours) params.append('older_than_hours', options.older_than_hours.toString())
    const response = await client.post<ClearResponse>(`/errors/clear?${params}`)
    return response.data
  }

  async function createTestError(severity: 'error' | 'critical' = 'error'): Promise<{ event_id: string; message: string }> {
    const response = await client.post<{ event_id: string; message: string }>(`/errors/test-error?severity=${severity}`)
    return response.data
  }

  async function getErrorMetricsSummary(): Promise<MetricsSummary> {
    const response = await client.get<MetricsSummary>('/errors/metrics/summary')
    return response.data
  }

  async function getErrorTimeline(options?: {
    hours?: number
    interval?: 'hour' | 'day'
  }): Promise<TimelineResponse> {
    const params = new URLSearchParams()
    if (options?.hours) params.append('hours', options.hours.toString())
    if (options?.interval) params.append('interval', options.interval)
    const response = await client.get<TimelineResponse>(`/errors/metrics/timeline?${params}`)
    return response.data
  }

  async function getTopErrors(options?: {
    hours?: number
    limit?: number
  }): Promise<TopErrorsResponse> {
    const params = new URLSearchParams()
    if (options?.hours) params.append('hours', options.hours.toString())
    if (options?.limit) params.append('limit', options.limit.toString())
    const response = await client.get<TopErrorsResponse>(`/errors/metrics/top-errors?${params}`)
    return response.data
  }

  async function resolveError(eventId: string): Promise<ResolveResponse> {
    const response = await client.post<ResolveResponse>(`/errors/metrics/resolve/${eventId}`)
    return response.data
  }

  async function configureAlertThreshold(config: AlertThresholdConfig): Promise<AlertThresholdResponse> {
    const response = await client.post<AlertThresholdResponse>('/errors/metrics/alert-threshold', config)
    return response.data
  }

  async function cleanupOldErrors(days?: number): Promise<CleanupResponse> {
    const params = days ? `?days=${days}` : ''
    const response = await client.post<CleanupResponse>(`/errors/metrics/cleanup${params}`)
    return response.data
  }

  // Security (Issue #813)

  async function getSecurityOverview(): Promise<SecurityOverviewResponse> {
    const response = await client.get<SecurityOverviewResponse>('/security/overview')
    return response.data
  }

  async function getAuditLogs(page: number = 1, perPage: number = 50, category?: string): Promise<AuditLogListResponse> {
    const params = new URLSearchParams({ page: String(page), per_page: String(perPage) })
    if (category) params.append('category', category)
    const response = await client.get<AuditLogListResponse>(`/security/audit-logs?${params}`)
    return response.data
  }

  async function getSecurityEvents(page: number = 1, perPage: number = 50, severity?: string): Promise<SecurityEventListResponse> {
    const params = new URLSearchParams({ page: String(page), per_page: String(perPage) })
    if (severity) params.append('severity', severity)
    const response = await client.get<SecurityEventListResponse>(`/security/events?${params}`)
    return response.data
  }

  async function getThreatSummary(hours: number = 24): Promise<ThreatSummary> {
    const response = await client.get<ThreatSummary>(`/security/events/summary?hours=${hours}`)
    return response.data
  }

  async function acknowledgeSecurityEvent(
    eventId: string,
    data?: { acknowledged_by?: string; notes?: string }
  ): Promise<SecurityEventResponse> {
    const response = await client.post<SecurityEventResponse>(`/security/events/${eventId}/acknowledge`, data || {})
    return response.data
  }

  async function resolveSecurityEvent(
    eventId: string,
    data: { resolved_by?: string; resolution_notes: string }
  ): Promise<SecurityEventResponse> {
    const response = await client.post<SecurityEventResponse>(`/security/events/${eventId}/resolve`, data)
    return response.data
  }

  async function getSecurityPolicies(page: number = 1, perPage: number = 50): Promise<SecurityPolicyListResponse> {
    const params = new URLSearchParams({ page: String(page), per_page: String(perPage) })
    const response = await client.get<SecurityPolicyListResponse>(`/security/policies?${params}`)
    return response.data
  }

  async function activateSecurityPolicy(policyId: string): Promise<SecurityPolicyResponse> {
    const response = await client.post<SecurityPolicyResponse>(`/security/policies/${policyId}/activate`)
    return response.data
  }

  async function deactivateSecurityPolicy(policyId: string): Promise<SecurityPolicyResponse> {
    const response = await client.post<SecurityPolicyResponse>(`/security/policies/${policyId}/deactivate`)
    return response.data
  }

  // Fleet cert expiry (Issue #926 Phase 7)
  async function getFleetCerts(nodeId?: string): Promise<FleetCert[]> {
    const params = nodeId ? `?node_id=${nodeId}` : ''
    const response = await client.get<FleetCert[]>(`/security/certificates${params}`)
    return response.data
  }

  // Node Reboot (Issue #813)
  async function rebootNode(
    nodeId: string
  ): Promise<{ success: boolean; message: string; node_id: string }> {
    const response = await client.post<{ success: boolean; message: string; node_id: string }>(
      `/nodes/${nodeId}/reboot`
    )
    return response.data
  }

  // Secrets (Issue #3079)

  async function listSecrets(): Promise<{ key: string; category: string; description: string }[]> {
    const response = await client.get<{ key: string; category: string; description: string }[]>('/secrets')
    return response.data
  }

  async function upsertSecret(key: string, value: string, category: string = 'api_key', description: string = ''): Promise<void> {
    try {
      await client.post('/secrets', { key, value, category, description })
    } catch (err: unknown) {
      const status = (err as { response?: { status?: number } })?.response?.status
      if (status === 409) {
        await client.put(`/secrets/${key}`, { value, description })
      } else {
        throw err
      }
    }
  }

  async function deleteSecret(key: string): Promise<void> {
    await client.delete(`/secrets/${key}`)
  }

  async function getSecretValue(key: string): Promise<string | null> {
    try {
      const response = await client.get<{ key: string; value: string }>(`/secrets/${key}/value`)
      return response.data.value
    } catch {
      return null
    }
  }

  // Setup Wizard (Issue #1294)
  async function getWizardStatus(): Promise<WizardStatusResponse> {
    const response = await client.get<WizardStatusResponse>('/setup/status')
    return response.data
  }

  async function completeWizardStep(step: string): Promise<{ status: string; completed_step: string }> {
    const response = await client.post<{ status: string; completed_step: string }>(
      '/setup/complete-step',
      { step }
    )
    return response.data
  }

  async function skipWizardSetup(): Promise<{ status: string; message: string }> {
    const response = await client.post<{ status: string; message: string }>('/setup/skip')
    return response.data
  }

  async function provisionWizardFleet(
    nodeIds?: string[]
  ): Promise<{ status: string; message: string; output: string }> {
    const response = await client.post<{ status: string; message: string; output: string }>(
      '/setup/provision-fleet',
      { node_ids: nodeIds || null }
    )
    return response.data
  }

  async function getProvisionStatus(sinceLine: number = 0): Promise<{
    status: string
    lines: string[]
    total_lines: number
    error: string | null
    elapsed_seconds?: number
  }> {
    const response = await client.get('/setup/provision-status', {
      params: { since_line: sinceLine },
    })
    return response.data
  }

  async function validateWizardFleet(): Promise<{
    health: string
    total_nodes: number
    online_nodes: number
    missing_required_roles: string[]
    ready: boolean
  }> {
    const response = await client.get('/setup/validate')
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
    getFleetUpdateSummary,  // Fleet update summary (#682)
    checkUpdates,
    applyUpdates,
    // Roles
    getRoles,
    getRoleOwners,
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
    stopReplication,
    verifyReplicationSync,
    // Verification
    verifyData,
    // Services (Issue #728)
    getNodeServices,
    startService,
    stopService,
    restartService,
    getServiceLogs,
    getFleetServices,
    startFleetService,
    stopFleetService,
    restartFleetService,
    updateServiceCategory,
    restartAllNodeServices,  // Issue #725
    // VNC Credentials (Issue #725)
    getVncEndpoints,
    getNodeVncCredentials,
    createVncCredential,
    updateVncCredential,
    deleteVncCredential,
    getVncConnectionInfo,
    // TLS Credentials (Issue #725: mTLS support)
    getTlsEndpoints,
    getTlsExpiringCertificates,
    getNodeTlsCredentials,
    getTlsCredential,
    createTlsCredential,
    updateTlsCredential,
    deleteTlsCredential,
    downloadTlsCaCert,
    downloadTlsServerCert,
    renewTlsCertificate,
    rotateTlsCertificate,
    bulkRenewExpiringCertificates,
    enableTlsOnServices,  // Issue #164
    // Maintenance Windows
    getMaintenanceWindows,
    getActiveMaintenanceWindows,
    getMaintenanceWindow,
    createMaintenanceWindow,
    updateMaintenanceWindow,
    deleteMaintenanceWindow,
    activateMaintenanceWindow,
    completeMaintenanceWindow,
    // Monitoring (Issue #729)
    getFleetMetrics,
    getNodeMetrics,
    getAlerts,
    getSystemHealth,
    getMonitoringDashboard,
    getMonitoringLogs,
    getErrorSummary,
    // Blue-Green Deployments (Issue #726)
    getBlueGreenDeployments,
    getBlueGreenDeployment,
    createBlueGreenDeployment,
    switchBlueGreenTraffic,
    rollbackBlueGreen,
    cancelBlueGreen,
    retryBlueGreen,
    getEligibleNodes,
    purgeRoles,
    // NPU Management (Issue #255)
    getNpuNodes,
    getNpuStatus,
    triggerNpuDetection,
    assignNpuRole,
    removeNpuRole,
    getNpuLoadBalancing,
    updateNpuLoadBalancing,
    getNpuFleetMetrics,
    getNpuNodeMetrics,
    getNpuWorkerConfig,
    updateNpuWorkerConfig,
    // Error Monitoring (Issue #563)
    getErrorStatistics,
    getRecentErrors,
    getErrorCategories,
    getErrorComponents,
    getErrorHealth,
    clearErrors,
    createTestError,
    getErrorMetricsSummary,
    getErrorTimeline,
    getTopErrors,
    resolveError,
    configureAlertThreshold,
    cleanupOldErrors,
    // Security (Issue #813)
    getSecurityOverview,
    getAuditLogs,
    getSecurityEvents,
    getThreatSummary,
    acknowledgeSecurityEvent,
    resolveSecurityEvent,
    getSecurityPolicies,
    activateSecurityPolicy,
    deactivateSecurityPolicy,
    // Fleet cert expiry (Issue #926 Phase 7)
    getFleetCerts,
    // Node Reboot (Issue #813)
    rebootNode,
    // Secrets (Issue #3079)
    listSecrets,
    upsertSecret,
    deleteSecret,
    getSecretValue,
    // Setup Wizard (Issue #1294)
    getWizardStatus,
    completeWizardStep,
    skipWizardSetup,
    provisionWizardFleet,
    getProvisionStatus,
    validateWizardFleet,
  }
}
