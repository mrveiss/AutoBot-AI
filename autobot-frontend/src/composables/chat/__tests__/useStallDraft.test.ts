// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
import { describe, it, expect } from 'vitest'
import { MAX_STALL_DRAFTS, getStallDraft, setStallDraft, useStallDraft } from '../useStallDraft'

describe('stall draft store (#21793)', () => {
  it('keeps a draft by message id and forgets an empty one', () => {
    setStallDraft('a', 'hello')
    expect(getStallDraft('a')).toBe('hello')
    setStallDraft('a', '')
    expect(getStallDraft('a')).toBe('')
  })

  it('reads and writes through a computed bound to a message id', () => {
    const draft = useStallDraft(() => 'b')
    draft.value = 'typed'
    expect(getStallDraft('b')).toBe('typed')
    expect(draft.value).toBe('typed')
  })

  it('evicts the oldest draft past the bound, never the newest', () => {
    for (let i = 0; i <= MAX_STALL_DRAFTS; i++) setStallDraft(`bound-${i}`, `text ${i}`)
    expect(getStallDraft('bound-0')).toBe('')
    expect(getStallDraft(`bound-${MAX_STALL_DRAFTS}`)).toBe(`text ${MAX_STALL_DRAFTS}`)
  })
})
