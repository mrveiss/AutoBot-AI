// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
//
// #12502: streaming sentence extraction must return the EXACT consumed span so
// the caller's cursor never drifts over multi-paragraph replies, and the
// unpunctuated end-of-stream tail must always be flushed.

import { describe, it, expect } from 'vitest'
import { extractCompleteSentences } from '../ttsSentences'

const MIN = 20

/** Words (non-whitespace runs) — order-preserving, whitespace-agnostic. */
const words = (s: string): string[] => s.split(/\s+/).filter(Boolean)

/**
 * Replay the ChatInterface streaming watcher over `fullText`, revealed a chunk
 * at a time, using the EXACT consumed span to advance the cursor (#12502).
 * Returns everything TTS would speak during streaming plus the end-of-stream
 * remainder flush.
 */
function simulateStreaming(fullText: string, chunk: number) {
  let cursor = 0
  const spoken: string[] = []
  const reveal = (content: string) => {
    const newText = content.slice(cursor)
    const { sentences, consumed } = extractCompleteSentences(newText, MIN)
    for (const s of sentences) spoken.push(s)
    cursor += consumed
  }
  for (let end = chunk; end < fullText.length; end += chunk) {
    reveal(fullText.slice(0, end))
  }
  reveal(fullText) // final streamed chunk
  const remainder = fullText.slice(cursor).trim() // stream-end flush
  return { spoken, remainder, cursor }
}

describe('extractCompleteSentences — exact consumed span (#12502)', () => {
  it('reports consumed span that includes the full inter-sentence whitespace run', () => {
    // Two paragraphs joined by a blank line: the terminator whitespace run is
    // "\n\n" (2 chars) but the sentence text only carries one, so summing
    // sentence lengths under-advances by 1 per boundary — hence `consumed`.
    const text =
      'This is the very first paragraph line.\n\nThis is the second paragraph line. '
    const { sentences, consumed } = extractCompleteSentences(text, MIN)
    expect(sentences.length).toBe(2)
    const summed = sentences.reduce((n, s) => n + s.length, 0)
    // Proof of the drift bug: naive `+= s.length` != the real consumed span.
    expect(summed).not.toBe(consumed)
    // The consumed span exactly tiles the accepted region of the source.
    expect(consumed).toBe(text.trimEnd().length + 1) // through the trailing "\n... . " space
  })

  it('advances with no dropped or duplicated words over a multi-paragraph reply', () => {
    const fullText =
      'Here is the opening statement of the reply.\n\n' +
      'The second paragraph continues with more detail here.\n\n' +
      'A third and final paragraph wraps everything up. '
    const { spoken, remainder } = simulateStreaming(fullText, 7)
    // Every word spoken exactly once, in order, with none dropped/duplicated.
    const produced = words(spoken.join(' ') + ' ' + remainder)
    expect(produced).toEqual(words(fullText))
  })
})

describe('extractCompleteSentences — tail flush at stream end (#12502)', () => {
  it('leaves an unpunctuated list/code tail as the end-of-stream remainder', () => {
    // No terminal ". "/"! "/"? " on the final line — it can only reach TTS via
    // the remainder flush.
    const fullText =
      'Here is the summary of the available options below.\n\n' +
      '- first bullet option\n' +
      '- second bullet option\n' +
      '- third and final option'
    const { spoken, remainder } = simulateStreaming(fullText, 9)
    expect(remainder.length).toBeGreaterThan(0)
    expect(remainder).toContain('third and final option')
    // Combined stream + flush loses nothing.
    const produced = words(spoken.join(' ') + ' ' + remainder)
    expect(produced).toEqual(words(fullText))
  })

  it('flushes a short unpunctuated tail that never met the sentence threshold', () => {
    const fullText = 'ok' // below MIN, no terminator — pure tail
    const { spoken, remainder } = simulateStreaming(fullText, 4)
    expect(spoken).toEqual([])
    expect(remainder).toBe('ok')
  })
})
