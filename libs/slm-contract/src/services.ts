// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * SLM contract types: services
 */

import type { components } from './generated/api'

// =============================================================================
// Service Types (Issue #728)
// =============================================================================

/**
 * A service's run-state, as the SLM agent maps systemd states
 * (`_map_status_from_states` in `slm/agent/health_collector.py`). Until #15401
 * this union carried four of the eight values the agent sends.
 */
export type ServiceStatus =
  | 'running'
  | 'starting'
  | 'stopping'
  | 'stopped'
  | 'completed'
  | 'failed'
  | 'crash-loop'
  | 'unknown'

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
