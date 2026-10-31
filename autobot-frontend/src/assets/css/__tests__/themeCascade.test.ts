// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * themeCascade.test.ts - the cascade rules #18161 and #17564 rest on.
 *
 * Reads the stylesheets as text: the property being pinned is which selector
 * declares which token, which a CSS parser in jsdom cannot report (it does not
 * compute custom-property inheritance across files).
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, it, expect } from 'vitest'

const assets = resolve(__dirname, '../../..')
const read = (rel: string): string =>
  readFileSync(resolve(assets, rel), 'utf-8').replace(/\/\*[\s\S]*?\*\//g, '')

/** selector prelude -> declared custom-property names, for top-level rules. */
function rules(css: string): Map<string, Set<string>> {
  const out = new Map<string, Set<string>>()
  for (const m of css.matchAll(/([^{}]+)\{([^{}]*)\}/g)) {
    const selector = m[1].replace(/\s+/g, ' ').trim()
    const names = [...m[2].matchAll(/(--[\w-]+)\s*:/g)].map((d) => d[1])
    out.set(selector, new Set([...(out.get(selector) ?? []), ...names]))
  }
  return out
}

describe('density scope (#18161, #17564)', () => {
  const prefs = rules(read('assets/css/themes/preferences.css'))
  const scopes = ['compact', 'spacious'].map((name) => {
    const key = `[data-layout-density="${name}"]`
    return { name, key, names: prefs.get(key) }
  })

  it.each(scopes)('$name is entered by the existing attribute alone', ({ key, names }) => {
    expect(names, `no rule for ${key}`).toBeDefined()
  })

  it('adds no density class names: the attribute is the one entry point', () => {
    expect([...prefs.keys()].some((sel) => /\.density-/.test(sel))).toBe(false)
  })

  it('every scope sets the same tokens, so switching it moves all of them', () => {
    const [first, ...rest] = scopes.map((s) => [...(s.names ?? [])].sort())
    for (const other of rest) expect(other).toEqual(first)
  })

  it('every scope sets the four #17564 tokens and the spacing scale', () => {
    const required = [
      '--table-row-height',
      '--table-cell-py',
      '--card-padding',
      '--spacing-unit',
      ...['xs', 'sm', 'md', 'lg', 'xl', '2xl'].map((s) => `--spacing-${s}`),
    ]
    for (const { names } of scopes) for (const name of required) expect(names).toContain(name)
  })

  it('design-tokens.css declares the four tokens once, as the comfortable base', () => {
    const base = read('assets/css/design-tokens.css')
    for (const name of ['--table-row-height', '--table-cell-py', '--card-padding', '--spacing-unit']) {
      expect([...base.matchAll(new RegExp(`^\\s*${name}\\s*:`, 'gm'))].length).toBe(1)
    }
  })
})

describe('ember palette scope (#18161)', () => {
  it('the base --red-500 and --orange-500 are the default palette', () => {
    const base = read('assets/css/design-tokens.css')
    expect(base).toMatch(/--red-500:\s*#ef4444/i)
    expect(base).toMatch(/--orange-500:\s*#ff7849/i)
  })

  it('ember.css declares them only behind the ember selector', () => {
    const ember = rules(read('assets/css/themes/ember.css'))
    for (const [selector, names] of ember) {
      const scoped = selector.includes('data-theme-variant="ember"')
      if (names.has('--red-500') || names.has('--orange-500')) expect(scoped, selector).toBe(true)
    }
    const hits = [...ember].filter(([, n]) => n.has('--red-500') && n.has('--orange-500'))
    expect(hits.length).toBe(1)
  })
})

describe('the theme accent (#18223)', () => {
  const map = rules(read('assets/css/themes/refined-map.css'))
  const key = ':root[data-theme="light"]:not([data-accent]), :root[data-theme="dark"]:not([data-accent])'

  it('light and dark take the Refined ink as the primary when no accent is chosen', () => {
    const names = map.get(key)
    expect(names, 'no rule for the theme accent').toBeDefined()
    expect(names).toContain('--color-primary')
    // The ink is pale in dark, so text on it must follow the theme, not stay white.
    expect(names).toContain('--text-on-primary')
  })

  it('the rule only applies while no accent preset is set', () => {
    expect(key).toContain(':not([data-accent])')
  })
})

describe('links keep a cue that is not colour (WCAG 1.4.1, #18223)', () => {
  it('the Refined link colour equals the text colour, so base.css underlines body-text links', () => {
    const tokens = read('assets/css/design-tokens.css')
    const colour = (name: string) => new RegExp(`${name}:\\s*([^;]+);`).exec(tokens)?.[1]
    // The reason the underline is needed: if this ever differs, revisit the rule.
    expect(colour('--link')).toBe(colour('--text'))
    const base = read('assets/base.css')
    const rule = /a:not\(\[class\]\),[^{]*\{([^}]*)\}/.exec(base)?.[1] ?? ''
    expect(rule).toMatch(/text-decoration:\s*underline/)
  })

  it('hover uses the handoff link-hover colour', () => {
    expect(read('assets/base.css')).toMatch(/a:not\(\[class\]\):hover[^{]*\{[^}]*--text-link-hover/)
  })
})

describe('ember does not repaint contrast or mono (#18223)', () => {
  // The selector list of the ember rule that sets the surface, text and border tokens
  // for the light/no-theme case. Evaluated against a real <html>, not pattern-matched.
  const ember = rules(read('assets/css/themes/ember.css'))
  const surfaceSelector = [...ember].find(([, names]) => names.has('--bg-primary') && names.has('--text-primary'))?.[0] ?? ''

  const matches = (theme: string | null, variant = 'ember'): boolean => {
    const root = document.documentElement
    root.setAttribute('data-theme-variant', variant)
    if (theme) root.setAttribute('data-theme', theme)
    else root.removeAttribute('data-theme')
    const hit = root.matches(surfaceSelector)
    root.removeAttribute('data-theme')
    root.removeAttribute('data-theme-variant')
    return hit
  }

  it('found the ember surface rule (control: an empty selector would match nothing)', () => {
    expect(surfaceSelector).toContain('data-theme-variant="ember"')
  })

  it.each(['contrast', 'mono'])('does not match under %s', (theme) => {
    expect(matches(theme)).toBe(false)
  })

  it.each([null, 'light'])('still matches ember on %s', (theme) => {
    expect(matches(theme)).toBe(true)
  })

  it('does not match without the ember variant', () => {
    expect(matches('light', 'default')).toBe(false)
  })
})
