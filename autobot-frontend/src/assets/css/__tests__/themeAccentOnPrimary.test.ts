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
})
