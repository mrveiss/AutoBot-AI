// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// #21989: the approved-delete watch: re-sync schedule, expiry, and what each decided event does to the list.
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'

type Listener = (event: { event_type: string; payload?: Record<string, unknown> }) => void

const { unsubscribe, subscribe } = vi.hoisted(() => ({ unsubscribe: vi.fn(), subscribe: vi.fn() }))
let listener: Listener | null = null

vi.mock('@/services/LiveEventService', () => ({ default: { subscribe } }))

import { RESYNC_DELAYS_MS, WATCH_TTL_MS, watchApprovedDelete } from '../approvedDeleteWatch'

function emit(eventType: string, approvalId: string) {
  listener?.({ event_type: eventType, payload: { approval_id: approvalId } })
}

describe('watchApprovedDelete (#21989)', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    unsubscribe.mockReset()
    subscribe.mockReset()
    subscribe.mockImplementation((_channel: string, cb: Listener) => {
      listener = cb
      return unsubscribe
    })
  })

  afterEach(() => {
    // Expire any watch a test left behind so module state does not leak between tests.
    vi.advanceTimersByTime(WATCH_TTL_MS + 1)
    vi.useRealTimers()
    listener = null
  })

  it('subscribes once to the global channel for any number of watches', () => {
    watchApprovedDelete('a1', vi.fn(), vi.fn())
    watchApprovedDelete('a2', vi.fn(), vi.fn())
    expect(subscribe).toHaveBeenCalledTimes(1)
    expect(subscribe.mock.calls[0][0]).toBe('global')
  })

  it('an approved event drops the rows, then re-reads on the schedule until settled', async () => {
    const onApproved = vi.fn()
    const resync = vi.fn().mockResolvedValueOnce(false).mockResolvedValueOnce(true)
    watchApprovedDelete('a1', onApproved, resync)
    expect(onApproved).not.toHaveBeenCalled()
    emit('approval_approved', 'a1')
    expect(onApproved).toHaveBeenCalledTimes(1)
    expect(resync).not.toHaveBeenCalled()
    await vi.advanceTimersByTimeAsync(RESYNC_DELAYS_MS[0])
    expect(resync).toHaveBeenCalledTimes(1)
    await vi.advanceTimersByTimeAsync(RESYNC_DELAYS_MS[1])
    expect(resync).toHaveBeenCalledTimes(2)
    await vi.advanceTimersByTimeAsync(RESYNC_DELAYS_MS[2])
    expect(resync).toHaveBeenCalledTimes(2)
  })

  it('stops re-reading after the last scheduled delay when it never settles', async () => {
    const resync = vi.fn().mockResolvedValue(false)
    watchApprovedDelete('a1', vi.fn(), resync)
    emit('approval_approved', 'a1')
    await vi.advanceTimersByTimeAsync(RESYNC_DELAYS_MS.reduce((a, b) => a + b, 0) + WATCH_TTL_MS)
    expect(resync).toHaveBeenCalledTimes(RESYNC_DELAYS_MS.length)
  })

  it('a failing re-read counts as not settled and is retried', async () => {
    const resync = vi.fn().mockRejectedValueOnce(new Error('x')).mockResolvedValueOnce(true)
    watchApprovedDelete('a1', vi.fn(), resync)
    emit('approval_approved', 'a1')
    await vi.advanceTimersByTimeAsync(RESYNC_DELAYS_MS[0] + RESYNC_DELAYS_MS[1])
    expect(resync).toHaveBeenCalledTimes(2)
  })

  it.each([
    'approval_rejected',
    'approval_withdrawn',
    'approval_expired',
    'approval_revision_requested',
  ])('%s drops nothing and never re-reads', async (eventType) => {
    const onApproved = vi.fn()
    const resync = vi.fn().mockResolvedValue(true)
    watchApprovedDelete('a1', onApproved, resync)
    emit(eventType, 'a1')
    await vi.advanceTimersByTimeAsync(WATCH_TTL_MS)
    expect(onApproved).not.toHaveBeenCalled()
    expect(resync).not.toHaveBeenCalled()
    expect(unsubscribe).toHaveBeenCalledTimes(1)
  })

  it('ignores events for other approvals and non-decision events', () => {
    const onApproved = vi.fn()
    watchApprovedDelete('a1', onApproved, vi.fn())
    emit('approval_approved', 'other')
    emit('approval_requested', 'a1')
    listener?.({ event_type: 'approval_approved' })
    expect(onApproved).not.toHaveBeenCalled()
    expect(unsubscribe).not.toHaveBeenCalled()
  })

  it('an entry expires after WATCH_TTL_MS and a later approval does nothing', () => {
    const onApproved = vi.fn()
    watchApprovedDelete('a1', onApproved, vi.fn())
    vi.advanceTimersByTime(WATCH_TTL_MS - 1)
    expect(unsubscribe).not.toHaveBeenCalled()
    vi.advanceTimersByTime(1)
    expect(unsubscribe).toHaveBeenCalledTimes(1)
    emit('approval_approved', 'a1')
    expect(onApproved).not.toHaveBeenCalled()
  })

  it('watching the same approval again replaces the earlier watch', () => {
    const first = vi.fn()
    const second = vi.fn()
    watchApprovedDelete('a1', first, vi.fn())
    watchApprovedDelete('a1', second, vi.fn())
    emit('approval_approved', 'a1')
    expect(first).not.toHaveBeenCalled()
    expect(second).toHaveBeenCalledTimes(1)
  })
})
