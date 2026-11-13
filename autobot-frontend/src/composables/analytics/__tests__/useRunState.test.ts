// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * useRunState: the run field on a results body and the run-state route feed ONE state (#21003).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { nextTick, ref } from 'vue'
import { flushPromises } from '@vue/test-utils'

vi.mock('@/utils/fetchWithAuth', () => ({
  fetchWithAuth: vi.fn(),
}))

vi.mock('@/config/AppConfig.js', () => ({
  default: {
    getServiceUrl: vi.fn(async () => 'http://backend.test'),
  },
}))

import { fetchWithAuth } from '@/utils/fetchWithAuth'
import { useRunState, type CodebaseRunState } from '../useRunState'

const mockedFetch = vi.mocked(fetchWithAuth)

const KILLED: CodebaseRunState = {
  run_id: 'r2',
  status: 'killed',
  partial: true,
  reason: 'killed by the hard timeout: run exceeded 1800s',
  started_at: '2026-11-01T14:25:50+00:00',
  finished_at: '2026-11-01T14:54:53+00:00',
  last_completed_at: '2026-10-30T09:00:00+00:00',
}

const withSource = (url: string) => `${url}?source_id=autobot`

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } })
}

describe('useRunState (#21003)', () => {
  beforeEach(() => {
    mockedFetch.mockReset()
  })

  it('takes the run off a results body', () => {
    const state = useRunState(withSource, () => 'autobot')
    state.applyRunFields({ status: 'success', partial: true, run: KILLED })
    expect(state.run.value).toEqual(KILLED)
  })

  it('a body with run: null clears it (no run record -> no banner)', () => {
    const state = useRunState(withSource, () => 'autobot')
    state.applyRunFields({ run: KILLED })
    state.applyRunFields({ status: 'success', partial: false, run: null })
    expect(state.run.value).toBeNull()
  })

  it('a body without the field (an older backend) changes nothing', () => {
    const state = useRunState(withSource, () => 'autobot')
    state.applyRunFields({ run: KILLED })
    state.applyRunFields({ status: 'success' })
    expect(state.run.value).toEqual(KILLED)
  })

  it('loadRunState asks the run-state route for the selected source', async () => {
    mockedFetch.mockResolvedValueOnce(jsonResponse({ status: 'success', source_id: 'autobot', partial: true, run: KILLED }))
    const state = useRunState(withSource, () => 'autobot')
    await state.loadRunState()
    expect(mockedFetch.mock.calls[0][0]).toBe('http://backend.test/api/analytics/codebase/index/run-state?source_id=autobot')
    expect(state.run.value).toEqual(KILLED)
  })

  it('a source with no run record answers run: null', async () => {
    const state = useRunState(withSource, () => 'autobot')
    state.applyRunFields({ run: KILLED })
    mockedFetch.mockResolvedValueOnce(jsonResponse({ status: 'success', source_id: 'autobot', partial: false, run: null }))
    await state.loadRunState()
    expect(state.run.value).toBeNull()
  })

  it('with no source selected nothing is requested', async () => {
    const state = useRunState((url) => url, () => '')
    await state.loadRunState()
    expect(mockedFetch).not.toHaveBeenCalled()
    expect(state.run.value).toBeNull()
  })

  describe('source switch', () => {
    const KILLED_B = { ...KILLED, run_id: 'rb' }
    const scopedBy = (source: { value: string }) => (url: string) => `${url}?source_id=${source.value}`
    const bodyFor = (run: CodebaseRunState | null) => jsonResponse({ status: 'success', partial: !!run, run })

    it('A partial banner, switch to B with no record: no banner', async () => {
      const source = ref('a')
      const state = useRunState(scopedBy(source), () => source.value)
      state.applyRunFields({ run: KILLED })
      mockedFetch.mockResolvedValueOnce(bodyFor(null))
      source.value = 'b'
      await nextTick()
      await flushPromises()
      expect(state.run.value).toBeNull()
      expect(mockedFetch.mock.calls[0][0]).toContain('source_id=b')
    })

    it('a late response for A is dropped once B is selected', async () => {
      const source = ref('a')
      const state = useRunState(scopedBy(source), () => source.value)
      let release: (r: Response) => void = () => {}
      mockedFetch.mockImplementationOnce(() => new Promise<Response>((resolve) => { release = resolve }))
      const pending = state.loadRunState() // for A
      await flushPromises()
      mockedFetch.mockResolvedValueOnce(bodyFor(null)) // B has no record
      source.value = 'b'
      await nextTick()
      release(bodyFor(KILLED_B))
      await pending
      await flushPromises()
      expect(state.run.value).toBeNull()
    })

    it('a results body for the previous source is not applied', async () => {
      const source = ref('a')
      const state = useRunState(scopedBy(source), () => source.value)
      mockedFetch.mockResolvedValueOnce(bodyFor(null))
      source.value = 'b'
      await nextTick()
      await flushPromises()
      state.applyRunFields({ run: KILLED }, 'a')
      expect(state.run.value).toBeNull()
      state.applyRunFields({ run: KILLED }, 'b')
      expect(state.run.value).toEqual(KILLED)
    })

    it('a failed read after a switch leaves no banner from the previous source', async () => {
      const source = ref('a')
      const state = useRunState(scopedBy(source), () => source.value)
      state.applyRunFields({ run: KILLED })
      mockedFetch.mockResolvedValueOnce(new Response('{}', { status: 500 }))
      source.value = 'b'
      await nextTick()
      await flushPromises()
      expect(state.run.value).toBeNull()
    })
  })
})
