// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * useSourceRegistry module-API Tests (#12363)
 *
 * Verifies the getBackendUrl-prefix removal for the module-level registry
 * helpers: paths are now relative (base URL resolved by apiClient) and the
 * POST/PUT branching in saveCodeSource is preserved.
 */

import { describe, it, expect, beforeEach, vi } from 'vitest'

vi.mock('@/utils/ApiClient', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
  },
}))

import apiClient from '@/utils/ApiClient'
import {
  fetchSourceSecrets,
  shareCodeSource,
  saveCodeSource,
} from '../useSourceRegistry'

describe('useSourceRegistry module API', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('fetchSourceSecrets calls the relative /api/secrets endpoint and unwraps secrets', async () => {
    vi.mocked(apiClient.get).mockResolvedValue({ secrets: [{ id: '1', name: 'k', type: 't', scope: 's' }] })

    const result = await fetchSourceSecrets()

    expect(apiClient.get).toHaveBeenCalledWith('/api/secrets')
    expect(result).toEqual([{ id: '1', name: 'k', type: 't', scope: 's' }])
  })

  it('fetchSourceSecrets returns [] when the payload has no secrets', async () => {
    vi.mocked(apiClient.get).mockResolvedValue({})
    expect(await fetchSourceSecrets()).toEqual([])
  })

  it('shareCodeSource POSTs to the relative share endpoint', async () => {
    vi.mocked(apiClient.post).mockResolvedValue({ id: 's1' })
    const payload = { access: 'shared' as const, user_ids: ['u1'] }

    await shareCodeSource('s1', payload)

    expect(apiClient.post).toHaveBeenCalledWith(
      '/api/analytics/codebase/sources/s1/share',
      payload,
    )
  })

  it('saveCodeSource POSTs to a relative path when creating (no id)', async () => {
    vi.mocked(apiClient.post).mockResolvedValue({ id: 'new' })
    const payload = {
      name: 'n', source_type: 'github' as const, repo: 'r', branch: 'main',
      access: 'private' as const, credential_id: null,
    }

    await saveCodeSource(payload)

    expect(apiClient.post).toHaveBeenCalledWith('/api/analytics/codebase/sources', payload)
    expect(apiClient.put).not.toHaveBeenCalled()
  })

  it('saveCodeSource PUTs to a relative id-scoped path when updating', async () => {
    vi.mocked(apiClient.put).mockResolvedValue({ id: 'x' })
    const payload = {
      name: 'n', source_type: 'local' as const, repo: 'r', branch: 'main',
      access: 'public' as const, credential_id: 'c1',
    }

    await saveCodeSource(payload, 'x')

    expect(apiClient.put).toHaveBeenCalledWith('/api/analytics/codebase/sources/x', payload)
    expect(apiClient.post).not.toHaveBeenCalled()
  })
})
