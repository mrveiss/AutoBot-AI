// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * SLM Type Definitions
 */

export type NodeStatus = 'registered' | 'pending' | 'enrolling' | 'healthy' | 'degraded' | 'unhealthy' | 'offline' | 'maintenance' | 'online' | 'error'

export type NodeRole =
  | 'slm-agent'
  | 'redis'
  | 'backend'
  | 'frontend'
  | 'llm'
  | 'ai-stack'
  | 'npu-worker'
  | 'browser-automation'
  | 'monitoring'

export type HealthStatus = 'healthy' | 'degraded' | 'unhealthy' | 'unknown'

export type AuthMethod = 'password' | 'key' | 'pki'

export type EventSeverity = 'info' | 'warning' | 'error' | 'critical'

export type EventType =
  | 'state_change'
  | 'health_check'
  | 'deployment_started'
  | 'deployment_completed'
  | 'deployment_failed'
  | 'certificate_issued'
  | 'certificate_renewed'
  | 'certificate_expiring'
  | 'remediation_started'
  | 'remediation_completed'
  | 'rollback_started'
  | 'rollback_completed'
  | 'manual_action'

export type CertificateStatus = 'valid' | 'expiring_soon' | 'expired' | 'not_issued'

export type UpdateSeverity = 'low' | 'medium' | 'high' | 'critical'

export interface NodeHealth {
  status: HealthStatus
  cpu_percent: number
  memory_percent: number
  disk_percent: number
  last_heartbeat: string | null
  services: ServiceHealth[]
}

export interface ServiceHealth {
  name: string
  status: HealthStatus
  details: Record<string, unknown>
}

export interface SLMNode {
  node_id: string
  hostname: string
  ip_address: string
  status: NodeStatus
  roles: NodeRole[]
  ssh_user?: string
  ssh_port?: number
  ssh_password?: string  // Only used for registration, never returned
  auth_method?: AuthMethod
  health: NodeHealth | null
  created_at: string
  updated_at: string
}

/**
 * Payload for creating/registering a new node
 */
export interface NodeCreate {
  hostname: string
  ip_address: string
  roles?: NodeRole[]
  ssh_user?: string
  ssh_port?: number
  ssh_password?: string
  auth_method?: AuthMethod
  ssh_key?: string
  auto_enroll?: boolean
  deploy_pki?: boolean
}

/**
 * Payload for updating an existing node
 */
export interface NodeUpdate {
  hostname?: string
  ip_address?: string
  roles?: NodeRole[]
  ssh_user?: string
  ssh_port?: number
  ssh_password?: string
  auth_method?: AuthMethod
  ssh_key?: string
  deploy_pki?: boolean
  run_enrollment?: boolean
}

/**
 * Lifecycle events for a node
 */
export interface NodeEvent {
  id: string
  node_id: string
  type: EventType
  severity: EventSeverity
  message: string
  timestamp: string
  details: Record<string, unknown>
}

/**
 * Available update information
 */
export interface UpdateInfo {
  id: string
  version: string
  description: string
  severity: UpdateSeverity
  available_at: string
  release_notes?: string
  affected_roles?: NodeRole[]
}

/**
 * Role category for grouping
 */
export type RoleCategory = 'core' | 'data' | 'application' | 'ai' | 'automation' | 'observability'

/**
 * Available role information from backend
 */
export interface RoleInfo {
  name: NodeRole
  description: string
  category: RoleCategory
  dependencies: NodeRole[]
  variables: Record<string, unknown>
  tools: string[]
}

/**
 * Response for listing available roles
 */
export interface RoleListResponse {
  roles: RoleInfo[]
}

/**
 * PKI certificate status for a node
 */
export interface CertificateInfo {
  issued_at: string | null
  expires_at: string | null
  fingerprint: string | null
  status: CertificateStatus
  issuer?: string
  subject?: string
  serial_number?: string
}

/**
 * Result of SSH connection test
 */
export interface ConnectionTestResult {
  success: boolean
  message?: string
  error?: string
  latency_ms?: number
  ssh_version?: string
  host_key_fingerprint?: string
  os?: string
}

/**
 * Request payload for connection test
 */
export interface ConnectionTestRequest {
  ip_address: string
  ssh_user: string
  ssh_port: number
  auth_method: AuthMethod
  password?: string
  ssh_key?: string
}

/**
 * Request payload for applying updates
 */
export interface ApplyUpdatesRequest {
  node_id: string
  update_ids: string[]
}

/**
 * Filters for fetching node events
 */
export interface NodeEventFilters {
  type?: EventType
  severity?: EventSeverity
  limit?: number
  offset?: number
}

export interface Deployment {
  deployment_id: string
  node_id: string
  roles: NodeRole[]
  status: 'pending' | 'in_progress' | 'completed' | 'failed' | 'rolled_back'
  started_at: string
  completed_at: string | null
  error: string | null
  playbook_output: string | null
}

export interface DeploymentRequest {
  node_id: string
  roles: NodeRole[]
  force?: boolean
}

