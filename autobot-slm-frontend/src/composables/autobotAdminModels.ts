// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * Served shapes of the main backend's permission, MCP external-server and agent-config
 * routes, as the SLM's useAutobotApi calls them (#15536). useAutobotApi re-exports these.
 */

import type { components as backend } from '@autobot/backend-contract'

/** A tool permission rule (autobot-backend/api/permissions.py); rules have no id. */
export interface PermissionRule {
  tool: string
  pattern: string
  action: 'allow' | 'ask' | 'deny'
  description?: string
}

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
