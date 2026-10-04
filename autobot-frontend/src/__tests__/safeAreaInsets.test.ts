// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * Safe-area inset handling (#14771). The page opts into the full screen with
 * viewport-fit=cover, the insets are defined once as tokens, and the app shell
 * keeps in-flow content inside them.
 *
 * Read through a parser (DOMParser, the browser's CSSOM) rather than matched as
 * text, so a comment that mentions a token cannot satisfy the check.
 */
import { describe, it, expect, afterEach } from 'vitest'
import { readFileSync } from 'node:fs'
import indexHtml from '../../index.html?raw'

// Vitest's CSS handling returns '' for a `?raw` .css import, so read from disk.
const read = (rel: string) => readFileSync(new URL(rel, import.meta.url), 'utf-8')
const designTokens = read('../assets/css/design-tokens.css')
const baseCss = read('../assets/base.css')

function rulesOf(css: string): CSSStyleRule[] {
  const style = document.createElement('style')
  style.textContent = css
  document.head.appendChild(style)
  return Array.from(style.sheet!.cssRules).filter((r): r is CSSStyleRule => r instanceof CSSStyleRule)
}

describe('safe-area insets (#14771)', () => {
  afterEach(() => {
    document.head.innerHTML = ''
  })

  it('opts the viewport into the full screen with viewport-fit=cover', () => {
    const doc = new DOMParser().parseFromString(indexHtml, 'text/html')
    const content = doc.querySelector('meta[name="viewport"]')!.getAttribute('content')!
    expect(content.split(',').map((part) => part.trim())).toContain('viewport-fit=cover')
  })

  it('defines each inset once as a token over env(), with a 0px fallback', () => {
    const root = rulesOf(designTokens).find((r) => r.selectorText === ':root')!
    for (const side of ['top', 'right', 'bottom', 'left']) {
      // The CSSOM normalises whitespace inside the value; compare without it.
      expect(root.style.getPropertyValue(`--safe-${side}`).replace(/\s+/g, '')).toBe(`env(safe-area-inset-${side},0px)`)
    }
  })

  it('pads the app shell by all four insets', () => {
    const app = rulesOf(baseCss).find((r) => r.selectorText === '#app')!
    expect(app.style.getPropertyValue('padding').trim()).toBe(
      'var(--safe-top) var(--safe-right) var(--safe-bottom) var(--safe-left)',
    )
  })
})
