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
  | 'npu-worker'
  | 'browser-automation'
  | 'monitoring'

export type HealthStatus = 'healthy' | 'degraded' | 'unhealthy' | 'unknown'

export type AuthMethod = 'password' | 'pki'

export type EventSeverity = 'info' | 'warning' | 'error' | 'critical'

export type EventType =
  | 'node_registered'
  | 'node_enrolled'
  | 'health_changed'
  | 'deployment_started'
  | 'deployment_completed'
  | 'deployment_failed'
  | 'certificate_issued'
  | 'certificate_renewed'
  | 'certificate_expiring'
  | 'update_available'
  | 'update_applied'

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
  primary_node_id: string
  replica_node_id: string
  service_type: string
  state: 'pending' | 'syncing' | 'synced' | 'failed' | 'stopped'
  sync_progress: number
  started_at: string | null
  completed_at: string | null
  error: string | null
  details: Record<string, unknown>
}

export interface ReplicationRequest {
  primary_node_id: string
  replica_node_id: string
  service_type?: string
}

export interface MaintenanceWindow {
  id: string
  node_id: string
  start_time: string
  end_time: string
  reason: string
  auto_drain: boolean
  created_at: string
}

export interface SLMWebSocketMessage {
  type: 'health_update' | 'deployment_status' | 'backup_status' | 'node_status'
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
