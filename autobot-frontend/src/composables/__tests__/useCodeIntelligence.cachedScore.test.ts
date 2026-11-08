// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * useCodeIntelligence reads the cached security score through the canonical reader (#18907).
 *
 * The route requires `source_id`; the request must carry it, and the fields the old copy
 * exposed (`from_cache`, `completed_at`) stay reachable.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/utils/fetchWithAuth', () => ({ fetchWithAuth: vi.fn() }))
vi.mock('@/config/AppConfig.js', () => ({
  default: { getServiceUrl: vi.fn(async () => 'http://backend.test') },
}))

import { fetchWithAuth } from '@/utils/fetchWithAuth'
import { useCodeIntelligence } from '../useCodeIntelligence'

const mockedFetch = vi.mocked(fetchWithAuth)
const withSourceId = (url: string) => `${url}?source_id=atlas`

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  })
}

describe('useCodeIntelligence cached security score (#18907)', () => {
  beforeEach(() => mockedFetch.mockReset())

  it('sends source_id and keeps every payload field', async () => {
    mockedFetch.mockResolvedValueOnce(
      jsonResponse({
        status: 'success',
        security_score: 88,
        from_cache: true,
        completed_at: '2026-11-08T00:00:00Z',
      }),
    )
    const ci = useCodeIntelligence({ withSourceId })
    const result = await ci.getSecurityScoreCached()

    expect(mockedFetch).toHaveBeenCalledTimes(1)
    const [url] = mockedFetch.mock.calls[0] as [string]
    expect(url).toBe(
      'http://backend.test/api/code-intelligence/security/score/cached?source_id=atlas',
    )
    expect(result?.from_cache).toBe(true)
    expect(result?.completed_at).toBe('2026-11-08T00:00:00Z')
    expect(ci.securityScoreCached.value?.security_score).toBe(88)
  })

  it('without a source scoper no request is sent', async () => {
    const ci = useCodeIntelligence()
    expect(await ci.getSecurityScoreCached()).toBeNull()
    expect(mockedFetch).not.toHaveBeenCalled()
  })

  it('a failed read lands in errors and returns null', async () => {
    mockedFetch.mockResolvedValueOnce(new Response('{}', { status: 422 }))
    const ci = useCodeIntelligence({ withSourceId })
    expect(await ci.getSecurityScoreCached()).toBeNull()
    expect(ci.errors.value.length).toBe(1)
  })

  it('a no_data payload is returned and stored, and loading returns to false', async () => {
    mockedFetch.mockResolvedValueOnce(jsonResponse({ status: 'no_data' }))
    const ci = useCodeIntelligence({ withSourceId })
    const result = await ci.getSecurityScoreCached()

    expect(result?.status).toBe('no_data')
    expect(ci.securityScoreCached.value?.status).toBe('no_data')
    expect(ci.isLoading.value).toBe(false)
    expect(ci.errors.value).toEqual([])
  })

  it('an overlapping call aborts the first, which returns null instead of stale data', async () => {
    mockedFetch.mockImplementationOnce(
      (_url, init) =>
        new Promise((_resolve, reject) => {
          init?.signal?.addEventListener('abort', () =>
            reject(new DOMException('aborted', 'AbortError')),
          )
        }),
    )
    mockedFetch.mockResolvedValueOnce(jsonResponse({ status: 'success', security_score: 70 }))
    const ci = useCodeIntelligence({ withSourceId })
    const first = ci.getSecurityScoreCached()
    await vi.waitFor(() => expect(mockedFetch).toHaveBeenCalledTimes(1))
    const second = ci.getSecurityScoreCached()

    expect(await first).toBeNull()
    expect((await second)?.security_score).toBe(70)
    expect(ci.errors.value).toEqual([])
    expect(ci.isLoading.value).toBe(false)
  })
})
