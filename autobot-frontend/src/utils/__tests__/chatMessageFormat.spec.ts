import { describe, it, expect } from 'vitest'
import { formatChatMessageHtml, linkifyBareUrls } from '../chatMessageFormat'

const hrefs = (html: string): string[] =>
  Array.from(html.matchAll(/<a href="([^"]*)"/g)).map((m) => m[1])

describe('chat message formatter (#21771)', () => {
  it('a URL at a line end does not swallow the <br> or the next word', () => {
    const html = formatChatMessageHtml('Navigated to: https://example.com/weather\nPage title: Forecast')
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
})
