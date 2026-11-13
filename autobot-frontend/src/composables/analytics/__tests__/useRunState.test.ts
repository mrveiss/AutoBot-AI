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
import { endedRunOutcome, useRunState, type CodebaseRunState } from '../useRunState'

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

  describe('a stale `running` snapshot (the requests are not ordered)', () => {
    const RUNNING = { ...KILLED, status: 'running', reason: '', finished_at: '' }

    it('does not replace the terminal state of the same run', () => {
      const state = useRunState(withSource, () => 'autobot')
      state.applyRunFields({ run: KILLED })
      state.applyRunFields({ status: 'success', partial: true, run: RUNNING }) // read before the kill, arrived after
      expect(state.run.value).toEqual(KILLED)
    })

    it('control: `running` of another run, and `running` first, are applied', () => {
      const state = useRunState(withSource, () => 'autobot')
      state.applyRunFields({ run: RUNNING })
      expect(state.run.value?.status).toBe('running')
      state.applyRunFields({ run: KILLED })
      expect(state.run.value).toEqual(KILLED)
      state.applyRunFields({ run: { ...RUNNING, run_id: 'r3' } }) // a new run started
      expect(state.run.value?.run_id).toBe('r3')
    })
  })

  describe('a failed read', () => {
    const failing = () => new Response('{}', { status: 503 })

    it('is exposed, keeps what was known, and is cleared by the next answer', async () => {
      const state = useRunState(withSource, () => 'autobot')
      state.applyRunFields({ run: KILLED })
      mockedFetch.mockResolvedValueOnce(failing())
      await state.loadRunState()
      expect(state.readFailed.value).toBe(true)
      expect(state.run.value).toEqual(KILLED) // a failure is not "no run record"
      mockedFetch.mockResolvedValueOnce(jsonResponse({ status: 'success', partial: true, run: KILLED }))
      await state.loadRunState() // the retry
      expect(state.readFailed.value).toBe(false)
    })

    it('differs from a read that answered "no run record"', async () => {
      const state = useRunState(withSource, () => 'autobot')
      mockedFetch.mockResolvedValueOnce(jsonResponse({ status: 'success', partial: false, run: null }))
      await state.loadRunState()
      expect([state.run.value, state.readFailed.value]).toEqual([null, false])
      mockedFetch.mockResolvedValueOnce(failing())
      await state.loadRunState()
      expect([state.run.value, state.readFailed.value]).toEqual([null, true])
    })

    it('a results body naming a run clears it; one with run: null (a label that may itself be unread) does not', async () => {
      const state = useRunState(withSource, () => 'autobot')
      mockedFetch.mockResolvedValueOnce(failing())
      await state.loadRunState()
      state.applyRunFields({ status: 'success', partial: false, run: null })
      expect(state.readFailed.value).toBe(true)
      state.applyRunFields({ status: 'success', partial: true, run: KILLED })
      expect(state.readFailed.value).toBe(false)
    })
  })

  describe('endedRunOutcome: how a job that left the task slot ended', () => {
    const of = (over: Partial<CodebaseRunState>) => ({ ...KILLED, ...over })

    it('reads completed, cancelled and the failures off the record of that job', () => {
      expect(endedRunOutcome(of({ status: 'completed', reason: '' }), 'r2')).toEqual({ status: 'completed' })
      expect(endedRunOutcome(of({ status: 'cancelled' }), 'r2')).toEqual({ status: 'cancelled' })
      expect(endedRunOutcome(KILLED, 'r2')).toEqual({ status: 'failed', error: KILLED.reason })
      expect(endedRunOutcome(of({ status: 'abandoned', reason: '' }), null)).toEqual({ status: 'failed', error: 'abandoned' })
    })

    it('says nothing for no record, a run still going, or another run than the job', () => {
      expect(endedRunOutcome(null, 'r2')).toBeNull()
      expect(endedRunOutcome(of({ status: 'running' }), 'r2')).toBeNull()
      expect(endedRunOutcome(of({ status: 'completed' }), 'other')).toBeNull()
    })

    it('with no task id, a record still naming the run that was newest when the wait began says nothing', () => {
      const done = of({ status: 'completed', reason: '' })
      expect(endedRunOutcome(done, null, 'r2')).toBeNull() // the queued request never ran
      expect(endedRunOutcome(done, null, 'earlier')).toEqual({ status: 'completed' }) // a newer run: the request's own
      expect(endedRunOutcome(done, null)).toEqual({ status: 'completed' }) // nothing was known when the wait began
      expect(endedRunOutcome(done, 'r2', 'r2')).toEqual({ status: 'completed' }) // a seen task id is matched by id alone
    })
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
      expect(state.readFailed.value).toBe(true) // ... and the page can say the new source's state is unknown
    })
  })
})
