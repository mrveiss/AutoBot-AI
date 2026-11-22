// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
//
// #21961: the active-link underline reads --nav-on-bw, so High contrast (and
// contrast-dark) draw 4px and the other themes 2px, instead of a fixed 2px.
import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, it, expect } from 'vitest'

const here = dirname(fileURLToPath(import.meta.url))
const read = (rel: string) => readFileSync(resolve(here, rel), 'utf-8')
const LINKS = read('../TopNavLinks.vue')

describe('TopNavLinks underline width (#21961)', () => {
  it('takes the underline width from --nav-on-bw, not a fixed utility', () => {
    expect(LINKS).toContain('border-b-(length:--nav-on-bw)')
    expect(LINKS).not.toMatch(/\bborder-b-2\b/)
  })

  it.each([
    ['../../../assets/css/design-tokens.css', '2px'],
    ['../../../assets/css/themes/contrast.css', '4px'],
    ['../../../assets/css/themes/contrast-dark.css', '4px'],
  ])('%s declares --nav-on-bw: %s', (file, width) => {
    expect(read(file)).toMatch(new RegExp(`--nav-on-bw:\\s*${width}`))
  })
})
