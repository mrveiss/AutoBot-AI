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

const luminance = (hex: string) => {
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

  it('defines an ink for the base state, where --primary is the sky 500', () => {
    const sky = block(MAIN, ':root')['--color-primary-500'] ?? '#0ea5e9'
    expect(block(SCHEME, ':root')['--on-primary']).toBe('var(--color-black)')
    expect(contrast(sky, '#000000')).toBeGreaterThanOrEqual(4.5)
  })
})
