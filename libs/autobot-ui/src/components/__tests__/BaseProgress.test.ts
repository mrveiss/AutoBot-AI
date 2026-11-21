// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
//
// BaseProgress (#21662): the progressbar role and value, clamping, the accessible name, the
// variant class, and tokens only.

import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import progressSource from '../BaseProgress.vue?raw'
import BaseProgress from '../BaseProgress.vue'

const bar = (props: Record<string, unknown>) =>
  mount(BaseProgress, { props: { value: 40, label: 'Upload', ...props } })

describe('BaseProgress', () => {
  it('is a progressbar named by label, with the value and bounds', () => {
    const w = bar({})
    expect(w.attributes('role')).toBe('progressbar')
    expect(w.attributes('aria-label')).toBe('Upload')
    expect(w.attributes('aria-valuenow')).toBe('40')
    expect(w.attributes('aria-valuemin')).toBe('0')
    expect(w.attributes('aria-valuemax')).toBe('100')
    expect(w.get('.aui-progress__fill').attributes('style')).toContain('40%')
  })

  it.each([
    [-5, '0'],
    [140, '100'],
    [Number.NaN, '0'],
  ])('clamps %s to %s', (value, expected) => {
    // fails if the value is passed through unclamped
    expect(bar({ value }).attributes('aria-valuenow')).toBe(expected)
  })

  it.each(['neutral', 'primary', 'success', 'warning', 'error', 'info'])('applies the %s variant class', (variant) => {
    expect(bar({ variant }).classes()).toContain(`aui-progress--${variant}`)
  })

  it('defaults to primary, md', () => {
    expect(bar({}).classes()).toEqual(expect.arrayContaining(['aui-progress--primary', 'aui-progress--md']))
  })

  it('styles through kit tokens only', () => {
    expect(progressSource).not.toMatch(/#[0-9a-fA-F]{3,8}\b|rgba?\(|box-shadow/)
  })
})
