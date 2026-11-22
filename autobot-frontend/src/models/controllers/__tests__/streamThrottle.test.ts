// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * A pending stream update is not replaced when another message id is scheduled before it flushed (#21793):
 * a stall question arriving before the preceding message's first update flushed used to overwrite that update,
 * and finalisation then deleted the empty message.
 */
import { afterEach, beforeEach, describe, it, expect, vi } from 'vitest'
import { StreamThrottle } from '../streamThrottle'

const update = (messageId: string, content: string, sessionId = 's1') => ({
  sessionId,
  messageId,
  content,
  type: 'response',
  metadata: {},
})

function makeThrottle() {
  const updateMessage = vi.fn()
  const throttle = new StreamThrottle({ updateMessage, setPreview: vi.fn(), isOpenChat: () => true })
  return { throttle, updateMessage }
}

describe('StreamThrottle buffering', () => {
  beforeEach(() => vi.useFakeTimers())
  afterEach(() => vi.useRealTimers())

  it('flushes both messages when a second id is scheduled before the first flushed', () => {
    const { throttle, updateMessage } = makeThrottle()
    throttle.schedule(update('m1', 'first reply'))
    throttle.schedule(update('stall', 'which way?'))
    vi.advanceTimersByTime(StreamThrottle.FLUSH_INTERVAL_MS)
    expect(updateMessage.mock.calls.map((c) => c[0]).sort()).toEqual(['m1', 'stall'])
  })

  it('keeps only the latest content of the same message id', () => {
    const { throttle, updateMessage } = makeThrottle()
    throttle.schedule(update('m1', 'a'))
    throttle.schedule(update('m1', 'ab'))
    throttle.flush()
    expect(updateMessage).toHaveBeenCalledTimes(1)
    expect(updateMessage.mock.calls[0][1].content).toBe('ab')
  })

  it('does not merge the same message id of two chats', () => {
    const { throttle, updateMessage } = makeThrottle()
    throttle.schedule(update('m1', 'one', 's1'))
    throttle.schedule(update('m1', 'two', 's2'))
    throttle.flush()
    expect(updateMessage).toHaveBeenCalledTimes(2)
  })

  it('finish flushes what is still buffered', () => {
    const { throttle, updateMessage } = makeThrottle()
    throttle.schedule(update('m1', 'first reply'))
    throttle.schedule(update('stall', 'which way?'))
    throttle.finish(false)
    expect(updateMessage).toHaveBeenCalledTimes(2)
  })
})
