// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * Served shapes of the main backend's permission, MCP external-server and agent-config
 * routes, as the SLM's useAutobotApi calls them (#15536). useAutobotApi re-exports these.
 */

import type { components as backend } from '@autobot/backend-contract'
import type { PermissionRule } from '@autobot/ui'

/** A tool permission rule (autobot-backend/api/permissions.py); rules have no id. The kit declares it. */
export type { PermissionRule }

/** GET /api/mcp/external_servers item (api/schemas_mcp_external_servers.py MCPServerResponse). */
export interface MCPServer {
  server_id: string
  name: string
  transport: string
  enabled: boolean
  owner_id: string
  created_at: string
  command: string | null
  url: string | null
  auth_type: string | null
  allowed_roles: string[]
  has_credential: boolean
}

/** GET /api/agent_config/agents item (api/agent_config.py list_agents); the fields read here. */
export interface AgentConfigSummary {
  id: string
  name: string
  description: string
  current_model: string
  provider: string
  enabled: boolean
  status: 'connected' | 'disconnected'
  priority: number
  tasks: string[]
}

// ---------------------------------------------------------------------------
// Log forwarding (#18734): autobot-backend/api/log_forwarding.py, typed from the main
// backend's generated OpenAPI contract (type-only alias; no runtime import), never by hand.
// Destinations are keyed by `name`; there is no id. Credentials are returned MASKED.
// ---------------------------------------------------------------------------

type BackendSchemas = backend['schemas']

/** GET /log-forwarding/destinations item (bare list); api_key/password are masked. */
export type LogForwardingDestination = BackendSchemas['LogForwardingDestinationItem']
export type LogForwardingDestinationType = LogForwardingDestination['type']
/** POST /log-forwarding/destinations body. */
export type LogForwardingDestinationCreate = BackendSchemas['LogFwdDestinationCreate']
/** PUT /log-forwarding/destinations/{name} body; every field optional. */
export type LogForwardingDestinationUpdate = BackendSchemas['LogFwdDestinationUpdate']
export type LogForwardingMessage = BackendSchemas['LogFwdMessageResponse']
/** POST/PUT destination response; `destination` is the sanitized (masked) config. */
export type LogForwardingMutationResult = BackendSchemas['LogFwdCreateUpdateResponse']
export type LogForwardingTestResult = BackendSchemas['LogFwdTestResponse']
/** POST /log-forwarding/test-all; `results` maps destination name to healthy. */
export type LogForwardingTestAllResult = BackendSchemas['LogFwdTestAllResponse']
export type LogForwardingDestinationStatus = BackendSchemas['LogFwdDestinationStatusItem']
/** GET /log-forwarding/status. Carries NO auto_start; read it from /auto-start. */
export type LogForwardingStatus = BackendSchemas['LogFwdStatusResponse']
export type LogForwardingAutoStart = BackendSchemas['LogFwdAutoStartResponse']

// ---------------------------------------------------------------------------
// Web research (#19217): autobot-backend/api/web_research_settings.py. The routes answer
// with the flat `*Data` bodies below (the contract's DataResponse envelope is documentation
// only), typed from the generated OpenAPI contract, never by hand.
// ---------------------------------------------------------------------------

/** GET /web-research/settings `settings`; PUT answers with the full set after the change. */
export type WebResearchSettings = BackendSchemas['WebResearchSettings']
export type WebResearchSettingKey = keyof WebResearchSettings
/** PUT /web-research/settings body: only the fields sent are changed; extra fields are rejected. */
export type WebResearchSettingsUpdate = BackendSchemas['WebResearchSettingsUpdate']
export type WebResearchSettingsData = BackendSchemas['WebResearchSettingsData']
/** PUT answer; `status` is "saved_not_applied" when saved but the running researcher did not take it. */
export type WebResearchSettingsUpdateData = BackendSchemas['WebResearchSettingsUpdateData']
/** GET /web-research/status; a 503 means the researcher failed to start. */
export type WebResearchStatusData = BackendSchemas['WebResearchStatusData']
/** POST /web-research/enable and /disable; `status` can be "saved_not_applied" too. */
export type WebResearchToggleData = BackendSchemas['WebResearchToggleData']
/** POST /web-research/clear-cache and /reset-circuit-breakers. */
export type WebResearchCacheClearData = BackendSchemas['WebResearchCacheClearData']

// GH#8998 / #10488: LLM fallback monitoring (moved from main frontend to SLM admin)
export interface LLMFallbackChain {
  primary_model: string
  fallback_chain: string
  provider: string
}

export interface LLMActiveFallback {
  conversation_id: string
  primary_model: string
  fallback_model: string
  primary_provider: string
  fallback_provider: string
  timestamp: number
}

export interface LLMFallbackStatus {
  configured_chains: LLMFallbackChain[]
  active_fallbacks: LLMActiveFallback[]
}

// Budget audit (#10488 Workstream A): read-only operator oversight of
// agent/project/task/tenant budget policies + hard-stop auto-pause config.
// Mirrors the backend BudgetPolicyResponse model (api/budget_policies.py).
export interface BudgetPolicy {
  id: string
  scope: string
  scope_id: string
  period: string
  threshold_usd: number
  warning_pct: number
  action: string
  enabled: boolean
  name: string
  description: string
  created_at: string
  updated_at: string
}

export interface BudgetPoliciesList {
  policies: BudgetPolicy[]
  count: number
}
