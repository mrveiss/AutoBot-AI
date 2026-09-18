// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
//
// Tests for useMcpExternalServersApi — #16825.

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { useMcpExternalServersApi } from '../useMcpExternalServersApi'

const mockGet = vi.fn()
const mockPost = vi.fn()
const mockPut = vi.fn()
const mockDelete = vi.fn()

vi.mock('@/plugins/api', () => ({
  useApiClient: () => ({
    get: mockGet,
    post: mockPost,
    put: mockPut,
    delete: mockDelete,
    patch: vi.fn(),
  }),
}))

vi.mock('@/config/ssot-config', () => ({
  getApiBase: () => '/api',
}))

vi.mock('@/utils/debugUtils', () => ({
  createLogger: () => ({ debug: vi.fn(), error: vi.fn(), warn: vi.fn(), info: vi.fn() }),
}))

const FAKE_SERVER = {
  server_id: 'srv-1',
  name: 'Example',
  transport: 'stdio' as const,
  enabled: true,
  owner_id: 'user-1',
  created_at: '2026-01-01T00:00:00Z',
  command: 'npx -y example-server',
  url: null,
  auth_type: null,
  allowed_roles: ['admin'],
  has_credential: false,
}

describe('useMcpExternalServersApi.list', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('calls GET /api/mcp/external_servers', async () => {
    mockGet.mockResolvedValue({ servers: [FAKE_SERVER] })
    const { list } = useMcpExternalServersApi()
    const result = await list()
    expect(mockGet).toHaveBeenCalledWith('/api/mcp/external_servers')
    expect(result).toEqual([FAKE_SERVER])
  })

  it('returns an empty array (not null) when the API call throws', async () => {
    mockGet.mockRejectedValue(new Error('network error'))
    const { list } = useMcpExternalServersApi()
    const result = await list()
    expect(result).toEqual([])
  })

  it('tolerates a response missing the servers field', async () => {
    mockGet.mockResolvedValue({})
    const { list } = useMcpExternalServersApi()
    const result = await list()
    expect(result).toEqual([])
  })
})

describe('useMcpExternalServersApi.create', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('POSTs the create payload to /api/mcp/external_servers', async () => {
    mockPost.mockResolvedValue(FAKE_SERVER)
    const { create } = useMcpExternalServersApi()
    const input = { name: 'Example', transport: 'stdio' as const, command: 'npx -y example', enabled: true }
    const result = await create(input)
    expect(mockPost).toHaveBeenCalledWith('/api/mcp/external_servers', input)
    expect(result).toEqual(FAKE_SERVER)
  })
})

describe('useMcpExternalServersApi.update', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('PUTs to the server_id path, URL-encoded', async () => {
    mockPut.mockResolvedValue(FAKE_SERVER)
    const { update } = useMcpExternalServersApi()
    await update('srv 1', { enabled: false })
    expect(mockPut).toHaveBeenCalledWith('/api/mcp/external_servers/srv%201', { enabled: false })
  })
})

describe('useMcpExternalServersApi.remove', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('DELETEs the server_id path', async () => {
    mockDelete.mockResolvedValue(undefined)
    const { remove } = useMcpExternalServersApi()
    await remove('srv-1')
    expect(mockDelete).toHaveBeenCalledWith('/api/mcp/external_servers/srv-1')
  })
})
