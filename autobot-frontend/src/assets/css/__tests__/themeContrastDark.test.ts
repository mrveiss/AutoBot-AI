// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * themeContrastDark.test.ts - the dark high-contrast theme (#18253).
 *
 * The High Contrast Dark preset used to set a second mechanism, the
 * `data-high-contrast` attribute. It now selects `data-theme="contrast-dark"`,
 * and this file pins (1) the theme's text and control pairs at WCAG AAA / AA
 * as computed from the stylesheet, (2) the theme's registration in the cascade
 * and (3) that the legacy attribute has no caller left.
 */
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { resolve, join } from 'node:path'
import { describe, it, expect } from 'vitest'
import { THEME_PRESETS } from '@/composables/themePresets'

const srcRoot = resolve(__dirname, '../../..')
const read = (rel: string): string =>
  readFileSync(resolve(srcRoot, rel), 'utf-8').replace(/\/\*[\s\S]*?\*\//g, '')

/** `--name: #RRGGBB` declarations of one theme file, by name. */
function palette(rel: string): Record<string, string> {
  return Object.fromEntries(
    [...read(rel).matchAll(/(--[\w-]+):\s*(#[0-9a-fA-F]{6})\s*;/g)].map((m) => [m[1], m[2].toUpperCase()]),
  )
}

function luminance(hex: string): number {
  const [r, g, b] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255)
  const lin = (c: number) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4)
  return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)
}
const ratio = (a: string, b: string): number => {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x)
  return (hi + 0.05) / (lo + 0.05)
}

describe('contrast-dark pairs (#18253)', () => {
  const p = palette('assets/css/themes/contrast-dark.css')

  it('control: the ratio helper gives 21:1 for black on white and 1:1 for equal colours', () => {
    expect(ratio('#000000', '#FFFFFF')).toBeCloseTo(21, 5)
    expect(ratio('#777777', '#777777')).toBeCloseTo(1, 5)
  })

  it.each([
    ['--text', '--bg', 7],
    ['--text', '--surface', 7],
    ['--text2', '--surface', 7],
    ['--muted', '--bg', 7],
    ['--link', '--bg', 7],
    ['--link-h', '--bg', 7],
    ['--alert-text', '--bg', 7],
    ['--on-primary', '--primary', 7],
    ['--brand-fg', '--brand-bg', 7],
    ['--bad-fg', '--bad-bg', 7],
    ['--ok-fg', '--ok-bg', 7],
    ['--info-fg', '--info-bg', 7],
    ['--code-text', '--code-bg', 7],
    ['--code-keyword', '--code-bg', 7],
    ['--code-string', '--code-bg', 7],
    ['--code-number', '--code-bg', 7],
    ['--code-comment', '--code-bg', 7],
    // Non-text parts need 3:1 (WCAG 1.4.11): borders and the focus ring against the page.
    ['--border', '--bg', 3],
    ['--focus', '--bg', 3],
    ['--dot-bad', '--bg', 3],
  ])('%s on %s is at least %s:1', (fg, bg, min) => {
    expect(p[fg], fg).toBeDefined()
    expect(p[bg], bg).toBeDefined()
    expect(ratio(p[fg], p[bg])).toBeGreaterThanOrEqual(min)
  })

  it('is registered in the cascade: dark tokens, Refined map, import after dark.css', () => {
    expect(read('assets/css/themes/dark.css')).toMatch(/\[data-theme="dark"\],\s*\[data-theme="contrast-dark"\]\s*\{/)
    expect(read('assets/css/themes/refined-map.css')).toContain('[data-theme="contrast-dark"]')
    const index = read('assets/css/index.css')
    expect(index.indexOf('themes/contrast-dark.css')).toBeGreaterThan(index.indexOf('themes/dark.css'))
  })

  it('wires the dark: utility variant to it', () => {
    expect(read('assets/tailwind.css')).toContain('[data-theme="contrast-dark"]')
  })
})

describe('the legacy data-high-contrast mechanism has no caller (#18253)', () => {
  const walk = (dir: string): string[] =>
    readdirSync(dir).flatMap((name) => {
      const full = join(dir, name)
      if (statSync(full).isDirectory()) return name === 'generated' ? [] : walk(full)
      return /\.(ts|vue|js|css)$/.test(name) && !/\.(test|spec|stories)\./.test(name) ? [full] : []
    })
  const files = walk(srcRoot).filter((f) => !f.includes('__tests__'))
  // Built at runtime so this file does not match itself.
  const legacy = new RegExp(['data', 'high', 'contrast'].join('-'))

  it('control: the walk sees the theme files', () => {
    expect(files.some((f) => f.endsWith('contrast-dark.css'))).toBe(true)
  })

  it('no source or stylesheet names the legacy attribute', () => {
    const hits = files.filter((f) => legacy.test(readFileSync(f, 'utf-8')))
    expect(hits).toEqual([])
  })

  it('both high-contrast presets map onto data-theme with no extra flag', () => {
    expect(THEME_PRESETS['high-contrast-dark']).toMatchObject({ theme: 'contrast-dark' })
    expect(THEME_PRESETS['high-contrast-light']).toMatchObject({ theme: 'contrast' })
    for (const name of ['high-contrast-dark', 'high-contrast-light'] as const) {
      expect(Object.keys(THEME_PRESETS[name]).sort()).toEqual(['accentColor', 'descriptionKey', 'nameKey', 'theme'])
    }
  })
})
