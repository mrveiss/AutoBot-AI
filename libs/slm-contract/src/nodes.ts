// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * SLM Type Definitions
 */

import type { components } from './generated/api'
import type { ServiceStatus } from './services'

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

export type NodeHealthStatus = 'healthy' | 'degraded' | 'unhealthy' | 'unknown'

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
  status: NodeHealthStatus
  cpu_percent: number
  memory_percent: number
  disk_percent: number
  last_heartbeat: string | null
  services: ServiceHealth[]
}

/**
 * One service in a node's health report (#15401). `GET /nodes/{id}/health`
 * returns `{ name, status }` per service, and `status` is the agent's systemd
 * run-state -- not a health verdict -- so it is `ServiceStatus`, not `HealthStatus`.
 */
export interface ServiceHealth {
  name: string
  status: ServiceStatus
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
  // #14676: roles assigned to this node that reach no ansible group and have
  // no dedicated playbook, so nothing will deploy them. Optional: older
  // backends do not send it.
  unreachable_roles?: string[]
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
  backup_path: string | null
  // #13307: the API field is `status` (models/schemas.py BackupResponse); `state` read undefined, so the
  // Status column was blank and Restore never appeared. `backup_path` is nullable until the copy succeeds.
  status: 'pending' | 'in_progress' | 'completed' | 'failed'
  // #19455: the API restores only these; restoring any other type over Redis destroyed its data.
  restorable: boolean
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
