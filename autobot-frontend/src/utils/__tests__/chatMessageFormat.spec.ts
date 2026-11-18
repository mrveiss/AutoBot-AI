// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect } from 'vitest'
import { formatChatMessageHtml, linkifyBareUrls } from '../chatMessageFormat'

const hrefs = (html: string): string[] =>
  Array.from(html.matchAll(/<a href="([^"]*)"/g)).map((m) => m[1])

describe('chat message formatter (#21771)', () => {
  it('a URL at a line end does not swallow the <br> or the next word', () => {
    const html = formatChatMessageHtml(
      'Navigated to: https://example.com/weather\nPage title: Forecast',
    )
    expect(hrefs(html)).toEqual(['https://example.com/weather'])
    expect(html).toContain('</a><br>Page title: Forecast')
  })

  it('keeps a URL in parentheses out of the closing parenthesis', () => {
    const html = formatChatMessageHtml('see (https://example.com/a) now')
    expect(hrefs(html)).toEqual(['https://example.com/a'])
    expect(html).toContain('</a>) now')
  })

  it('keeps balanced parentheses that belong to the URL', () => {
    const html = formatChatMessageHtml('https://en.example.org/wiki/Foo_(bar)')
    expect(hrefs(html)).toEqual(['https://en.example.org/wiki/Foo_(bar)'])
  })

  it.each(['.', ',', ';', ':', '!', '?'])('trailing %s stays outside the href', (p) => {
    const html = formatChatMessageHtml(`go to https://example.com/x${p} then`)
    expect(hrefs(html)).toEqual(['https://example.com/x'])
    expect(html).toContain(`</a>${p} then`)
  })

  it('does not wrap a URL already inside an anchor a second time', () => {
    const html = formatChatMessageHtml('[https://example.com/a](https://example.com/a)')
    expect(hrefs(html)).toEqual(['https://example.com/a'])
    expect((html.match(/<a /g) || []).length).toBe(1)
  })

  it('linkifyBareUrls leaves existing anchors alone', () => {
    const input = '<a href="https://e.com/a">https://e.com/a</a> and https://e.com/b'
    expect(hrefs(linkifyBareUrls(input))).toEqual(['https://e.com/a', 'https://e.com/b'])
  })

  it('does not strip literal bracket text from prose (ANSI rules are ESC-anchored)', () => {
    expect(formatChatMessageHtml('array[1;2h] ok')).toContain('array[1;2h] ok')
  })

  it('renders bold, italics and inline code', () => {
    const html = formatChatMessageHtml('**b** *i* `c`')
    expect(html).toContain('<strong>b</strong>')
    expect(html).toContain('<em>i</em>')
    expect(html).toContain('<code>c</code>')
  })

  describe('hostile input (output is the DOMPurify chat preset result)', () => {
    const parse = (html: string): HTMLElement => {
      const d = document.createElement('div')
      d.innerHTML = html
      return d
    }

    it('a quote in a bare URL cannot break out of the href attribute', () => {
      const root = parse(
        formatChatMessageHtml('go https://x.example/"class="evil" onmouseover="alert(1)'),
      )
      const a = root.querySelector('a')
      expect(a).not.toBeNull()
      expect(a?.getAttribute('class')).toBeNull()
      expect(a?.getAttribute('onmouseover')).toBeNull()
      expect(a?.getAttribute('href')).toBe('https://x.example/')
    })

    it('javascript: markdown links never become anchors', () => {
      const root = parse(formatChatMessageHtml('[x](javascript:alert(1))'))
      expect(root.querySelector('a')).toBeNull()
      expect(root.innerHTML).not.toMatch(/href=/i)
    })

    it('data: markdown links never become anchors', () => {
      const root = parse(formatChatMessageHtml('[x](data:text/html,<script>alert(1)</script>)'))
      expect(root.querySelector('a')).toBeNull()
      expect(root.querySelector('script')).toBeNull()
    })

    it('a script tag in text is removed', () => {
      const root = parse(formatChatMessageHtml('hi <script>alert(1)</script> there'))
      expect(root.querySelector('script')).toBeNull()
    })
  })

  describe('inline passes leave links and prose alone', () => {
    it('underscores and asterisks inside a URL stay in the href', () => {
      const html = formatChatMessageHtml('see https://example.com/a*b*c and *real*')
      expect(hrefs(html)).toEqual(['https://example.com/a*b*c'])
      expect(html).toContain('<em>real</em>')
    })

    it('arr[0](x) in prose is not collapsed to its label', () => {
      expect(formatChatMessageHtml('use arr[0](x) here')).toContain('arr[0](x)')
    })
  })

  it('a fenced block is not rewritten by the link passes', () => {
    const html = formatChatMessageHtml('```md\n[label](relative.md) and *x*\n```')
    expect(html).toContain('[label](relative.md) and *x*')
  })

  it('many surplus closing parentheses stay out of the href quickly', () => {
    const html = formatChatMessageHtml('https://example.com/a' + ')'.repeat(20000))
    expect(hrefs(html)).toEqual(['https://example.com/a'])
  })
})
