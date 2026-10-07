// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * LLM protocol tags — ONE spelling, shared by every stripper (#18065).
 *
 * These are the sentinels a model emits so the backend can find structure in a
 * completion: `<TOOL_CALL …>…</TOOL_CALL>` and the bracket markers
 * `[THOUGHT]` / `[PLANNING]` / `[DEBUG]` / `[SOURCES]`. They are internal
 * protocol and must never reach a reader.
 *
 * They were forked across four files, and the fork had already cost a live
 * defect. The backend prompts teach UPPERCASE (`<TOOL_CALL name="web_search"`,
 * 20x in `resources/prompts/chat/system_prompt.md`), while two of the four
 * strippers matched lowercase CASE-SENSITIVELY:
 *
 *   ChatMessages.vue:908        /<tool_call…>/gs    lowercase, no `i`  -> MISSED
 *   MessageItem.vue:360         /<tool_call…>/gs    lowercase, no `i`  -> MISSED
 *   ChatController.ts:553-554   two replaces, one per case
 *   useVoiceConversation.ts:152 /gi
 *
 * `ChatMessages.vue` is the main chat renderer, so the tag this system actually
 * asks for was the one it could not strip. The pair of adjacent replaces in
 * `ChatController.ts` is the fork made visible: someone hit this, fixed one
 * file, and the other two never got it. Adding `i` in four places would have
 * been the fifth patch of one defect, so the spelling lives here instead.
 *
 * NOT flattened: the two strip behaviours are genuinely different and both are
 * wanted. Display removes a tool call ENTIRELY; speech removes only the tags
 * and keeps the description between them, because that text is written for a
 * human to hear. They are separate exported functions so neither can be
 * reached by accident.
 *
 * Anchoring is per-site and explicit for the same reason: the partial-tag
 * regexes differed on whether they were anchored to end-of-string
 * (`ChatController.ts:524` was not; the other two were). That is a behaviour
 * difference this module does not silently resolve — it takes an option, so
 * consolidating the SPELLING does not quietly change what any caller strips.
 */

/** The bracket-marker families. Keep in sync with the backend — see the parity test. */
export const PROTOCOL_BRACKET_TAGS = ['THOUGHT', 'PLANNING', 'DEBUG', 'SOURCES'] as const

/**
 * Complete bracket markers, e.g. `[THOUGHT]`, `[/PLANNING]`.
 *
 * The closing `]` is REQUIRED and a letter may not follow the family name. The
 * version this replaced made `]` optional, so `[THOUGHT` matched inside
 * `[THOUGHTFUL]` and `stripBracketTags('See [THOUGHTFUL]')` returned
 * `'See FUL]'` -- it mangled an ordinary word. That regex predates this module
 * (it was copied identically into all four former call sites), so the bug was
 * four-way; consolidating is what made it fixable once.
 */
const BRACKET_COMPLETE_RE = /\[\/?(?:THOUGHT|PLANNING|DEBUG|SOURCES)(?![A-Za-z])\]/gi

/**
 * A marker truncated mid-stream, e.g. `[/THO`. Two variants because callers
 * disagreed on anchoring and that difference is behavioural.
 *
 * `(?![A-Za-z])` is what keeps `[THOUGHTFUL]` intact: after the family prefix
 * a letter means this is a longer word, not a marker.
 */
const BRACKET_PARTIAL_BODY =
  '\\[\\/?(?:THO(?:UGH?T?)?|PLA(?:NN?I?N?G?)?|DEB(?:UG?)?|SOU(?:RC?E?S?)?)(?![A-Za-z])\\]?'
const BRACKET_PARTIAL_AT_END_RE = new RegExp(BRACKET_PARTIAL_BODY + '$', 'gi')
const BRACKET_PARTIAL_ANYWHERE_RE = new RegExp(BRACKET_PARTIAL_BODY, 'gi')

/**
 * A tool call must carry its SIGNATURE before a `[` is read as a tag opening.
 * `See [TOOL_CALL](docs) for details` is a markdown link, and converting its
 * bracket produced `<TOOL_CALL](docs)`, which the stray-tag pass then ate along
 * with the rest of the sentence. Requiring `params=` before the first `]`/`>`
 * means a link label, however it is spelled, is never a call.
 */
