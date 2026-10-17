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
