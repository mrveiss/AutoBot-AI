// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
//
// #17564 AC3: the kit card takes its inner padding from --card-padding (via the
// --aui-card-padding contract token), so a layout-density scope resizes it. The
// card paints no fixed --aui-space-* padding of its own.
import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const here = dirname(fileURLToPath(import.meta.url))
const read = (rel: string) => readFileSync(resolve(here, rel), 'utf-8')
const cardSource = read('../BaseCard.vue')
const adapterCss = read('../../tokens/adapter.css')
const contractCss = read('../../tokens/contract.css')

const paddings = [...cardSource.matchAll(/^\s*padding:\s*([^;]+);/gm)].map((m) => m[1].trim())

describe('BaseCard density (#17564)', () => {
  it('body, header and footer padding are all derived from --aui-card-padding', () => {
    const tokened = paddings.filter((p) => p.includes('--aui-card-padding'))
    expect(tokened).toHaveLength(3)
  })

  it('no region keeps a fixed --aui-space-* padding', () => {
    expect(paddings.filter((p) => p.includes('--aui-space-') && p !== '0')).toEqual([])
  })

  it('the adapter maps the contract token onto the app-side --card-padding', () => {
    expect(adapterCss).toMatch(/--aui-card-padding:\s*var\(--card-padding\)/)
  })

  it('the contract keeps a neutral default for apps outside the adapter', () => {
    expect(contractCss).toMatch(/--aui-card-padding:\s*var\(--aui-space-5\)/)
  })
})
