// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * API Response Type Definitions
 *
 * Shared interfaces for SLM API responses, extracted from useSlmApi.ts so
 * that consumer components can import them directly instead of duplicating
 * definitions locally.  Issue #3196.
 */

// =============================================================================
// Replication
// =============================================================================

export interface SyncVerifyCheck {
  name: string
  status: string
  message: string
}

export interface SyncVerifyResponse {
  is_healthy: boolean
  service_type: string
  details: {
    source?: Record<string, unknown>
    target?: Record<string, unknown>
    comparison?: Record<string, unknown>
    lag?: Record<string, unknown>
  }
  checks: SyncVerifyCheck[]
}

// =============================================================================
// Services — Restart All (Issue #725)
// =============================================================================

export interface RestartAllServicesRequest {
  category?: 'autobot' | 'system' | 'all'
  exclude_services?: string[]
}

export interface RestartServiceResult {
  service_name: string
  success: boolean
  message: string
  is_slm_agent: boolean
}

export interface RestartAllServicesResponse {
  node_id: string
  success: boolean
  message: string
  total_services: number
  successful_restarts: number
  failed_restarts: number
  results: RestartServiceResult[]
  slm_agent_restarted: boolean
}

// =============================================================================
// VNC Credentials (Issue #725)
// =============================================================================

export interface VNCCredentialCreate {
  vnc_type?: 'desktop' | 'browser' | 'custom'
  name?: string
  password: string
  port?: number
  display_number?: number
  vnc_port?: number
  websockify_enabled?: boolean
}

