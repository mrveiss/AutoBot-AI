// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * AutoBot - AI-Powered Automation Platform
 * Author: mrveiss
 *
 * ttsSentences.ts - streaming sentence extraction for sentence-level TTS (#1319).
 * Extracted from ChatInterface.vue so the cursor-advance logic is unit-testable
 * and returns the EXACT consumed span (including the inter-sentence whitespace
 * run) so the caller's streaming cursor never drifts over multi-paragraph
 * replies (#12502).
 */

export interface ExtractedSentences {
  /** Complete sentences (>= minChars) ready to dispatch to TTS. */
  sentences: string[]
  /**
   * Number of characters consumed from `text` — the end offset of the last
   * accepted sentence INCLUDING its trailing whitespace run. Callers must
   * advance their streaming cursor by exactly this amount. Advancing by the
   * summed sentence lengths instead omits the inter-sentence whitespace (the
   * sentence text excludes the full whitespace run) and drifts over
   * multi-paragraph replies, dropping or duplicating slices (#12502).
   */
  consumed: number
}

/**
 * Extract sentences terminated by ". ", "! ", or "? " from `text`. A trailing
 * fragment with no terminator (and any sub-`minChars` candidate) stays buffered
 * for the next call. Returns the accepted sentences plus the exact consumed span.
 */
export function extractCompleteSentences(
  text: string,
  minChars: number,
): ExtractedSentences {
  const sentences: string[] = []
  const terminators = /(?<=[.!?])\s+/g
  let lastEnd = 0
  let match: RegExpExecArray | null
  while ((match = terminators.exec(text)) !== null) {
    const candidate = text.slice(lastEnd, match.index + 1)
    if (candidate.length >= minChars) {
      sentences.push(candidate)
      lastEnd = match.index + match[0].length
    }
  }
  return { sentences, consumed: lastEnd }
}
