// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// GH#12729: nav icons mix Heroicons' 24-grid and 20-grid sets, whose path
// coordinates differ. App.vue rendered every one in a hardcoded viewBox
// "0 0 20 20", so 24-grid glyphs ran past the box and clipped at the edge
// (nav.home reached y=21.29 in a 20-high box).
//
// Note on parsing: SVG arc commands pack their two boolean flags without
// separators — `a8 8 0 100-16` is rx=8 ry=8 rot=0 large-arc=1 sweep=0 x=0 y=-16.
// A regex that reads "100" as a number reports wild coordinates and invents
// bugs that do not exist, so flags are read one character at a time here.

import { describe, expect, it } from 'vitest'
import { navItems } from '../navItems'

const ARGC: Record<string, number> = { M: 2, L: 2, T: 2, H: 1, V: 1, C: 6, S: 4, Q: 4, A: 7, Z: 0 }

function pathPoints(d: string): Array<[number, number]> {
  const out: Array<[number, number]> = []
  let i = 0
  let cmd = ''
  let x = 0
  let y = 0

  const skip = () => {
    while (i < d.length && ' ,\t\n\r'.includes(d[i])) i++
  }
  const num = (): number | null => {
    skip()
    const m = /^-?\d*\.?\d+(?:[eE][-+]?\d+)?/.exec(d.slice(i))
    if (!m) return null
    i += m[0].length
    return parseFloat(m[0])
  }
  const flag = (): number | null => {
    skip()
    if (i < d.length && (d[i] === '0' || d[i] === '1')) return parseInt(d[i++], 10)
    return null
  }

  for (;;) {
    skip()
    if (i >= d.length) break
    if (/[a-zA-Z]/.test(d[i])) {
      cmd = d[i++]
      if (cmd === 'Z' || cmd === 'z') continue
    }
    if (!cmd) { i++; continue }
    const up = cmd.toUpperCase()
    const rel = cmd === cmd.toLowerCase()
    if (!(up in ARGC)) { i++; cmd = ''; continue }

    let nx: number | null
    let ny: number | null
    if (up === 'A') {
      const rx = num(), ry = num(), rot = num()
      const laf = flag(), swf = flag()
      nx = num(); ny = num()
      if ([rx, ry, rot, laf, swf, nx, ny].some((v) => v === null)) break
    } else {
      const args: Array<number | null> = []
      for (let k = 0; k < ARGC[up]; k++) args.push(num())
      if (args.some((v) => v === null)) break
      if (up === 'H') { nx = args[0]; ny = rel ? 0 : y }
      else if (up === 'V') { nx = rel ? 0 : x; ny = args[0] }
      else { nx = args[args.length - 2]; ny = args[args.length - 1] }
    }
    x = rel ? x + (nx as number) : (nx as number)
    y = rel ? y + (ny as number) : (ny as number)
    out.push([x, y])
  }
  return out
}

function boxOf(item: { iconViewBox?: string }): number {
  const vb = item.iconViewBox ?? '0 0 20 20'
  const parts = vb.split(/\s+/).map(Number)
  return Math.max(parts[2], parts[3])
}

describe('nav icon viewBox (GH#12729)', () => {
  it('parses packed arc flags rather than reading them as coordinates', () => {
    // rx=8 ry=8 rot=0 large-arc=1 sweep=0 x=0 y=-16  ->  endpoint (10, 2)
    const pts = pathPoints('M10 18a8 8 0 100-16')
    expect(pts[pts.length - 1]).toEqual([10, 2])
  })

  it('no icon path escapes the viewBox it is rendered in', () => {
    const offenders: string[] = []
    for (const item of navItems) {
      const paths = item.iconPaths ?? (item.icon ? [item.icon] : [])
      const box = boxOf(item)
      for (const d of paths) {
        for (const [px, py] of pathPoints(d)) {
          if (px > box + 0.05 || py > box + 0.05 || px < -0.05 || py < -0.05) {
            offenders.push(`${item.labelKey}: (${px}, ${py}) outside ${box}`)
          }
        }
      }
    }
    expect(offenders).toEqual([])
  })

  it('24-grid paths are tagged so they are not rendered in a 20 box', () => {
    for (const item of navItems) {
      const paths = item.iconPaths ?? (item.icon ? [item.icon] : [])
      const extent = Math.max(
        0,
        ...paths.flatMap((d) => pathPoints(d).flatMap(([px, py]) => [px, py])),
      )
      if (extent > 20.05) {
        expect(item.iconViewBox, `${item.labelKey} is a 24-grid path`).toBe('0 0 24 24')
      }
    }
  })
})
