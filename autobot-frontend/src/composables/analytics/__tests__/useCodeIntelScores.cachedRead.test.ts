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

// The live scan is a polled background task; its outcome is scripted here.
const liveScan = vi.hoisted(() => ({ ok: true }))
vi.mock('@/composables/useTaskLoader', async () => {
  const { ref } = await import('vue')
  return {
    useTaskLoader: (_url: string, extract: (r: Record<string, unknown>) => unknown) => {
      const data = ref<unknown>(null)
      const error = ref('')
      return {
        data,
        loading: ref(false),
        error,
        load: async () => {
          data.value = null
          error.value = liveScan.ok ? '' : 'scan failed'
          if (!liveScan.ok) return null
          data.value = extract({ status: 'success', security_score: 80, grade: 'B' })
          return data.value
        },
      }
    },
  }
})

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

  it('a no_data answer is still one plain GET', async () => {
    mockedFetch.mockResolvedValueOnce(jsonResponse({ status: 'no_data' }))
    const scores = makeScores()
    await scores.loadCachedSecurityScore()

    expect(mockedFetch).toHaveBeenCalledTimes(1)
    const [, init] = mockedFetch.mock.calls[0] as [string, RequestInit | undefined]
    expect((init?.method ?? 'GET').toUpperCase()).toBe('GET')
    expect(scores.securityScore.value).toBeNull()
  })

  it('a no_data answer shows no error', async () => {
    mockedFetch.mockResolvedValueOnce(jsonResponse({ status: 'no_data' }))
    const scores = makeScores()
    await scores.loadCachedSecurityScore()
    expect(scores.securityScoreError.value).toBe('')
  })

  it('a failed stored read is surfaced, not shown as the empty state', async () => {
    mockedFetch.mockResolvedValueOnce(
      new Response(JSON.stringify({ detail: 'unprocessable' }), {
        status: 422,
        headers: { 'Content-Type': 'application/json' },
      }),
    )
    const scores = makeScores()
    await scores.loadCachedSecurityScore()
    expect(scores.securityScoreError.value).not.toBe('')
    expect(scores.securityScoreError.value).not.toContain('analytics.codebase.errors')
    expect(scores.securityScore.value).toBeNull()
  })

  const failedRead = () =>
    new Response(JSON.stringify({ detail: 'unprocessable' }), {
      status: 422,
      headers: { 'Content-Type': 'application/json' },
    })

  it('a later successful live scan clears the stale cached-read error', async () => {
    liveScan.ok = true
    mockedFetch.mockResolvedValueOnce(failedRead())
    const scores = makeScores()
    await scores.loadCachedSecurityScore()
    // Control: the error was showing before the scan.
    expect(scores.securityScoreError.value).not.toBe('')

    await scores.loadSecurityScore()
    expect(scores.securityScore.value?.security_score).toBe(80)
    expect(scores.securityScoreError.value).toBe('')
  })

  it('a failed live scan keeps showing the cached-read error', async () => {
    liveScan.ok = false
    mockedFetch.mockResolvedValueOnce(failedRead())
    const scores = makeScores()
    await scores.loadCachedSecurityScore()
    await scores.loadSecurityScore()
    expect(scores.securityScoreError.value).toBe('scan failed')
  })

  it('a new successful cached read clears the earlier cached-read error', async () => {
    mockedFetch.mockResolvedValueOnce(failedRead())
    mockedFetch.mockResolvedValueOnce(
      jsonResponse({ status: 'success', security_score: 91, grade: 'A' }),
    )
    const scores = makeScores()
    await scores.loadCachedSecurityScore()
    expect(scores.securityScoreError.value).not.toBe('')
    await scores.loadCachedSecurityScore()
    expect(scores.securityScoreError.value).toBe('')
    expect(scores.securityScore.value?.security_score).toBe(91)
  })

  it('a no_data answer after a failed read stays silent', async () => {
    mockedFetch.mockResolvedValueOnce(failedRead())
    mockedFetch.mockResolvedValueOnce(jsonResponse({ status: 'no_data' }))
    const scores = makeScores()
    await scores.loadCachedSecurityScore()
    await scores.loadCachedSecurityScore()
    expect(scores.securityScoreError.value).toBe('')
  })
})
