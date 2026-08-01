// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * SLM Type Definitions
 */

import type { components } from './generated/api'

/**
 * Node status — derived from the generated OpenAPI type (#12662), which is
 * itself generated from the backend's canonical `NodeStatus` enum
 * (autobot-slm-backend/models/database.py). Do not hand-declare this union;
 * it drifted to 11 hand-invented values ('registered', 'healthy',
 * 'unhealthy') that the backend has never emitted before #12662 fixed it.
 * Re-run `npm run gen:types:openapi && npm run gen:types` after a backend
 * enum change — `verify-generated-types-slm` (CI) fails if this drifts.
 */
export type NodeStatus = components['schemas']['NodeStatus']

/**
 * Role names the SLM fleet can assign.
 *
 * Mirror of `DEFAULT_ROLES` in
 * autobot-slm-backend/services/role_registry.py:416 — the registry is the
 * source of truth and `constants/node-roles.ts` carries the matching metadata.
 * `'docker'` (`_INFRA_ROLES`, role_registry.py:372) was missing from this union
 * until #13138; `GET /deployments/roles` has always returned it.
 */
export type NodeRole =
  | 'slm-backend'
  | 'slm-frontend'
  | 'slm-database'
  | 'slm-monitoring'
  | 'backend'
  | 'celery'
  | 'scheduler'
  | 'frontend'
  | 'redis'
  | 'postgres'
  | 'ai-stack'
  | 'chromadb'
  | 'npu-worker'
  | 'tts-worker'
  | 'browser-service'
  | 'autobot-llm-cpu'
  | 'autobot-llm-gpu'
  | 'autobot_shared'
  | 'slm-agent'
  | 'vnc'
  | 'docker'

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
 * Raw per-package update record as returned by the backend's
 * UpdateInfoResponse (models/schemas.py) — field names mirror the wire
 * format exactly (#11964).
 */
export interface NodeUpdateRecord {
  update_id: string
  node_id: string | null
  package_name: string
  current_version: string | null
  available_version: string
  severity: string
  description: string | null
  is_applied: boolean
  applied_at: string | null
  created_at: string
}

/**
 * Response from GET /nodes/{node_id}/updates — the live "Check for updates"
 * scan (#11964). code_update_available/code_status mirror the SAME
 * node.code_status field NodeUpdateSummary reads, so the live scan and the
 * fleet-summary badge can never disagree.
 */
export interface NodeUpdateCheckResponse {
  updates: NodeUpdateRecord[]
  total: number
  code_update_available: boolean
  code_status: string
}

/**
 * Role category for grouping
 */
export type RoleCategory = 'core' | 'data' | 'application' | 'ai' | 'automation' | 'observability' | 'remote-access' | 'infrastructure'

/**
 * Available role information — response element of GET `/deployments/roles`
 * (`RoleInfo`, models/schemas.py:421). Derived from the generated contract
 * (#13138).
 *
 * The hand-written declaration omitted `ansible_role` entirely
 * (schemas.py:427) — the playbook the role maps to — so the UI could not reach
 * it.
 *
 * `name` and `category` are widened to `str` by the contract but stay narrowed
 * here: `_build_available_roles` (api/deployments.py:149-171) copies
 * `reg["name"]` out of `role_registry.DEFAULT_ROLES`, which
 * `constants/node-roles.ts` is documented to mirror, and every `category` comes
 * from `_ROLE_UI_META` (deployments.py:44-147) or the `"core"` default — both
 * sets match these unions exactly. Deriving them surfaced the one real gap:
 * `'docker'` was missing from `NodeRole`.
 *
 * `dependencies` is NOT narrowed back to `NodeRole[]`: the builder passes
 * `dependencies=[]` unconditionally (deployments.py:166), so the old claim
 * described a field the endpoint never populates.
 */
export type RoleInfo = components['schemas']['RoleInfo'] & {
  name: NodeRole
  category: RoleCategory
}

/**
 * Response model of GET `/deployments/roles` (models/schemas.py:435).
 *
 * NOTE (#13138) — the narrowed member comes FIRST in these list envelopes on
 * purpose. `A[] & B[]` keeps both `map` signatures and TypeScript resolves the
 * callback against the first one, so `base & { items: Narrow[] }` silently
 * types the callback parameter as the WIDE element (that is how
 * `useNodeServices.ts` ended up mapping `category` as `string`). Writing
 * `{ items: Narrow[] } & base` picks the narrowed element.
 */
export type RoleListResponse = { roles: RoleInfo[] } & components['schemas']['RoleListResponse']

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

/**
 * Request body of POST `/maintenance/windows` — `MaintenanceWindowCreate`.
 * Derived from the generated contract (#13138).
 *
 * `Partial<>` because `auto_drain`, `suppress_alerts` and `suppress_remediation`
 * all carry server-side defaults and openapi-typescript emits defaulted fields
 * as REQUIRED — backwards for a request body. The two genuinely mandatory
 * fields are re-required by indexed access so they stay derived.
 */
export type MaintenanceWindowCreate = Partial<
  components['schemas']['MaintenanceWindowCreate']
> & {
  start_time: components['schemas']['MaintenanceWindowCreate']['start_time']
  end_time: components['schemas']['MaintenanceWindowCreate']['end_time']
}

/** Response model of GET `/maintenance/windows`. */
export type MaintenanceWindowListResponse = { windows: MaintenanceWindow[] } &
  components['schemas']['MaintenanceWindowListResponse']

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
 * Per-node update summary from the fleet update check (#682), derived from the
 * generated contract (#13138).
 */
export type NodeUpdateSummary = components['schemas']['NodeUpdateSummary']

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

/**
 * A systemd unit tracked on a node — the `ServiceResponse` model
 * (autobot-slm-backend/models/schemas.py), derived from the generated contract
 * (#13138). The hand-written declaration was missing `endpoint_path`, `port`,
 * `protocol` and `is_discoverable`.
 *
 * `status` and `category` are widened to `string` by the contract but kept as
 * unions here: `category` is written only through `ServiceCategoryUpdate`,
 * which pins `pattern="^(autobot|system)$"`, and `status` is written only from
 * the `ServiceStatus` enum. Issue #1019: `extra_data` may include
 * `error_message` for failed services.
 */
export type NodeService = components['schemas']['ServiceResponse'] & {
  status: ServiceStatus
  category: ServiceCategory
}

/**
 * Response model of GET `/nodes/{node_id}/services` (#13138). The intersection
 * keeps `services` pinned to `NodeService`, whose `status`/`category` literal
 * unions the contract widens to `string`.
 */
export type ServiceListResponse = { services: NodeService[] } & components['schemas']['ServiceListResponse']

export interface ServiceActionResponse {
  action: string
  service_name: string
  node_id: string
  success: boolean
  message: string
  job_id?: string
}

/** Response model of GET `/nodes/{node_id}/services/{name}/logs` (#13138). */
export type ServiceLogsResponse = components['schemas']['ServiceLogsResponse']

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

/**
 * Blue-green deployment lifecycle status.
 *
 * The contract widens `status` to `str`; the real value set is the
 * `BlueGreenStatus` enum (models/database.py:573-586), which the column
 * default and every assignment site draw from. `'monitoring'` is the
 * post-deployment health-watch state added by Issue #726 Phase 3
 * (services/blue_green.py:780) and was missing from this union — a deployment
 * sitting in it fell through every bucket of `bgStats` in `DeploymentsView`.
 */
export type BlueGreenStatus =
  | 'pending'
  | 'borrowing'
  | 'deploying'
  | 'verifying'
  | 'switching'
  | 'active'
  | 'monitoring'
  | 'rolling_back'
  | 'rolled_back'
  | 'completed'
  | 'failed'

/**
 * `deployment_type` value set — a bare `str` column with an `upgrade` default
 * and an enumerating comment (models/database.py:617).
 */
export type BlueGreenDeploymentType = 'upgrade' | 'migration' | 'failover'

/**
 * Response model of the blue-green endpoints — `BlueGreenResponse`
 * (autobot-slm-backend/api/blue_green.py). Derived from the generated contract
 * (#13138); the intersection keeps the two literal unions the schema widens to
 * `string`.
 */
export type BlueGreenDeployment = components['schemas']['BlueGreenResponse'] & {
  status: BlueGreenStatus
  deployment_type: BlueGreenDeploymentType
}

/**
 * Request body of POST `/blue-green` — `BlueGreenCreate`.
 *
 * `Partial<>` because every optional knob carries a server-side default and
 * openapi-typescript emits defaulted fields as REQUIRED, which is backwards for
 * a request body; the three genuinely mandatory fields are re-required by
 * indexed access so they stay derived.
 */
export type BlueGreenDeploymentCreate = Partial<
  components['schemas']['BlueGreenCreate']
> & {
  blue_node_id: components['schemas']['BlueGreenCreate']['blue_node_id']
  green_node_id: components['schemas']['BlueGreenCreate']['green_node_id']
  roles: components['schemas']['BlueGreenCreate']['roles']
  deployment_type?: BlueGreenDeploymentType
}

/** Response model of GET `/blue-green` (paginated list). */
export type BlueGreenListResponse = { deployments: BlueGreenDeployment[] } &
  components['schemas']['BlueGreenListResponse']

export interface EligibleNode {
  node_id: string
  hostname: string
  ip_address: string
  current_roles: string[]
  available_capacity: number
  status: string
}

/** Response model of GET `/blue-green/eligible-nodes` (#13138). */
export type EligibleNodesResponse = { nodes: EligibleNode[] } &
  components['schemas']['EligibleNodesResponse']

/**
 * Request body of the role-purge endpoint (#13138). `force` carries a
 * server-side default, so `Partial<>` + re-required mandatory fields.
 */
export type RolePurgeRequest = Partial<
  components['schemas']['RolePurgeRequest']
> & {
  node_id: components['schemas']['RolePurgeRequest']['node_id']
  roles: components['schemas']['RolePurgeRequest']['roles']
}

// =============================================================================
// NPU Worker Types (Issue #255 - NPU Fleet Integration)
// =============================================================================

export type NPUDeviceType = 'intel-npu' | 'nvidia-gpu' | 'amd-gpu' | 'unknown'

export type NPULoadBalancingStrategy = 'round-robin' | 'least-loaded' | 'model-affinity'

/**
 * NPU device capabilities reported by detection (#13138).
 *
 * `deviceType` is deliberately NOT narrowed back to `NPUDeviceType`: it is
 * copied verbatim out of an external NPU worker's `/health` payload
 * (`data.get("deviceType", "unknown")`, api/npu.py:83), so nothing constrains
 * it to the four known values. All three renderers already fall through to the
 * raw string for an unknown device (NPUNodeCard.vue:50,
 * NPUWorkerMonitor.vue:97, NPUDetailsPanel.vue:54), so the union was an
 * unverifiable claim the UI never relied on. `NPUDeviceType` stays exported as
 * the set of values that get a friendly label.
 */
export type NPUCapabilities = components['schemas']['NPUCapabilities']

export interface NPUNodeStatus {
  node_id: string
  capabilities: NPUCapabilities | null
  loadedModels: string[]
  queueDepth: number
  lastHealthCheck: string | null
  detectionStatus: 'pending' | 'detected' | 'failed' | 'unavailable'
  detectionError?: string
}

/**
 * NPU load-balancing configuration (#13138).
 *
 * `strategy` is a bare `str` on the model (models/schemas.py:2115), but the
 * value set is enumerated by `NPULoadBalancingStrategy`
 * (models/schemas.py:2078-2085) and matches this union exactly, so the
 * narrowing is kept by intersection. `modelAffinity` is `default_factory=dict`,
 * hence optional in the contract.
 */
export type NPULoadBalancingConfig =
  components['schemas']['NPULoadBalancingConfig'] & {
    strategy: NPULoadBalancingStrategy
  }

export interface NPUModelInfo {
  name: string
  size_mb: number
  loaded: boolean
  inference_time_ms: number | null
  total_requests: number
}

// NPU Metrics & Config Types (Issue #590 - NPU Dashboard Improvements)

/**
 * Per-worker NPU metrics (#13138). `temperature_celsius` and `timestamp` are
 * optional AND nullable in the contract; the hand-written declaration required
 * both to be present.
 */
export type NPUWorkerMetrics = components['schemas']['NPUWorkerMetrics']

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

/**
 * Configuration for an individual NPU worker (models/schemas.py:2196), derived
 * from the generated contract (#13138).
 *
 * `failure_action` is a bare `str` with only a `retry` default server-side
 * (schemas.py:2202); its sole construction site is the four-option `<select>`
 * at `components/fleet/NPUDetailsPanel.vue:383-386`, so the union is a real
 * frontend-side guarantee and is kept by intersection.
 */
export type NPUWorkerConfig = components['schemas']['NPUWorkerConfig'] & {
  failure_action: 'retry' | 'failover' | 'skip' | 'alert'
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

/**
 * Request body of POST `/external-agents` (#13138).
 *
 * `Partial<>` because `enabled`, `ssl_verify` and `tags` carry server-side
 * defaults that openapi-typescript emits as REQUIRED — backwards for a request
 * body; `name` and `base_url` are re-required by indexed access.
 */
export type ExternalAgentCreate = Partial<
  components['schemas']['ExternalAgentCreate']
> & {
  name: components['schemas']['ExternalAgentCreate']['name']
  base_url: components['schemas']['ExternalAgentCreate']['base_url']
}

/**
 * Request body of PATCH `/external-agents/{id}` (#13138) — every field is a
 * nullable override, so a plain alias is correct here.
 */
export type ExternalAgentUpdate = components['schemas']['ExternalAgentUpdate']

export interface ExternalAgentCard {
  id: number
  name: string
  base_url: string
  card: Record<string, unknown>
}

// =============================================================================
// Infrastructure Playbooks (Issue #1177)
//
// Derived from the generated OpenAPI contract (#13138) — response models of
// autobot-slm-backend/api/infrastructure.py. `PlaybookInfo` was declared
// identically in `components/InfrastructureWizard.vue` and
// `views/InfrastructureView.vue`, so one backend change had two places to
// drift from; both now import this single definition.
// =============================================================================

/**
 * Response element of GET `/infrastructure/playbooks`
 * (api/infrastructure.py:54).
 *
 * Both hand-written copies omitted `tags`, and typed `category` as a bare
 * `string` where the contract has the `PlaybookCategory` enum.
 */
export type PlaybookInfo = components['schemas']['PlaybookInfo']

/** Playbook category enum (api/infrastructure.py:33). */
export type PlaybookCategory = components['schemas']['PlaybookCategory']

/**
 * Playbook run state (api/infrastructure.py:69). `output` is
 * `default_factory=list` and therefore optional in the contract.
 */
export type PlaybookExecution = components['schemas']['PlaybookExecution']

/** Playbook execution status enum (api/infrastructure.py:44). */
export type PlaybookStatus = components['schemas']['PlaybookStatus']

// =============================================================================
// Security API Response Types (Issue #3184)
//
// Derived from the generated OpenAPI contract (#13138). Every shape below is
// the response model of a `/security/*` endpoint in
// autobot-slm-backend/api/security.py, so `vue-tsc` now fails when the backend
// schema moves instead of the drift reaching a security dashboard unnoticed.
// =============================================================================

/** Response model of GET/POST `/security/events*` (security.py:530, :549, :577). */
export type SecurityEventResponse = components['schemas']['SecurityEventResponse']

/** Response model of GET `/security/overview` (security.py:191). */
export type SecurityOverviewResponse = components['schemas']['SecurityOverviewResponse']

/** Response model of GET `/security/audit-logs/{log_id}` (security.py:292). */
export type AuditLogResponse = components['schemas']['AuditLogResponse']

/** Response model of GET `/security/audit-logs` (security.py:231). */
export type AuditLogListResponse = components['schemas']['AuditLogListResponse']

/** Response model of GET `/security/events` (security.py:376). */
export type SecurityEventListResponse = components['schemas']['SecurityEventListResponse']

/** Response model of GET `/security/events/summary` (security.py:456). */
export type ThreatSummary = components['schemas']['ThreatSummary']

/** Response model of GET/PATCH `/security/policies/{policy_id}` (security.py:696, :715). */
export type SecurityPolicyResponse = components['schemas']['SecurityPolicyResponse']

/** Response model of GET `/security/policies` (security.py:617). */
export type SecurityPolicyListResponse = components['schemas']['SecurityPolicyListResponse']
