// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
//
// Message HTML cache (#1312, #19118): one format per id+length, sanitised at the sink, oldest evicted first.
import { describe, it, expect, vi, beforeEach } from 'vitest'

const h = vi.hoisted(() => ({ format: vi.fn((c: string) => '<p>' + c + '</p>'), sanitize: vi.fn((h: string) => h) }))
vi.mock('@/utils/chatMessageFormat', () => ({ formatChatMessageHtml: h.format }))
vi.mock('@/utils/sanitize', () => ({ sanitizeChatHtml: h.sanitize }))

import { createMessageFormatter } from '../useChatMessageFormat'

beforeEach(() => { h.format.mockClear(); h.sanitize.mockClear() })

describe('createMessageFormatter', () => {
  it('formats once per message id and content length', () => {
    const f = createMessageFormatter()
    expect(f('abc', 'm1')).toBe('<p>abc</p>')
    f('abc', 'm1')
    expect(h.format).toHaveBeenCalledTimes(1)
    f('abcd', 'm1')
    expect(h.format).toHaveBeenCalledTimes(2)
  })

  it('sanitises the formatted HTML (every v-html reads this)', () => {
    createMessageFormatter()('x', 'm1')
    expect(h.sanitize).toHaveBeenCalledWith('<p>x</p>')
  })

  it('keys by content when there is no id', () => {
    const f = createMessageFormatter()
    f('same')
    f('same')
    expect(h.format).toHaveBeenCalledTimes(1)
  })

  it('evicts the oldest entry once the cache is full', () => {
    const f = createMessageFormatter(2)
    f('a', '1'); f('b', '2'); f('c', '3')
    h.format.mockClear()
    f('b', '2')
    expect(h.format).not.toHaveBeenCalled()
    f('a', '1')
    expect(h.format).toHaveBeenCalledTimes(1)
  })
})
