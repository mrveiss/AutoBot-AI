// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * SLM contract types: external agents, playbooks and security
 */

import type { components } from './generated/api'

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
