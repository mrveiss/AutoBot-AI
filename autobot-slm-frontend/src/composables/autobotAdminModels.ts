// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * Served shapes of the main backend's permission, MCP external-server and agent-config
 * routes, as the SLM's useAutobotApi calls them (#15536). useAutobotApi re-exports these.
 */

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
// Log forwarding (#18734): autobot-backend/api/log_forwarding.py. Destinations
// are keyed by `name`; there is no id. Credentials are returned MASKED.
// ---------------------------------------------------------------------------

export type LogForwardingDestinationType =
  | 'seq'
  | 'elasticsearch'
  | 'loki'
  | 'syslog'
  | 'webhook'
  | 'file'

/** GET /log-forwarding/destinations item (bare list); api_key/password are masked. */
export interface LogForwardingDestination {
  name: string
  type: LogForwardingDestinationType
  enabled: boolean
  url: string | null
  api_key: string | null
  username: string | null
  password: string | null
  index: string | null
  file_path: string | null
  min_level: string
  batch_size: number
  batch_timeout: number
  retry_count: number
  retry_delay: number
  scope: string
  target_hosts: string[]
  syslog_protocol: string
  ssl_verify: boolean
  ssl_ca_cert: string | null
  ssl_client_cert: string | null
  ssl_client_key: string | null
  healthy: boolean
  last_error: string | null
  sent_count: number
  failed_count: number
}

/** POST /log-forwarding/destinations body (LogFwdDestinationCreate). */
export interface LogForwardingDestinationCreate {
  name: string
  type: LogForwardingDestinationType
  enabled: boolean
  url?: string | null
  api_key?: string | null
  username?: string | null
  password?: string | null
  index?: string | null
  file_path?: string | null
  min_level: string
  batch_size: number
  batch_timeout: number
  retry_count: number
  retry_delay: number
  scope: string
  syslog_protocol?: string
}

/** PUT /log-forwarding/destinations/{name} body (LogFwdDestinationUpdate); all optional. */
export type LogForwardingDestinationUpdate = Partial<
  Omit<LogForwardingDestinationCreate, 'name' | 'type'>
>

export interface LogForwardingMessage {
  message: string
}

/** POST/PUT destination response; `destination` is the sanitized (masked) config. */
export interface LogForwardingMutationResult extends LogForwardingMessage {
  destination: Record<string, unknown>
}

export interface LogForwardingTestResult {
  name: string
  healthy: boolean
  last_error: string | null
  message: string
}

/** POST /log-forwarding/test-all; `results` maps destination name to healthy (bool). */
export interface LogForwardingTestAllResult {
  results: Record<string, boolean>
  total: number
  healthy: number
  unhealthy: number
}

export interface LogForwardingDestinationStatus {
  name: string
  type: string
  enabled: boolean
  healthy: boolean
  last_error: string | null
  sent_count: number
  failed_count: number
  scope: string
}

/** GET /log-forwarding/status. Carries NO auto_start; read it from /auto-start. */
export interface LogForwardingStatus {
  running: boolean
  hostname: string
  queue_size: number
  destinations: LogForwardingDestinationStatus[]
  total_destinations: number
  enabled_destinations: number
  healthy_destinations: number
  total_sent: number
  total_failed: number
}

export interface LogForwardingAutoStart {
  auto_start: boolean
  message: string
}
