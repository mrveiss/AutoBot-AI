// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
//
// #21567: the primary fill utilities (bg-autobot-primary) paint the active scheme's
// --primary, and the ink on it (text-autobot-text-on-primary) is that scheme's
// --on-primary. Pin that the pair is defined wherever the fill is, and that the ink
// meets 4.5:1 on the fill in every state, high-contrast and the no-theme state included.
import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, it, expect } from 'vitest'

const here = dirname(fileURLToPath(import.meta.url))
const SCHEME = readFileSync(resolve(here, './slm-scheme.css'), 'utf-8')
const MAIN = readFileSync(resolve(here, './main.css'), 'utf-8')

const stripComments = (s: string) => s.replace(/\/\*[\s\S]*?\*\//g, '')

/** Declarations of the top-level block whose selector (comments removed) is exactly *selector*. */
function block(css: string, selector: string): Record<string, string> {
  const out: Record<string, string> = {}
  for (const [, sel, body] of stripComments(css).matchAll(/([^{}]+)\{([^{}]*)\}/g)) {
    if (sel.trim() !== selector) continue
    for (const [, k, v] of body.matchAll(/(--[a-z0-9-]+)\s*:\s*([^;]+);/g)) out[k] = v.trim()
  }
  return out
}

/** Opaque six-digit hex only: an 8-digit value's alpha would be silently dropped, and the browser paints it translucent. */
const OPAQUE_HEX = /^#[0-9a-f]{6}$/i
const luminance = (hex: string) => {
  if (!OPAQUE_HEX.test(hex)) throw new Error(`not an opaque #rrggbb colour: ${hex}`)
  const [r, g, b] = [1, 3, 5].map((i) => {
    const c = parseInt(hex.slice(i, i + 2), 16) / 255
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4
  })
  return 0.2126 * r + 0.7152 * g + 0.0722 * b
}
const contrast = (a: string, b: string) => {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x)
  return (hi + 0.05) / (lo + 0.05)
}

const SCHEMES = [
  [SCHEME, ":root[data-app='slm']:not([data-theme]),\n:root[data-app='slm'][data-theme='light']"],
  [SCHEME, ":root[data-app='slm'][data-theme='dark']"],
  [SCHEME, ":root[data-app='slm'][data-theme='contrast']"],
  [SCHEME, ":root[data-app='slm'][data-theme='mono']"],
  [MAIN, ":root[data-theme='high-contrast']"],
] as const

describe('SLM primary fill and its ink (#21567)', () => {
  it.each(SCHEMES)('defines --primary and --on-primary together with ≥4.5:1 contrast (%#)', (css, sel) => {
    // selector lists are normalised by the block() trim; compare per-line for the light block
    const decl = block(css, sel)
    expect(Object.keys(decl), sel).toEqual(expect.arrayContaining(['--primary', '--on-primary']))
    expect(contrast(decl['--primary'], decl['--on-primary'])).toBeGreaterThanOrEqual(4.5)
  })

  it('paints the fill from --primary and the ink from --on-primary', () => {
    expect(block(MAIN, ':root')['--color-primary']).toBe('var(--primary)')
    expect(block(SCHEME, ':root')['--text-on-primary']).toBe('var(--on-primary)')
  })

  // The save button paints the Tailwind utilities bg-autobot-primary / text-autobot-text-on-primary, which
  // read these @theme aliases; they must resolve through the tokens tested above, not around them.
  it('routes the utility pair through --color-primary and --text-on-primary', () => {
    const theme = block(SCHEME, '@theme')
    expect(theme['--color-autobot-primary']).toBe('var(--color-primary)')
    expect(theme['--color-autobot-text-on-primary']).toBe('var(--text-on-primary)')
  })

  it('rejects a translucent colour instead of reading only its rgb channels', () => {
    expect(() => contrast('#2CC5A800', '#000000')).toThrow(/opaque/)
  })

  it('defines an ink for the base state, where --primary is the sky 500 (read from @theme)', () => {
    const sky = block(MAIN, '@theme')['--color-primary-500']
    expect(sky, '--color-primary-500 must be declared in main.css @theme').toBeDefined()
    expect(block(SCHEME, ':root')['--on-primary']).toBe('var(--color-black)')
    expect(contrast(sky, '#000000')).toBeGreaterThanOrEqual(4.5)
  })

  // With no scheme --primary-h is unset, so hover and pressed paint these fallbacks under the black ink.
  it.each(['--color-primary-hover', '--color-primary-active'])('%s falls back to a shade the black ink can be read on', (prop) => {
    const fallback = /^var\(--primary-h, var\((--color-primary-\d+)\)\)$/.exec(block(SCHEME, ':root')[prop])
    expect(fallback, `${prop} must be var(--primary-h, var(--color-primary-N))`).not.toBeNull()
    const shade = block(MAIN, '@theme')[fallback![1]]
    expect(contrast(shade, '#000000'), fallback![1]).toBeGreaterThanOrEqual(4.5)
  })
})

