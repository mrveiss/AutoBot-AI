// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * Page-open reads of Codebase Analytics are plain GETs of stored results (#20491).
 *
 * The cached security route requires `source_id`; without it the page-open read answered 422.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/utils/fetchWithAuth', () => ({ fetchWithAuth: vi.fn() }))
vi.mock('@/config/AppConfig.js', () => ({
  default: { getServiceUrl: vi.fn(async () => 'http://backend.test') },
}))

import { fetchWithAuth } from '@/utils/fetchWithAuth'
import { useCodeIntelScores } from '../useCodeIntelScores'
import type { UseCodeIntelAnalysisDeps } from '../codeIntelTypes'

const mockedFetch = vi.mocked(fetchWithAuth)

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  })
}

function makeScores() {
  const deps = {
    rootPath: { value: '/repo' },
    withSourceId: (url: string) => `${url}?source_id=atlas`,
  } as unknown as UseCodeIntelAnalysisDeps
  return useCodeIntelScores(deps)
}

describe('cached security score read (#20491)', () => {
  beforeEach(() => mockedFetch.mockReset())

  it('sends the selected source and issues no write', async () => {
    mockedFetch.mockResolvedValueOnce(
      jsonResponse({ status: 'success', security_score: 91, grade: 'A' }),
    )
    const scores = makeScores()
    await scores.loadCachedSecurityScore()

    // Control: the mock was reached, so the assertions below are about a real call.
    expect(mockedFetch).toHaveBeenCalledTimes(1)
    const [url, init] = mockedFetch.mock.calls[0] as [string, RequestInit | undefined]
    expect(url).toBe(
      'http://backend.test/api/code-intelligence/security/score/cached?source_id=atlas',
    )
    expect((init?.method ?? 'GET').toUpperCase()).toBe('GET')
    expect(scores.securityScore.value?.security_score).toBe(91)
  })

  it('control: a start route would be caught by the method check', async () => {
    mockedFetch.mockResolvedValueOnce(jsonResponse({ status: 'no_data' }))
    await makeScores().loadCachedSecurityScore()
    const calls = mockedFetch.mock.calls.map((c) => String(c[0]))
    expect(calls.some((u) => u.includes('/security/score/analyze'))).toBe(false)
    expect(calls.some((u) => u.includes('/security/score/cached'))).toBe(true)
  })
})
