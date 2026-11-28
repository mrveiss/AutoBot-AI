// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * The Minimal-mode CSS contract (#18240): `.adv` chrome disappears under
 * html[data-ui="minimal"], `.only-min` appears only there, and neither rule
 * needs !important (the selector specificity does the work).
 */
import { describe, it, expect, beforeEach } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const css = readFileSync(resolve(__dirname, '../components.css'), 'utf-8')
// Comments stripped: the block's own header comment says !important in prose.
const stripped = css.replace(/\/\*[\s\S]*?\*\//g, '')
const uiModeBlock = stripped.slice(stripped.indexOf('html[data-ui="minimal"] .adv'))

function probe(cls: string, mode: 'minimal' | 'full'): string {
  document.documentElement.setAttribute('data-ui', mode)
  const el = document.createElement('div')
  el.className = cls
  document.body.appendChild(el)
  return getComputedStyle(el).display
}

beforeEach(() => {
  document.head.innerHTML = ''
  document.body.innerHTML = ''
  const style = document.createElement('style')
  style.textContent = uiModeBlock
  document.head.appendChild(style)
})

describe('ui-mode CSS', () => {
  it('declares the rules without !important', () => {
    expect(uiModeBlock).toContain('html[data-ui="minimal"] .adv')
    expect(uiModeBlock).toContain('html[data-ui="minimal"] .only-min')
    expect(uiModeBlock).not.toContain('!important')
  })

  it('hides .adv in minimal and shows it in full', () => {
    expect(probe('adv', 'minimal')).toBe('none')
    expect(probe('adv', 'full')).toBe('block')
  })

  it('shows .only-min in minimal only', () => {
    expect(probe('only-min', 'minimal')).toBe('flex')
    expect(probe('only-min', 'full')).toBe('none')
  })

  it('beats a bare display utility on the same element (no !important needed)', () => {
    const style = document.createElement('style')
    style.textContent = '.flex { display: flex; }'
    document.head.appendChild(style)
    expect(probe('flex adv', 'minimal')).toBe('none')
    expect(probe('flex adv', 'full')).toBe('flex')
  })
})