export interface VNCCredentialResponse {
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

export interface VNCEndpointResponse {
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

export interface VNCEndpointsResponse {
  endpoints: VNCEndpointResponse[]
  total: number
}

export interface VNCConnectionInfo {
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

// =============================================================================
// TLS Credentials (Issue #725)
// =============================================================================

export interface TLSCredentialCreate {
  name?: string
  ca_cert: string
  server_cert: string
  server_key: string
  common_name?: string
  expires_at?: string
}

export interface TLSCredentialResponse {
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

export interface TLSEndpointResponse {
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

export interface TLSEndpointsResponse {
  endpoints: TLSEndpointResponse[]
  total: number
  expiring_soon: number
}

export interface TLSRenewResponse {
  success: boolean
  message: string
  old_credential_id: string
  new_credential_id: string
  expires_at: string | null
  deployed: boolean
  deployment_message: string | null
}

export interface TLSRotateResponse {
  success: boolean
  message: string
  old_credential_id: string
  old_deactivated: boolean
  new_credential_id: string
  expires_at: string | null
  deployed: boolean
  deployment_message: string | null
}

export interface TLSBulkRenewResult {
  old_credential_id: string
  new_credential_id?: string
  node_id: string
  success: boolean
  deployed?: boolean
  error?: string
}

export interface TLSBulkRenewResponse {
  success: boolean
  message: string
  renewed: number
  failed: number
  results: TLSBulkRenewResult[]
}

export interface TLSEnableResults {
  deploy_certs: {
    success: boolean
    returncode: number
    stdout: string
    stderr: string
  } | null
  enable_tls: {
    success: boolean
    returncode: number
    stdout: string
    stderr: string
  } | null
  services_enabled: string[]
}

export interface TLSEnableResponse {
  success: boolean
  message: string
  services: string[]
  results: TLSEnableResults
}

// =============================================================================
// Monitoring (Issue #729)
// =============================================================================

export interface FleetMetricsNode {
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
}

export interface FleetMetrics {
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
  nodes: FleetMetricsNode[]
  timestamp: string
}

export interface AlertItem {
  alert_id: string
  severity: string
  category: string
  message: string
  node_id: string | null
  hostname: string | null
  timestamp: string
  acknowledged: boolean
}

export interface AlertsResponse {
  total_count: number
  critical_count: number
  warning_count: number
  info_count: number
  alerts: AlertItem[]
}

export interface MonitoringSystemHealth {
  overall_status: string
  health_score: number
  components: Record<string, string>
  issues: string[]
  last_check: string
}

export interface DashboardOverview {
  fleet_metrics: FleetMetrics
  recent_alerts: AlertItem[]
  recent_deployments: number
  active_maintenance: number
  health_summary: MonitoringSystemHealth
}

export interface LogEntry {
  event_id: string
  node_id: string
  hostname: string
  event_type: string
  severity: string
  message: string
  timestamp: string
}

export interface LogsResponse {
  logs: LogEntry[]
  total: number
  page: number
  per_page: number
}

// =============================================================================
// Blue-Green Deployments (Issue #726 Phase 3)
// =============================================================================

export interface BlueGreenDeploymentApi {
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

export interface BlueGreenCreate {
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

export interface BlueGreenListResponse {
  deployments: BlueGreenDeploymentApi[]
  total: number
  page: number
  per_page: number
}

// =============================================================================
// NPU Management (Issue #255)
// =============================================================================

export interface NPUNodesResponse {
  nodes: import('./slm').NPUNodeStatus[]
  total: number
}

export interface NPURoleResponse {
  success: boolean
  message: string
  node_id: string
  detection_triggered?: boolean
}

export interface NPUDetectionResponse {
  success: boolean
  message: string
  node_id: string
  capabilities: import('./slm').NPUNodeStatus['capabilities'] | null
}

// =============================================================================
// Error Monitoring (Issue #563)
// =============================================================================

export interface ErrorStatistics {
  total_errors: number
  errors_24h: number
  errors_7d: number
  errors_30d: number
  resolved_count: number
  unresolved_count: number
  error_rate_per_hour: number
  trend: 'increasing' | 'decreasing' | 'stable'
}

export interface RecentError {
  event_id: string
  node_id: string
  hostname: string
  event_type: string
  severity: string
  message: string
  timestamp: string
  resolved: boolean
  resolved_at: string | null
  resolved_by: string | null
}

export interface RecentErrorsResponse {
  errors: RecentError[]
  total: number
  page: number
  per_page: number
}

export interface CategoryBreakdown {
  category: string
  count: number
  percentage: number
}

export interface CategoriesResponse {
  categories: CategoryBreakdown[]
  total: number
}

export interface ComponentBreakdown {
  node_id: string
  hostname: string
  count: number
  percentage: number
}

export interface ComponentsResponse {
  components: ComponentBreakdown[]
  total: number
}

export interface ErrorHealthResponse {
  status: 'healthy' | 'warning' | 'critical'
  error_rate_current: number
  error_rate_threshold_warning: number
  error_rate_threshold_critical: number
  recent_critical_count: number
  message: string
}

export interface MetricsSummary {
  total_errors: number
  unresolved_errors: number
  critical_errors: number
  error_rate_per_hour: number
  mean_time_to_resolve_hours: number | null
  top_error_type: string | null
  most_affected_node: string | null
}

export interface TimelinePoint {
  timestamp: string
  count: number
  critical: number
  error: number
}

export interface TimelineResponse {
  timeline: TimelinePoint[]
  interval: string
  start: string
  end: string
}

export interface TopError {
  event_type: string
  message: string
  count: number
  last_occurred: string
  affected_nodes: string[]
}

export interface TopErrorsResponse {
  errors: TopError[]
}

export interface AlertThresholdConfig {
  warning_threshold: number
  critical_threshold: number
  retention_days: number
}

export interface AlertThresholdResponse extends AlertThresholdConfig {
  updated: boolean
}

export interface CleanupResponse {
  deleted_count: number
  retention_days: number
  message: string
}

export interface ClearResponse {
  deleted_count: number
  message: string
}

export interface ResolveResponse {
  event_id: string
  resolved: boolean
  resolved_at: string
  resolved_by: string
}

// =============================================================================
// Security (Issue #813)
// =============================================================================

export interface SecurityEventResponse {
  id: number
  event_id: string
  timestamp: string
  event_type: string
  severity: string
  category: string | null
  source_ip: string | null
  source_user: string | null
  source_node_id: string | null
  target_resource: string | null
  target_node_id: string | null
  title: string
  description: string | null
  threat_indicator: string | null
  threat_score: number | null
  mitre_technique: string | null
  is_acknowledged: boolean
  acknowledged_by: string | null
  acknowledged_at: string | null
  is_resolved: boolean
  resolved_by: string | null
  resolved_at: string | null
  resolution_notes: string | null
  created_at: string
}

export interface SecurityOverviewResponse {
  security_score: number
  active_threats: number
  failed_logins_24h: number
  policy_violations: number
  total_events_24h: number
  critical_events: number
  certificates_expiring: number
  recent_events: SecurityEventResponse[]
}

export interface AuditLogResponse {
  id: number
  log_id: string
  timestamp: string
  user_id: string | null
  username: string | null
  ip_address: string | null
  category: string
  action: string
  resource_type: string | null
  resource_id: string | null
  description: string | null
  request_method: string | null
  request_path: string | null
  response_status: number | null
  success: boolean
  error_message: string | null
  created_at: string
}

export interface AuditLogListResponse {
  logs: AuditLogResponse[]
  total: number
  page: number
  per_page: number
}

export interface SecurityEventListResponse {
  events: SecurityEventResponse[]
  total: number
  page: number
  per_page: number
  unacknowledged_count: number
  critical_count: number
}

export interface ThreatSummary {
  total_threats: number
  critical: number
  high: number
  medium: number
  low: number
  acknowledged: number
  resolved: number
  by_type: Record<string, number>
  by_source_ip: Record<string, number>
  trend_24h: Array<Record<string, unknown>>
}

export interface SecurityPolicyResponse {
  id: number
  policy_id: string
  name: string
  description: string | null
  category: string
  policy_type: string
  rules: unknown[]
  parameters: Record<string, unknown>
  applies_to_nodes: unknown[]
  applies_to_roles: unknown[]
  status: string
  is_enforced: boolean
  last_evaluated: string | null
  compliance_score: number | null
  violations_count: number
  version: number
  created_by: string | null
  updated_by: string | null
  created_at: string
  updated_at: string
}

export interface SecurityPolicyListResponse {
  policies: SecurityPolicyResponse[]
  total: number
  page: number
  per_page: number
}

// =============================================================================
// Fleet Certificates (Issue #926 Phase 7)
// =============================================================================

export interface FleetCert {
  cert_id: string
  node_id: string
  serial_number: string | null
  subject: string | null
  issuer: string | null
  not_before: string | null
  not_after: string | null
  fingerprint: string | null
  status: string
  days_until_expiry: number | null
  created_at: string
  updated_at: string
}

// =============================================================================
// Setup Wizard (Issue #1294)
// =============================================================================

export interface WizardStep {
  name: string
  index: number
  completed: boolean
  current: boolean
}

export interface WizardStatusResponse {
  completed: boolean
  current_step: string
  current_step_index: number
  total_steps: number
  steps: WizardStep[]
}

// =============================================================================
// Generic action response (used across multiple endpoints)
// =============================================================================

export interface ActionResponse {
  action: string
  success: boolean
  message: string
  resource_id?: string
}
