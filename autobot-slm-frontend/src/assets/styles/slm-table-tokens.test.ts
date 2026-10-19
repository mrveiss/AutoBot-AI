// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
//
// The kit adapter maps every --aui-table-* token to a --tbl-* token (#14778). The SLM
// must define each of those in every theme, high-contrast included, or the mapped
// value is invalid and the table loses its sizes, borders and type.
import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, it, expect } from 'vitest'

const here = dirname(fileURLToPath(import.meta.url))
const read = (rel: string) => readFileSync(resolve(here, rel), 'utf-8')
const ADAPTER = read('../../../../libs/autobot-ui/src/tokens/adapter.css')
const SCHEME = read('./slm-scheme.css')

const ALL_THEMES = ":root[data-app='slm']"
const HIGH_CONTRAST = ":root[data-app='slm'][data-theme='high-contrast']"
const OTHER_THEMES = ":root[data-app='slm']:not([data-theme='high-contrast'])"

const consumed = [...new Set([...ADAPTER.matchAll(/var\((--tbl-[a-z-]+)\)/g)].map((m) => m[1]))]

/** --tbl-* names declared in the top-level blocks whose selector is exactly *selector*. */
function declaredUnder(selector: string): Set<string> {
  const names = new Set<string>()
  for (const [, sel, body] of SCHEME.matchAll(/([^{}]+)\{([^{}]*)\}/g)) {
    if (sel.replace(/\/\*[\s\S]*?\*\//g, '').trim() !== selector) continue
    for (const [, name] of body.matchAll(/(--tbl-[a-z-]+)\s*:/g)) names.add(name)
  }
  return names
}

const missingIn = (selectors: string[]) => {
  const defined = new Set(selectors.flatMap((s) => [...declaredUnder(s)]))
  return consumed.filter((name) => !defined.has(name))
}

describe('SLM table tokens', () => {
  it('the adapter reads table tokens at all', () => {
    // fails if the scan reads nothing, which would make the checks below pass vacuously
    expect(consumed.length).toBeGreaterThan(10)
  })

  it('defines every adapter table token under high-contrast', () => {
    // fails if a --tbl-* token is defined only in the non-high-contrast block
    expect(missingIn([ALL_THEMES, HIGH_CONTRAST])).toEqual([])
  })

  it('defines every adapter table token in the other themes', () => {
    expect(missingIn([ALL_THEMES, OTHER_THEMES])).toEqual([])
  })

  it('does not count the non-high-contrast block toward high-contrast', () => {
    // contrast case: the colours live in that block, so it must be told apart
    expect(declaredUnder(OTHER_THEMES).has('--tbl-head-bg')).toBe(true)
    expect(missingIn([ALL_THEMES])).toContain('--tbl-head-bg')
  })
})
