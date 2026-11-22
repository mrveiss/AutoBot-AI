// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/** Query highlighting for knowledge search results (#3296 / #18244): safe for v-html. */
import { describe, it, expect } from 'vitest'
import { buildHighlightRegex, highlightSnippet, highlightText, scoreVariant } from '../searchHighlight'

describe('searchHighlight', () => {
  it('escapes HTML before marking, so a result cannot inject markup', () => {
    expect(highlightText('<script>alert(1)</script> rag', 'rag')).toBe(
      '&lt;script&gt;alert(1)&lt;/script&gt; <mark class="kb-highlight">rag</mark>',
    )
  })

  it('marks every term of two or more characters, case-insensitively', () => {
    expect(highlightText('Fleet node', 'FLEET n')).toBe('<mark class="kb-highlight">Fleet</mark> node')
  })

  it('treats regex characters in the query literally and returns plain escaped text when no term qualifies', () => {
    expect(buildHighlightRegex('a')).toBeNull()
    expect(highlightText('1+1=2 (ok)', '(ok)')).toContain('<mark class="kb-highlight">(ok)</mark>')
    expect(highlightText('a < b', 'x')).toBe('a &lt; b')
    expect(highlightText('', 'x')).toBe('')
  })

  it('cuts a long snippet at 200 characters with an ellipsis', () => {
    expect(highlightSnippet('z'.repeat(250), 'q')).toBe(`${'z'.repeat(200)}…`)
    expect(highlightSnippet('short', 'q')).toBe('short')
  })

  it('maps a relevance score to a badge variant', () => {
    expect([0.9, 0.8, 0.7, 0.6, 0.59].map(scoreVariant)).toEqual(['success', 'success', 'warning', 'warning', 'error'])
  })
})
