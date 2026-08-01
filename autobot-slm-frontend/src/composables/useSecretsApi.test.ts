// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * #12420 Phase 2 (batch 2) — proves the secrets composable routes every method
 * through the canonical `slmApiClient` with endpoints relative to the API base,
 * returns parsed JSON directly, and URL-encodes the secret key path segment.
 * Non-auth endpoints → 401 session handling is the client's concern.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'

const mockGet = vi.fn()
const mockPost = vi.fn()
const mockPut = vi.fn()
const mockDelete = vi.fn()

vi.mock('@/utils/ApiClient', () => ({
  default: {
    get: (...args: unknown[]) => mockGet(...args),
    post: (...args: unknown[]) => mockPost(...args),
    put: (...args: unknown[]) => mockPut(...args),
    delete: (...args: unknown[]) => mockDelete(...args),
  },
}))

import { useSecretsApi } from './useSecretsApi'

describe('useSecretsApi — migrated onto slmApiClient (#12420 Phase 2)', () => {
  beforeEach(() => {
    mockGet.mockReset()
    mockPost.mockReset()
    mockPut.mockReset()
    mockDelete.mockReset()
  })

  it('listSecrets GETs /secrets and returns the parsed body', async () => {
    mockGet.mockResolvedValue([{ id: 1, key: 'A' }])

    const result = await useSecretsApi().listSecrets()

    expect(mockGet).toHaveBeenCalledWith('/secrets')
    expect(result).toEqual([{ id: 1, key: 'A' }])
  })

  it('createSecret POSTs the payload to /secrets', async () => {
    const payload = { key: 'HF_TOKEN', value: 'x', category: 'system' }
    mockPost.mockResolvedValue({ id: 1 })

    await useSecretsApi().createSecret(payload)

    expect(mockPost).toHaveBeenCalledWith('/secrets', payload)
  })

  it('updateSecret PUTs to the URL-encoded key path', async () => {
    mockPut.mockResolvedValue({ id: 1 })

    await useSecretsApi().updateSecret('a b/c', { value: 'v' })

    expect(mockPut).toHaveBeenCalledWith('/secrets/a%20b%2Fc', { value: 'v' })
  })

  it('deleteSecret DELETEs the URL-encoded key path', async () => {
    mockDelete.mockResolvedValue({})

    await useSecretsApi().deleteSecret('a b/c')

    expect(mockDelete).toHaveBeenCalledWith('/secrets/a%20b%2Fc')
  })

  it('getDependentRolesMapping GETs /secrets/dependent-roles', async () => {
    mockGet.mockResolvedValue({ mapping: {} })

    await useSecretsApi().getDependentRolesMapping()

    expect(mockGet).toHaveBeenCalledWith('/secrets/dependent-roles')
  })

  it('applySecret POSTs the key to /secrets/apply', async () => {
    mockPost.mockResolvedValue({ success: true, key: 'A' })

    await useSecretsApi().applySecret('A')

    expect(mockPost).toHaveBeenCalledWith('/secrets/apply', { key: 'A' })
  })
})
