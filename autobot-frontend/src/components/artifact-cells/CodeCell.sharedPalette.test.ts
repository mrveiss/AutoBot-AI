// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * Both CodeCells read ONE syntax palette (#14853), and it comes from the active
 * theme (#18497): `--codecell-syntax-*` in design-tokens.css alias the theme's
 * `--code-*` palette and hold no literal colour, and each of the four themes
 * defines that palette -- High contrast at WCAG AA, Monochrome with no hue.
 */
import { describe, it, expect } from 'vitest'
import artifact from './CodeCell.vue?raw'
import canvas from '../canvas/CodeCell.vue?raw'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

// Read from disk: vitest's css handling does not give `?raw` the real text.
const css = (rel: string) => readFileSync(resolve(__dirname, '../../assets/css', rel), 'utf-8')
const tokens = css('design-tokens.css')
const styleOf = (src: string) => src.slice(src.indexOf('<style')).replace(/\/\*[\s\S]*?\*\//g, '')
const used = (src: string) => new Set(styleOf(src).match(/--codecell-syntax-[a-z-]+/g) ?? [])
const definitions = [...tokens.matchAll(/^\s*(--codecell-syntax-[a-z-]+):\s*([^;]+);/gm)]
const defined = new Set(definitions.map((m) => m[1]))

/** The categories both cells colour, as `--code-*` names each theme must set. */
const PALETTE = ['bg', 'keyword', 'string', 'number', 'comment', 'function', 'tag', 'attribute']

/** `--code-*` values declared in one theme file, by name. */
function codePalette(file: string): Record<string, string> {
  const text = css(`themes/${file}`).replace(/\/\*[\s\S]*?\*\//g, '')
  return Object.fromEntries([...text.matchAll(/--code-([a-z-]+):\s*(#[0-9a-fA-F]{6})\s*;/g)].map((m) => [m[1], m[2]]))
}

function luminance(hex: string): number {
  const [r, g, b] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255)
  const lin = (c: number) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4)
  return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)
}
const contrast = (a: string, b: string) => {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x)
  return (hi + 0.05) / (lo + 0.05)
}

describe.each([
  ['artifact-cells/CodeCell.vue', artifact],
  ['canvas/CodeCell.vue', canvas],
])('%s syntax palette', (_name, src) => {
  it('uses at least one shared syntax token', () => {
    expect(used(src).size).toBeGreaterThan(0)
  })
  it('references only tokens design-tokens.css defines', () => {
    for (const t of used(src)) expect(defined.has(t), t).toBe(true)
  })
  it('carries no literal hex in its style block', () => {
    expect(styleOf(src)).not.toMatch(/#[0-9a-fA-F]{3,8}\b/)
  })
  it('does not pick a palette by the OS colour scheme (#18497)', () => {
    expect(styleOf(src)).not.toMatch(/prefers-color-scheme/)
    expect(src).not.toMatch(/matchMedia\(['"]\(prefers-color-scheme/)
  })
})

describe('--codecell-syntax-* come from the theme (#18497)', () => {
  it('defines the shared tokens', () => {
    expect(definitions.length).toBeGreaterThanOrEqual(7)
  })
  it.each(definitions.map((m) => [m[1], m[2]]))('%s holds no literal colour', (_name, value) => {
    expect(value).not.toMatch(/#[0-9a-fA-F]{3,8}\b|rgba?\(|hsla?\(|oklch\(/)
    expect(value).toMatch(/^var\(--code-/)
  })
  it('a literal colour would be caught (contrast fixture)', () => {
    expect('#88bbff').toMatch(/#[0-9a-fA-F]{3,8}\b/)
  })
})

describe.each(['light.css', 'dark.css', 'contrast.css', 'mono.css'])('%s syntax palette', (file) => {
  it('defines every category the cells colour', () => {
    const palette = codePalette(file)
    for (const key of PALETTE) expect(palette[key], `--code-${key}`).toBeDefined()
  })
})

describe('accessible palettes (#18497)', () => {
  it('High contrast meets WCAG AA (4.5:1) for every category against its code background', () => {
    const p = codePalette('contrast.css')
    for (const key of PALETTE.filter((k) => k !== 'bg')) {
      expect(contrast(p[key], p.bg), `--code-${key}`).toBeGreaterThanOrEqual(4.5)
    }
  })
  it("Monochrome carries no hue: every colour is one of the theme's own neutral inks and surfaces", () => {
    const text = css('themes/mono.css').replace(/\/\*[\s\S]*?\*\//g, '')
    const own = (name: string) => text.match(new RegExp(`--${name}:\\s*(#[0-9a-fA-F]{6})`))?.[1]
    const inks = new Set(['text', 'text2', 'muted', 'surface', 'surface2', 'bg'].map(own).filter(Boolean))
    expect(inks.size).toBe(6)
    for (const [key, hex] of Object.entries(codePalette('mono.css'))) {
      expect(inks.has(hex), `--code-${key} ${hex}`).toBe(true)
    }
  })
})
