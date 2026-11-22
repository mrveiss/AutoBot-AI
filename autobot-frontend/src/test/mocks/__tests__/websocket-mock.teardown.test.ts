// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// #17638: MockWebSocket's simulated `open` must not outlive teardown.

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { MockWebSocket } from '../websocket-mock'

describe('MockWebSocket open timer (#17638)', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    MockWebSocket.clearInstances()
    MockWebSocket.mockImplementation()
  })
  afterEach(() => {
    MockWebSocket.restoreImplementation()
    MockWebSocket.clearInstances()
    vi.useRealTimers()
  })

  it('opens after the simulated delay when nothing tears it down (control)', () => {
    const ws = new MockWebSocket('ws://test')
    const onopen = vi.fn()
    ws.onopen = onopen
    vi.advanceTimersByTime(20)
    expect(onopen).toHaveBeenCalledTimes(1)
    expect(ws.readyState).toBe(MockWebSocket.OPEN)
  })

  it('never opens once the test environment restores WebSocket', () => {
    const ws = new MockWebSocket('ws://test')
    // The #17638 trace: onopen reads the global WebSocket that teardown deletes.
    const onopen = vi.fn(() => WebSocket.OPEN)
    ws.onopen = onopen
    MockWebSocket.restoreImplementation()
    expect(() => vi.advanceTimersByTime(20)).not.toThrow()
    expect(onopen).not.toHaveBeenCalled()
  })

  it('never opens after close(), and close() is still a spy', () => {
    const ws = new MockWebSocket('ws://test')
    const onopen = vi.fn()
    ws.onopen = onopen
    ws.close()
    vi.advanceTimersByTime(20)
    expect(onopen).not.toHaveBeenCalled()
    expect(ws.close).toHaveBeenCalledTimes(1)
    expect(ws.readyState).toBe(MockWebSocket.CLOSED)
  })

  it('clearInstances() cancels every pending open', () => {
    const a = new MockWebSocket('ws://a')
    const b = new MockWebSocket('ws://b')
    const opened = vi.fn()
    a.onopen = opened
    b.onopen = opened
    MockWebSocket.clearInstances()
    vi.advanceTimersByTime(20)
    expect(opened).not.toHaveBeenCalled()
  })
})