export interface Backup {
  backup_id: string
  node_id: string
  service_type: string
  backup_path: string
  state: 'pending' | 'in_progress' | 'completed' | 'failed'
  size_bytes: number
  started_at: string | null
  completed_at: string | null
  error: string | null
  checksum: string | null
}

export interface BackupRequest {
  node_id: string
  service_type?: string
  backup_name?: string
}

export interface Replication {
  replication_id: string
  source_node_id: string
  target_node_id: string
  service_type: string
  status: 'pending' | 'syncing' | 'active' | 'failed' | 'stopped'
  sync_position: string | null
  lag_bytes: number
  started_at: string | null
  completed_at: string | null
  error: string | null
  created_at: string
  updated_at: string
}

export interface ReplicationRequest {
  source_node_id: string
  target_node_id: string
  service_type?: string
}

export interface MaintenanceWindow {
  id: number
  window_id: string
  node_id: string | null
  start_time: string
  end_time: string
  reason: string | null
  auto_drain: boolean
  suppress_alerts: boolean
  suppress_remediation: boolean
  status: 'scheduled' | 'active' | 'completed' | 'cancelled'
  created_by: string | null
  created_at: string
  updated_at: string
}

export interface MaintenanceWindowCreate {
  node_id?: string
  start_time: string
  end_time: string
  reason?: string
  auto_drain?: boolean
  suppress_alerts?: boolean
  suppress_remediation?: boolean
}

export interface MaintenanceWindowListResponse {
  windows: MaintenanceWindow[]
  total: number
}

export interface SLMWebSocketMessage {
  type: 'health_update' | 'deployment_status' | 'backup_status' | 'node_status' | 'remediation_event' | 'service_status' | 'rollback_event'
  node_id: string
  data: Record<string, unknown>
  timestamp: string
}

export interface FleetSummary {
  total_nodes: number
  healthy_nodes: number
  degraded_nodes: number
  unhealthy_nodes: number
  offline_nodes: number
}

// =============================================================================
// Service Types (Issue #728)
// =============================================================================

export type ServiceStatus = 'running' | 'stopped' | 'failed' | 'unknown'

export type ServiceCategory = 'autobot' | 'system'

export interface NodeService {
  id: number
  node_id: string
  service_name: string
  status: ServiceStatus
  category: ServiceCategory
  enabled: boolean
  description: string | null
  active_state: string | null
  sub_state: string | null
  main_pid: number | null
  memory_bytes: number | null
  last_checked: string | null
  created_at: string
  updated_at: string
}

export interface ServiceListResponse {
  services: NodeService[]
  total: number
}

export interface ServiceActionResponse {
  action: string
  service_name: string
  node_id: string
  success: boolean
  message: string
  job_id?: string
}

export interface ServiceLogsResponse {
  service_name: string
  node_id: string
  logs: string
  lines_returned: number
}

export interface FleetServiceStatus {
  service_name: string
  category: ServiceCategory
  nodes: Array<{
    node_id: string
    hostname: string
    status: ServiceStatus
  }>
  running_count: number
  stopped_count: number
  failed_count: number
  total_nodes: number
}

export interface ServiceCategoryUpdateRequest {
  category: ServiceCategory
}

export interface FleetServicesResponse {
  services: FleetServiceStatus[]
  total_services: number
}

// =============================================================================
// Blue-Green Deployment Types (Issue #726 Phase 3)
// =============================================================================

export type BlueGreenStatus =
  | 'pending'
  | 'borrowing'
  | 'deploying'
  | 'verifying'
  | 'switching'
  | 'active'
  | 'rolling_back'
  | 'rolled_back'
  | 'completed'
  | 'failed'

export interface BlueGreenDeployment {
  id: number
  bg_deployment_id: string
  blue_node_id: string
  blue_roles: string[]
  green_node_id: string
  green_original_roles: string[]
  borrowed_roles: string[]
  purge_on_complete: boolean
  deployment_type: 'upgrade' | 'migration' | 'failover'
  health_check_url: string | null
  health_check_interval: number
  health_check_timeout: number
  auto_rollback: boolean
  status: BlueGreenStatus
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

export interface BlueGreenDeploymentCreate {
  blue_node_id: string
  green_node_id: string
  roles: string[]
  deployment_type?: 'upgrade' | 'migration' | 'failover'
  health_check_url?: string
  health_check_interval?: number
  health_check_timeout?: number
  auto_rollback?: boolean
  purge_on_complete?: boolean
}

export interface BlueGreenListResponse {
  deployments: BlueGreenDeployment[]
  total: number
  page: number
  per_page: number
}

export interface EligibleNode {
  node_id: string
  hostname: string
  ip_address: string
  current_roles: string[]
  available_capacity: number
  status: string
}

export interface EligibleNodesResponse {
  nodes: EligibleNode[]
  total: number
}

export interface RolePurgeRequest {
  node_id: string
  roles: string[]
  force?: boolean
}
