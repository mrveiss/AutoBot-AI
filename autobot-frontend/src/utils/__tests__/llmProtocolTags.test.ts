// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * One spelling for the LLM protocol tags (#18065).
 *
 * The live defect these pin: the backend teaches UPPERCASE `<TOOL_CALL …>`, and
 * two of the four strippers matched lowercase case-sensitively, so the main chat
 * renderer could not strip the tag the system actually asks for.
 *
 * The negatives matter as much as the positives. `[` is markdown first, so a
 * stripper that ate `[the docs](url)` would be a worse defect than the leak.
 */
import { describe, it, expect } from 'vitest'

import {
  PROTOCOL_BRACKET_TAGS,
  normalizeToolCallBrackets,
  stripBracketTags,
  stripProtocolTagsForDisplay,
  stripProtocolTagsForSpeech,
  stripToolCallBlocks,
  stripToolCallTags,
} from '../llmProtocolTags'

const UPPER = '<TOOL_CALL name="web_search" params=\'{"q":"x"}\'>Searching</TOOL_CALL>'
const LOWER = '<tool_call name="web_search" params=\'{"q":"x"}\'>Searching</tool_call>'
const SQUARE = '[TOOL_CALL name="web_search" params=\'{"q":"x"}\']Searching[/TOOL_CALL]'
const MIXED_CLOSE = 'Answer here.\n[/TOOL_CALL>'

describe('case is not a spelling (the live defect)', () => {
  it.each([UPPER, LOWER, SQUARE])('strips the whole block regardless of case or bracket', raw => {
    const out = stripToolCallBlocks(`Before. ${raw} After.`)
    expect(out).not.toMatch(/tool_?call/i)
    expect(out).toContain('Before.')
    expect(out).toContain('After.')
  })

  it('strips the UPPERCASE form the prompts actually teach', () => {
    // The exact regression: /<tool_call…>/gs with no `i` left this on screen.
    expect(stripToolCallBlocks(UPPER)).toBe('')
  })

  it('removes a dangling close that has no opening tag', () => {
    expect(stripProtocolTagsForDisplay(MIXED_CLOSE)).toBe('Answer here.')
  })
})

describe('display and speech are different on purpose', () => {
  it('display removes the description inside the call', () => {
    expect(stripToolCallBlocks(UPPER)).not.toContain('Searching')
  })

  it('speech keeps the description, because it is written to be heard', () => {
    const spoken = stripToolCallTags(UPPER)
    expect(spoken).toContain('Searching')
    expect(spoken).not.toMatch(/tool_?call/i)
  })

  it('the two entry points differ on the same input', () => {
    expect(stripProtocolTagsForDisplay(UPPER)).not.toContain('Searching')
    expect(stripProtocolTagsForSpeech(UPPER)).toContain('Searching')
  })
})

describe('markdown is not a protocol tag', () => {
  it.each([
    'see [the docs](https://example.test/y) for more',
    'a reference [a list][1] and its target',
    'an array [1, 2, 3] in prose',
    'the [toolbox] is fine',
    '[tool] and [call] apart are not a tag',
  ])('leaves %s untouched', prose => {
    expect(normalizeToolCallBrackets(prose)).toBe(prose)
    expect(stripToolCallBlocks(prose)).toBe(prose)
  })

  it('keeps a JSON array inside params intact rather than cutting at the first ]', () => {
    const withList = '[TOOL_CALL name="run" params=\'{"a":[1,2]}\']go[/TOOL_CALL]'
    // Normalisation must produce a well-formed angle tag, params unmangled.
    expect(normalizeToolCallBrackets(withList)).toContain('params=\'{"a":[1,2]}\'>')
    // And the whole block must then strip, leaving nothing behind.
    expect(stripToolCallBlocks(withList)).toBe('')
  })

  it('is idempotent on text that already uses angle brackets', () => {
    expect(normalizeToolCallBrackets(UPPER)).toBe(UPPER)
    expect(normalizeToolCallBrackets(normalizeToolCallBrackets(UPPER))).toBe(UPPER)
  })
})

