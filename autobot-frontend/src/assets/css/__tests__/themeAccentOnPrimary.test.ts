// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * themeAccentOnPrimary.test.ts - the label on an accent preset's fill is chosen for that accent (#21566).
 *
 * Reads the stylesheets as text, like themeCascade.test.ts: custom-property inheritance across files is
 * not computed by jsdom. The ratio is WCAG 2.x relative-luminance contrast of the hex fallback fill.
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, it, expect } from 'vitest'

const themes = resolve(__dirname, '../themes')
const read = (file: string): string =>
  readFileSync(resolve(themes, file), 'utf-8').replace(/\/\*[\s\S]*?\*\//g, '')

const channel = (v: number): number => {
  const c = v / 255
  return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4
}
function luminance(hex: string): number {
  const n = parseInt(hex.slice(1), 16)
  return 0.2126 * channel(n >> 16) + 0.7152 * channel((n >> 8) & 255) + 0.0722 * channel(n & 255)
}
function ratio(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x)
  return (hi + 0.05) / (lo + 0.05)
}

/** accent name -> { fill, label } from the hex block, which ends where the OKLCH block starts. */
function accents(): Map<string, { fill: string; label: string | undefined }> {
  const css = read('accents.css')
  const hexPart = css.slice(0, css.indexOf('@supports'))
  const out = new Map<string, { fill: string; label: string | undefined }>()
  for (const m of hexPart.matchAll(/\[data-accent="(\w+)"\]\s*\{([^{}]*)\}/g)) {
    const fill = /--color-primary:\s*(#[0-9a-fA-F]{6})/.exec(m[2])?.[1]
    const label = /--text-on-primary:\s*(#[0-9a-fA-F]{6})/.exec(m[2])?.[1]
    if (fill) out.set(m[1], { fill, label })
  }
  return out
}

/** OKLCH (L in percent) to an sRGB hex, enough to read the fill the OKLCH block paints in current browsers. */
function oklchToHex(lPct: number, chroma: number, hue: number): string {
  const a = chroma * Math.cos((hue * Math.PI) / 180)
  const b = chroma * Math.sin((hue * Math.PI) / 180)
  const L = lPct / 100
  const [l, m, s] = [L + 0.3963377774 * a + 0.2158037573 * b, L - 0.1055613458 * a - 0.0638541728 * b, L - 0.0894841775 * a - 1.291485548 * b].map((v) => v ** 3)
  const lin = [4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s, -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s, -0.0041960863 * l - 0.7034186147 * m + 1.707614701 * s]
  const enc = (v: number): number => {
    const c = Math.min(1, Math.max(0, v))
    return Math.round(255 * (c <= 0.0031308 ? 12.92 * c : 1.055 * c ** (1 / 2.4) - 0.055))
  }
  return '#' + lin.map((v) => enc(v).toString(16).padStart(2, '0')).join('')
}

/** accent name -> the fill the OKLCH block paints. */
function oklchFills(): Map<string, string> {
  const css = read('accents.css')
  const out = new Map<string, string>()
  for (const m of css.slice(css.indexOf('@supports')).matchAll(/\[data-accent="(\w+)"\]\s*\{([^{}]*)\}/g)) {
    const fill = /--color-primary:\s*oklch\(([\d.]+)%\s+([\d.]+)\s+([\d.]+)\)/.exec(m[2])
    if (fill) out.set(m[1], oklchToHex(Number(fill[1]), Number(fill[2]), Number(fill[3])))
  }
  return out
}

const WHITE = '#FFFFFF'
const INK = '#0E1420'

describe('--text-on-primary under an accent preset (#21566)', () => {
  const all = [...accents()]

  it('reads the eight presets', () => {
    expect(all.map(([name]) => name).sort()).toEqual(
      ['blue', 'green', 'indigo', 'orange', 'pink', 'purple', 'red', 'teal'],
    )
  })

  it.each(all)('%s sets a label colour, not the fixed white fallback', (_name, { label }) => {
    expect(label).toBeDefined()
  })

  it.each(all)('%s uses whichever of white and the dark ink contrasts more', (_name, { fill, label }) => {
    const best = ratio(fill, WHITE) >= ratio(fill, INK) ? WHITE : INK
    expect(label?.toUpperCase()).toBe(best)
  })

  it.each(['contrast.css', 'mono.css', 'contrast-dark.css'])(
    '%s keeps its own ink whatever the accent',
    (file) => {
      const css = read(file)
      const block = new RegExp(`\\[data-theme="[\\w-]+"\\]\\[data-accent\\]\\s*\\{([^{}]*)\\}`).exec(css)
      expect(block?.[1]).toMatch(/--text-on-primary:\s*var\(--on-primary\)/)
    },
  )

  it.each(all)('%s: the label reaches WCAG AA (4.5) on the hex fill', (_name, { fill, label }) => {
    expect(ratio(fill, label ?? WHITE)).toBeGreaterThanOrEqual(4.5)
  })

  it('the OKLCH fills (what current browsers paint) give the same label choice and reach AA', () => {
    const fills = oklchFills()
    expect([...fills.keys()].sort()).toEqual(all.map(([name]) => name).sort())
    for (const [name, { label }] of all) {
      const fill = fills.get(name) as string
      const best = ratio(fill, WHITE) >= ratio(fill, INK) ? WHITE : INK
      expect(label?.toUpperCase(), `${name} label on its OKLCH fill`).toBe(best)
      expect(ratio(fill, best), `${name} contrast on its OKLCH fill`).toBeGreaterThanOrEqual(4.5)
    }
  })

  it('the OKLCH block sets no --text-on-primary, so the hex block is the one owner of the label', () => {
    const css = read('accents.css')
    expect(css.slice(css.indexOf('@supports'))).not.toContain('--text-on-primary')
  })
})
