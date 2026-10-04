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
// A line start whose kind is not yet known: only indentation, a lone list
// marker, or a 1-2 character fence run. It may become a fence, indented code
// or a list item once the next slice arrives, so it is held, not classified.
const UNDECIDED_LINE_RE = /^[ \t]*(?:[-*+]|\d+[.)]?|`{1,2}|~{1,2})?$/

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

const INDENTED_RE = /^(?: {4}| {0,3}\t)/
const LIST_ITEM_RE = /^[ \t]*(?:[-*+]|\d+[.)])[ \t]/

/**
 * Indented code blocks (#17953), conservatively: a run of lines indented 4+
 * spaces (or a tab) that follows a blank line and is not list content. An
 * indented line straight after prose continues the paragraph, and indented
 * lines under a list item are nested list content -- both stay spoken.
 */
function createIndentedCodeTracker() {
  let prevBlank = true
  let inList = false
  let inCode = false
  return {
    inCode: () => inCode,
    /** Records a complete line start; returns whether it is speakable as far as indented code goes. */
    recordLine(line: string, eligible: boolean): boolean {
      const blank = line.trim() === ''
      const indented = INDENTED_RE.test(line)
      if (inCode && !blank && !indented) inCode = false
      if (!inCode && eligible && prevBlank && indented && !blank && !inList) inCode = true
      if (!blank) inList = LIST_ITEM_RE.test(line) || (inList && indented)
      prevBlank = blank
      return !inCode
    },
    reset() {
      prevBlank = true
      inList = false
      inCode = false
    },
  }
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
  const indentedCode = createIndentedCodeTracker()

  const keepLine = (line: string, lineStart: boolean): boolean => {
    if (!lineStart) return !fence && !indentedCode.inCode()
    if (fence) {
      if (closesFence(line, fence)) fence = null
      indentedCode.recordLine(line, false)
      return false
    }
    const opened = indentedCode.inCode() ? null : openingFence(line)
    if (opened) fence = opened
    return indentedCode.recordLine(line, !opened) && !opened
  }

  return {
    push(slice: string): string {
      const text = held + slice
      const tailStart = text.lastIndexOf('\n') + 1
      const tail = text.slice(tailStart)
      // An undecided line start is held whole -- never recorded twice, never
      // mistaken for a blank line just because a slice ended after a newline.
      const holdTail = (tailStart > 0 || atLineStart) && UNDECIDED_LINE_RE.test(tail)
      held = holdTail ? tail : ''
      const body = holdTail ? text.slice(0, tailStart) : text
      const lines = body === '' ? [] : body.split('\n')
      if (body.endsWith('\n')) lines.pop()
      const kept = lines.filter((line, i) => keepLine(line, i > 0 || atLineStart))
      atLineStart = holdTail || body.endsWith('\n')
      return shapeProse(kept.join('\n'), ph).replace(/\s+/g, ' ').trim()
    },
    /** End of reply: a held undecided line start is markup or indent -- never spoken. */
    flush(): string {
      held = ''
      fence = null
      atLineStart = true
      indentedCode.reset()
      return ''
    },
  }
}

/** Shape a complete (non-streamed) text for speech. */
export function shapeForSpeech(text: string, ph: SpeechPlaceholders): string {
  return createSpeechShaper(ph).push(text)
}

// ─── Opening-chunk fast start (#13103) ───────────────────────────────────

/**
 * Minimum chars a terminated sentence needs before it is dispatched (#1485).
 * Short fragments like "Hello there! " (13 chars) sound choppy spoken alone, so
 * they wait to merge with the next sentence or flush as the remainder.
 */
export const MIN_TTS_SENTENCE_CHARS = 20
/**
 * The opening chunk of a reply may go out at a clause boundary (`,` `;` `:`
 * `—` `–`) once it is this long. MODEL-SPECIFIC: too short an opening renders in
 * a different timbre on some TTS models, so this is set by a listening test
 * against our TTS worker (#13103), not by a unit test.
 */
export const OPENING_CLAUSE_MIN_CHARS = 16
/** With no early clause boundary, the opening goes out at a word boundary once this long. */
export const OPENING_WORD_MIN_CHARS = 48

interface SpeechChunk {
  spans: string[]
  consumed: number
}

/** A cut here would split a markdown link, so the shaper could not rejoin it. */
const insideLink = (span: string): boolean => /\[[^\]]*$|\]\([^)]*$/.test(span)

/**
 * The opening chunk of `text`, released before any sentence terminates, or
 * null. Null whenever a terminator is present: the standard rule owns that
 * text, and a short terminated sentence there is HELD for merging -- an early
 * opening must never jump ahead of it.
 */
export function extractOpeningChunk(text: string): SpeechChunk | null {
  if (/[.!?]\s/.test(text)) return null
  const clause = /[,;:—–]\s+/g
  let m: RegExpExecArray | null
  while ((m = clause.exec(text)) !== null) {
    const end = m.index + m[0].length
    if (m.index + 1 < OPENING_CLAUSE_MIN_CHARS || insideLink(text.slice(0, end))) continue
    return { spans: [text.slice(0, end)], consumed: end }
  }
  if (text.length < OPENING_WORD_MIN_CHARS) return null
  const lastGap = /\s+(?=\S*$)/.exec(text)
  if (!lastGap || lastGap.index === 0) return null
  const end = lastGap.index + lastGap[0].length
  if (insideLink(text.slice(0, end))) return null
  return { spans: [text.slice(0, end)], consumed: end }
}

/**
 * Per-reply TTS chunking: the opening chunk on a weaker signal, then the
 * standard terminated-sentence rule for everything after it. `next()` takes
 * the unspoken tail and returns the spans to speak plus the exact span
 * consumed, so the caller's cursor never drifts (#12502).
 *
 * @param alreadyOpened  true for a reply already under way (e.g. voice enabled
 *                       mid-reply), which must not get a second "opening".
 */
export function createTtsStream(alreadyOpened = false) {
  let opened = alreadyOpened
  return {
    next(text: string): SpeechChunk {
      const standard = extractCompleteSentences(text, MIN_TTS_SENTENCE_CHARS)
      if (opened || standard.spans.length > 0) {
        opened = true
        return { spans: standard.spans, consumed: standard.consumed }
      }
      const opening = extractOpeningChunk(text)
      if (opening) opened = true
      return opening ?? { spans: [], consumed: 0 }
    },
  }
}
