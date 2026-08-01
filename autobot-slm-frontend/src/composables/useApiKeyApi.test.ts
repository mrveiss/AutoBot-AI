// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * #12420 Phase 2 (batch 2) — proves the API-key composable is migrated onto the
 * canonical `slmApiClient`: every method routes through the shared client with
 * endpoints relative to the API base (base URL + bearer token injected by the
 * client) and returns the parsed JSON body directly (no axios `.data`). These
 * are non-auth endpoints, so 401 session handling is the client's centralised
 * concern — the composable no longer owns an axios interceptor.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'

const mockGet = vi.fn()
const mockPost = vi.fn()
const mockPatch = vi.fn()
const mockDelete = vi.fn()

vi.mock('@/utils/ApiClient', () => ({
  default: {
    get: (...args: unknown[]) => mockGet(...args),
    post: (...args: unknown[]) => mockPost(...args),
    patch: (...args: unknown[]) => mockPatch(...args),
    delete: (...args: unknown[]) => mockDelete(...args),
  },
}))

import { useApiKeyApi } from './useApiKeyApi'

describe('useApiKeyApi — migrated onto slmApiClient (#12420 Phase 2)', () => {
  beforeEach(() => {
    mockGet.mockReset()
    mockPost.mockReset()
    mockPatch.mockReset()
    mockDelete.mockReset()
  })

  it('listKeys GETs /api-keys and returns the parsed body directly', async () => {
    const body = { keys: [], total: 0 }
    mockGet.mockResolvedValue(body)

    const result = await useApiKeyApi().listKeys()

    expect(mockGet).toHaveBeenCalledWith('/api-keys')
    expect(result).toEqual(body)
  })

  it('createKey POSTs the payload to /api-keys', async () => {
    const payload = { name: 'ci', scopes: ['read'] }
    mockPost.mockResolvedValue({ id: '1', key: 'k' })

    await useApiKeyApi().createKey(payload)

    expect(mockPost).toHaveBeenCalledWith('/api-keys', payload)
  })

  it('getKey GETs /api-keys/:id', async () => {
    mockGet.mockResolvedValue({ id: 'abc' })

    await useApiKeyApi().getKey('abc')

    expect(mockGet).toHaveBeenCalledWith('/api-keys/abc')
  })

  it('updateKey PATCHes /api-keys/:id with the payload', async () => {
    mockPatch.mockResolvedValue({ id: 'abc', name: 'new' })

    await useApiKeyApi().updateKey('abc', { name: 'new' })

    expect(mockPatch).toHaveBeenCalledWith('/api-keys/abc', { name: 'new' })
  })

  it('revokeKey DELETEs /api-keys/:id', async () => {
    mockDelete.mockResolvedValue({})

    await useApiKeyApi().revokeKey('abc')

    expect(mockDelete).toHaveBeenCalledWith('/api-keys/abc')
  })

  // The endpoint returns APIScopesResponse — `{ scopes: { ... } }` — not the
  // bare map (autobot-slm-backend/api/api_keys.py:118-121). The composable used
  // to type the response as the bare map and hand the envelope straight to the
  // scope picker, which then rendered one bogus entry keyed `scopes`.
  it('getScopes unwraps the APIScopesResponse envelope into a bare scope map', async () => {
    mockGet.mockResolvedValue({
      scopes: { 'chat:use': 'Send and receive chat messages' },
    })

    const result = await useApiKeyApi().getScopes()

    expect(mockGet).toHaveBeenCalledWith('/api-keys/scopes')
    expect(result).toEqual({ 'chat:use': 'Send and receive chat messages' })
  })

  it('getScopes yields an empty map when the envelope carries no scopes', async () => {
    mockGet.mockResolvedValue({})

    expect(await useApiKeyApi().getScopes()).toEqual({})
  })
})
