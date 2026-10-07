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

/** Complete bracket markers, e.g. `[THOUGHT]`, `[/PLANNING]`. */
const BRACKET_COMPLETE_RE = /\[\/?(THOUGHT|PLANNING|DEBUG|SOURCES)\]?/gi

/**
 * A marker truncated mid-stream, e.g. `[/THO`. Built as two variants because
 * callers disagreed on anchoring and that difference is behavioural, not
 * cosmetic.
 */
const BRACKET_PARTIAL_AT_END_RE =
  /\[\/?(?:THO(?:UGH?T?)?|PLA(?:NN?I?N?G?)?|DEB(?:UG?)?|SOU(?:RC?E?S?)?)\]?$/gi
const BRACKET_PARTIAL_ANYWHERE_RE =
  /\[\/?(?:THO(?:UGH?T?)?|PLA(?:NN?I?N?G?)?|DEB(?:UG?)?|SOU(?:RC?E?S?)?)\]?/gi

/**
 * Square/mixed brackets normalised to the angle spelling before anything else,
 * mirroring `chat_workflow/tool_call_grammar.normalize_tool_call_brackets`.
 *
 * Anchored on the `TOOL_CALL` token and, for the open tag, on the closing QUOTE
 * of `params=` — never the first `]`, which would cut `params='{"a":[1,2]}'` in
 * half. `[` is markdown first: `[the docs](url)`, `[a list][1]` and `[1,2,3]`
 * must survive untouched, which the tests pin.
 */
export function normalizeToolCallBrackets(text: string): string {
  if (!text) return text
  return text
    .replace(/\[\s*\/\s*tool_?\s*call\b\s*[\]>]?/gi, '</TOOL_CALL>')
    .replace(/\[(?=\s*tool_?\s*call\b)/gi, '<')
    .replace(/(<\s*tool_?\s*call\b[^\]>]*?params=(["'])(?:[\s\S]+?)\2\s*)\]/gi, '$1>')
}

/**
 * Remove a tool call and the text inside it. For anything a user READS.
 *
 * Two passes, and the second is not redundant. The block pattern needs a
 * MATCHED PAIR, so a dangling close with no opening tag survives it — which is
 * the exact shape reported live (`[/TOOL_CALL>` alone in a reply) and the same
 * gap the backend had at `strip_unparsed_tool_tags`'s early return. The first
 * test written against this module failed on it, so the stray-tag sweep runs
 * after the block sweep rather than instead of it: pairs must lose their
 * contents, and whatever is left must lose its tags.
 */
export function stripToolCallBlocks(text: string): string {
  if (!text) return text
  return normalizeToolCallBrackets(text)
    .replace(/<\s*tool_?\s*call\b[^>]*>[\s\S]*?<\/\s*tool_?\s*call\b[^>]*>?/gi, '')
    .replace(/<\/?\s*tool_?\s*call\b[^>]*>?/gi, '')
}

/**
 * Remove only the tool-call TAGS, keeping the description between them.
 * For speech: that description is written for a human to hear.
 */
export function stripToolCallTags(text: string): string {
  if (!text) return text
  return normalizeToolCallBrackets(text).replace(/<\/?\s*tool_?\s*call\b[^>]*>?/gi, '')
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
