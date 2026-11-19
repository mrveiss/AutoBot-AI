// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * The ONE chat-message formatter (#21771).
 *
 * `ChatMessages.vue` and `MessageItem.vue` each carried their own copy of this
 * pipeline and the copies had drifted. Differences found when merging them, and
 * the behaviour chosen:
 *
 *  - ANSI: the `MessageItem` copy dropped the ESC prefix on its last two rules,
 *    so it stripped literal `[1;2h` / `]0;...` text from prose. Chosen: the
 *    ESC-anchored rules of the `ChatMessages` copy.
 *  - Protocol tags: `ChatMessages` stripped bracket markers plus tool-call
 *    blocks, `MessageItem` only tool-call blocks. Chosen: the superset
 *    (`stripProtocolTagsForDisplay`).
 *  - `[text](href)` links: only `MessageItem` rendered them. Chosen: render them
 *    (#9479) everywhere.
 *  - Bare URLs: `ChatMessages` linkified after `\n` -> `<br>` with `[^\s]+`, so
 *    the href swallowed `<br>` and the next word. Chosen: stop at `<`, never
 *    re-wrap a URL that is already inside an anchor, and keep trailing
 *    punctuation / an unbalanced closing parenthesis out of the href.
 *  - Bold, italics, inline code, code blocks, sanitising: identical.
 */
import { stripProtocolTagsForDisplay } from '@/utils/llmProtocolTags'
import { escapeHtml, sanitizeChatHtml } from '@/utils/sanitize'
import { renderMarkdownLinks } from '@/composables/chat/useEntityAnchors'

const ANCHOR_RE = /(<a\b[^>]*>[\s\S]*?<\/a\s*>)/i
const PRE_RE = /(<pre\b[\s\S]*?<\/pre>)/
const BARE_URL_RE = /https?:\/\/[^\s<>"']+/g
const TRAILING_PUNCT_CHARS = '.,;:!?\'"'
// A trailing `*` or backtick belongs to the markup only when it closes a delimiter opened right before the URL.
const DELIMITER_CHARS = '*`'

// Control characters are built at runtime, never written as regex escapes (ESLint no-control-regex): a literal
// control byte in a pattern is a lint error and unreadable besides.
const ESC = String.fromCharCode(27)
const BEL = String.fromCharCode(7)
const CSI_RE = /\[[?0-9;]*[a-zA-Z]/y
const SHORT_RE = /(?:[=>]|[()][AB012])/y
const OSC_HEAD_RE = /\][0-9;]*/y

function matchLength(re: RegExp, s: string, at: number): number {
  re.lastIndex = at
  const m = re.exec(s)
  return m ? m[0].length : 0
}

/** Index just past the escape sequence whose body starts at `at` (the char after ESC), or -1 when there is none. */
function ansiSequenceEnd(s: string, at: number): number {
  const csi = matchLength(CSI_RE, s, at) || matchLength(SHORT_RE, s, at)
  if (csi) return at + csi
  const head = matchLength(OSC_HEAD_RE, s, at)
  if (!head) return -1
  const bel = s.indexOf(BEL, at + head)
  if (bel >= 0) return bel + 1 // OSC ... BEL
  const next = s.indexOf(ESC, at + head)
  if (next < 0) return s.length // unterminated: to the end
  return s[next + 1] === '\\' ? next + 2 : next // OSC ... ST (ESC \)
}

function stripAnsi(content: string): string {
  let out = ''
  let i = 0
  while (i < content.length) {
    const esc = content.indexOf(ESC, i)
    if (esc < 0) return (out + content.slice(i)).trim()
    out += content.slice(i, esc)
    const end = ansiSequenceEnd(content, esc + 1)
    if (end < 0) out += ESC
    i = end < 0 ? esc + 1 : end
  }
  return out.trim()
}

/** Length of the run of `d` ending `text` at index `to` (exclusive), scanned backwards without slicing the prefix. */
function trailingRun(text: string, to: number, d: string): number {
  let n = 0
  while (n < to && text[to - 1 - n] === d) n++
  return n
}

/** Split a matched URL into [href, trailing text that is not part of it]; `before` is `text` up to `beforeEnd`. */
function splitTrailing(raw: string, text = '', beforeEnd = 0): [string, string] {
  const open: Record<string, number> = {}
  for (const d of DELIMITER_CHARS) open[d] = trailingRun(text, beforeEnd, d)
  let end = raw.length
  let opens = 0
  let closes = 0
  for (const ch of raw) {
    if (ch === '(') opens++
    else if (ch === ')') closes++
  }
  while (end > 0) {
    const ch = raw[end - 1]
    if (TRAILING_PUNCT_CHARS.includes(ch)) end--
    else if (DELIMITER_CHARS.includes(ch) && open[ch] > 0) {
      open[ch]--
      end--
    } else if (ch === ')' && closes > opens) {
      closes--
      end--
    } else break
  }
  return [raw.slice(0, end), raw.slice(end)]
}

/** Wrap bare URLs in anchors, leaving existing anchors untouched. */
export function linkifyBareUrls(html: string): string {
  return html
    .split(ANCHOR_RE)
    .map((part, i) => {
      if (i % 2 === 1) return part
      return part.replace(BARE_URL_RE, (raw, offset: number) => {
        const [url, tail] = splitTrailing(raw, part, offset)
        if (!/^https?:\/\/./i.test(url)) return raw
        return `<a href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(url)}</a>${tail}`
      })
    })
    .join('')
}

// A Unicode noncharacter (not a control character, and unlike a private-use point it is never a font glyph): it cannot occur in rendered text.
const LINK_STASH = '\uFDD0'

/** Swap every match of `re` (one capture group) for a placeholder, appending the originals to `store`. */
function stash(html: string, re: RegExp, store: string[]): string {
  return html
    .split(re)
    .map((part, i) => {
      if (i % 2 === 0) return part
      store.push(part)
      return `${LINK_STASH}${store.length - 1}${LINK_STASH}`
    })
    .join('')
}

function restoreAnchors(text: string, anchors: string[]): string {
  return text.replace(/\uFDD0(\d+)\uFDD0/g, (_m, n) => anchors[Number(n)])
}

/** Render raw chat message text to sanitised HTML (sanitising is always the LAST step). */
export function formatChatMessageHtml(raw: string): string {
  let content = stripProtocolTagsForDisplay(stripAnsi(raw)).split(LINK_STASH).join('')

  content = content.replace(/```(\w+)?\n([\s\S]*?)```/g, (_m, lang, code) => {
    return `<pre class="code-block${lang ? ` language-${lang}` : ''}"><code>${code.trim()}</code></pre>`
  })

  // Code blocks are set aside before the link passes; anchors before the inline passes.
  const anchors: string[] = []
  const prose = stash(content, PRE_RE, anchors)
  const text = stash(linkifyBareUrls(renderMarkdownLinks(prose)), ANCHOR_RE, anchors)
  const inline = text
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.*?)\*/g, '<em>$1</em>')
    .replace(/`(.*?)`/g, '<code>$1</code>')
    .replace(/\n/g, '<br>')

  return sanitizeChatHtml(restoreAnchors(inline, anchors))
}
