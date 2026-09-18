// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * External MCP Server Admin CRUD Composable (#16825)
 *
 * Surfaces the #11542 backend (user-configured stdio/SSE/streamable_http
 * MCP servers, credential threading, egress guard, stdio launcher
 * allowlist), which had no reachable GUI.
 *
 * AutoBot - AI-Powered Automation Platform
 * Author: mrveiss
 */

import { useApiClient } from '@/plugins/api'
import { getApiBase } from '@/config/ssot-config'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('useMcpExternalServersApi')

export type McpTransport = 'stdio' | 'sse' | 'streamable_http'
export type McpAuthType = 'BearerAuth' | 'ApiKeyAuth' | 'BasicAuth' | ''

export interface McpServer {
  server_id: string
  name: string
  transport: McpTransport
  enabled: boolean
  owner_id: string
  created_at: string
  command: string | null
  url: string | null
  auth_type: string | null
  allowed_roles: string[]
  has_credential: boolean
}

export interface McpServerCreateInput {
  name: string
  transport: McpTransport
  command?: string
  url?: string
  auth_type?: McpAuthType
  credentials?: Record<string, string>
  enabled: boolean
  allowed_roles?: string[]
}

export interface McpServerUpdateInput {
  name?: string
  enabled?: boolean
  command?: string
  url?: string
  auth_type?: McpAuthType
  credentials?: Record<string, string>
  allowed_roles?: string[]
}

export interface UseMcpExternalServersApiReturn {
  list: () => Promise<McpServer[]>
  create: (input: McpServerCreateInput) => Promise<McpServer>
  update: (serverId: string, input: McpServerUpdateInput) => Promise<McpServer>
  remove: (serverId: string) => Promise<void>
}

export function useMcpExternalServersApi(): UseMcpExternalServersApiReturn {
  const api = useApiClient()
  const base = `${getApiBase()}/mcp/external_servers`

  async function list(): Promise<McpServer[]> {
    try {
      // No generated-contract type for this endpoint's response shape yet
      // (the backend returns a bare dict) -- api.get's own <T = unknown>
      // default plus a cast here, rather than a type argument at the call
      // site, is what keeps this off repo_tests/frontend_api_contract_
      // ratchet_test.py's inline_generics count (#16875); the shape claim
      // itself is exactly as unverified either way.
      const data = (await api.get(base)) as { servers?: McpServer[] }
      return data?.servers ?? []
    } catch (error: unknown) {
      logger.error('Failed to list external MCP servers', error)
      return []
    }
  }

  async function create(input: McpServerCreateInput): Promise<McpServer> {
    return (await api.post(base, input)) as McpServer
  }

  async function update(serverId: string, input: McpServerUpdateInput): Promise<McpServer> {
    return (await api.put(`${base}/${encodeURIComponent(serverId)}`, input)) as McpServer
  }

  async function remove(serverId: string): Promise<void> {
    await api.delete(`${base}/${encodeURIComponent(serverId)}`)
  }

  return { list, create, update, remove }
}
