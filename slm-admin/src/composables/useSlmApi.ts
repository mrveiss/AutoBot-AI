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

  async function stopReplication(replicationId: string): Promise<ActionResponse> {
    const response = await client.post<ActionResponse>(
      `/stateful/replications/${replicationId}/stop`
    )
    return response.data
  }

  interface SyncVerifyResponse {
    is_healthy: boolean
    service_type: string
    details: {
      source?: Record<string, unknown>
      target?: Record<string, unknown>
      comparison?: Record<string, unknown>
      lag?: Record<string, unknown>
    }
    checks: Array<{
      name: string
      status: string
      message: string
    }>
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
  interface RestartAllServicesRequest {
    category?: 'autobot' | 'system' | 'all'
    exclude_services?: string[]
  }

  interface RestartAllServicesResponse {
    node_id: string
    success: boolean
    message: string
    total_services: number
    successful_restarts: number
    failed_restarts: number
    results: Array<{
      service_name: string
      success: boolean
      message: string
      is_slm_agent: boolean
    }>
    slm_agent_restarted: boolean
  }

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
  interface VNCCredentialCreate {
    vnc_type?: 'desktop' | 'browser' | 'custom'
    name?: string
    password: string
    port?: number
    display_number?: number
    vnc_port?: number
    websockify_enabled?: boolean
  }

  interface VNCCredentialResponse {
    id: number
    credential_id: string
    node_id: string
    vnc_type: string | null
    name: string | null
    port: number | null
    display_number: number | null
    vnc_port: number | null
    websockify_enabled: boolean
    is_active: boolean
    last_used: string | null
    created_at: string
    updated_at: string
    websocket_url: string | null
  }

  interface VNCEndpointResponse {
    credential_id: string
    node_id: string
    hostname: string
    ip_address: string
    vnc_type: string
    name: string | null
    port: number
    websocket_url: string
    is_active: boolean
  }

  interface VNCEndpointsResponse {
    endpoints: VNCEndpointResponse[]
    total: number
  }

  interface VNCConnectionInfo {
    credential_id: string
    node_id: string
    vnc_type: string
    host: string
    port: number
    display_number: number
    websocket_url: string
    connection_token: string | null
    token_expires_at: string | null
  }

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
  interface TLSCredentialCreate {
    name?: string
    ca_cert: string
    server_cert: string
    server_key: string
    common_name?: string
    expires_at?: string
  }

  interface TLSCredentialResponse {
    id: number
    credential_id: string
    node_id: string
    name: string | null
    common_name: string | null
    expires_at: string | null
    fingerprint: string | null
    is_active: boolean
    created_at: string
    updated_at: string
  }

  interface TLSEndpointResponse {
    credential_id: string
    node_id: string
    hostname: string
    ip_address: string
    name: string | null
    common_name: string | null
    expires_at: string | null
    is_active: boolean
    days_until_expiry: number | null
  }

  interface TLSEndpointsResponse {
    endpoints: TLSEndpointResponse[]
    total: number
    expiring_soon: number
  }

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
  interface TLSRenewResponse {
    success: boolean
    message: string
    old_credential_id: string
    new_credential_id: string
    expires_at: string | null
    deployed: boolean
    deployment_message: string | null
  }

  interface TLSRotateResponse {
    success: boolean
    message: string
    old_credential_id: string
    old_deactivated: boolean
    new_credential_id: string
    expires_at: string | null
    deployed: boolean
    deployment_message: string | null
  }

  interface TLSBulkRenewResponse {
    success: boolean
    message: string
    renewed: number
    failed: number
    results: Array<{
      old_credential_id: string
      new_credential_id?: string
      node_id: string
      success: boolean
      deployed?: boolean
      error?: string
    }>
  }

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

  interface FleetMetrics {
    total_nodes: number
    online_nodes: number
    degraded_nodes: number
    offline_nodes: number
    avg_cpu_percent: number
    avg_memory_percent: number
    avg_disk_percent: number
    total_services: number
    running_services: number
    failed_services: number
    nodes: Array<{
      node_id: string
      hostname: string
      ip_address: string
      status: string
      cpu_percent: number
      memory_percent: number
      disk_percent: number
      last_heartbeat: string | null
      services_running: number
      services_failed: number
    }>
    timestamp: string
  }

  interface AlertItem {
    alert_id: string
    severity: string
    category: string
    message: string
    node_id: string | null
    hostname: string | null
    timestamp: string
    acknowledged: boolean
  }

  interface AlertsResponse {
    total_count: number
    critical_count: number
    warning_count: number
    info_count: number
    alerts: AlertItem[]
  }

  interface SystemHealth {
    overall_status: string
    health_score: number
    components: Record<string, string>
    issues: string[]
    last_check: string
  }

  interface DashboardOverview {
    fleet_metrics: FleetMetrics
    recent_alerts: AlertItem[]
    recent_deployments: number
    active_maintenance: number
    health_summary: SystemHealth
  }

  interface LogEntry {
    event_id: string
    node_id: string
    hostname: string
    event_type: string
    severity: string
    message: string
    timestamp: string
  }

  interface LogsResponse {
    logs: LogEntry[]
    total: number
    page: number
    per_page: number
  }

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

  async function getSystemHealth(): Promise<SystemHealth> {
    const response = await client.get<SystemHealth>('/monitoring/health')
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

  interface BlueGreenDeployment {
    id: number
    bg_deployment_id: string
    blue_node_id: string
    blue_roles: string[]
    green_node_id: string
    green_original_roles: string[]
    borrowed_roles: string[]
    purge_on_complete: boolean
    deployment_type: string
    health_check_url: string | null
    health_check_interval: number
    health_check_timeout: number
    auto_rollback: boolean
    status: string
    progress_percent: number
    current_step: string | null
    error: string | null
    started_at: string | null
    switched_at: string | null
    completed_at: string | null
    rollback_at: string | null
    triggered_by: string | null
    created_at: string
    updated_at: string
  }

  interface BlueGreenCreate {
    blue_node_id: string
    green_node_id: string
    roles: string[]
    deployment_type?: string
    health_check_url?: string
    health_check_interval?: number
    health_check_timeout?: number
    auto_rollback?: boolean
    purge_on_complete?: boolean
  }

  interface BlueGreenListResponse {
    deployments: BlueGreenDeployment[]
    total: number
    page: number
    per_page: number
  }

  interface EligibleNode {
    node_id: string
    hostname: string
    ip_address: string
    current_roles: string[]
    available_capacity: number
    status: string
  }

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

  async function getBlueGreenDeployment(deploymentId: string): Promise<BlueGreenDeployment> {
    const response = await client.get<BlueGreenDeployment>(`/blue-green/${deploymentId}`)
    return response.data
  }

  async function createBlueGreenDeployment(data: BlueGreenCreate): Promise<BlueGreenDeployment> {
    const response = await client.post<BlueGreenDeployment>('/blue-green', data)
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
  }
}
