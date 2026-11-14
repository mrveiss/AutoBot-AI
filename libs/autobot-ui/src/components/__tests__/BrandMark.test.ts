// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
//
// BrandMark behavioral tests (#18240): decorative vs labelled, and size.

import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import BrandMark from '../BrandMark.vue'

describe('BrandMark', () => {
  it('is decorative (aria-hidden, no role) without a label', () => {
    const el = mount(BrandMark).element
    expect(el.getAttribute('aria-hidden')).toBe('true')
    expect(el.getAttribute('role')).toBeNull()
    expect(el.getAttribute('aria-label')).toBeNull()
  })

  it('is a labelled img when a label is passed', () => {
    const el = mount(BrandMark, { props: { label: 'AutoBot home' } }).element
    expect(el.getAttribute('role')).toBe('img')
    expect(el.getAttribute('aria-label')).toBe('AutoBot home')
    expect(el.getAttribute('aria-hidden')).toBeNull()
  })

  it('sizes the tile from the size prop', () => {
    const el = mount(BrandMark, { props: { size: 64 } }).element as HTMLElement
    expect(el.style.width).toBe('64px')
    expect(el.style.height).toBe('64px')
  })

  it('draws the robot head: body, two eyes, antenna and bulb', () => {
    const w = mount(BrandMark)
    expect(w.findAll('rect')).toHaveLength(1)
    expect(w.findAll('circle')).toHaveLength(3)
    expect(w.findAll('path')).toHaveLength(1)
  })
})
