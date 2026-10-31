// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * SLM contract types: blue-green deployments
 */

import type { components } from './generated/api'

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
