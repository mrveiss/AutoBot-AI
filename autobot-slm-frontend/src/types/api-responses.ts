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

import type { components } from './generated/api'

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
//
// Derived from the generated OpenAPI contract (#13138) — response models of
// autobot-slm-backend/api/vnc.py.
// =============================================================================

/** Request body of POST `/nodes/{node_id}/vnc/credentials` (vnc.py:48). */
export type VNCCredentialCreate = components['schemas']['VNCCredentialCreate']

/** Response model of the VNC credential endpoints (vnc.py:48, :115, :139). */
export type VNCCredentialResponse = components['schemas']['VNCCredentialResponse']

/** Response model of GET `/nodes/{node_id}/vnc/credentials` (vnc.py:82). */
export type VNCCredentialListResponse = components['schemas']['VNCCredentialListResponse']

/** Entry of the fleet-wide VNC endpoint list (vnc.py:227). */
export type VNCEndpointResponse = components['schemas']['VNCEndpointResponse']

/** Response model of GET `/vnc/endpoints` (vnc.py:227). */
export type VNCEndpointsResponse = components['schemas']['VNCEndpointsResponse']

/** Response model of POST `/vnc/credentials/{credential_id}/connect` (vnc.py:187). */
export type VNCConnectionInfo = components['schemas']['VNCConnectionInfo']

// =============================================================================
// TLS Credentials (Issue #725)
//
// Derived from the generated OpenAPI contract (#13138) — response models of
// autobot-slm-backend/api/tls.py. `TLSCredentialResponse` carries `ca_cert`
// and `server_cert` (public certificate data; the private key is never
// returned — models/schemas.py:1352-1368), both of which the hand-written
// declaration omitted.
// =============================================================================

/** Request body of POST `/nodes/{node_id}/tls/credentials` (tls.py:68). */
export type TLSCredentialCreate = components['schemas']['TLSCredentialCreate']

/** Response model of the TLS credential endpoints (tls.py:68, :138, :160). */
export type TLSCredentialResponse = components['schemas']['TLSCredentialResponse']

/** Response model of GET `/nodes/{node_id}/tls/credentials` (tls.py:101). */
export type TLSCredentialListResponse = components['schemas']['TLSCredentialListResponse']

/** Entry of the fleet-wide TLS endpoint list (tls.py:282). */
export type TLSEndpointResponse = components['schemas']['TLSEndpointResponse']

/** Response model of GET `/tls/endpoints` and `/tls/expiring` (tls.py:282, :305). */
export type TLSEndpointsResponse = components['schemas']['TLSEndpointsResponse']

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

// Application-log viewer (Issue #11302) — tails allowlisted on-node log files
// (backend-error.log, celery-error.log, etc.) via GET /monitoring/app-logs.
export interface AppLogEntry {
  line_number: number
  timestamp: string | null
  severity: string | null
  message: string
}

export interface AppLogsResponse {
  entries: AppLogEntry[]
  total: number
  page: number
  per_page: number
  node_id: string
  service: string
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
//
// Single-sourced from `types/slm.ts` (#13138): these eight shapes were
// hand-declared identically here and there, so one backend change had two
// places to drift from. `types/slm.ts` now derives them from the generated
// OpenAPI contract; this module re-exports so existing importers keep working.
// =============================================================================

export type {
  SecurityEventResponse,
  SecurityOverviewResponse,
  AuditLogResponse,
  AuditLogListResponse,
  SecurityEventListResponse,
  ThreatSummary,
  SecurityPolicyResponse,
  SecurityPolicyListResponse,
} from './slm'

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