const SQUARE_OPEN_WITH_SIGNATURE_RE = /\[(?=\s*tool_?\s*call\b[^\]>]*\bparams\s*=)/gi
const SQUARE_CLOSE_RE = /\[\s*\/\s*tool_?\s*call\b\s*[\]>]?/gi
const SQUARE_OPEN_TERM_RE = /(<\s*tool_?\s*call\b[^\]>]*?params=(["'])(?:[\s\S]+?)\2\s*)\]/gi

/**
 * A square tag that LOOKS like a tool call but cannot be parsed -- no `params`,
 * so it was never normalised. Bounded by a REQUIRED `]`, so it can only ever
 * consume the tag itself. `[TOOL_CALL name="run"] b` used to become `a ` once
 * the half-converted form met an unbounded sweep.
 *
 * An `=` is also required, i.e. at least one attribute. Without it this matched
 * the LABEL of `[TOOL_CALL](docs)` and left `(docs)` dangling in the sentence.
 * A real call always carries `name=`; a bare `[TOOL_CALL]` is far likelier to
 * be prose or a link label, and leaving a visible token is the lesser harm
 * against deleting someone's text.
 */
const SQUARE_UNPARSEABLE_RE = /\[\/?\s*tool_?\s*call\b[^\]\n]*=[^\]\n]*\]/gi

/** A complete angle tag. The `>` is REQUIRED -- see `ANGLE_UNTERMINATED_RE`. */
const ANGLE_TAG_RE = /<\/?\s*tool_?\s*call\b[^>\n]*>/gi

/**
 * An angle tag whose `>` never arrived, which streaming produces. Bounded to the
 * REST OF THE LINE, never `[^>]*>?` across the whole input: with the terminator
 * optional, that pattern matched to end-of-string and deleted every remaining
 * sentence. Two inputs lost their tail to it before this was split out.
 */
const ANGLE_UNTERMINATED_RE = /<\/?\s*tool_?\s*call\b[^>\n]*$/gim

/** An opening tag with no matching close: in DISPLAY its contents must go too. */
const ANGLE_UNCLOSED_BLOCK_RE = /<\s*tool_?\s*call\b[^>\n]*>[\s\S]*$/gi
const ANGLE_BLOCK_RE = /<\s*tool_?\s*call\b[^>\n]*>[\s\S]*?<\/\s*tool_?\s*call\b[^>\n]*>/gi

/**
 * Square/mixed brackets normalised to the angle spelling, mirroring
 * `chat_workflow/tool_call_grammar.normalize_tool_call_brackets`.
 *
 * The open conversion requires the tool-call signature; the terminator is found
 * by anchoring on the closing QUOTE of `params=`, never the first `]`, which
 * would cut `params='{"a":[1,2]}'` in half.
 */
export function normalizeToolCallBrackets(text: string): string {
  if (!text) return text
  return text
    .replace(SQUARE_CLOSE_RE, '</TOOL_CALL>')
    .replace(SQUARE_OPEN_WITH_SIGNATURE_RE, '<')
    .replace(SQUARE_OPEN_TERM_RE, '$1>')
}

/**
 * Remove a tool call and the text inside it. For anything a user READS.
 *
 * Four passes, in this order, and none is redundant:
 *   1. matched pairs, contents included;
 *   2. an OPENING tag with no close -- its contents are the model's args and
 *      must not render as prose. A streamed `<TOOL_CALL …>Searching for data`
 *      showed `Searching for data` before this pass existed;
 *   3. a square tag that never normalised because it had no `params`;
 *   4. whatever single tags remain, each bounded so none can eat the line.
 */
export function stripToolCallBlocks(text: string): string {
  if (!text) return text
  return normalizeToolCallBrackets(text)
    .replace(ANGLE_BLOCK_RE, '')
    .replace(ANGLE_UNCLOSED_BLOCK_RE, '')
    .replace(SQUARE_UNPARSEABLE_RE, '')
    .replace(ANGLE_TAG_RE, '')
    .replace(ANGLE_UNTERMINATED_RE, '')
}

/**
 * Remove only the tool-call TAGS, keeping the description between them.
 * For speech: that description is written for a human to hear, so an unclosed
 * tag keeps its text here -- the opposite of the display path, on purpose.
 */
export function stripToolCallTags(text: string): string {
  if (!text) return text
  return normalizeToolCallBrackets(text)
    .replace(SQUARE_UNPARSEABLE_RE, '')
    .replace(ANGLE_TAG_RE, '')
    .replace(ANGLE_UNTERMINATED_RE, '')
}

/** Remove the bracket markers. `partialAnywhere` keeps a caller's existing reach. */
export function stripBracketTags(text: string, partialAnywhere = false): string {
  if (!text) return text
  const partial = partialAnywhere ? BRACKET_PARTIAL_ANYWHERE_RE : BRACKET_PARTIAL_AT_END_RE
  return text.replace(BRACKET_COMPLETE_RE, '').replace(partial, '')
}

/** Everything a reader must not see: markers plus whole tool-call blocks. */
export function stripProtocolTagsForDisplay(text: string, partialAnywhere = false): string {
  if (!text) return text
  return stripToolCallBlocks(stripBracketTags(text, partialAnywhere)).trim()
}

/** Markers plus tool-call tags, description retained for the voice path. */
export function stripProtocolTagsForSpeech(text: string): string {
  if (!text) return text
  return stripToolCallTags(stripBracketTags(text))
}
