// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * A failed duplicate scan is never reported as "0 duplicates" (#17983, the
 * frontend half of #17982). The backend answers HTTP 200 with
 * {"status":"error"} when the scan did not run; every path that fills the
 * duplicates list must read that as a failure.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref, computed } from 'vue'
import { readDuplicatePayload } from '../duplicatePayload'
import { useAnalyticsDataFetchers } from '../useAnalyticsDataFetchers'

const fetchWithAuth = vi.fn()
vi.mock('@/utils/fetchWithAuth', () => ({ fetchWithAuth: (...a: unknown[]) => fetchWithAuth(...a) }))
vi.mock('@/config/AppConfig.js', () => ({
  default: { getServiceUrl: vi.fn().mockResolvedValue('http://backend'), getApiUrl: vi.fn().mockResolvedValue('http://backend/api') },
}))
vi.mock('@/utils/debugUtils', () => ({
  createLogger: () => ({ info: vi.fn(), warn: vi.fn(), error: vi.fn(), debug: vi.fn() }),
}))

const ERROR_200 = { status: 'error', message: 'source does not resolve to a code source; nothing scanned' }
const respond = (body: unknown) => ({ ok: true, status: 200, json: async () => body, text: async () => JSON.stringify(body) })

describe('readDuplicatePayload (#17983)', () => {
  it.each([
    [{ status: 'success', duplicates: [] }, 'done', 0],
    [{ status: 'success', duplicates: [{ file1: 'a', file2: 'b', similarity: 90, lines: 4 }] }, 'done', 1],
    [{ status: 'partial', duplicates: [{ file1: 'a', file2: 'b', similarity: 90, lines: 4 }] }, 'done', 1],
    [ERROR_200, 'failed', 0],
    [{ status: 'no_data' }, 'not_scanned', 0],
    [{ duplicates: [] }, 'not_scanned', 0],
    [null, 'not_scanned', 0],
  ])('%j -> %s', (raw, state, count) => {
    const reading = readDuplicatePayload(raw)
    expect(reading.state).toBe(state)
    expect(reading.duplicates).toHaveLength(count)
  })
})

describe('duplicates fetchers given a 200 {"status":"error"} (#17983)', () => {
  const notify = vi.fn()
  const fetchers = () =>
    useAnalyticsDataFetchers({
      rootPath: ref('/repo'),
      sourceIdQuery: computed(() => ''),
      withSourceId: (url: string) => url,
      t: (key: string) => key,
      showToast: vi.fn(),
      notify,
    } as unknown as Parameters<typeof useAnalyticsDataFetchers>[0])

  beforeEach(() => {
    fetchWithAuth.mockReset()
    notify.mockReset()
    fetchWithAuth.mockResolvedValue(respond(ERROR_200))
  })

  it('cached endpoint: the scan state is failed, not an empty result', async () => {
    const f = fetchers()
    await f.loadCachedDuplicates()
    expect(f.duplicateScanState.value).toBe('failed')
    expect(f.duplicateAnalysis.value).toEqual([])
  })

  it('live endpoint: reports the failure, never "0 duplicates found"', async () => {
    const f = fetchers()
    await f.getDuplicatesData()
    expect(f.duplicateScanState.value).toBe('failed')
    const keys = notify.mock.calls.map((c) => JSON.stringify(c))
    expect(keys.some((k) => k.includes('analytics.codebase.notify.duplicatesFound'))).toBe(false)
    // Contrast: the notify path did run, and it reported the failure.
    expect(keys.some((k) => k.includes('analytics.codebase.notify.duplicatesFailed'))).toBe(true)
  })

  it('a real empty result is still "done", so "none found" stays possible', async () => {
    fetchWithAuth.mockResolvedValue(respond({ status: 'success', duplicates: [] }))
    const f = fetchers()
    await f.loadCachedDuplicates()
    expect(f.duplicateScanState.value).toBe('done')
  })
})
