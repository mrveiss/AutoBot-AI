// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * The `/duplicates` index fallback feeds the page's run state (#21418).
 *
 * When the live scan fails, the backend serves the duplicates the last indexing run stored, labelled
 * with that run's `partial`/`run` like every #21003 results route. The page's ONE run state (read by
 * `RunStateNotice`) takes the label off that body as it does off the stats and problems bodies; a
 * live result carries no label and changes nothing.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref, computed } from 'vue'
import { useAnalyticsDataFetchers } from '../useAnalyticsDataFetchers'

const fetchWithAuth = vi.fn()
vi.mock('@/utils/fetchWithAuth', () => ({ fetchWithAuth: (...a: unknown[]) => fetchWithAuth(...a) }))
vi.mock('@/config/AppConfig.js', () => ({
  default: { getServiceUrl: () => Promise.resolve('http://backend'), getApiUrl: () => Promise.resolve('http://backend/api') },
}))
vi.mock('@/utils/debugUtils', () => ({
  createLogger: () => ({ info: () => undefined, warn: () => undefined, error: () => undefined, debug: () => undefined }),
}))

const respond = (body: unknown) => ({ ok: true, status: 200, json: async () => body, text: async () => JSON.stringify(body) })
const HIT = { file1: 'a.py', file2: 'b.py', similarity: 91, lines: 6 }
const KILLED_RUN = {
  run_id: 'run-2',
  status: 'killed',
  partial: true,
  reason: 'killed by the hard timeout: run exceeded 1800s',
  started_at: '2026-11-15T10:00:00+00:00',
  finished_at: '2026-11-15T10:30:00+00:00',
  last_completed_at: '2026-11-14T10:30:00+00:00',
}

const fetchers = () =>
  useAnalyticsDataFetchers({
    rootPath: ref('/repo'),
    sourceIdParam: computed(() => 'source_id=s1'),
    sourceIdQuery: computed(() => ({ source_id: 's1' })),
    withSourceId: (url: string) => `${url}${url.includes('?') ? '&' : '?'}source_id=s1`,
    analyzing: ref(false),
    t: (key: string) => key,
    showToast: () => undefined,
    notify: () => undefined,
  })

beforeEach(() => {
  fetchWithAuth.mockReset()
})

describe('the duplicates index fallback and the run state (#21418)', () => {
  it('a fallback labelled partial sets the page run state to the interrupted run', async () => {
    fetchWithAuth.mockResolvedValue(
      respond({ status: 'success', duplicates: [HIT], total_count: 1, storage_type: 'chromadb_fallback', partial: true, run: KILLED_RUN }),
    )
    const f = fetchers()

    await f.getDuplicatesData()

    expect(f.duplicateAnalysis.value).toHaveLength(1)
    expect(f.runState.run.value?.status).toBe('killed')
    expect(f.runState.run.value?.partial).toBe(true)
  })

  it('a live result, which carries no run label, leaves the run state as it was', async () => {
    fetchWithAuth.mockResolvedValue(respond({ status: 'success', duplicates: [HIT], total_count: 1, storage_type: 'live_analysis' }))
    const f = fetchers()

    await f.getDuplicatesData()

    expect(f.duplicateAnalysis.value).toHaveLength(1)
    expect(f.runState.run.value).toBeNull()
  })
})
