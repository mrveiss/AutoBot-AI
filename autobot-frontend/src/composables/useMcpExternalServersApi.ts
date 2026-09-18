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
      const data = await api.get<{ servers?: McpServer[] }>(base)
      return data?.servers ?? []
    } catch (error: unknown) {
      logger.error('Failed to list external MCP servers', error)
      return []
    }
  }

  async function create(input: McpServerCreateInput): Promise<McpServer> {
    return api.post<McpServer>(base, input)
  }

  async function update(serverId: string, input: McpServerUpdateInput): Promise<McpServer> {
    return api.put<McpServer>(`${base}/${encodeURIComponent(serverId)}`, input)
  }

  async function remove(serverId: string): Promise<void> {
    await api.delete(`${base}/${encodeURIComponent(serverId)}`)
  }

  return { list, create, update, remove }
}
