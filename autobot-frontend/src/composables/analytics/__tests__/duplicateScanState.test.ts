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
// A non-2xx. `useFetchEndpoint` throws on `!response.ok` (useFetchEndpoint.ts:249),
// so this lands in the fetcher's catch and reaches `onError` -- NOT `onSuccess`,
// which is why a 200 {"status":"error"} and a 404 are two different paths.
const reject = (status: number) => ({
  ok: false,
  status,
  json: async () => ({ detail: 'source does not resolve' }),
  text: async () => '{"detail":"source does not resolve"}',
})

describe('readDuplicatePayload (#17983)', () => {
  it.each([
    [{ status: 'success', duplicates: [] }, 'done', 0],
    [{ status: 'success', duplicates: [{ file1: 'a', file2: 'b', similarity: 90, lines: 4 }] }, 'done', 1],
    [{ status: 'partial', duplicates: [{ file1: 'a', file2: 'b', similarity: 90, lines: 4 }] }, 'done', 1],
    [ERROR_200, 'failed', 0],
    // #17983, measured against the live backend: a TIMEOUT carrying nothing.
    // `partial` + [] used to read as 'done' -> "no duplicates found", which is
    // the defect this module exists to stop, surviving in the one branch that
    // was not separated. With rows it IS a real (incomplete) result.
    [{ status: 'partial', duplicates: [], total_count: 0, storage_type: 'timeout' }, 'failed', 0],
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

describe('duplicates fetchers given an HTTP error (#17983)', () => {
  // The OTHER failure path. The endpoint answers 404 for a source it cannot
  // resolve (api/codebase_analytics/endpoints/duplicates.py), which throws
  // rather than returning a body -- so `onSuccess` never runs and, before
  // `onError` was wired, the state simply kept whatever it already held.
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
  })

  it('cached endpoint on 404: failed, not "not_scanned"', async () => {
    fetchWithAuth.mockResolvedValue(reject(404))
    const f = fetchers()
    await f.loadCachedDuplicates()
    expect(f.duplicateScanState.value).toBe('failed')
    expect(f.duplicateAnalysis.value).toEqual([])
  })

  it('live endpoint on 500: failed, and never "0 duplicates found"', async () => {
    fetchWithAuth.mockResolvedValue(reject(500))
    const f = fetchers()
    await f.getDuplicatesData()
    expect(f.duplicateScanState.value).toBe('failed')
    const keys = notify.mock.calls.map((c) => JSON.stringify(c))
    expect(keys.some((k) => k.includes('analytics.codebase.notify.duplicatesFound'))).toBe(false)
  })

  it('a 404 after a SUCCESSFUL scan clears the stale list instead of keeping it', async () => {
    // The worst shape of the bug: state stays `done` and the PREVIOUS source's
    // rows stay on screen under a scan that just failed. `not_scanned` at least
    // says "no scan has run"; a stale `done` asserts a result that is not this
    // source's. This is the assertion that fails if only the state is set and
    // the list is left alone.
    const hit = { file1: 'a.py', file2: 'b.py', similarity: 90, lines: 4 }
    fetchWithAuth.mockResolvedValue(respond({ status: 'success', duplicates: [hit] }))
    const f = fetchers()
    await f.loadCachedDuplicates()
    // CONTROL: the first scan really did populate, so the clear below is a
    // change of state and not a no-op on an already-empty list.
    expect(f.duplicateScanState.value).toBe('done')
    expect(f.duplicateAnalysis.value).toHaveLength(1)

    fetchWithAuth.mockResolvedValue(reject(404))
    await f.loadCachedDuplicates()
    expect(f.duplicateScanState.value).toBe('failed')
    expect(f.duplicateAnalysis.value).toEqual([])
  })
})

describe('the dupTask path clears stale rows too (#17983)', () => {
  // The third failure path. `failDuplicates` was wired into the two endpoint
  // fetchers and NOT into the background-task branch, which only set the state.
  // `DuplicatesSection` checks `duplicates.length > 0` BEFORE `scanState`, so a
  // populated list from an earlier scan shows those rows and hides the failure —
  // the same defect, surviving in the one path that was missed.
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
  })

  it('a successful scan then a failed background task leaves no rows behind', async () => {
    const hit = { file1: 'a.py', file2: 'b.py', similarity: 90, lines: 4 }
    fetchWithAuth.mockResolvedValue(respond({ status: 'success', duplicates: [hit] }))
    const f = fetchers()
    await f.loadCachedDuplicates()
    // CONTROL: the first scan really populated, so the clear below is a change.
    expect(f.duplicateScanState.value).toBe('done')
    expect(f.duplicateAnalysis.value).toHaveLength(1)

    // `loadDuplicates`, NOT `getDuplicatesData`: the branch under test is in
    // `loadDuplicates`, and the first version of this test called the other
    // function — where `duplicatesSilent`'s onError clears the rows first, so it
    // passed with the fix reverted and proved nothing. Mutation-checked.
    fetchWithAuth.mockRejectedValue(new Error('task start failed'))
    await f.loadDuplicates()
    expect(f.duplicateScanState.value).toBe('failed')
    expect(f.duplicateAnalysis.value).toEqual([])
  })
})
