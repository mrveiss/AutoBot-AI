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

// ─── Speech shaping (#13102) ─────────────────────────────────────────────
// Assistant replies carry markdown, URLs, file paths and fenced code; read
// aloud they are symbol soup. These transforms shape ONLY the spoken copy —
// callers keep the raw text for the transcript.

/** Localized words spoken in place of a URL or a file path. */
export interface SpeechPlaceholders {
  url: string
  path: string
}

const FENCE = '```'
const URL_RE = /\b(?:https?:\/\/|www\.)[^\s<>()]+[^\s<>().,;:!?'"]/gi
const CODE_EXT = 'py|pyi|ts|tsx|js|jsx|mjs|cjs|vue|json|ya?ml|toml|ini|cfg|md|sh|bash|rs|go|java|kt|c|h|cpp|hpp|cs|rb|php|css|scss|html|sql|lock|log|env'
// A token with 2+ slashes, a rooted/relative prefix, or a code-file extension.
// One bare slash ("and/or", "24/7") is prose and survives.
const PATH_RE = new RegExp(
  String.raw`(?<![\w/.-])(?:(?:~|\.{1,2})?\/(?:[\w.-]+\/)*[\w.-]*[\w-]|[\w.-]+(?:\/[\w.-]+)+\/[\w.-]*[\w-]|(?:[\w.-]+\/)*[\w-][\w.-]*\.(?:${CODE_EXT}))(?![\w/])`,
  'g',
)
// "Node.js"-style product names: capitalised word + .js — prose, not a file.
const PRODUCT_JS_RE = /^[A-Z][a-z]+\.js$/

/** Path-shaped but spoken as prose: "Node.js", a bare "/etc", a date, slash-joined words. */
function isProseToken(token: string): boolean {
  return (
    PRODUCT_JS_RE.test(token) ||
    /^\/\w*$/.test(token) ||
    /^[\d/.-]+$/.test(token) ||
    /^[A-Za-z]+(?:\/[A-Za-z]+)+$/.test(token) // "he/she/they", "TCP/IP/UDP"
  )
}

function shapeProse(text: string, ph: SpeechPlaceholders): string {
  return text
    .replace(/!?\[([^\]]*)\]\([^)]*\)/g, '$1') // links / images -> their text
    .replace(/`([^`]*)`/g, '$1') // inline code -> its contents
    .replace(/`+/g, '') // an unpaired backtick is never spoken
    .replace(URL_RE, ph.url)
    .replace(PATH_RE, (m) => (isProseToken(m) ? m : ph.path))
    .replace(/^[ \t]*#{1,6}[ \t]+/gm, '') // headings
    .replace(/^[ \t]*>[ \t]?/gm, '') // blockquotes
    .replace(/^[ \t]*(?:[-*+]|\d+[.)])[ \t]+/gm, '') // list markers
    .replace(/^[ \t]*[-*_]{3,}[ \t]*$/gm, '') // horizontal rules
    .replace(/(^|[^\w*_~])[*_~]+(?=\S)/g, '$1') // opening emphasis
    .replace(/(?<=\S)[*_~]+(?=[^\w*_~]|$)/g, '') // closing emphasis
    .replace(/([a-z])([.!?])([A-Z])/g, '$1$2 $3') // "now.Right" -> "now. Right"
}

/**
 * Stateful speech shaper for one reply. `push()` takes successive streamed
 * slices and returns the speakable text; fenced code blocks are dropped whole,
 * with fence state — and a trailing partial ``` marker — carried across slices.
 */
export function createSpeechShaper(ph: SpeechPlaceholders) {
  let inFence = false
  let held = ''

  const shapeSlice = (slice: string): string => {
    const parts = slice.split(FENCE)
    let out = ''
    parts.forEach((part, i) => {
      if (i > 0) inFence = !inFence
      if (!inFence) out += part
    })
    return shapeProse(out, ph).replace(/\s+/g, ' ').trim()
  }

  return {
    push(slice: string): string {
      const text = held + slice
      // Only a run at the start or after whitespace can begin a fence; a run
      // closing inline code (`ls`) is spoken now, not held.
      const tail = /(?:^|\s)(`{1,2})$/.exec(text)
      held = tail && !text.endsWith(FENCE) ? tail[1] : ''
      return shapeSlice(held ? text.slice(0, -held.length) : text)
    },
    /** End of reply: a held partial marker is only backticks — never spoken. */
    flush(): string {
      held = ''
      inFence = false
      return ''
    },
  }
}

/** Shape a complete (non-streamed) text for speech. */
export function shapeForSpeech(text: string, ph: SpeechPlaceholders): string {
  return createSpeechShaper(ph).push(text)
}
