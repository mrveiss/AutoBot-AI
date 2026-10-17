// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * Opening-chunk fast start (#13103): the first chunk of a reply goes to TTS at
 * a clause or word boundary, everything after it keeps the terminated-sentence
 * rule, and the cursor advances by exactly the consumed span.
 */
import { describe, it, expect } from 'vitest'
import {
  createTtsStream,
  extractOpeningChunk,
  MIN_TTS_SENTENCE_CHARS,
  OPENING_CLAUSE_MIN_CHARS,
  OPENING_WORD_MIN_CHARS,
} from '../ttsSentences'

/** Feed `full` in `step`-char deltas the way ChatInterface's watcher does. */
function stream(full: string, step: number, opened = false) {
  const tts = createTtsStream(opened)
  const spoken: string[] = []
  let cursor = 0
  for (let end = step; end < full.length + step; end += step) {
    const { spans, consumed } = tts.next(full.slice(0, Math.min(end, full.length)).slice(cursor))
    spoken.push(...spans)
    cursor += consumed
  }
  return { spoken, remainder: full.slice(cursor) }
}

describe('extractOpeningChunk (#13103)', () => {
  it('releases the opening at a clause boundary below the standard bar', () => {
    const text = 'Looking at your logs, the failure starts'
    expect(text.indexOf(',') + 1).toBeGreaterThanOrEqual(OPENING_CLAUSE_MIN_CHARS)
    expect(extractOpeningChunk(text)).toEqual({ spans: ['Looking at your logs, '], consumed: 22 })
  })

  it('skips a clause boundary that comes too early', () => {
    expect(extractOpeningChunk('Well, that is')).toBeNull()
  })

  it('falls back to a word boundary for a long opening with no early pause', () => {
    const text = 'This opening sentence runs on for quite a while without any pause in it'
    expect(text.length).toBeGreaterThanOrEqual(OPENING_WORD_MIN_CHARS)
    const chunk = extractOpeningChunk(text)!
    expect(chunk.spans[0]).toBe('This opening sentence runs on for quite a while without any pause in ')
    expect(chunk.consumed).toBe(chunk.spans[0].length)
  })

  it('never cuts the opening inside a markdown link', () => {
    // The comma and every word gap sit inside the still-open link text.
    expect(extractOpeningChunk('[see the docs for the parser, especially the long section on')).toBeNull()
    // Once the link has closed, a later gap is a fair cut.
    expect(extractOpeningChunk('[the docs](http://x.y/z) explain the parser in a long section on')!.spans[0]).toBe(
      '[the docs](http://x.y/z) explain the parser in a long section ',
    )
  })

  it('waits while the opening is short and has no clause boundary', () => {
    expect(extractOpeningChunk('Short opening with no pause')).toBeNull()
  })

  it('stays out of the way once any sentence has terminated', () => {
    // "Hi there." is shorter than the standard bar, so it is HELD for merging;
    // an early opening must not jump ahead of it.
    expect('Hi there.'.length).toBeLessThan(MIN_TTS_SENTENCE_CHARS)
    expect(extractOpeningChunk('Hi there. And then, after a long while it goes on')).toBeNull()
  })
})

describe('createTtsStream (#13103)', () => {
  it('speaks the opening early, then only terminated sentences', () => {
    const tts = createTtsStream()
    expect(tts.next('Looking at your logs, the failure')).toEqual({ spans: ['Looking at your logs, '], consumed: 22 })
    // After the opening, a clause boundary alone releases nothing.
    expect(tts.next('the failure starts in the parser, then')).toEqual({ spans: [], consumed: 0 })
    expect(tts.next('the failure starts in the parser. Then')).toEqual({
      spans: ['the failure starts in the parser. '],
      consumed: 34,
    })
  })

  it('gives no fast start to a reply already under way', () => {
    const tts = createTtsStream(true)
    expect(tts.next('Looking at your logs, the failure')).toEqual({ spans: [], consumed: 0 })
  })

  it('treats a standard sentence as the opening when one arrives first', () => {
    const tts = createTtsStream()
    expect(tts.next('The build failed in the parser. Next')).toEqual({
      spans: ['The build failed in the parser. '],
      consumed: 32,
    })
    expect(tts.next('Next, we look at the tokenizer')).toEqual({ spans: [], consumed: 0 })
  })

  it.each([1, 3, 7, 50])('advances the cursor by the exact consumed span — no drift (step %i)', (step) => {
    const full =
      'Looking at your logs, the failure starts in the parser. It reads a stray token.\n\nThe fix is small: skip it.'
    const { spoken, remainder } = stream(full, step)

    expect(spoken.join('') + remainder).toBe(full)
    expect(spoken.length).toBeGreaterThan(0)
  })
})
