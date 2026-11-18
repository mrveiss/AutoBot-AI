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
import { sanitizeChatHtml } from '@/utils/sanitize'
import { escapeHtml, renderMarkdownLinks } from '@/composables/chat/useEntityAnchors'

const ANCHOR_RE = /(<a\b[^>]*>[\s\S]*?<\/a\s*>)/i
const PRE_RE = /(<pre\b[\s\S]*?<\/pre>)/
const BARE_URL_RE = /https?:\/\/[^\s<>"']+/g
const TRAILING_PUNCT_CHARS = '.,;:!?\'"'

function stripAnsi(content: string): string {
  return content
    .replace(/\u001b\[[0-9;]*[a-zA-Z]/g, '')
    .replace(/\u001b\][0-9;]*[^\u0007]*\u0007/g, '')
    .replace(/\u001b\][0-9;]*[^\u0007\u001b]*(?:\u001b\\)?/g, '')
    .replace(/\u001b[=>]/g, '')
    .replace(/\u001b[()][AB012]/g, '')
    .replace(/\u001b\[[?\d;]*[hlHJ]/g, '')
    .replace(/\u001b\]0;[^\u0007\n]*\u0007?/g, '')
    .trim()
}

/** Split a matched URL into [href, trailing text that is not part of it]. */
function splitTrailing(raw: string): [string, string] {
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
    else if (ch === ')' && closes > opens) {
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
      return part.replace(BARE_URL_RE, (raw) => {
        const [url, tail] = splitTrailing(raw)
        if (!/^https?:\/\/./i.test(url)) return raw
        return `<a href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(url)}</a>${tail}`
      })
    })
    .join('')
}

const LINK_STASH = '\u0000'

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
  return text.replace(/\u0000(\d+)\u0000/g, (_m, n) => anchors[Number(n)])
}

/** Render raw chat message text to sanitised HTML (sanitising is always the LAST step). */
export function formatChatMessageHtml(raw: string): string {
  let content = stripProtocolTagsForDisplay(stripAnsi(raw)).replace(/\u0000/g, '')

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
