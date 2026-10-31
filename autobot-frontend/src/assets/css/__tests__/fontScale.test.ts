// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * fontScale.test.ts - the font-size preference drives the one --text-* scale (#20390).
 *
 * jsdom does not compute custom properties across files, so the cascade for
 * <html> is replayed here from the stylesheet text, in index.css import order
 * (design-tokens, ember, preferences). Every rule involved has the same
 * specificity, so a later declaration wins.
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, it, expect } from 'vitest'

const css = resolve(__dirname, '..')
const read = (rel: string): string =>
  readFileSync(resolve(css, rel), 'utf-8').replace(/\/\*[\s\S]*?\*\//g, '')

type Decls = Record<string, string>

/** Declarations of every top-level rule whose selector list contains `selector`. */
function declsFor(source: string, selector: string): Decls {
  const out: Decls = {}
  for (const m of source.matchAll(/([^{}]+)\{([^{}]*)\}/g)) {
    const selectors = m[1].split(',').map((s) => s.replace(/\s+/g, ' ').trim())
    if (!selectors.includes(selector)) continue
    for (const d of m[2].matchAll(/(--[\w-]+)\s*:\s*([^;]+);/g)) out[d[1]] = d[2].trim()
  }
  return out
}

interface Html {
  themeVariant?: 'ember'
  fontSize?: 'small' | 'medium' | 'large'
}

/** The custom properties on <html> for a theme variant and a font-size preference. */
function cascade({ themeVariant, fontSize = 'medium' }: Html): Decls {
  const tokens = read('design-tokens.css')
  const ember = read('themes/ember.css')
  const prefs = read('themes/preferences.css')
  return {
    ...declsFor(tokens, ':root'),
    ...(themeVariant ? declsFor(ember, `[data-theme-variant="${themeVariant}"]`) : {}),
    ...declsFor(prefs, `[data-font-size="${fontSize}"]`),
  }
}

/** A --text-* step in rem, with `calc(<n>rem * var(--font-scale))` resolved. */
function remOf(step: string, props: Decls): number {
  const value = props[`--text-${step}`]
  const m = /^calc\(\s*([\d.]+)rem\s*\*\s*var\(--font-scale\)\s*\)$/.exec(value ?? '')
  expect(m, `--text-${step} must be calc(<n>rem * var(--font-scale)), got ${value}`).not.toBeNull()
  return Number(m![1]) * Number(props['--font-scale'])
}

const STEPS = ['xs', 'sm', 'base', 'lg', 'xl', '2xl', '3xl', '4xl', '5xl', '6xl']
const EMBER_OVERRIDES: Record<string, number> = { xl: 1.375, '2xl': 1.75 }
const BASE_REM: Record<string, number> = {
  xs: 0.75, sm: 0.875, base: 1, lg: 1.125, xl: 1.25, '2xl': 1.5, '3xl': 1.875, '4xl': 2.25, '5xl': 3, '6xl': 3.75,
}

describe('one font-size scale driven by the preference (#20390)', () => {
  it('medium renders every step exactly as before, with and without ember', () => {
    for (const step of STEPS) {
      expect(remOf(step, cascade({}))).toBe(BASE_REM[step])
      expect(remOf(step, cascade({ themeVariant: 'ember' }))).toBe(EMBER_OVERRIDES[step] ?? BASE_REM[step])
    }
  })

  it.each([
    ['small', 0.9375],
    ['large', 1.0625],
  ] as const)('%s scales every step by %s', (fontSize, factor) => {
    const props = cascade({ fontSize })
    expect(Number(props['--font-scale'])).toBe(factor)
    for (const step of STEPS) expect(remOf(step, props)).toBeCloseTo(BASE_REM[step] * factor, 10)
  })

  it.each(['small', 'large'] as const)('%s with ember scales ember\'s own steps, not the defaults', (fontSize) => {
    const factor = fontSize === 'small' ? 0.9375 : 1.0625
    const props = cascade({ themeVariant: 'ember', fontSize })
    for (const step of STEPS) {
      expect(remOf(step, props)).toBeCloseTo((EMBER_OVERRIDES[step] ?? BASE_REM[step]) * factor, 10)
    }
  })

  it('every theme that redefines a --text-* step multiplies it by --font-scale', () => {
    const ember = declsFor(read('themes/ember.css'), '[data-theme-variant="ember"]')
    const steps = Object.keys(ember).filter((n) => n.startsWith('--text-') && /--text-(xs|sm|base|lg|[2-6]?xl)$/.test(n))
    expect(steps.length).toBeGreaterThan(0)
    for (const name of steps) expect(ember[name], name).toContain('var(--font-scale)')
  })

  it('the removed --font-size-* steps are defined nowhere in the stylesheets', () => {
    for (const rel of ['design-tokens.css', 'themes/ember.css', 'themes/preferences.css']) {
      expect(read(rel), rel).not.toMatch(/--font-size-(xs|sm|base|lg|xl|2xl|3xl)\b/)
    }
  })
})
