// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * #12420 Phase 2 (batch 3) — proves the LLM-config composable is migrated onto
 * the canonical `slmApiClient`: every method routes through the shared client
 * with endpoints relative to the SLM API base (base URL + bearer token injected
 * by the client) and returns the parsed JSON body directly (no axios `.data`).
 * These are non-auth endpoints, so 401 session handling is the client's
 * centralised concern — the composable no longer owns an axios interceptor.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'

const mockGet = vi.fn()
const mockPut = vi.fn()
const mockPost = vi.fn()

vi.mock('@/utils/ApiClient', () => ({
  default: {
    get: (...args: unknown[]) => mockGet(...args),
    put: (...args: unknown[]) => mockPut(...args),
    post: (...args: unknown[]) => mockPost(...args),
  },
}))

import { useLlmConfigApi } from './useLlmConfigApi'

describe('useLlmConfigApi — migrated onto slmApiClient (#12420 Phase 2)', () => {
  beforeEach(() => {
    mockGet.mockReset()
    mockPut.mockReset()
    mockPost.mockReset()
  })

  it('getConfig GETs /settings/admin/llm and returns the parsed body directly', async () => {
    const body = { config: { active_provider: 'ollama' }, message: 'ok' }
    mockGet.mockResolvedValue(body)

    const result = await useLlmConfigApi().getConfig()

    expect(mockGet).toHaveBeenCalledWith('/settings/admin/llm')
    expect(result).toEqual(body)
  })

  it('saveConfig PUTs the config to /settings/admin/llm', async () => {
    const config = { active_provider: 'ollama', providers: [] }
    mockPut.mockResolvedValue({ config, message: 'saved' })

    await useLlmConfigApi().saveConfig(config as never)

    expect(mockPut).toHaveBeenCalledWith('/settings/admin/llm', config)
  })

  it('testConnection POSTs the request to /settings/admin/llm/test', async () => {
    const request = { provider: 'openai', api_key: 'k' }
    mockPost.mockResolvedValue({ success: true })

    await useLlmConfigApi().testConnection(request)

    expect(mockPost).toHaveBeenCalledWith('/settings/admin/llm/test', request)
  })

  it('applyToFleet POSTs node_ids to /settings/admin/llm/apply', async () => {
    mockPost.mockResolvedValue({ success: true, node_count: 2 })

    await useLlmConfigApi().applyToFleet(['a', 'b'])

    expect(mockPost).toHaveBeenCalledWith('/settings/admin/llm/apply', {
      node_ids: ['a', 'b'],
    })
  })

  it('applyToFleet sends node_ids: null when no nodes are provided', async () => {
    mockPost.mockResolvedValue({ success: true, node_count: 0 })

    await useLlmConfigApi().applyToFleet()

    expect(mockPost).toHaveBeenCalledWith('/settings/admin/llm/apply', {
      node_ids: null,
    })
  })
})