describe('bracket markers', () => {
  it('strips every declared family, both open and close', () => {
    const raw = PROTOCOL_BRACKET_TAGS.map(t => `[${t}]x[/${t}]`).join(' ')
    expect(stripBracketTags(raw)).not.toMatch(/\[\/?[A-Z]+\]/)
  })

  it('strips a stream-truncated marker at the end', () => {
    expect(stripBracketTags('thinking [/THO')).toBe('thinking ')
  })

  it('leaves a mid-text truncation alone unless the caller asks for anywhere', () => {
    // The anchoring difference between the old call sites, preserved explicitly.
    const mid = 'a [/THO b'
    expect(stripBracketTags(mid)).toBe(mid)
    expect(stripBracketTags(mid, true)).toBe('a  b')
  })
})

describe('empty and absent input', () => {
  it.each(['', 'plain text with no tags at all'])('returns %p unchanged', text => {
    expect(stripProtocolTagsForDisplay(text)).toBe(text ? text : '')
    expect(stripProtocolTagsForSpeech(text)).toBe(text)
  })
})

describe('a bounded sweep never eats the rest of the message (#18095 review)', () => {
  // Every one of these DELETED the remainder of its input before the patterns
  // were bounded. `[^>]*>?` with an optional terminator matches to end-of-input,
  // so an unterminated tag consumed every following sentence. Measured, not
  // predicted: these are the exact strings that lost their tails.
  it('keeps the sentence around a markdown link labelled TOOL_CALL', () => {
    const out = stripToolCallBlocks('See [TOOL_CALL](docs) for details')
    expect(out).toContain('for details')
    expect(out).toBe('See [TOOL_CALL](docs) for details')
  })

  it('keeps the text after a square tag that has no params', () => {
    // Recognised as tool-call-shaped but unparseable: the TAG goes, the prose stays.
    const out = stripToolCallBlocks('a [TOOL_CALL name="run"] b')
    expect(out).toContain('b')
    expect(out).not.toMatch(/tool_?call/i)
  })

  it('keeps the text after an unterminated angle tag', () => {
    const out = stripToolCallBlocks('before <TOOL_CALL name="run"\nafter')
    expect(out).toContain('after')
    expect(out).not.toMatch(/tool_?call/i)
  })
})

describe('an unclosed tool call hides its arguments in DISPLAY (#18095 review)', () => {
  const unclosed = `x <TOOL_CALL name="search" params='{}'>Searching for data`

  it('display removes the opening tag AND its contents', () => {
    const out = stripToolCallBlocks(unclosed)
    expect(out).not.toContain('Searching for data')
    expect(out).not.toMatch(/tool_?call/i)
    expect(out).toContain('x')
  })

  it('speech still keeps the description — the paths differ on purpose', () => {
    const spoken = stripToolCallTags(unclosed)
    expect(spoken).toContain('Searching for data')
    expect(spoken).not.toMatch(/tool_?call/i)
  })
})

describe('a longer word starting with a marker name survives (#18095 review)', () => {
  it.each([
    ['See [THOUGHTFUL]', 'See [THOUGHTFUL]'],
    ['two [PLANNINGS] here', 'two [PLANNINGS] here'],
    ['a [DEBUGGER] tool', 'a [DEBUGGER] tool'],
    ['the [SOURCEMAP] file', 'the [SOURCEMAP] file'],
  ])('%s is untouched', (input, expected) => {
    // `stripBracketTags('See [THOUGHTFUL]')` returned 'See FUL]' -- the optional
    // `]` let `[THOUGHT` match inside a longer word. Four-way bug: the regex was
    // copied identically into all four former call sites.
    expect(stripBracketTags(input)).toBe(expected)
    expect(stripBracketTags(input, true)).toBe(expected)
  })

  it('CONTROL: the real markers are still stripped', () => {
    expect(stripBracketTags('[THOUGHT]x[/THOUGHT]')).toBe('x')
    expect(stripBracketTags('truncated [/THO')).toBe('truncated ')
  })
})
