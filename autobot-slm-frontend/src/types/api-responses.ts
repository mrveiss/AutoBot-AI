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
//
// Derived from the generated OpenAPI contract (#13138) — request/response
// models of POST `/nodes/{node_id}/services/restart-all`
// (autobot-slm-backend/api/services.py:932).
// =============================================================================

/**
 * Request body of POST `/nodes/{node_id}/services/restart-all`
 * (models/schemas.py:897).
 *
 * `Partial<>` because both fields carry a server-side default (`category=None`,
 * `exclude_services=[]`) and openapi-typescript emits defaulted fields as
 * REQUIRED — correct for a response, backwards for a request body.
 *
 * The intersected `category` keeps the literal union: the contract widens it to
 * `string` because OpenAPI cannot express `pattern="^(autobot|system|all)$"`
 * (models/schemas.py:900), but sending anything else is a guaranteed 422.
 */
export type RestartAllServicesRequest = Partial<
  components['schemas']['RestartAllServicesRequest']
> & {
  category?: 'autobot' | 'system' | 'all' | null
}

/**
 * Element of `RestartAllServicesResponse.results`.
 *
 * Hand-written on purpose: the response model types `results` as a bare
 * `List[Dict]` (models/schemas.py:920), so the contract can only say
 * `{ [key: string]: unknown }[]`. The real keys are built at
 * api/services.py:892-897 and always include `is_slm_agent`.
 */
export interface RestartServiceResult {
  service_name: string
  success: boolean
  message: string
  is_slm_agent: boolean
}

/**
 * Response model of POST `/nodes/{node_id}/services/restart-all`
 * (models/schemas.py:911), with `results` pinned to the shape the endpoint
 * actually builds.
 */
