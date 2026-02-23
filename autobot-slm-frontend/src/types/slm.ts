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
  | 'vnc'

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

export interface A2ASkill {
  id: string
  name: string
  description: string
  tags?: string[]
  examples?: string[]
}

export interface A2AAgentCard {
  name: string
  description: string
  url: string
  version: string
  skills: A2ASkill[]
  capabilities?: Record<string, unknown>
  provider?: Record<string, unknown> | string
  documentationUrl?: string
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
  code_status?: 'up_to_date' | 'outdated' | 'unknown'
  code_version?: string
  a2a_card?: A2AAgentCard | null
  // Issue #1019: Per-service health summary counts
  service_summary?: { running: number; stopped: number; failed: number; total: number } | null
  // Issue #1129: Role-centric architecture — roles detected by slm-agent heartbeat
  detected_roles?: string[]
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
export type RoleCategory = 'core' | 'data' | 'application' | 'ai' | 'automation' | 'observability' | 'remote-access'

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

/**
 * Per-node update summary from fleet update check (#682)
 */
export interface NodeUpdateSummary {
  node_id: string
  hostname: string
  system_updates: number
  code_update_available: boolean
  code_status: string
  total_updates: number
}

/**
 * Fleet-wide update summary response (#682)
 */
export interface FleetUpdateSummary {
  nodes: NodeUpdateSummary[]
  total_system_updates: number
  total_code_updates: number
  nodes_needing_updates: number
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
  // Issue #1019: extra_data may include error_message for failed services
  extra_data: Record<string, unknown>
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

// =============================================================================
// NPU Worker Types (Issue #255 - NPU Fleet Integration)
// =============================================================================

export type NPUDeviceType = 'intel-npu' | 'nvidia-gpu' | 'amd-gpu' | 'unknown'

export type NPULoadBalancingStrategy = 'round-robin' | 'least-loaded' | 'model-affinity'

export interface NPUCapabilities {
  models: string[]
  maxConcurrent: number
  memoryGB: number
  deviceType: NPUDeviceType
  utilization: number
}

export interface NPUNodeStatus {
  node_id: string
  capabilities: NPUCapabilities | null
  loadedModels: string[]
  queueDepth: number
  lastHealthCheck: string | null
  detectionStatus: 'pending' | 'detected' | 'failed' | 'unavailable'
  detectionError?: string
}

export interface NPULoadBalancingConfig {
  strategy: NPULoadBalancingStrategy
  modelAffinity: Record<string, string[]>
}

export interface NPUModelInfo {
  name: string
  size_mb: number
  loaded: boolean
  inference_time_ms: number | null
  total_requests: number
}

// NPU Metrics & Config Types (Issue #590 - NPU Dashboard Improvements)

export interface NPUWorkerMetrics {
  node_id: string
  utilization: number
  temperature_celsius: number | null
  inference_count: number
  avg_latency_ms: number
  throughput_rps: number
  queue_depth: number
  memory_used_gb: number
  memory_total_gb: number
  uptime_seconds: number
  error_count: number
  timestamp: string | null
}

export interface NPUFleetMetrics {
  total_nodes: number
  online_nodes: number
  total_inference_count: number
  avg_utilization: number
  avg_latency_ms: number
  total_throughput_rps: number
  total_queue_depth: number
  node_metrics: NPUWorkerMetrics[]
}

export interface NPUWorkerConfig {
  priority: number
  weight: number
  max_concurrent: number
  failure_action: 'retry' | 'failover' | 'skip' | 'alert'
  max_retries: number
  assigned_models: string[]
}

// =============================================================================
// External Agent Registry Types (Issue #963)
// =============================================================================

/**
 * External A2A-compliant agent registered in the SLM registry.
 */
export interface ExternalAgent {
  id: number
  name: string
  base_url: string
  description: string | null
  tags: string[]
  enabled: boolean
  has_api_key: boolean
  verified: boolean
  card_data: Record<string, unknown> | null
  card_fetched_at: string | null
  card_error: string | null
  skill_count: number
  created_by: string | null
  created_at: string | null
  updated_at: string | null
}

export interface ExternalAgentCreate {
  name: string
  base_url: string
  description?: string
  tags?: string[]
  enabled?: boolean
  ssl_verify?: boolean
  api_key?: string
}

export interface ExternalAgentUpdate {
  name?: string
  description?: string
  tags?: string[]
  enabled?: boolean
  ssl_verify?: boolean
  api_key?: string
}

export interface ExternalAgentCard {
  id: number
  name: string
  base_url: string
  card: Record<string, unknown>
}
