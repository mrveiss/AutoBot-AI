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
import { renderMarkdownLinks } from '@/composables/chat/useEntityAnchors'

const ANCHOR_RE = /(<a\b[^>]*>[\s\S]*?<\/a>)/i
const BARE_URL_RE = /https?:\/\/[^\s<]+/g
const TRAILING_PUNCT_RE = /[.,;:!?'"]+$/

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
  let url = raw
  let tail = ''
  for (;;) {
    const punct = TRAILING_PUNCT_RE.exec(url)
    if (punct) {
      tail = punct[0] + tail
      url = url.slice(0, punct.index)
      continue
    }
    const opens = (url.match(/\(/g) || []).length
    const closes = (url.match(/\)/g) || []).length
    if (url.endsWith(')') && closes > opens) {
      tail = ')' + tail
      url = url.slice(0, -1)
      continue
    }
    return [url, tail]
  }
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
        return `<a href="${url}" target="_blank" rel="noopener noreferrer">${url}</a>${tail}`
      })
    })
    .join('')
}

/** Render raw chat message text to sanitised HTML. */
export function formatChatMessageHtml(raw: string): string {
  let content = stripProtocolTagsForDisplay(stripAnsi(raw))

  content = content.replace(/```(\w+)?\n([\s\S]*?)```/g, (_m, lang, code) => {
    return `<pre class="code-block${lang ? ` language-${lang}` : ''}"><code>${code.trim()}</code></pre>`
  })

  content = renderMarkdownLinks(content)

  content = content
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.*?)\*/g, '<em>$1</em>')
    .replace(/`(.*?)`/g, '<code>$1</code>')
    .replace(/\n/g, '<br>')

  return sanitizeChatHtml(linkifyBareUrls(content))
}
