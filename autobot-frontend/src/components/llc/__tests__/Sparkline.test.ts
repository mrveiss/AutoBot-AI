// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// GH#10232: Sparkline renders an SVG polyline for >=2 points, nothing otherwise.

import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'

import Sparkline from '../Sparkline.vue'

describe('Sparkline (GH#10232)', () => {
  it('renders nothing for fewer than two points', () => {
    expect(mount(Sparkline, { props: { points: [] } }).find('svg').exists()).toBe(false)
    expect(mount(Sparkline, { props: { points: [5] } }).find('svg').exists()).toBe(false)
  })

  it('renders a polyline with one coordinate per point', () => {
    const wrapper = mount(Sparkline, { props: { points: [1, 3, 2, 4] } })
    const poly = wrapper.find('polyline')
    expect(poly.exists()).toBe(true)
    expect(poly.attributes('points')!.trim().split(/\s+/)).toHaveLength(4)
  })

  it('keeps a flat series finite (no divide-by-zero)', () => {
    const poly = mount(Sparkline, { props: { points: [2, 2, 2] } }).find('polyline')
    expect(poly.attributes('points')).not.toMatch(/NaN|Infinity/)
  })
})