export type RestartAllServicesResponse =
  components['schemas']['RestartAllServicesResponse'] & {
    results?: RestartServiceResult[]
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
//
// Derived from the generated OpenAPI contract (#13138) — response models of
// autobot-slm-backend/api/monitoring.py. The local names are kept as aliases
// of the differently-named schemas so existing importers stay untouched.
//
// NOTE for future passes: the same three names — `DashboardOverview`,
// `SystemMetrics` and `LogEntry` — are ALSO declared in
// `composables/usePrometheusMetrics.ts`, `views/monitoring/LogViewer.vue` and
// `components/DeploymentLogViewer.vue`. Those are client-side VIEW-MODELS that
// deliberately remap these endpoints; they must never be derived. They were
// renamed in #13138 so the collision cannot come back.
// =============================================================================

/** Entry of `FleetMetricsResponse.nodes` — `NodeMetrics` (monitoring.py:53). */
export type FleetMetricsNode = components['schemas']['NodeMetrics']

/**
 * Response model of GET `/monitoring/metrics/fleet` — `FleetMetricsResponse`
 * (monitoring.py:68). `timestamp` is `default_factory`, hence optional here.
 */
export type FleetMetrics = components['schemas']['FleetMetricsResponse']

/** Entry of `AlertsResponse.alerts` (monitoring.py:85). */
export type AlertItem = components['schemas']['AlertItem']

/** Response model of GET `/monitoring/alerts` (monitoring.py:98). */
export type AlertsResponse = components['schemas']['AlertsResponse']

/**
 * Response model of GET `/monitoring/health` — `SystemHealthResponse`
 * (monitoring.py:108). `last_check` is `default_factory`, hence optional.
 */
export type MonitoringSystemHealth = components['schemas']['SystemHealthResponse']

/** Response model of GET `/monitoring/dashboard` (monitoring.py:118). */
export type DashboardOverview = components['schemas']['DashboardOverview']

/** Entry of `LogsResponse.logs` (monitoring.py:128). */
export type LogEntry = components['schemas']['LogEntry']

/** Response model of GET `/monitoring/logs` (monitoring.py:140). */
export type LogsResponse = components['schemas']['LogsResponse']

// Application-log viewer (Issue #11302) — tails allowlisted on-node log files
// (backend-error.log, celery-error.log, etc.) via GET /monitoring/app-logs.

/** Entry of `AppLogsResponse.entries` (monitoring.py:149). */
export type AppLogEntry = components['schemas']['AppLogEntry']

/** Response model of GET `/monitoring/app-logs` (monitoring.py:158). */
export type AppLogsResponse = components['schemas']['AppLogsResponse']

// =============================================================================
// Blue-Green Deployments (Issue #726 Phase 3)
//
// Single-sourced from `types/slm.ts` (#13138): these three shapes were declared
// here AND there for the same wire models, and `DeploymentsView.vue` bridged
// the two copies with an `as BlueGreenDeployment[]` cast — so a divergence
// would have been silently cast away. `types/slm.ts` now derives them from the
// generated contract; these are aliases so existing importers keep working.
// =============================================================================

export type {
  BlueGreenDeployment as BlueGreenDeploymentApi,
  BlueGreenDeploymentCreate as BlueGreenCreate,
  BlueGreenListResponse,
} from './slm'

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

/**
 * Response model of POST `/npu/nodes/{node_id}/detect` (api/npu.py).
 * `capabilities` is the derived `NPUCapabilities` (types/slm.ts), narrowed
 * there to the `NPUDeviceType` union the detector actually emits.
 */
export type NPUDetectionResponse =
  components['schemas']['NPUDetectionResponse'] & {
    capabilities?: import('./slm').NPUCapabilities | null
  }

// =============================================================================
// Error Monitoring (Issue #563)
// =============================================================================

/**
 * Response model of GET `/errors/statistics` (api/errors.py:37).
 *
 * `trend` is a bare `str` in the contract, but `_calculate_error_trend`
 * (api/errors.py:245-273) returns exactly one of three literals on every path,
 * so the union is a real guarantee and is kept by intersection.
 */
export type ErrorStatistics = components['schemas']['ErrorStatistics'] & {
  trend: 'increasing' | 'decreasing' | 'stable'
}

/** Entry of `RecentErrorsResponse.errors` (api/errors.py:50). */
export type RecentError = components['schemas']['RecentError']

/** Response model of GET `/errors/recent` (api/errors.py:65). */
export type RecentErrorsResponse = components['schemas']['RecentErrorsResponse']

/** Entry of `CategoriesResponse.categories` (api/errors.py:74). */
export type CategoryBreakdown = components['schemas']['CategoryBreakdown']

/** Response model of GET `/errors/categories` (api/errors.py:82). */
export type CategoriesResponse = components['schemas']['CategoriesResponse']

/** Entry of `ComponentsResponse.components` (api/errors.py:89). */
export type ComponentBreakdown = components['schemas']['ComponentBreakdown']

/** Response model of GET `/errors/components` (api/errors.py:98). */
export type ComponentsResponse = components['schemas']['ComponentsResponse']

/**
 * Response model of GET `/errors/health` (api/errors.py:105).
 *
 * `status` is a bare `str` in the contract; `get_error_health`
 * (api/errors.py:509-518) assigns exactly one of three literals on every
 * branch, so the union is kept by intersection.
 */
export type ErrorHealthResponse = components['schemas']['ErrorHealthResponse'] & {
  status: 'healthy' | 'warning' | 'critical'
}

/** Response model of GET `/errors/metrics/summary` (api/errors.py:116). */
export type MetricsSummary = components['schemas']['MetricsSummary']

/** Entry of `TimelineResponse.timeline` (api/errors.py:128). */
export type TimelinePoint = components['schemas']['TimelinePoint']

/** Response model of GET `/errors/metrics/timeline` (api/errors.py:137). */
export type TimelineResponse = components['schemas']['TimelineResponse']

/** Entry of `TopErrorsResponse.errors` (api/errors.py:146). */
export type TopError = components['schemas']['TopError']

/** Response model of GET `/errors/metrics/top-errors` (api/errors.py:156). */
export type TopErrorsResponse = components['schemas']['TopErrorsResponse']

/**
 * Request body of POST `/errors/metrics/alert-threshold` (api/errors.py:162).
 * All three fields are genuinely required — they carry `ge`/`le` bounds but no
 * default — so a plain alias is correct here, not `Partial`.
 */
export type AlertThresholdConfig = components['schemas']['AlertThresholdConfig']

/** Response model of POST `/errors/metrics/alert-threshold` (api/errors.py:170). */
export type AlertThresholdResponse = components['schemas']['AlertThresholdResponse']

/** Response model of POST `/errors/metrics/cleanup` (api/errors.py:179). */
export type CleanupResponse = components['schemas']['CleanupResponse']

/** Response model of POST `/errors/clear` (api/errors.py:187). */
export type ClearResponse = components['schemas']['ClearResponse']

/** Response model of POST `/errors/metrics/resolve/{event_id}` (api/errors.py:201). */
export type ResolveResponse = components['schemas']['ResolveResponse']

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

/**
 * Shared action envelope (`ActionResponse`, models/schemas.py). `resource_id`
 * is optional AND nullable in the contract.
 */
export type ActionResponse = components['schemas']['ActionResponse']