/** Selector parts a state's attributes can satisfy; anything else (a class, a descendant) never matches :root. */
type Attrs = { 'data-app'?: string; 'data-theme'?: string }
/** An optional leading `html` (type selector) then :root and attribute/:not([attr]) parts: all this model evaluates. */
const EVALUABLE = /^(html)?:root(\[[^\]]+\]|:not\(\[[^\]]+\]\))*$/
function matches(sel: string, attrs: Attrs): boolean {
  if (!EVALUABLE.test(sel)) return false
  for (const [, neg, name, val] of sel.matchAll(/(:not\()?\[([a-z-]+)(?:='([^']*)')?\]/g)) {
    const have = attrs[name as keyof Attrs]
    const hit = val === undefined ? have !== undefined : have === val
    if (neg ? hit : !hit) return false
  }
  return true
}
/** Classes-level weight (:root and each attribute count as one) then the type selector: compared as one number. */
const specificity = (sel: string) => (1 + (sel.match(/\[/g) ?? []).length) * 10 + (sel.startsWith('html') ? 1 : 0)
/** A selector that could style <html> but that matches() cannot evaluate would silently drop a rule that may win. */
const TARGETS_ROOT = /(^|[\s,>+~])(html|body|:root)\b|^:root/

/** The value a custom property resolves to on <html>: highest (importance, specificity), later declaration wins
 *  a tie. main.css @imports slm-scheme.css at its top, so the scheme's rules precede main.css's own. */
function cascade(prop: string, attrs: Attrs): string | undefined {
  let best: { imp: number; spec: number; order: number; value: string } | undefined
  let order = 0
  for (const css of [SCHEME, MAIN]) {
    for (const [, sels, body] of stripComments(css).matchAll(/([^{}]+)\{([^{}]*)\}/g)) {
      for (const [, name, raw] of body.matchAll(/(--[a-z0-9-]+)\s*:\s*([^;]+);/g)) {
        order++ // every declaration is ordered, so a later duplicate in the same block wins
        if (name !== prop) continue
        const imp = /!important\s*$/.test(raw) ? 1 : 0
        const value = raw.replace(/\s*!important\s*$/, '').trim()
        for (const sel of sels.split(',').map((x) => x.trim())) {
          if (!matches(sel, attrs)) {
            if (TARGETS_ROOT.test(sel) && !EVALUABLE.test(sel)) throw new Error(`cannot evaluate "${sel}" which sets ${prop}`)
            continue
          }
          const spec = specificity(sel)
          if (!best || imp > best.imp || (imp === best.imp && (spec > best.spec || (spec === best.spec && order >= best.order)))) {
            best = { imp, spec, order, value }
          }
        }
      }
    }
  }
  return best?.value
}

describe('SLM primary pair resolves through the cascade (#21567 review)', () => {
  it('data-app=slm + high-contrast: the high-contrast yellow pair wins over every slm scheme', () => {
    const attrs = { 'data-app': 'slm', 'data-theme': 'high-contrast' }
    expect(cascade('--primary', attrs)).toBe('#facc15')
    expect(cascade('--on-primary', attrs)).toBe('#000000')
  })

  it('data-app=slm with no theme attribute takes the light scheme pair, not the base sky', () => {
    const attrs = { 'data-app': 'slm' }
    const light = block(SCHEME, SCHEMES[0][1])
    expect(cascade('--primary', attrs)).toBe(light['--primary'])
    expect(cascade('--on-primary', attrs)).toBe(light['--on-primary'])
  })

  it('no scheme at all: --primary is the sky 500 and the ink is black', () => {
    expect(cascade('--primary', {})).toBe('var(--color-primary-500)')
    expect(cascade('--on-primary', {})).toBe('var(--color-black)')
  })

  it('the matcher evaluates an html-prefixed root selector instead of discarding it', () => {
    expect(matches(":root[data-app='slm'][data-theme='high-contrast']", { 'data-app': 'slm', 'data-theme': 'high-contrast' })).toBe(true)
    expect(matches("html:root[data-app='slm'][data-theme='high-contrast']", { 'data-app': 'slm', 'data-theme': 'high-contrast' })).toBe(true)
    expect(specificity("html:root[data-app='slm'][data-theme='high-contrast']")).toBeGreaterThan(specificity(":root[data-app='slm'][data-theme='high-contrast']"))
  })

  it('the matcher ignores selectors a bare :root cannot satisfy', () => {
    expect(matches(':root[data-theme=\'high-contrast\'] .card', { 'data-theme': 'high-contrast' })).toBe(false)
    expect(matches(":root[data-app='slm']:not([data-theme])", { 'data-app': 'slm', 'data-theme': 'dark' })).toBe(false)
  })
})
