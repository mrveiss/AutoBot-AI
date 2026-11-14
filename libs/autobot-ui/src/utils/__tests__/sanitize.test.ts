// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
//
// The one kit sanitiser (#19118): hostile markup stripped, formatting kept per
// named preset, links that open a new context get rel="noopener noreferrer".

import { describe, expect, it } from 'vitest'
import { sanitizeChatHtml, sanitizeHtml, sanitizeKnowledgeHtml } from '../sanitize'
import type { SanitizePreset } from '../sanitize'

const PRESETS: SanitizePreset[] = ['chat', 'knowledge', 'code', 'plain']

describe('sanitizeHtml hostile input', () => {
  it.each(PRESETS)('%s strips <iframe>, <script> and event handlers', (preset) => {
    const out = sanitizeHtml(
      '<iframe src="https://evil.test"></iframe><script>alert(1)</script><span onclick="x()" onmouseover="y()">t</span>',
      preset,
    )
    expect(out).not.toMatch(/iframe|script|onclick|onmouseover/i)
  })

  it.each(['chat', 'knowledge'] as SanitizePreset[])('%s strips <img onerror>', (preset) => {
    expect(sanitizeHtml('<img src=x onerror="alert(1)">', preset)).not.toMatch(/img|onerror/i)
  })

  it('strips javascript: and data:text/html hrefs', () => {
    expect(sanitizeChatHtml('<a href="javascript:alert(1)">x</a>')).not.toMatch(/javascript:/i)
    expect(sanitizeChatHtml('<a href="data:text/html,<script>1</script>">x</a>')).not.toMatch(/data:/i)
  })
})

describe('sanitizeHtml allowed formatting survives', () => {
  const FORMAT = '<b>b</b><i>i</i><code>c</code><pre>p</pre><ul><li>one</li></ul><ol><li>two</li></ol>'

  it.each(['chat', 'knowledge'] as SanitizePreset[])('%s keeps b, i, code, pre and lists', (preset) => {
    expect(sanitizeHtml(FORMAT, preset)).toBe(FORMAT)
  })

  it('chat keeps https links', () => {
    expect(sanitizeChatHtml('<a href="https://x.test/p">l</a>')).toBe('<a href="https://x.test/p">l</a>')
  })

  it('knowledge drops links but keeps their text', () => {
    expect(sanitizeKnowledgeHtml('<a href="https://x.test">l</a>')).toBe('l')
  })

  it('code keeps highlight spans and drops other tags', () => {
    expect(sanitizeHtml('<span class="hljs-keyword">if</span><b>x</b>', 'code')).toBe(
      '<span class="hljs-keyword">if</span>x',
    )
  })

  it('plain removes all markup', () => {
    expect(sanitizeHtml('<b>x</b><span class="a">y</span>', 'plain')).toBe('xy')
  })
})

describe('reverse-tabnabbing hook', () => {
  it('adds rel="noopener noreferrer" to a target link', () => {
    const out = sanitizeChatHtml('<a href="https://x.test" target="_blank">x</a>')
    expect(out).toContain('target="_blank"')
    expect(out).toContain('rel="noopener noreferrer"')
  })

  it('overrides a hostile rel value', () => {
    expect(sanitizeChatHtml('<a href="https://x.test" target="_blank" rel="opener">x</a>')).toContain(
      'rel="noopener noreferrer"',
    )
  })

  it('does not add rel to a link without a target', () => {
    expect(sanitizeChatHtml('<a href="https://x.test">x</a>')).not.toContain('rel=')
  })

  it('is registered once, not once per call', () => {
    for (let i = 0; i < 5; i++) sanitizeChatHtml('<a href="https://x.test" target="_blank">x</a>')
    const out = sanitizeChatHtml('<a href="https://x.test" target="_blank">x</a>')
    expect(out.match(/rel=/g)).toHaveLength(1)
  })
})
