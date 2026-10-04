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
   * The same sentences as exact raw spans of `text`, each INCLUDING its whole
   * trailing whitespace run, so the spans concatenate to `text.slice(0, consumed)`.
   * A speech shaper needs them: a newline in that run is what puts the next
   * sentence at the start of a line, where a code fence can open (#13102).
   */
  spans: string[]
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
  const spans: string[] = []
  const terminators = /(?<=[.!?])\s+/g
  let lastEnd = 0
  let match: RegExpExecArray | null
  while ((match = terminators.exec(text)) !== null) {
    const candidate = text.slice(lastEnd, match.index + 1)
    if (candidate.length >= minChars) {
      sentences.push(candidate)
      spans.push(text.slice(lastEnd, match.index + match[0].length))
      lastEnd = match.index + match[0].length
    }
  }
  return { sentences, spans, consumed: lastEnd }
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

const URL_RE = /\b(?:https?:\/\/|www\.)[^\s<>()]+[^\s<>().,;:!?'"]/gi
const CODE_EXT = 'py|pyi|ts|tsx|js|jsx|mjs|cjs|vue|json|ya?ml|toml|ini|cfg|md|sh|bash|rs|go|java|kt|c|h|cpp|hpp|cs|rb|php|css|scss|html|sql|lock|log|env'
// A token with 2+ slashes, a rooted/relative prefix, a code-file extension, or
// a Windows drive path (C:\Users\...).
// One bare slash ("and/or", "24/7") is prose and survives.
const PATH_RE = new RegExp(
  String.raw`(?<![\w/.-])(?:(?:~|\.{1,2})?\/(?:[\w.-]+\/)*[\w.-]*[\w-]|[\w.-]+(?:\/[\w.-]+)+\/[\w.-]*[\w-]|(?:[\w.-]+\/)*[\w-][\w.-]*\.(?:${CODE_EXT})|[A-Za-z]:\\(?:[\w.-]+\\)*[\w.-]*[\w-])(?![\w/\\])`,
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

interface OpenFence {
  char: string
  len: number
}

// A fence line per CommonMark: up to 3 spaces of indent, then 3+ backticks or
// tildes. A backtick fence's info string may not itself contain a backtick.
const FENCE_LINE_RE = /^[ \t]{0,3}(`{3,}|~{3,})(.*)$/
// A line that so far is only a 1-2 character marker run: it may become a
// fence once the next slice arrives, so it is held rather than shaped.
const PARTIAL_FENCE_RE = /^[ \t]{0,3}(?:`{1,2}|~{1,2})$/

/** Opens a fence? Returns the fence, or null for an ordinary line. */
function openingFence(line: string): OpenFence | null {
  const m = FENCE_LINE_RE.exec(line)
  if (!m || (m[1][0] === '`' && m[2].includes('`'))) return null
  return { char: m[1][0], len: m[1].length }
}

/** Closes `fence`? Same character, at least as long, nothing after it. */
function closesFence(line: string, fence: OpenFence): boolean {
  const m = FENCE_LINE_RE.exec(line)
  return !!m && m[1][0] === fence.char && m[1].length >= fence.len && m[2].trim() === ''
}

/**
 * Stateful speech shaper for one reply. `push()` takes successive streamed
 * slices and returns the speakable text. Fenced code blocks (``` or ~~~) are
 * dropped whole by CommonMark's rules -- a fence opens and closes only at the
 * start of a line, and closes only on the same character at least as long --
 * with fence state, line position and a partial marker carried across slices.
 */
export function createSpeechShaper(ph: SpeechPlaceholders) {
  let fence: OpenFence | null = null
  let atLineStart = true
  let held = ''

  const keepLine = (line: string, lineStart: boolean): boolean => {
    if (fence) {
      if (lineStart && closesFence(line, fence)) fence = null
      return false
    }
    const opened = lineStart ? openingFence(line) : null
    if (opened) fence = opened
    return !opened
  }

  return {
    push(slice: string): string {
      let text = held + slice
      const lastBreak = text.lastIndexOf('\n')
      const tailStart = lastBreak + 1
      const tailAtLineStart = lastBreak >= 0 || atLineStart
      held = tailAtLineStart && PARTIAL_FENCE_RE.test(text.slice(tailStart)) ? text.slice(tailStart) : ''
      if (held) text = text.slice(0, tailStart)
      const kept = text.split('\n').filter((line, i) => keepLine(line, i > 0 || atLineStart))
      atLineStart = held !== '' || text.endsWith('\n')
      return shapeProse(kept.join('\n'), ph).replace(/\s+/g, ' ').trim()
    },
    /** End of reply: a held partial marker is only backticks or tildes -- never spoken. */
    flush(): string {
      held = ''
      fence = null
      atLineStart = true
      return ''
    },
  }
}

/** Shape a complete (non-streamed) text for speech. */
export function shapeForSpeech(text: string, ph: SpeechPlaceholders): string {
  return createSpeechShaper(ph).push(text)
}
