// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * #21463: `GET /api/code-intelligence/security/score/cached` requires `source_id` and answers 422
 * without it. With a scoper but no source selected, the read makes no request.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('@/utils/fetchWithAuth', () => ({ fetchWithAuth: vi.fn() }))
vi.mock('@/config/AppConfig.js', () => ({
  default: { getServiceUrl: vi.fn(async () => 'http://backend.test') },
}))

import { fetchWithAuth } from '@/utils/fetchWithAuth'
import { useCachedSecurityScore } from '../useCachedSecurityScore'

const mockedFetch = vi.mocked(fetchWithAuth)

describe('the cached security score read needs a source (#21463)', () => {
  beforeEach(() => mockedFetch.mockReset())

  it('with no source selected the scoper adds nothing and no request is sent', async () => {
    const score = useCachedSecurityScore({ withSourceId: (url) => url })
    await score.load()
    expect(mockedFetch).not.toHaveBeenCalled()
  })

  it('with a source selected the request carries it', async () => {
    mockedFetch.mockResolvedValue(new Response(JSON.stringify({ status: 'no_data' }), { status: 200 }))
    const score = useCachedSecurityScore({ withSourceId: (url) => `${url}?source_id=atlas` })
    await score.load()
    expect(mockedFetch).toHaveBeenCalledTimes(1)
    expect(String(mockedFetch.mock.calls[0][0])).toBe(
      'http://backend.test/api/code-intelligence/security/score/cached?source_id=atlas',
    )
  })
})
